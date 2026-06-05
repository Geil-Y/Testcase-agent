from __future__ import annotations

import sqlite3

from ..parser.json_parser import parse_test_basis_json, parse_case_intents_json, TestBasis
from ..parser.html_parser import parse_generated_case, GeneratedCase
from ..prompts import render_prompt
from ..provider.base import LlmProvider
from ..pipeline.generate import RequirementInput


def run_llm_a(
    requirement: RequirementInput,
    provider: LlmProvider,
    run_id: int,
    db: sqlite3.Connection,
) -> None:
    sys_a, usr_a = render_prompt(
        "analyze_test_basis",
        requirement_key=requirement.requirement_key,
        description=requirement.description,
    )
    raw = provider.complete(sys_a, usr_a)
    tb = parse_test_basis_json(raw)

    section_order = [
        ("signals", tb.allowed_signals),
        ("thresholds", tb.allowed_thresholds),
        ("timing", tb.allowed_timing),
        ("states", tb.allowed_states),
        ("observations", tb.allowed_observations),
    ]

    for sort_order, (section_name, values) in enumerate(section_order):
        cur = db.execute(
            "INSERT INTO test_basis_sections (run_id, section_name, sort_order) VALUES (?, ?, ?)",
            (run_id, section_name, sort_order),
        )
        section_id = cur.lastrowid

        for i, val in enumerate(values):
            db.execute(
                """INSERT INTO test_basis_items
                   (section_id, item_id, status, content, need, source_text, sort_order)
                   VALUES (?, ?, 'known', ?, '', ?, ?)""",
                (section_id, f"{section_name[:4]}-{i+1}", val, requirement.description, i),
            )

        section_mi = [mi for mi in tb.missing_info if mi.category == _section_to_category(section_name)]
        for j, mi in enumerate(section_mi):
            db.execute(
                """INSERT INTO test_basis_items
                   (section_id, item_id, status, content, need, source_text, sort_order)
                   VALUES (?, ?, 'needs_review', '', ?, '', ?)""",
                (section_id, f"{section_name[:4]}-needs-{j+1}", mi.description, len(values) + j),
            )

    db.execute(
        "UPDATE runs SET status='extraction_ready', updated_at=datetime('now') WHERE id=?",
        (run_id,),
    )
    db.commit()


