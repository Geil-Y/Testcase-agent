from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def accept_stage(db: sqlite3.Connection, run_id: int, stage: str) -> None:
    """Accept all items in the given stage, set accepted_at and llm_X_accepted."""
    now = datetime.now(timezone.utc).isoformat()

    if stage == "a":
        db.execute(
            "UPDATE test_basis_items SET review_status='accepted', accepted_at=? "
            "WHERE id IN (SELECT i.id FROM test_basis_items i "
            "JOIN test_basis_sections s ON i.section_id = s.id WHERE s.run_id = ?)",
            (now, run_id),
        )
        db.execute(
            "UPDATE runs SET llm_a_accepted=1, updated_at=datetime('now') WHERE id=?",
            (run_id,),
        )
    elif stage == "b":
        db.execute(
            "UPDATE case_intents SET review_status='accepted', accepted_at=? "
            "WHERE run_id=? AND review_status != 'stale'",
            (now, run_id),
        )
        db.execute(
            "UPDATE runs SET llm_b_accepted=1, updated_at=datetime('now') WHERE id=?",
            (run_id,),
        )
    elif stage == "c":
        db.execute(
            "UPDATE test_cases SET review_status='accepted', accepted_at=? "
            "WHERE run_id=?",
            (now, run_id),
        )
        db.execute(
            "UPDATE runs SET llm_c_accepted=1, updated_at=datetime('now') WHERE id=?",
            (run_id,),
        )
    else:
        raise ValueError(f"Invalid stage: {stage}")

    record_action(db, run_id, stage, "accept", target_type="stage", target_id=None, comment=None)
    db.commit()


def unlock_stage(db: sqlite3.Connection, run_id: int, stage: str, cascade: bool = False) -> None:
    """Unlock a stage, clearing accepted_at. If cascade, also stale downstream data."""
    if stage == "a":
        db.execute(
            "UPDATE test_basis_items SET review_status='pending', accepted_at=NULL "
            "WHERE id IN (SELECT i.id FROM test_basis_items i "
            "JOIN test_basis_sections s ON i.section_id = s.id WHERE s.run_id = ?)",
            (run_id,),
        )
        db.execute(
            "UPDATE runs SET llm_a_accepted=0, updated_at=datetime('now') WHERE id=?",
            (run_id,),
        )
        if cascade:
            cascade_stale_data(db, run_id, "a")
    elif stage == "b":
        db.execute(
            "UPDATE case_intents SET review_status='pending', accepted_at=NULL "
            "WHERE run_id=?",
            (run_id,),
        )
        db.execute(
            "UPDATE runs SET llm_b_accepted=0, updated_at=datetime('now') WHERE id=?",
            (run_id,),
        )
        if cascade:
            cascade_stale_data(db, run_id, "b")
    elif stage == "c":
        db.execute(
            "UPDATE test_cases SET review_status='pending', accepted_at=NULL "
            "WHERE run_id=?",
            (run_id,),
        )
        db.execute(
            "UPDATE runs SET llm_c_accepted=0, updated_at=datetime('now') WHERE id=?",
            (run_id,),
        )
    else:
        raise ValueError(f"Invalid stage: {stage}")

    record_action(db, run_id, stage, "unlock", target_type="stage", target_id=None, comment=None)
    db.commit()


def check_cascade_impact(db: sqlite3.Connection, run_id: int, stage: str) -> dict:
    """Return the number of downstream items that would be affected by an unlock."""
    result = {"affected_intents": 0, "affected_cases": 0}
    if stage == "a":
        result["affected_intents"] = db.execute(
            "SELECT COUNT(*) FROM case_intents WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        result["affected_cases"] = db.execute(
            "SELECT COUNT(*) FROM test_cases WHERE run_id=?", (run_id,)
        ).fetchone()[0]
    elif stage == "b":
        result["affected_cases"] = db.execute(
            "SELECT COUNT(*) FROM test_cases WHERE run_id=?", (run_id,)
        ).fetchone()[0]
    return result


def can_advance(db: sqlite3.Connection, run_id: int) -> tuple[bool, str]:
    """Check if the current stage can be advanced. Returns (ok, message)."""
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        return False, f"Run {run_id} not found"

    status = run["status"]
    if status == "extraction_ready":
        if run["review_llm_a"] == 1 and run["llm_a_accepted"] == 0:
            return False, "LLM-A stage not yet accepted"
        return True, ""
    elif status == "intents_ready":
        if run["review_llm_b"] == 1 and run["llm_b_accepted"] == 0:
            return False, "LLM-B stage not yet accepted"
        return True, ""
    elif status == "cases_ready":
        if run["review_llm_c"] == 1 and run["llm_c_accepted"] == 0:
            return False, "LLM-C stage not yet accepted"
        return True, ""
    elif status == "evaluated":
        return True, ""
    else:
        return False, f"Cannot advance run in status: {status}"


def can_regenerate_intents(db: sqlite3.Connection, run_id: int) -> bool:
    """Check if LLM-B regenerate count is under the limit (3)."""
    row = db.execute(
        "SELECT MAX(regenerate_count) as max_count FROM case_intents WHERE run_id=?",
        (run_id,),
    ).fetchone()
    max_count = row["max_count"] if row and row["max_count"] is not None else 0
    return max_count < 3


def get_stage_states(db: sqlite3.Connection, run_id: int) -> dict:
    """Return review state for each stage (for frontend button rendering)."""
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    return {
        "a": {
            "review_required": bool(run["review_llm_a"]),
            "accepted": bool(run["llm_a_accepted"]),
            "status": run["status"],
        },
        "b": {
            "review_required": bool(run["review_llm_b"]),
            "accepted": bool(run["llm_b_accepted"]),
            "status": run["status"],
            "can_regenerate": can_regenerate_intents(db, run_id),
        },
        "c": {
            "review_required": bool(run["review_llm_c"]),
            "accepted": bool(run["llm_c_accepted"]),
            "status": run["status"],
        },
    }


def cascade_stale_data(db: sqlite3.Connection, run_id: int, from_stage: str) -> None:
    """Mark downstream data as stale when unlocking an upstream stage."""
    if from_stage == "a":
        db.execute(
            "UPDATE case_intents SET review_status='stale' WHERE run_id=?", (run_id,)
        )
        db.execute(
            "UPDATE test_cases SET review_status='stale' WHERE run_id=?", (run_id,)
        )
        db.execute(
            "UPDATE runs SET llm_b_accepted=0, llm_c_accepted=0, status='extraction_ready', "
            "updated_at=datetime('now') WHERE id=?",
            (run_id,),
        )
    elif from_stage == "b":
        db.execute(
            "UPDATE test_cases SET review_status='stale' WHERE run_id=?", (run_id,)
        )
        db.execute(
            "UPDATE runs SET llm_c_accepted=0, status='intents_ready', "
            "updated_at=datetime('now') WHERE id=?",
            (run_id,),
        )


def record_action(
    db: sqlite3.Connection,
    run_id: int,
    stage: str,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    comment: str | None = None,
) -> None:
    """Insert an audit record into review_actions."""
    db.execute(
        """INSERT INTO review_actions (run_id, stage, action, target_type, target_id, comment)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (run_id, stage, action, target_type, target_id, comment),
    )
