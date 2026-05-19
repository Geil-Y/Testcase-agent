"""Generate per-round case-display HTML in the format of exports/generated_cases.html."""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime

CHECKLIST = {
    "1.1.1": ("title 不为空/非placeholder", "结构完整性"),
    "1.1.2": ("objective 不为空", "结构完整性"),
    "1.1.3": ("precondition 不为空", "结构完整性"),
    "1.1.4": ("postcondition 不为空", "结构完整性"),
    "1.1.5": ("至少1个step且有action", "结构完整性"),
    "1.1.6": ("related_requirement 存在", "结构完整性"),
    "2.1.1": ("已知信号名在case中引用", "领域正确性"),
    "2.1.2": ("不凭空发明标识符", "领域正确性"),
    "2.2.1": ("不凭空发明数值阈值", "领域正确性"),
    "2.2.2": ("符号化参数名视为有效值", "领域正确性"),
    # v2 Section 3 — [NEEDS REVIEW] with five-category hard gates
    "3.2.1": ("[HARD] 需要signal/threshold/timing/state/observation但case未标[NEEDS REVIEW]", "NEEDS REVIEW规范"),
    "3.2.2": ("[HARD] action/expected编造需求未提供的signal/threshold/timing/state/observation", "NEEDS REVIEW规范"),
    "3.2.3": ("[WARNING] 需求语义完整但case添加不必要[NEEDS REVIEW]", "NEEDS REVIEW规范"),
    "3.3.1": ("[NEEDS REVIEW]只能放在action/expected，不放在title/objective/precondition/postcondition", "NEEDS REVIEW规范"),
    "3.3.2": ("timing缺失时[NEEDS REVIEW]应放在Wait action", "NEEDS REVIEW规范"),
    "3.3.3": ("禁止[NEEDS REVIEW: timing]带category后缀", "NEEDS REVIEW规范"),
    "4.1.1": ("时序等待与执行动作分两步 [WARNING]", "步骤质量"),
    "4.1.4": ("action 不包含意图叙述（无 such that / in order to 等）", "步骤质量"),
    "4.1.5": ("action 不冗长（每条 ≤15 词）", "步骤质量"),
    "4.2.1": ("至少一个expected具体可观测", "步骤质量"),
    "4.2.2": ("无模糊expected result", "步骤质量"),
    "4.2.3": ("无read/check-only expected", "步骤质量"),
    "4.2.4": ("expected 不冗长（每条 ≤15 词）", "步骤质量"),
    "5.2.1": ("触发/不触发等价类覆盖", "覆盖维度"),
    "5.2.2": ("边界值case覆盖", "覆盖维度"),
    "5.2.3": ("参数/时序正交拆分", "覆盖维度"),
    "6.1.1": ("所有case统一precondition", "测试工程深度"),
    "6.1.2": ("所有case统一postcondition", "测试工程深度"),
    "6.1.3": ("setup动作放action非precondition", "测试工程深度"),
    "6.2.1": ("Title描述测试条件和预期行为", "测试工程深度"),
    "6.3.1": ("每个case仅验证一个需求的一个行为", "测试工程深度"),
    "6.3.2": ("不合并多个阈值场景", "测试工程深度"),
}

# Categories legal in expected_missing_categories and missing_info_items
_MISSING_CATEGORIES = {"signal", "threshold", "timing", "state", "observation"}

STANDARD_PRECONDITION = "BMS initialized, all parameters within normal operating range, no active faults."
STANDARD_POSTCONDITION = "System returned to normal operating state."