def run_llm_b(run_id: int, provider: LlmProvider, db: sqlite3.Connection) -> None:
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    req = db.execute("SELECT * FROM requirements WHERE id = ?", (run["requirement_id"],)).fetchone()

    sections = db.execute(
        "SELECT * FROM test_basis_sections WHERE run_id = ? ORDER BY sort_order", (run_id,)
    ).fetchall()

    context: dict[str, str] = {}
    missing_parts: list[str] = []
    for sec in sections:
        items = db.execute(
            "SELECT * FROM test_basis_items WHERE section_id = ? ORDER BY sort_order", (sec["id"],)
        ).fetchall()

        known = [it["content"] for it in items if it["status"] == "known" and it["content"]]
        needs = [it for it in items if it["status"] == "needs_review"]

        if sec["section_name"] == "signals":
            context["allowed_signals"] = ", ".join(known)
        elif sec["section_name"] == "thresholds":
            context["allowed_thresholds"] = ", ".join(known)
        elif sec["section_name"] == "timing":
            context["allowed_timing"] = ", ".join(known)
        elif sec["section_name"] == "states":
            context["allowed_states"] = ", ".join(known)
        elif sec["section_name"] == "observations":
            context["allowed_observations"] = ", ".join(known)

        for n in needs:
            cat = _section_to_category(sec["section_name"])
            if n["need"]:
                missing_parts.append(f'{{"category": "{cat}", "description": "{n["need"]}"}}')

    missing_json = "[" + ", ".join(missing_parts) + "]" if missing_parts else "[]"

    sys_b, usr_b = render_prompt(
        "plan_case_intents",
        requirement_key=req["requirement_key"],
        description=req["description"],
        allowed_signals=context.get("allowed_signals", ""),
        allowed_thresholds=context.get("allowed_thresholds", ""),
        allowed_timing=context.get("allowed_timing", ""),
        allowed_states=context.get("allowed_states", ""),
        allowed_observations=context.get("allowed_observations", ""),
        missing_info=missing_json,
    )
    raw = provider.complete(sys_b, usr_b)
    plan = parse_case_intents_json(raw)

    for idx, intent in enumerate(plan.case_intents):
        db.execute(
            """INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, intent.intent_id, intent.coverage_dimension, intent.intent_text, idx),
        )

    db.execute(
        "UPDATE runs SET status='intents_ready', updated_at=datetime('now') WHERE id=?",
        (run_id,),
    )
    db.commit()


def run_llm_c(run_id: int, provider: LlmProvider, db: sqlite3.Connection) -> None:
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    req = db.execute("SELECT * FROM requirements WHERE id = ?", (run["requirement_id"],)).fetchone()

    sections = db.execute(
        "SELECT * FROM test_basis_sections WHERE run_id = ? ORDER BY sort_order", (run_id,)
    ).fetchall()

    context: dict[str, str] = {"missing_str": "", "signals": "", "thresholds": "", "timing": "", "states": "", "observations": ""}
    missing_descs: list[str] = []
    missing_items_lines: list[str] = []
    for sec in sections:
        items = db.execute(
            "SELECT * FROM test_basis_items WHERE section_id = ? ORDER BY sort_order", (sec["id"],)
        ).fetchall()
        known = [it["content"] for it in items if it["status"] == "known" and it["content"]]
        needs = [it for it in items if it["status"] == "needs_review"]

        if sec["section_name"] == "signals":
            context["signals"] = ", ".join(known)
        elif sec["section_name"] == "thresholds":
            context["thresholds"] = ", ".join(known)
        elif sec["section_name"] == "timing":
            context["timing"] = ", ".join(known)
        elif sec["section_name"] == "states":
            context["states"] = ", ".join(known)
        elif sec["section_name"] == "observations":
            context["observations"] = ", ".join(known)

        for n in needs:
            cat = _section_to_category(sec["section_name"])
            if n["need"]:
                missing_descs.append(n["need"])
                missing_items_lines.append(f"[{cat}] {n["need"]}")

    context["missing_str"] = ", ".join(missing_descs)
    missing_items_str = "\n".join(missing_items_lines)

    intents = db.execute(
        "SELECT * FROM case_intents WHERE run_id = ? ORDER BY sort_order", (run_id,)
    ).fetchall()

    generation_failures: list[int] = []
    for idx, intent in enumerate(intents):
        sys_c, usr_c = render_prompt(
            "generate_case",
            requirement_key=req["requirement_key"],
            description=req["description"],
            supplementary_info="",
            coverage_dimension=intent["coverage_dimension"],
            case_intent=intent["intent_text"],
            review_comment="",
            extracted_signals=context["signals"],
            extracted_thresholds=context["thresholds"],
            extracted_timing=context["timing"],
            extracted_states=context["states"],
            extracted_observations=context["observations"],
            missing_info=context["missing_str"],
            missing_info_items=missing_items_str,
        )

        try:
            html = provider.complete(sys_c, usr_c)
            case = parse_generated_case(html)
        except Exception:
            case = GeneratedCase(
                title=intent["intent_text"][:80],
                objective=intent["intent_text"],
                steps=[],
                raw_html="",
            )
            generation_failures.append(idx)

        cur = db.execute(
            """INSERT INTO test_cases
               (run_id, intent_id, title, objective, precondition, postcondition, raw_html, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, intent["id"], case.title, case.objective,
             case.precondition, case.postcondition, case.raw_html or "", idx),
        )
        case_id = cur.lastrowid

        for step in case.steps:
            db.execute(
                """INSERT INTO test_case_steps (case_id, step_order, action, expected)
                   VALUES (?, ?, ?, ?)""",
                (case_id, step.order, step.action, step.expected or ""),
            )

    status = "cases_ready" if not generation_failures else "cases_ready"

    db.execute(
        "UPDATE runs SET status=?, updated_at=datetime('now') WHERE id=?",
        (status, run_id),
    )
    db.commit()


