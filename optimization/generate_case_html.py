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
    "2.1.1": ("已知信号名在expected中引用", "领域正确性"),
    "2.1.2": ("不凭空发明信号名", "领域正确性"),
    "2.1.3": ("信号名与原文一致", "领域正确性"),
    "2.2.1": ("已知阈值在expected中引用", "领域正确性"),
    "2.2.2": ("不凭空发明数值阈值", "领域正确性"),
    "2.3.1": ("已知时序参数在expected中引用", "领域正确性"),
    "2.3.2": ("符号化参数名直接使用", "领域正确性"),
    "2.4.1": ("不凭空发明CAN ID", "领域正确性"),
    "2.4.2": ("不凭空发明calibration name", "领域正确性"),
    "3.1.1": ("NEEDS REVIEW仅用于缺失信息", "NEEDS REVIEW规范"),
    "3.1.2": ("有具体值时不加NEEDS REVIEW", "NEEDS REVIEW规范"),
    "3.2.1": ("NEEDS REVIEW位置正确", "NEEDS REVIEW规范"),
    "3.2.2": ("时序缺失时expected有占位符", "NEEDS REVIEW规范"),
    "4.1.1": ("每个step有action和expected", "步骤质量"),
    "4.2.1": ("时序等待与执行动作分两步", "步骤质量"),
    "4.2.2": ("无重复stimulus/wait步骤", "步骤质量"),
    "4.3.1": ("至少一个expected具体可观测", "步骤质量"),
    "4.3.2": ("无模糊expected result", "步骤质量"),
    "4.3.3": ("无read/check-only expected", "步骤质量"),
    "5.1.1": ("normal_behavior匹配", "覆盖维度匹配"),
    "5.1.2": ("boundary_or_threshold匹配", "覆盖维度匹配"),
    "5.1.3": ("fault_or_protection匹配", "覆盖维度匹配"),
    "5.1.4": ("state_transition匹配", "覆盖维度匹配"),
    "5.1.5": ("observability匹配", "覆盖维度匹配"),
    "5.2.1": ("参数/时序未触发为独立case", "覆盖维度匹配"),
    "5.2.2": ("参数阈值和时序阈值独立", "覆盖维度匹配"),
    "6.1.1": ("所有case统一precondition", "测试工程深度"),
    "6.1.2": ("所有case统一postcondition", "测试工程深度"),
    "6.1.3": ("action不写BMS内部行为", "测试工程深度"),
    "6.2.1": ("Title描述测试条件和预期行为", "测试工程深度"),
    "6.3.1": ("每个case聚焦一个意图", "测试工程深度"),
    "6.3.2": ("不合并多个阈值场景", "测试工程深度"),
}

STANDARD_PRECONDITION = "BMS initialized, all parameters within normal operating range, no active faults."
STANDARD_POSTCONDITION = "System returned to normal operating state."


