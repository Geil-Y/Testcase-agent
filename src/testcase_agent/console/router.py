from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from .db import get_db
from .pipeline_runner import run_llm_a, run_llm_b
from .advance import advance_run as do_advance
from .evaluate import evaluate_run as do_evaluate
from ..pipeline.import_requirements import ParsedRequirement, parse_requirements, ColumnMapping
from ..config import get_settings
from ..provider.factory import create_provider
from ..pipeline.generate import RequirementInput

console_router = APIRouter()


# ── Requirements ──────────────────────────────────────────────────────────────

@console_router.get("/requirements")
def list_requirements(q: str = "", status: str = "", offset: int = 0, limit: int = 50):
    db = get_db()
    clauses = ["1=1"]
    params: list[Any] = []

    if q:
        clauses.append("(requirement_key LIKE ? OR description LIKE ? OR function_name LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    if status:
        clauses.append("""
            COALESCE(
                (SELECT CASE
                    WHEN r.status IN ('cases_ready','evaluated') THEN 'reviewed'
                    WHEN r.status IN ('extraction_ready','intents_ready') THEN 'pending'
                    ELSE 'new'
                END
                FROM runs r WHERE r.requirement_id = requirements.id
                ORDER BY r.created_at DESC LIMIT 1
                ), 'new') = ?
        """)
        params.append(status)

    count_sql = f"SELECT COUNT(*) FROM requirements WHERE {' AND '.join(clauses)}"
    total = db.execute(count_sql, params).fetchone()[0]

    rows = db.execute(
        f"""SELECT r.*,
            (SELECT COUNT(*) FROM test_cases tc
             JOIN runs ru ON tc.run_id = ru.id
             WHERE ru.requirement_id = r.id) as case_count,
            COALESCE(
                (SELECT CASE
                    WHEN rn.status IN ('cases_ready','evaluated') THEN 'reviewed'
                    WHEN rn.status IN ('extraction_ready','intents_ready') THEN 'pending'
                    ELSE 'new'
                END
                FROM runs rn WHERE rn.requirement_id = r.id
                ORDER BY rn.created_at DESC LIMIT 1
            ), 'new') as status
        FROM requirements r WHERE {' AND '.join(clauses)} ORDER BY r.id DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()

    items = [_row_to_dict(r) for r in rows]
    return {"items": items, "total": total}


@console_router.post("/requirements/import")
def import_requirements(file: UploadFile, sheet_name: str | None = None):
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "Only .xlsx files are supported")

    content = file.file.read()
    import tempfile, os
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    try:
        os.write(fd, content)
        os.close(fd)

        from ..pipeline.import_requirements import list_columns
        headers = list_columns(tmp_path, sheet_name)
        mapping = _auto_detect_mapping(headers)
        parsed = parse_requirements(tmp_path, mapping, sheet_name)
    finally:
        from pathlib import Path
        Path(tmp_path).unlink(missing_ok=True)

    db = get_db()
    inserted = 0
    for req in parsed:
        cur = db.execute(
            """INSERT OR IGNORE INTO requirements
               (requirement_key, description, function_name, requirement_type,
                supplementary_info, source_row)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (req.requirement_key, req.description, req.function_name,
             req.requirement_type, req.supplementary_info, req.source_row),
        )
        if cur.rowcount > 0:
            inserted += 1
    db.commit()

    return {"imported": inserted, "total_rows": len(parsed)}


@console_router.get("/requirements/{req_id:int}")
def get_requirement(req_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM requirements WHERE id = ?", (req_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Requirement not found")

    runs = db.execute(
        "SELECT * FROM runs WHERE requirement_id = ? ORDER BY created_at DESC",
        (req_id,),
    ).fetchall()

    return {
        "requirement": _row_to_dict(row),
        "runs": [_row_to_dict(r) for r in runs],
    }


# ── Runs ──────────────────────────────────────────────────────────────────────

@console_router.post("/runs")
def create_run(body: dict):
    requirement_id = body.get("requirement_id")
    review_required: list[str] = body.get("review_required", [])

    if not requirement_id:
        raise HTTPException(422, "requirement_id is required")

    db = get_db()
    req = db.execute("SELECT * FROM requirements WHERE id = ?", (requirement_id,)).fetchone()
    if not req:
        raise HTTPException(404, "Requirement not found")

    ra = 1 if "a" in review_required else 0
    rb = 1 if "b" in review_required else 0
    rc = 1 if "c" in review_required else 0

    cur = db.execute(
        """INSERT INTO runs (requirement_id, review_llm_a, review_llm_b, review_llm_c)
           VALUES (?, ?, ?, ?)""",
        (requirement_id, ra, rb, rc),
    )
    run_id = cur.lastrowid

    settings = get_settings()
    provider = create_provider(settings)
    req_input = RequirementInput(
        requirement_key=req["requirement_key"],
        description=req["description"],
        function_name=req["function_name"] or "",
        supplementary_info=req["supplementary_info"] or "",
    )

    try:
        run_llm_a(req_input, provider, run_id, db)
    except Exception as e:
        db.execute("UPDATE runs SET status='failed', error=?, updated_at=datetime('now') WHERE id=?",
                   (str(e), run_id))
        db.commit()

    return _build_run_response(run_id, db)


@console_router.get("/runs/{run_id:int}")
def get_run(run_id: int):
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")
    return _build_run_response(run_id, db)


@console_router.post("/runs/{run_id:int}/advance")
def advance_run(run_id: int):
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")

    from .review_state import can_advance as check_advance
    ok, msg = check_advance(db, run_id)
    if not ok:
        raise HTTPException(409, msg)

    settings = get_settings()
    provider = create_provider(settings)

    do_advance(run_id, provider, db)

    return _build_run_response(run_id, db)


# ── Review Endpoints ──────────────────────────────────────────────────────────

@console_router.get("/runs/{run_id:int}/review-state")
def get_review_state(run_id: int):
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")
    from .review_state import get_stage_states
    return get_stage_states(db, run_id)


@console_router.post("/runs/{run_id:int}/accept/{stage:str}")
def accept_stage_endpoint(run_id: int, stage: str):
    if stage not in ("a", "b", "c"):
        raise HTTPException(422, "Invalid stage: must be a, b, or c")

    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")

    from .review_state import accept_stage
    already = False
    if stage == "a":
        already = bool(run["llm_a_accepted"])
    elif stage == "b":
        already = bool(run["llm_b_accepted"])
    elif stage == "c":
        already = bool(run["llm_c_accepted"])

    if already:
        raise HTTPException(409, f"Stage {stage} already accepted")

    accept_stage(db, run_id, stage)
    return _build_run_response(run_id, db)


@console_router.post("/runs/{run_id:int}/unlock/{stage:str}")
def unlock_stage_endpoint(run_id: int, stage: str, cascade: bool = False):
    if stage not in ("a", "b", "c"):
        raise HTTPException(422, "Invalid stage: must be a, b, or c")

    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")

    from .review_state import unlock_stage, check_cascade_impact

    if not cascade and stage != "c":
        impact = check_cascade_impact(db, run_id, stage)
        total = impact["affected_intents"] + impact["affected_cases"]
        if total > 0:
            return {
                "cascade_warning": True,
                "affected_intents": impact["affected_intents"],
                "affected_cases": impact["affected_cases"],
                "message": f"Unlocking stage {stage} will affect {impact['affected_intents']} intents and {impact['affected_cases']} cases downstream. Confirm with cascade=true to proceed.",
            }

    unlock_stage(db, run_id, stage, cascade=cascade)
    return _build_run_response(run_id, db)


@console_router.post("/runs/{run_id:int}/sections/{section:str}/items/{item_id:str}/regenerate")
def regenerate_item_endpoint(run_id: int, section: str, item_id: str, body: dict):
    if section not in _VALID_SECTIONS:
        raise HTTPException(422, f"Invalid section: {section}")

    comment = body.get("comment", "")
    if not comment or not comment.strip():
        raise HTTPException(422, "comment is required for regeneration")

    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")

    settings = get_settings()
    provider = create_provider(settings)

    from .pipeline_runner import regenerate_test_basis
    regenerate_test_basis(db, run_id, item_id, comment.strip(), provider)

    return _build_run_response(run_id, db)


@console_router.post("/runs/{run_id:int}/evaluate")
def evaluate_run(run_id: int):
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")

    result = do_evaluate(run_id, db)
    return result


# ── Case Update ───────────────────────────────────────────────────────────────

@console_router.put("/runs/{run_id:int}/cases/{case_id:int}")
def update_case(run_id: int, case_id: int, body: dict):
    db = get_db()

    case = db.execute(
        "SELECT * FROM test_cases WHERE id = ? AND run_id = ?",
        (case_id, run_id),
    ).fetchone()
    if not case:
        raise HTTPException(404, "Case not found in this run")

    updatable = ("title", "objective", "precondition", "postcondition")
    sets = []
    values: list[Any] = []
    for field in updatable:
        if field in body:
            sets.append(f"{field}=?")
            values.append(body[field])
    if sets:
        values.append(case_id)
        db.execute(f"UPDATE test_cases SET {', '.join(sets)} WHERE id=?", values)

    if "steps" in body and isinstance(body["steps"], list):
        db.execute("DELETE FROM test_case_steps WHERE case_id = ?", (case_id,))
        for step in body["steps"]:
            db.execute(
                """INSERT INTO test_case_steps (case_id, step_order, action, expected)
                   VALUES (?, ?, ?, ?)""",
                (case_id, step.get("step_order", 0), step.get("action", ""), step.get("expected", "")),
            )

    db.commit()
    updated_case = db.execute("SELECT * FROM test_cases WHERE id = ?", (case_id,)).fetchone()
    steps = db.execute(
        "SELECT * FROM test_case_steps WHERE case_id = ? ORDER BY step_order",
        (case_id,),
    ).fetchall()
    result = _row_to_dict(updated_case)
    result["steps"] = [_row_to_dict(s) for s in steps]
    return result


# ── Intents ────────────────────────────────────────────────────────────────────

@console_router.delete("/runs/{run_id:int}/intents/{intent_id:int}")
def delete_intent(run_id: int, intent_id: int):
    db = get_db()
    intent = db.execute(
        "SELECT * FROM case_intents WHERE id = ? AND run_id = ?",
        (intent_id, run_id),
    ).fetchone()
    if not intent:
        raise HTTPException(404, "Intent not found in this run")
    db.execute("DELETE FROM case_intents WHERE id = ?", (intent_id,))
    db.commit()
    from fastapi.responses import Response
    return Response(status_code=204)


@console_router.post("/runs/{run_id:int}/regenerate-intents")
def regenerate_intents(run_id: int):
    db = get_db()
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "Run not found")

    db.execute("DELETE FROM case_intents WHERE run_id = ?", (run_id,))
    db.commit()

    settings = get_settings()
    provider = create_provider(settings)

    try:
        run_llm_b(run_id, provider, db)
    except Exception as e:
        db.execute(
            "UPDATE runs SET status='failed', error=?, updated_at=datetime('now') WHERE id=?",
            (str(e), run_id),
        )
        db.commit()
        raise HTTPException(500, str(e))

    return _build_run_response(run_id, db)