def regenerate_test_basis(
    db: sqlite3.Connection,
    run_id: int,
    item_id: str,
    comment: str,
    provider: LlmProvider,
) -> list[dict]:
    """Regenerate the full test basis for a run based on human review feedback."""
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    req = db.execute("SELECT * FROM requirements WHERE id = ?", (run["requirement_id"],)).fetchone()

    sections = db.execute(
        "SELECT * FROM test_basis_sections WHERE run_id = ? ORDER BY sort_order", (run_id,)
    ).fetchall()
    items_by_section: dict[str, list[str]] = {}
    focus_desc = ""
    for sec in sections:
        items = db.execute(
            "SELECT * FROM test_basis_items WHERE section_id = ? ORDER BY sort_order", (sec["id"],)
        ).fetchall()
        items_by_section[sec["section_name"]] = [it["content"] or it["need"] for it in items]
        for it in items:
            if it["item_id"] == item_id:
                focus_desc = it["content"] or it["need"] or it["item_id"]

    previous_output = "\n".join(
        f"{sec}: {', '.join(contents)}" for sec, contents in items_by_section.items()
    )

    requirement_text = req["description"]
    if req["supplementary_info"]:
        requirement_text += "\n" + req["supplementary_info"]

    sys_prompt, usr_prompt = render_prompt(
        "regenerate_test_basis_item",
        requirement_text=requirement_text,
        previous_output=previous_output,
        review_comment=comment,
        focus_item_id=item_id,
        focus_item_description=focus_desc,
    )

    raw = provider.complete(sys_prompt, usr_prompt)
    from ..parser.json_parser import parse_test_basis_json
    tb = parse_test_basis_json(raw)

    for sec in sections:
        db.execute("DELETE FROM test_basis_items WHERE section_id = ?", (sec["id"],))
    db.execute("DELETE FROM test_basis_sections WHERE run_id = ?", (run_id,))

    section_order = [
        ("signals", tb.allowed_signals),
        ("thresholds", tb.allowed_thresholds),
        ("timing", tb.allowed_timing),
        ("states", tb.allowed_states),
        ("observations", tb.allowed_observations),
    ]

    result: list[dict] = []
    for sort_order, (section_name, values) in enumerate(section_order):
        cur = db.execute(
            "INSERT INTO test_basis_sections (run_id, section_name, sort_order) VALUES (?, ?, ?)",
            (run_id, section_name, sort_order),
        )
        section_id = cur.lastrowid

        for i, val in enumerate(values):
            db.execute(
                """INSERT INTO test_basis_items
                   (section_id, item_id, status, content, need, source_text, sort_order)
                   VALUES (?, ?, 'known', ?, '', ?, ?)""",
                (section_id, f"{section_name[:4]}-{i+1}", val, req["description"], i),
            )
            result.append({"item_id": f"{section_name[:4]}-{i+1}", "content": val})

        section_mi = [mi for mi in tb.missing_info if mi.category == _section_to_category(section_name)]
        for j, mi in enumerate(section_mi):
            db.execute(
                """INSERT INTO test_basis_items
                   (section_id, item_id, status, content, need, source_text, sort_order)
                   VALUES (?, ?, 'needs_review', '', ?, '', ?)""",
                (section_id, f"{section_name[:4]}-needs-{j+1}", mi.description, len(values) + j),
            )
            result.append({"item_id": f"{section_name[:4]}-needs-{j+1}", "need": mi.description})

    from .review_state import record_action
    record_action(db, run_id, "a", "regenerate", target_type="test_basis_item",
                   target_id=None, comment=comment)

    db.commit()
    return result


def _section_to_category(section_name: str) -> str:
    mapping = {
        "signals": "signal",
        "thresholds": "threshold",
        "timing": "timing",
        "states": "state",
        "observations": "observation",
    }
    return mapping.get(section_name, section_name)
