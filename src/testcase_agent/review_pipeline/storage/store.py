"""Review Memory storage using SQLite.

Stores validated, human-reviewed clarification and case intent decisions
with derived pattern tags for future retrieval (Issue 12).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from testcase_agent.review_pipeline.artifacts.io import read_json
from testcase_agent.review_pipeline.artifacts.legacy_models import (
    ClarificationReview,
    CaseIntentReview,
    ApprovedCasePlan,
)
from testcase_agent.review_pipeline.tag_rules.pattern_tag_rules import derive_all_tags, reject_unknown_tags

_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "review_memory.db"


def get_db_path() -> str:
    return os.environ.get("REVIEW_MEMORY_DB", str(_DEFAULT_DB_PATH))


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()


# ── Import ─────────────────────────────────────────────────────────────────

def import_memory(run_dir: str, db_path: str | None = None) -> None:
    """Import validated review artifacts from a run directory into Review Memory.

    Only imports validated, human-reviewed artifacts. Pattern tags are derived
    and stored with evidence. Re-import is deterministic and idempotent.
    """
    rdir = Path(run_dir)
    conn = get_connection(db_path)

    try:
        # Import clarification review if present
        clar_path = rdir / "clarification_review.json"
        approved_path = rdir / "approved_case_plan.json"

        if clar_path.exists():
            clar_data = read_json(clar_path)
            review = ClarificationReview(**clar_data)
            _import_clarification(conn, review)

        if approved_path.exists():
            plan = ApprovedCasePlan(**read_json(approved_path))
            _import_approved_plan(conn, plan)

        # Also import intent review for decisions
        intent_path = rdir / "case_intent_review.json"
        if intent_path.exists():
            intent_review = CaseIntentReview(**read_json(intent_path))
            _import_intent_review(conn, intent_review)

        conn.commit()
    finally:
        conn.close()


def _import_clarification(conn: sqlite3.Connection, review: ClarificationReview) -> None:
    session_id = review.review_session_id

    # Upsert session
    conn.execute(
        """INSERT OR REPLACE INTO review_sessions
           (session_id, requirement_key, source_requirement_hash, source_type, source_ref, overall_status, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
        (session_id, review.requirement_key, review.source_requirement_hash, "clarification", "", "reviewed"),
    )

    for dec in review.decisions:
        amb = _find_ambiguity(review, dec.item_id)
        ambiguity_type = amb.ambiguity_type if amb else ""
        severity = amb.severity if amb else "medium"
        drivers = amb.confidence_drivers if amb else {}
        confidence = sum(drivers.values()) / len(drivers) if drivers else 0.0

        conn.execute(
            """INSERT INTO clarification_memory_items
               (session_id, item_id, decision, reason_codes, reason_text,
                clarified_value, severity, ambiguity_type, confidence_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, dec.item_id, dec.decision,
                json.dumps(dec.reason_codes), dec.reason_text,
                dec.clarified_value, severity, ambiguity_type, confidence,
            ),
        )

        # Derive and store pattern tags
        tags = derive_all_tags(
            reason_codes=dec.reason_codes,
            ambiguity_types=[ambiguity_type] if ambiguity_type else None,
            text=dec.reason_text or "",
        )
        tags = reject_unknown_tags(tags)
        for tag in tags:
            conn.execute(
                """INSERT INTO memory_item_tags
                   (item_type, item_ref, memory_item_id, session_id, tag,
                    tag_strength, source, rule_id, evidence_text, confidence)
                   VALUES (?, ?, last_insert_rowid(), ?, ?, ?, ?, ?, ?, ?)""",
                ("clarification", dec.item_id, session_id, tag.tag,
                 tag.tag_strength, tag.source, tag.rule_id, tag.evidence_text, tag.confidence),
            )


def _import_intent_review(conn: sqlite3.Connection, review: CaseIntentReview) -> None:
    session_id = review.review_session_id

    conn.execute(
        """INSERT OR REPLACE INTO review_sessions
           (session_id, requirement_key, source_requirement_hash, test_basis_hash, source_type, source_ref, overall_status, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (session_id, review.requirement_key, review.source_requirement_hash, review.test_basis_hash, "case_intent", "", "reviewed"),
    )

    for dec in review.decisions:
        intent = _find_intent(review, dec.intent_id)
        coverage = intent.coverage_dimension if intent else ""
        confidence = intent.confidence_score if intent else 0.0

        conn.execute(
            """INSERT INTO case_intent_memory_items
               (session_id, intent_id, decision, reason_codes, reason_text,
                coverage_dimension, confidence_score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, dec.intent_id, dec.decision,
                json.dumps(dec.reason_codes), dec.reason_text,
                coverage, confidence,
            ),
        )

        tags = derive_all_tags(
            reason_codes=dec.reason_codes,
            coverage_dimensions=[coverage] if coverage else None,
            text=dec.reason_text or "",
        )
        tags = reject_unknown_tags(tags)
        for tag in tags:
            conn.execute(
                """INSERT INTO memory_item_tags
                   (item_type, item_ref, memory_item_id, session_id, tag,
                    tag_strength, source, rule_id, evidence_text, confidence)
                   VALUES (?, ?, last_insert_rowid(), ?, ?, ?, ?, ?, ?, ?)""",
                ("case_intent", dec.intent_id, session_id, tag.tag,
                 tag.tag_strength, tag.source, tag.rule_id, tag.evidence_text, tag.confidence),
            )


def _import_approved_plan(conn: sqlite3.Connection, plan: ApprovedCasePlan) -> None:
    conn.execute(
        """UPDATE review_sessions SET overall_status = ?, updated_at = datetime('now')
           WHERE session_id = ? AND overall_status = 'reviewed'""",
        ("approved", plan.review_session_id),
    )


# ── Retrieval (Issue 12) ───────────────────────────────────────────────────

def retrieve_by_requirement_hash(source_hash: str, db_path: str | None = None) -> list[dict[str, Any]]:
    """Retrieve prior sessions for the same requirement hash."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM review_sessions WHERE source_requirement_hash = ? ORDER BY created_at DESC",
            (source_hash,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def retrieve_by_test_basis_hash(basis_hash: str, db_path: str | None = None) -> list[dict[str, Any]]:
    """Retrieve prior sessions for the same test basis hash."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM review_sessions WHERE test_basis_hash = ? ORDER BY created_at DESC",
            (basis_hash,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def retrieve_by_tags(tags: list[str], db_path: str | None = None) -> list[dict[str, Any]]:
    """Retrieve items matching any of the given pattern tags, with evidence."""
    conn = get_connection(db_path)
    try:
        if not tags:
            return []
        placeholders = ",".join("?" for _ in tags)
        rows = conn.execute(
            f"""SELECT mit.*, rs.requirement_key, rs.source_requirement_hash
                FROM memory_item_tags mit
                JOIN review_sessions rs ON mit.session_id = rs.session_id
                WHERE mit.tag IN ({placeholders})
                ORDER BY mit.confidence DESC
                LIMIT 50""",
            tags,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def retrieve_by_reason_codes(reason_codes: list[str], db_path: str | None = None) -> list[dict[str, Any]]:
    """Retrieve items matching any of the given reason codes."""
    conn = get_connection(db_path)
    try:
        results: list[dict[str, Any]] = []
        for table in ("clarification_memory_items", "case_intent_memory_items"):
            for rc in reason_codes:
                rows = conn.execute(
                    f"""SELECT *, '{table}' as source_table FROM {table}
                        WHERE reason_codes LIKE ?
                        ORDER BY created_at DESC LIMIT 25""",
                    (f"%{rc}%",),
                ).fetchall()
                results.extend(dict(r) for r in rows)
        return results
    finally:
        conn.close()


def get_decision_statistics(tags: list[str], db_path: str | None = None) -> dict[str, Any]:
    """Return decision statistics for matching tags/reasons."""
    conn = get_connection(db_path)
    try:
        stats: dict[str, Any] = {"total_items": 0, "decisions": {}}
        if not tags:
            return stats

        placeholders = ",".join("?" for _ in tags)
        for table, id_col in [("clarification_memory_items", "item_id"), ("case_intent_memory_items", "intent_id")]:
            rows = conn.execute(
                f"""SELECT ci.decision, COUNT(*) as cnt
                    FROM {table} ci
                    JOIN memory_item_tags mit ON mit.session_id = ci.session_id
                       AND mit.item_ref = ci.{id_col}
                    WHERE mit.tag IN ({placeholders})
                    GROUP BY ci.decision""",
                tags,
            ).fetchall()
            for r in rows:
                stats["total_items"] += r["cnt"]
                stats["decisions"][r["decision"]] = stats["decisions"].get(r["decision"], 0) + r["cnt"]
        return stats
    finally:
        conn.close()


# ── Historical confidence support (Issue 12) ──────────────────────────────

def compute_historical_support(source_hash: str, tags: list[str], db_path: str | None = None) -> dict[str, Any]:
    """Compute historical support data for confidence adjustment.

    Returns hints for reviewer, but never makes decisions automatically.
    """
    same_req = retrieve_by_requirement_hash(source_hash, db_path)
    tag_matches = retrieve_by_tags(tags, db_path)
    decision_stats = get_decision_statistics(tags, db_path)

    total_matches = len(same_req) + len(tag_matches)
    if total_matches == 0:
        return {"historical_pattern_support": 0.5, "historical_decision_support": 0.5,
                "hints": [], "adjustment": 0.0}

    # Same-requirement matches are stronger than tag-only matches
    same_req_weight = min(len(same_req) * 0.15, 0.5)
    tag_weight = min(len(tag_matches) * 0.03, 0.3)
    raw_support = 0.5 + same_req_weight + tag_weight

    from testcase_agent.review_pipeline.confidence.engine import normalize_historical_adjustment
    adjustment = normalize_historical_adjustment(raw_support - 0.5)

    hints: list[str] = []
    if same_req:
        hints.append(f"{len(same_req)} prior review(s) for same requirement")
    if decision_stats.get("total_items"):
        top_decisions = sorted(decision_stats.get("decisions", {}).items(), key=lambda x: -x[1])[:3]
        hints.append(f"Prior decisions: {', '.join(f'{d}({c})' for d, c in top_decisions)}")

    return {
        "historical_pattern_support": raw_support,
        "historical_decision_support": raw_support,
        "hints": hints,
        "adjustment": adjustment,
        "same_requirement_sessions": len(same_req),
        "tag_match_count": len(tag_matches),
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _find_ambiguity(review: ClarificationReview, item_id: str) -> Any:
    for a in review.decomposition.ambiguities:
        if a.item_id == item_id:
            return a
    return None


def _find_intent(review: CaseIntentReview, intent_id: str) -> Any:
    for i in review.plan.intents:
        if i.intent_id == intent_id:
            return i
    return None