def evaluate_case(case: dict, req_info: dict, global_data: dict) -> tuple[list[str], list[str]]:
    """Evaluate a single case against checklist items.

    Returns (failed_item_ids, warning_item_ids).
    """
    failed: list[str] = []
    warnings: list[str] = []

    title = case["title"].strip()
    obj = case["objective"].strip()
    pre = case["precondition"].strip()
    post = case["postcondition"].strip()
    steps = case["steps"]

    signals = [s.strip() for s in req_info.get("signals", []) if s.strip()]
    thresholds = [t.strip() for t in req_info.get("thresholds", []) if t.strip()]
    timing = [t.strip() for t in req_info.get("timing", []) if t.strip() and t.strip().lower() != "none found"]
    expected_missing = req_info.get("expected_missing_categories", [])
    coverage = req_info.get("case_coverage", "")

    case_text = f"{title} {obj} {pre} {post}"
    all_expected = " ".join([s["expected"] or "" for s in steps]).lower()

    rr = case.get("related_requirement", "").strip()

    # Build step text for NEEDS REVIEW checks
    steps_lower = "".join(
        s["action"] + (s.get("expected") or "")
        for s in steps
    ).lower()
    # Content fields excluding raw_html
    non_step_fields = f"{title} {obj} {pre} {post}".lower()
    has_needs_review = "[needs review]" in f"{non_step_fields} {steps_lower}"

    # 1.1.1
    if not title or title.lower() in {"draft test case", "test case", "boundary test"}:
        failed.append("1.1.1")
    # 1.1.2
    if not obj:
        failed.append("1.1.2")
    # 1.1.3
    if not pre:
        failed.append("1.1.3")
    # 1.1.4
    if not post:
        failed.append("1.1.4")
    # 1.1.5
    if not steps:
        failed.append("1.1.5")
    # 1.1.6 - related_requirement present and matches
    if not rr:
        failed.append("1.1.6")

    # 2.1.1 - signal reference
    if signals and all_expected:
        if not any(s.lower() in all_expected for s in signals):
            failed.append("2.1.1")

    # 2.2.1 - invented numeric values (check against requirement description + supplementary_info + timing + thresholds + signals)
    req_desc = req_info.get("requirement_description", "").lower()
    supp_info = req_info.get("supplementary_info", "").lower()
    known_text = req_desc + " " + supp_info + " " + " ".join(timing + thresholds + signals).lower()
    for s in steps:
        text = f"{s['action']} {s['expected'] or ''}"
        found_nums = re.findall(r"\d+\.?\d*\s*(?:deg\s*C|°C|kOhm|MOhm|mOhm|kΩ|MΩ|mΩ|mV|mA|ms|ohm|Ω|deg|V|A|s|%)(?!\w)", text, re.IGNORECASE)
        for n in found_nums:
            if n.lower() not in known_text:
                failed.append("2.2.1")
                break
        else:
            continue
        break

    # 2.2.2 - symbolic parameter names treated as valid values
    # (No deterministic check — semantic assessment only. Pass by default.)

    # ── v2 Section 3: [NEEDS REVIEW] hard gates ────────────────────────────

    # 3.2.1 [HARD] — need signal/threshold/timing/state/observation but case
    # lacks [NEEDS REVIEW]. Only checkable when expected_missing_categories is
    # available (Prompt Evaluation Set).
    if expected_missing:
        nr_in_steps = any(
            "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
            for s in steps
        )
        if not nr_in_steps:
            failed.append("3.2.1")

    # 3.2.2 [HARD] — action/expected invents missing signal/threshold/timing/
    # state/observation. Detected when expected_missing is non-empty and we see
    # numeric inventions or unknown signals without [NEEDS REVIEW].
    if expected_missing:
        if "threshold" in expected_missing:
            for s in steps:
                text = f"{s['action']} {s['expected'] or ''}"
                if re.search(r"\d+\.?\d+", text) and "[needs review]" not in text.lower():
                    failed.append("3.2.2")
                    break

    # 3.2.3 [WARNING] — requirement complete but case adds [NEEDS REVIEW]
    if has_needs_review and not expected_missing:
        warnings.append("3.2.3")

    # 3.3.1 — [NEEDS REVIEW] only in action/expected, not elsewhere
    nr_in_non_step = "[needs review]" in non_step_fields
    if nr_in_non_step:
        failed.append("3.3.1")

    # 3.3.2 — timing missing → [NEEDS REVIEW] in Wait action
    needs_review_in_steps = any(
        "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
        for s in steps
    )
    if "timing" in expected_missing and needs_review_in_steps:
        nr_in_wait = any(
            "[needs review]" in s["action"].lower() and "wait" in s["action"].lower()
            for s in steps
        )
        if not nr_in_wait:
            failed.append("3.3.2")

    # 3.3.3 — no [NEEDS REVIEW: category] suffix
    nr_with_suffix_pattern = re.compile(
        r"\[needs review\s*:\s*\w+\]", re.IGNORECASE
    )
    if nr_with_suffix_pattern.search(case.get("raw_html", "")) or \
       nr_with_suffix_pattern.search(steps_lower):
        failed.append("3.3.3")

    # 4.1.1 - timing and action in separate steps [WARNING — not counted in pass/fail]
    has_null_action = False
    has_merged_wait = False
    wait_count = 0
    separated_count = 0
    for i, s in enumerate(steps):
        act = s["action"].strip().lower()
        exp = s["expected"]
        if "wait" in act:
            wait_count += 1
            if exp and exp != "none":
                has_merged_wait = True
            if i + 1 < len(steps):
                next_exp = (steps[i + 1]["expected"] or "").strip()
                if next_exp and next_exp.lower() != "none":
                    separated_count += 1
    # 4.1.1 downgraded to WARNING — still tracked but not counted for pass/fail
    if has_merged_wait and separated_count < wait_count:
        warnings.append("4.1.1")

    # 4.1.4 - action should not describe intent (no "such that", "in order to", etc.)
    _INTENT_PATTERNS = ["such that", "in order to", "to verify", "to ensure",
                        "to check", "so that", "to confirm", "to validate"]
    for s in steps:
        act = s["action"].strip().lower()
        if any(p in act for p in _INTENT_PATTERNS):
            failed.append("4.1.4")
            break

    # 4.1.5 - action not overly verbose (max 15 words)
    for s in steps:
        act = s["action"].strip()
        if not act:
            continue
        if len(act.split()) > 15:
            failed.append("4.1.5")
            break

    # 4.2.1 - at least one concrete observable expected
    has_concrete = any(
        (s["expected"] or "").strip().lower() not in ("", "none", "null") and len((s["expected"] or "").strip()) > 10
        for s in steps
    )
    if not has_concrete:
        failed.append("4.2.1")

    # 4.2.2 - no vague expected
    for s in steps:
        exp = (s["expected"] or "").lower()
        if exp and any(v in exp for v in ["system works correctly", "behaves as expected", "works as expected"]):
            failed.append("4.2.2")
            break

    # 4.2.3 - no read/check-only expected
    for s in steps:
        exp = (s["expected"] or "").lower()
        act = s["action"].lower()
        if exp and any(v in exp for v in ["read", "check", "verify", "observe", "monitor", "capture"]):
            if not any(w in act for w in ["set", "apply", "simulate"]):
                if len(exp.split()) < 8:
                    failed.append("4.2.3")
                    break

    # 4.2.4 - expected not overly verbose (max 15 words)
    for s in steps:
        exp = (s["expected"] or "").strip()
        if not exp or exp.lower() == "none":
            continue
        if len(exp.split()) > 15:
            failed.append("4.2.4")
            break

    # 6.1.1 - unified precondition (check keyword overlap)
    pre_keywords = ["bms initialized", "normal operating", "no active fault"]
    pre_lower = pre.lower()
    if not any(kw in pre_lower for kw in pre_keywords):
        failed.append("6.1.1")

    # 6.1.2 - unified postcondition (check keyword overlap)
    post_lower = post.lower()
    if not ("return" in post_lower or "normal" in post_lower or "restored" in post_lower):
        failed.append("6.1.2")

    # 6.1.3 - action is tester action, not BMS behavior
    for s in steps:
        act = s["action"].strip().lower()
        if any(p in act for p in ["bms shall", "bms initiates", "bms verifies",
                                   "bms injects", "bms should", "bms performs"]):
            failed.append("6.1.3")
            break

    # 6.2.1 - descriptive title
    if title.lower() in {"draft test case", "test case", "boundary test"}:
        failed.append("6.2.1")

    return failed, warnings


