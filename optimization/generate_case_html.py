"""Generate per-round case-display HTML in the format of exports/generated_cases.html."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from optimization.evaluator import (
    CHECKLIST,
    evaluate_generated_cases,
)

STANDARD_PRECONDITION = "BMS initialized, all parameters within normal operating range, no active faults."
STANDARD_POSTCONDITION = "System returned to normal operating state."


def generate_round_html(round_dir: Path, round_num: int) -> None:
    cases_path = round_dir / "generated_cases.json"
    if not cases_path.exists():
        print(f"No data for round {round_num}")
        return

    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    evaluation = evaluate_generated_cases(data)
    total_passed = evaluation.total_passed
    total_failed = evaluation.total_cases - evaluation.total_passed

    # Build per-requirement HTML blocks
    req_blocks = []

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
            case_eval = evaluation.case_results.get((req["requirement_key"], ci_idx))
            failed_items = case_eval.failed_items if case_eval else []

            if failed_items:
                badge = '<span style="background:#ef4444;color:#fff;padding:1px 8px;border-radius:3px;font-size:0.7rem;margin-left:8px">FAIL</span>'
                fail_details = "<div style='margin-top:6px;font-size:0.82rem'>"
                fail_details += "<details><summary style='color:#ef4444;cursor:pointer'><b>Failed checklist items ({})</b></summary>".format(len(failed_items))
                fail_details += "<ul style='margin:4px 0;padding-left:20px'>"
                for fi in failed_items:
                    desc, cat = CHECKLIST.get(fi, (fi, ""))
                    fail_details += f"<li><b>{fi}</b> [{cat}] — {desc}</li>"
                fail_details += "</ul></details></div>"
            else:
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

    pass_rate = evaluation.case_pass_rate

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
