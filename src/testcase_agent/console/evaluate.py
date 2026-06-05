from __future__ import annotations

import sqlite3

from testcase_agent.quality.evaluator import evaluate_generated_cases


def evaluate_run(run_id: int, db: sqlite3.Connection) -> dict:
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    req = db.execute("SELECT * FROM requirements WHERE id = ?", (run["requirement_id"],)).fetchone()

    sections = db.execute(
        "SELECT * FROM test_basis_sections WHERE run_id = ? ORDER BY sort_order", (run_id,)
    ).fetchall()

    signals: list[str] = []
    thresholds: list[str] = []
    timing: list[str] = []
    missing_info_items: list[dict] = []

    for sec in sections:
        items = db.execute(
            "SELECT * FROM test_basis_items WHERE section_id = ? ORDER BY sort_order",
            (sec["id"],),
        ).fetchall()
        known = [it["content"] for it in items if it["status"] == "known" and it["content"]]
        needs = [it for it in items if it["status"] == "needs_review"]

        if sec["section_name"] == "signals":
            signals = known
        elif sec["section_name"] == "thresholds":
            thresholds = known
        elif sec["section_name"] == "timing":
            timing = known

        for n in needs:
            if n["need"]:
                cat_map = {
                    "signals": "signal", "thresholds": "threshold", "timing": "timing",
                    "states": "state", "observations": "observation",
                }
                missing_info_items.append({
                    "category": cat_map.get(sec["section_name"], sec["section_name"]),
                    "description": n["need"],
                })

    intents = db.execute(
        "SELECT * FROM case_intents WHERE run_id = ? ORDER BY sort_order", (run_id,)
    ).fetchall()

    analysis = {
        "signals": signals,
        "thresholds": thresholds,
        "timing": timing,
        "missing_info_items": missing_info_items,
        "case_intents": [{"coverage": i["coverage_dimension"]} for i in intents],
    }

    cases = db.execute(
        "SELECT * FROM test_cases WHERE run_id = ? ORDER BY sort_order", (run_id,)
    ).fetchall()

    if not cases:
        return {"error": "No cases to evaluate", "summary": {"total_cases": 0, "passed": 0, "failed": 0, "pass_rate": 0.0}}

    grouped_cases: list[dict] = []
    for case in cases:
        steps = db.execute(
            "SELECT * FROM test_case_steps WHERE case_id = ? ORDER BY step_order",
            (case["id"],),
        ).fetchall()
        grouped_cases.append({
            "title": case["title"],
            "objective": case["objective"],
            "precondition": case["precondition"],
            "postcondition": case["postcondition"],
            "related_requirement": req["requirement_key"],
            "steps": [{"action": s["action"], "expected": s["expected"]} for s in steps],
            "raw_html": case["raw_html"] or "",
        })

    grouped = [{
        "requirement_key": req["requirement_key"],
        "description": req["description"],
        "analysis": analysis,
        "cases": grouped_cases,
    }]

    result = evaluate_generated_cases(grouped)

    # Store results
    for (req_key, ci), ce in result.case_results.items():
        case_row = cases[ci] if ci < len(cases) else None
        if case_row is None:
            continue

        for item_id in ce.failed_items:
            db.execute(
                "INSERT INTO evaluation_results (case_id, item_id, result) VALUES (?, ?, ?)",
                (case_row["id"], str(item_id), "fail"),
            )
        for item_id in ce.warning_items:
            db.execute(
                "INSERT INTO evaluation_results (case_id, item_id, result) VALUES (?, ?, ?)",
                (case_row["id"], str(item_id), "warn"),
            )

    db.execute(
        "UPDATE runs SET status='evaluated', updated_at=datetime('now') WHERE id=?",
        (run_id,),
    )
    db.commit()

    total = result.total_cases
    passed = result.total_passed
    summary = {
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total > 0 else 0.0,
    }

    cases_data: list[dict] = []
    for ci, case in enumerate(cases):
        failed = []
        warned = []
        passed_items = []
        evals = db.execute(
            "SELECT * FROM evaluation_results WHERE case_id = ?", (case["id"],)
        ).fetchall()
        for e in evals:
            if e["result"] == "fail":
                failed.append(e["item_id"])
            elif e["result"] == "warn":
                warned.append(e["item_id"])
            else:
                passed_items.append(e["item_id"])

        cases_data.append({
            "case_id": case["id"],
            "title": case["title"],
            "passed": not failed,
            "failed_items": failed,
            "warning_items": warned,
        })

    return {"summary": summary, "cases": cases_data}