def _enrich_req_info(req: dict) -> dict:
    """Build the req_info dict needed by evaluate_case from a requirement entry."""
    signals = req["analysis"]["signals"]
    thresholds = req["analysis"].get("thresholds", [])
    timing = [t for t in req["analysis"].get("timing", []) if t.strip().lower() != "none found"]

    info: dict = {
        "signals": signals,
        "thresholds": thresholds,
        "timing": timing,
        "case_coverage": "",
        "requirement_description": req.get("description", ""),
        "supplementary_info": req.get("supplementary_info", ""),
    }
    # Prompt Evaluation Set metadata when available
    if req.get("expected_missing_categories") is not None:
        info["expected_missing_categories"] = req["expected_missing_categories"]
    if req.get("evaluation_bucket"):
        info["evaluation_bucket"] = req["evaluation_bucket"]
    # Actual missing categories from analysis
    actual = req.get("analysis", {}).get("missing_info_items", [])
    if actual:
        info["actual_missing_categories"] = [mi["category"] for mi in actual if mi.get("category")]
    return info


def evaluate_missing_info_hard_gates(data: list[dict]) -> list[dict]:
    """Compare expected vs actual missing categories per requirement.

    Returns a list of severe-hard-gate failure records for the report.
    """
    records: list[dict] = []
    for req in data:
        expected = req.get("expected_missing_categories")
        if not expected:
            continue  # nothing expected → nothing to compare
        actual_items = req.get("analysis", {}).get("missing_info_items", [])
        actual_cats = {mi["category"] for mi in actual_items if mi.get("category")}

        missing_cats = [c for c in expected if c not in actual_cats]
        extra_cats = [c for c in actual_cats if c not in expected]
        matched = [c for c in expected if c in actual_cats]

        # Determine hard gate item IDs
        item_ids: list[str] = []
        if missing_cats:
            item_ids.append("3.2.1")
        if extra_cats:
            item_ids.append("3.2.3")

        # Check each case for [NEEDS REVIEW] presence
        case_issues: list[dict] = []
        for case in req.get("cases", []):
            nr_in_steps = any(
                "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
                for s in case.get("steps", [])
            )
            if expected and not nr_in_steps:
                case_issues.append({
                    "case_title": case.get("title", ""),
                    "issue": "missing [NEEDS REVIEW] in action/expected",
                    "missing_categories": expected,
                    "item_id": "3.2.1",
                })

        records.append({
            "requirement_key": req["requirement_key"],
            "evaluation_bucket": req.get("evaluation_bucket", ""),
            "expected_missing_categories": expected,
            "actual_missing_categories": sorted(actual_cats),
            "matched": matched,
            "missing_from_actual": missing_cats,
            "extra_in_actual": extra_cats,
            "case_issues": case_issues,
            "item_ids": item_ids,
        })
    return records