# ── Section Items ─────────────────────────────────────────────────────────────

_VALID_SECTIONS = {"signals", "thresholds", "timing", "states", "observations"}


@console_router.put("/runs/{run_id:int}/sections/{section:str}/items/{item_id:str}")
def update_item(run_id: int, section: str, item_id: str, body: dict):
    if section not in _VALID_SECTIONS:
        raise HTTPException(422, f"Invalid section: {section}")

    db = get_db()
    row = db.execute(
        """SELECT i.id FROM test_basis_items i
           JOIN test_basis_sections s ON i.section_id = s.id
           WHERE s.run_id = ? AND s.section_name = ? AND i.item_id = ?""",
        (run_id, section, item_id),
    ).fetchone()

    if not row:
        raise HTTPException(404, f"Item {item_id} not found in section {section}")

    fields: dict[str, Any] = {}
    for key in ("status", "content", "need"):
        if key in body:
            fields[key] = body[key]

    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [row["id"]]
        db.execute(f"UPDATE test_basis_items SET {sets} WHERE id=?", values)
        db.commit()

    updated = db.execute("SELECT * FROM test_basis_items WHERE id = ?", (row["id"],)).fetchone()
    return _row_to_dict(updated)


@console_router.post("/runs/{run_id:int}/sections/{section:str}/items")
def add_item(run_id: int, section: str, body: dict):
    if section not in _VALID_SECTIONS:
        raise HTTPException(422, f"Invalid section: {section}")

    db = get_db()
    sec = db.execute(
        "SELECT id FROM test_basis_sections WHERE run_id = ? AND section_name = ?",
        (run_id, section),
    ).fetchone()
    if not sec:
        raise HTTPException(404, f"Section {section} not found in run")

    item_id = body.get("item_id", "")
    status = body.get("status", "known")
    content = body.get("content", "")
    need = body.get("need", "")
    source_text = body.get("source_text", "")

    cur = db.execute(
        """INSERT INTO test_basis_items (section_id, item_id, status, content, need, source_text)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sec["id"], item_id, status, content, need, source_text),
    )
    db.commit()

    new_row = db.execute("SELECT * FROM test_basis_items WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_dict(new_row)


@console_router.delete("/runs/{run_id:int}/sections/{section:str}/items/{item_id:str}")
def delete_item(run_id: int, section: str, item_id: str):
    if section not in _VALID_SECTIONS:
        raise HTTPException(422, f"Invalid section: {section}")

    db = get_db()
    row = db.execute(
        """SELECT i.id FROM test_basis_items i
           JOIN test_basis_sections s ON i.section_id = s.id
           WHERE s.run_id = ? AND s.section_name = ? AND i.item_id = ?""",
        (run_id, section, item_id),
    ).fetchone()

    if not row:
        raise HTTPException(404, f"Item {item_id} not found in section {section}")

    db.execute("DELETE FROM test_basis_items WHERE id = ?", (row["id"],))
    db.commit()
    from fastapi.responses import Response
    return Response(status_code=204)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _auto_detect_mapping(headers: list[str]) -> ColumnMapping:
    mapping = ColumnMapping()
    lower = [h.lower() for h in headers]

    for i, h in enumerate(lower):
        if not mapping.requirement_key_col and ("key" in h or "requirement" in h or h == "id"):
            mapping.requirement_key_col = headers[i]
        elif not mapping.description_col and ("description" in h or "desc" in h or "requirement" in h or "detail" in h):
            mapping.description_col = headers[i]
        elif not mapping.function_name_col and ("function" in h or "func" in h):
            mapping.function_name_col = headers[i]
        elif not mapping.requirement_type_col and ("type" in h or "category" in h):
            mapping.requirement_type_col = headers[i]
        else:
            mapping.supplementary_info_cols.append(headers[i])

    return mapping


def _build_run_response(run_id: int, db: sqlite3.Connection) -> dict:
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    req = db.execute("SELECT * FROM requirements WHERE id = ?", (run["requirement_id"],)).fetchone()

    sections = db.execute(
        "SELECT * FROM test_basis_sections WHERE run_id = ? ORDER BY sort_order",
        (run_id,),
    ).fetchall()

    sections_data = []
    for sec in sections:
        items = db.execute(
            "SELECT * FROM test_basis_items WHERE section_id = ? ORDER BY sort_order",
            (sec["id"],),
        ).fetchall()
        sections_data.append({
            "section_name": sec["section_name"],
            "items": [_row_to_dict(it) for it in items],
        })

    intents = db.execute(
        "SELECT * FROM case_intents WHERE run_id = ? ORDER BY sort_order",
        (run_id,),
    ).fetchall()

    cases = db.execute(
        "SELECT * FROM test_cases WHERE run_id = ? ORDER BY sort_order",
        (run_id,),
    ).fetchall()

    cases_data = []
    for case in cases:
        steps = db.execute(
            "SELECT * FROM test_case_steps WHERE case_id = ? ORDER BY step_order",
            (case["id"],),
        ).fetchall()
        case_dict = _row_to_dict(case)
        case_dict["steps"] = [_row_to_dict(s) for s in steps]

        evals = db.execute(
            "SELECT * FROM evaluation_results WHERE case_id = ?",
            (case["id"],),
        ).fetchall()
        case_dict["evaluation_items"] = [_row_to_dict(e) for e in evals]
        cases_data.append(case_dict)

    evaluation = None
    if run["status"] == "evaluated":
        total = len(cases_data)
        passed = sum(
            1 for c in cases_data
            if not any(e["result"] == "fail" for e in c["evaluation_items"])
        )
        evaluation = {
            "total_cases": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total > 0 else 0.0,
            "cases": [
                {
                    "case_id": c["id"],
                    "title": c["title"],
                    "passed": not any(e["result"] == "fail" for e in c["evaluation_items"]),
                    "failed_items": [e["item_id"] for e in c["evaluation_items"] if e["result"] == "fail"],
                    "warning_items": [e["item_id"] for e in c["evaluation_items"] if e["result"] == "warn"],
                }
                for c in cases_data
            ],
        }

    return {
        "run": _row_to_dict(run),
        "requirement": _row_to_dict(req),
        "sections": sections_data,
        "intents": [_row_to_dict(i) for i in intents],
        "cases": cases_data,
        "evaluation": evaluation,
    }