def evaluate_case(case: dict, req_info: dict, global_data: dict) -> list[str]:
    """Evaluate a single case against checklist items. Returns list of failed item IDs."""
    failed = []

    title = case["title"].strip()
    obj = case["objective"].strip()
    pre = case["precondition"].strip()
    post = case["postcondition"].strip()
    steps = case["steps"]

    signals = [s.strip() for s in req_info.get("signals", []) if s.strip()]
    thresholds = [t.strip() for t in req_info.get("thresholds", []) if t.strip()]
    timing = [t.strip() for t in req_info.get("timing", []) if t.strip() and t.strip().lower() != "none found"]
    missing_info = req_info.get("missing_critical_info", [])
    has_missing = missing_info and "none" not in " ".join(missing_info).lower()
    coverage = req_info.get("case_coverage", "")

    case_text = f"{title} {obj} {pre} {post}"
    all_expected = " ".join([s["expected"] or "" for s in steps]).lower()

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

    # 2.1.1 - signal reference
    if signals and all_expected:
        if not any(s.lower() in all_expected for s in signals):
            failed.append("2.1.1")

    # 2.2.1 - threshold reference
    if thresholds and all_expected:
        if not any(t.lower() in all_expected for t in thresholds):
            failed.append("2.2.1")

    # 2.2.2 - invented numeric values
    for s in steps:
        text = f"{s['action']} {s['expected'] or ''}"
        known = " ".join(timing + thresholds).lower()
        found_nums = re.findall(r"\d+\.?\d*\s*(?:V|A|deg C|\xb0C|ms|s|ohm|%)", text)
        for n in found_nums:
            if n.lower() not in known:
                failed.append("2.2.2")
                break
        else:
            continue
        break

    # 3.1.1 - NEEDS REVIEW only for missing info
    case_lower = json.dumps(case).lower()
    if "[needs review]" in case_lower and not has_missing:
        failed.append("3.1.1")

    # 4.1.1 - every step has action + expected
    has_null_action = False
    has_merged_wait = False
    wait_count = 0
    separated_count = 0
    for i, s in enumerate(steps):
        act = s["action"].strip().lower()
        exp = s["expected"]
        is_wait = act.startswith("wait")
        if not is_wait and exp is None:
            has_null_action = True
        if "wait" in act and exp and exp != "none":
            has_merged_wait = True
        if "wait" in act:
            wait_count += 1
            if i + 1 < len(steps):
                next_exp = (steps[i + 1]["expected"] or "").strip()
                if next_exp and next_exp.lower() != "none":
                    separated_count += 1
    if has_null_action:
        failed.append("4.1.1")

    # 4.2.1 - timing and action separately (fail only if merged dominates separated)
    if has_merged_wait and separated_count < wait_count:
        failed.append("4.2.1")

    # 4.3.2 - no vague expected
    for s in steps:
        exp = (s["expected"] or "").lower()
        if exp and any(v in exp for v in ["system works correctly", "behaves as expected", "works as expected"]):
            failed.append("4.3.2")

    # 4.3.3 - no read/check-only expected
    for s in steps:
        exp = (s["expected"] or "").lower()
        if exp and any(v in exp for v in ["read", "check", "verify", "observe", "monitor", "capture"]):
            if len(exp.split()) < 8 and not any(c.isdigit() for c in exp):
                failed.append("4.3.3")
                break

    # 6.1.1 - unified precondition (check keyword overlap)
    pre_keywords = ["bms initialized", "normal operating", "no active fault"]
    pre_lower = pre.lower()
    if not any(kw in pre_lower for kw in pre_keywords):
        failed.append("6.1.1")

    # 6.1.2 - unified postcondition (check keyword overlap)
    post_lower = post.lower()
    if not ("returned" in post_lower or "normal operating" in post_lower or "restored" in post_lower):
        failed.append("6.1.2")

    # 6.1.3 - action is tester action, not BMS behavior
    for s in steps:
        act = s["action"].strip().lower()
        if any(p in act for p in ["bms shall", "the bms", "bms initiates", "bms verifies",
                                   "bms injects", "bms should", "bms performs"]):
            failed.append("6.1.3")
            break

    # 6.2.1 - descriptive title
    if title.lower() in {"draft test case", "test case", "boundary test"}:
        failed.append("6.2.1")

    return failed


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
        thresholds = req["analysis"]["thresholds"]
        timing = [t for t in req["analysis"].get("timing", []) if t.strip().lower() != "none found"]
        missing_info = req["analysis"].get("missing_critical_info", [])

        signals_str = ", ".join(signals) if signals else "—"
        thresholds_str = ", ".join(thresholds) if thresholds else "—"
        timing_str = ", ".join(timing) if timing else "—"

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

            req_info = {
                "signals": signals,
                "thresholds": thresholds,
                "timing": timing,
                "missing_critical_info": missing_info,
                "case_coverage": coverage,
            }
            global_data = {
                "all_preconds": all_preconds,
                "all_postconds": all_postconds,
            }
            failed_items = evaluate_case(case, req_info, global_data)

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
      <div style="display:flex;gap:24px;font-size:0.85rem;margin:8px 0">
        <div><b>Signals:</b> {signals_str}</div>
        <div><b>Thresholds:</b> {thresholds_str}</div>
        <div><b>Timing:</b> {timing_str}</div>
      </div>
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