def generate_round_html(round_dir: Path, round_num: int) -> None:
    cases_path = round_dir / "generated_cases.json"
    if not cases_path.exists():
        print(f"No data for round {round_num}")
        return

    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    total_cases = sum(len(r["cases"]) for r in data)
    total_passed = 0
    total_failed = 0

    # Build per-requirement HTML blocks
    req_blocks = []
    all_preconds = set()
    all_postconds = set()

    for req in data:
        for c in req["cases"]:
            all_preconds.add(c["precondition"])
            all_postconds.add(c["postcondition"])

    for req in data:
        signals = req["analysis"]["signals"]
        thresholds = req["analysis"].get("thresholds", [])
        timing = [t for t in req["analysis"].get("timing", []) if t.strip().lower() != "none found"]
        states = req["analysis"].get("states", [])
        observations = req["analysis"].get("observations", [])

        signals_str = ", ".join(signals) if signals else "—"
        thresholds_str = ", ".join(thresholds) if thresholds else "—"
        timing_str = ", ".join(timing) if timing else "—"
        states_str = ", ".join(states) if states else "—"
        observations_str = ", ".join(observations) if observations else "—"

        # Set metadata
        bucket_label = req.get("evaluation_bucket", "")
        expected_missing_str = ", ".join(req.get("expected_missing_categories", [])) or "—"
        actual_cats = [
            mi["category"] for mi in req.get("analysis", {}).get("missing_info_items", [])
            if mi.get("category")
        ]
        actual_missing_str = ", ".join(sorted(set(actual_cats))) if actual_cats else "—"

        set_meta_html = ""
        if bucket_label:
            set_meta_html += f"""
            <div style="display:flex;gap:24px;font-size:0.82rem;margin:4px 0;color:#555">
              <div><b>Bucket:</b> {bucket_label}</div>
              <div><b>Expected missing:</b> {expected_missing_str}</div>
              <div><b>Actual missing:</b> {actual_missing_str}</div>
            </div>"""

        # Coverage plan
        intents_html = ""
        for ci in req["analysis"]["case_intents"]:
            intents_html += f'<li><b>{ci["coverage"]}</b> — {ci["description"]}</li>'

        case_blocks = []
        for ci_idx, case in enumerate(req["cases"]):
            # Find matching case intent
            coverage = ""
            if ci_idx < len(req["analysis"]["case_intents"]):
                coverage = req["analysis"]["case_intents"][ci_idx]["coverage"]

            req_info = _enrich_req_info(req)
            req_info["case_coverage"] = coverage
            global_data = {
                "all_preconds": all_preconds,
                "all_postconds": all_postconds,
            }
            failed_items, case_warnings = evaluate_case(case, req_info, global_data)

            if failed_items:
                total_failed += 1
                badge = '<span style="background:#ef4444;color:#fff;padding:1px 8px;border-radius:3px;font-size:0.7rem;margin-left:8px">FAIL</span>'
                fail_details = "<div style='margin-top:6px;font-size:0.82rem'>"
                fail_details += "<details><summary style='color:#ef4444;cursor:pointer'><b>Failed checklist items ({})</b></summary>".format(len(failed_items))
                fail_details += "<ul style='margin:4px 0;padding-left:20px'>"
                for fi in failed_items:
                    desc, cat = CHECKLIST.get(fi, (fi, ""))
                    fail_details += f"<li><b>{fi}</b> [{cat}] — {desc}</li>"
                fail_details += "</ul></details></div>"
            else:
                total_passed += 1
                badge = '<span style="background:#16a34a;color:#fff;padding:1px 8px;border-radius:3px;font-size:0.7rem;margin-left:8px">PASS</span>'
                fail_details = ""

            # Steps table
            steps_rows = ""
            for s in case["steps"]:
                exp_display = s["expected"] if s["expected"] else '<span style="color:#ef4444;font-style:italic">null</span>'
                steps_rows += f'<tr><td style="text-align:center;color:#888">{s["order"]}</td><td>{s["action"]}</td><td>{exp_display}</td></tr>'

            case_blocks.append(f"""
        <div style="border:1px solid #ddd; border-radius:6px; padding:14px; margin-bottom:10px; page-break-inside:avoid">
          <h4 style="margin:0 0 6px 0">Case {ci_idx + 1} — {case["title"]}{badge}</h4>
          <p style="margin:4px 0"><b>Related Requirement:</b> {case.get("related_requirement", "")}</p>
          <p style="margin:4px 0"><b>Objective:</b> {case["objective"]}</p>
          <p style="margin:4px 0"><b>Precondition:</b> {case["precondition"]}</p>
          <table style="width:100%;border-collapse:collapse;margin:8px 0;font-size:0.85rem">
            <thead><tr style="background:#f5f5f5"><th style="width:40px;text-align:center">#</th><th style="width:45%">Action</th><th>Expected Result</th></tr></thead>
            <tbody>{steps_rows}</tbody>
          </table>
          <p style="margin:4px 0"><b>Postcondition:</b> {case["postcondition"]}</p>
          {fail_details}
        </div>""")

        req_blocks.append(f"""
    <div style="border:2px solid #2563eb; border-radius:8px; padding:18px; margin-bottom:24px; page-break-inside:avoid">
      <h2 style="margin:0 0 4px 0;color:#2563eb">{req["requirement_key"]}</h2>
      <p style="color:#888;margin:0 0 8px 0">{req.get("function_name", "")}</p>
      <p style="background:#f8f9fa;padding:10px;border-radius:4px;font-size:0.95rem">{req["description"]}</p>
      <div style="display:flex;gap:24px;font-size:0.85rem;margin:8px 0;flex-wrap:wrap">
        <div><b>Signals:</b> {signals_str}</div>
        <div><b>Thresholds:</b> {thresholds_str}</div>
        <div><b>Timing:</b> {timing_str}</div>
        <div><b>States:</b> {states_str}</div>
        <div><b>Observations:</b> {observations_str}</div>
      </div>
      {set_meta_html}
      <details style="margin:8px 0;font-size:0.85rem">
        <summary><b>Coverage Plan</b> ({len(req["analysis"]["case_intents"])} intents)</summary>
        <ul>{intents_html}</ul>
      </details>
      <h3 style="margin:12px 0 8px 0">{len(req["cases"])} Test Cases</h3>
      {"".join(case_blocks)}
    </div>""")

    pass_rate = round(total_passed / (total_passed + total_failed) * 100, 1) if (total_passed + total_failed) else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BMS Test Cases — Round {round_num} — qwen2.5:7b</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1000px; margin: 0 auto; padding: 24px; color: #111; line-height: 1.5; background: #fafafa; }}
  h1 {{ color: #2563eb; }}
  footer {{ color: #888; font-size: 0.8rem; margin-top: 32px; text-align: center; }}
  @media print {{ body {{ background: #fff; }} }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border-bottom: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
  .summary {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
</style>
</head>
<body>
<h1>BMS HIL Test Cases — Round {round_num}</h1>
<p style="color:#888">Generated by <b>qwen2.5:7b</b> via Ollama — {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>

<div class="summary">
  <b>Summary:</b> {total_passed + total_failed} cases total |
  <span style="color:#16a34a"><b>{total_passed} PASS</b></span> |
  <span style="color:#ef4444"><b>{total_failed} FAIL</b></span> |
  Pass rate: <b>{pass_rate}%</b>
</div>

{"".join(req_blocks)}

<footer>Generated with Testcase Agent — prompt optimization run</footer>
</body>
</html>"""

    report_path = round_dir / "cases_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"Round {round_num}: {total_passed}P / {total_failed}F ({pass_rate}%) -> {report_path}")


def main():
    run_dir = Path("optimization_runs/run_20260518_233620")
    for rn in range(1, 6):
        generate_round_html(run_dir / f"round_0{rn}", rn)


if __name__ == "__main__":
    main()
