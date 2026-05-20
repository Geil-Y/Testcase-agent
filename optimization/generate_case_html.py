"""Generate the unified cases_report.html — main evaluation report.

Combines hard-rule, DeepSeek, and ChatGPT evaluations into a single HTML report
with per-case display and aggregated summary stats.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from optimization.evaluator import CHECKLIST, evaluate_generated_cases, load_all_evaluations

STANDARD_PRECONDITION = "BMS initialized, all parameters within normal operating range, no active faults."
STANDARD_POSTCONDITION = "System returned to normal operating state."

EVAL_LABELS = {
    "hardrule": "Hard-Rule",
    "deepseek": "DeepSeek",
}

EVAL_COLORS = {
    "hardrule": "#6366f1",
    "deepseek": "#22c55e",
}


DIM_LABELS = {
    "requirement_alignment": "Requirement Alignment",
    "information_integrity": "Information Integrity",
    "executability": "Executability",
    "observability": "Observability",
    "pass_fail_clarity": "Pass/Fail Clarity",
    "coverage_value": "Coverage Value",
    "state_and_environment_control": "State & Environment",
    "automation_readiness": "Automation Readiness",
}

DIM_ORDER = [
    "requirement_alignment",
    "information_integrity",
    "executability",
    "observability",
    "pass_fail_clarity",
    "coverage_value",
    "state_and_environment_control",
    "automation_readiness",
]


def _is_new_format(ev: dict | None) -> bool:
    """Detect dimension scoring format (has dimension_averages, no case_pass_rate)."""
    if ev is None:
        return False
    return "dimension_averages" in ev and "case_pass_rate" not in ev


def _score_color(score: int) -> str:
    if score >= 4:
        return "#16a34a"
    if score >= 3:
        return "#f59e0b"
    return "#ef4444"


def _badge(passed: bool) -> str:
    if passed:
        return '<span style="background:#16a34a;color:#fff;padding:1px 8px;border-radius:3px;font-size:0.7rem;margin-left:4px">PASS</span>'
    return '<span style="background:#ef4444;color:#fff;padding:1px 8px;border-radius:3px;font-size:0.7rem;margin-left:4px">FAIL</span>'


def _get_case_result(eval_data: dict | None, req_key: str, case_idx: int) -> dict | None:
    """Find a specific case's evaluation in the eval data."""
    if eval_data is None:
        return None
    for c in eval_data.get("cases", []):
        if c.get("requirement_key") == req_key and c.get("case_index") == case_idx:
            return c
    for req in eval_data.get("requirements", []):
        if req.get("requirement_key") != req_key:
            continue
        for c in req.get("cases", []):
            if c.get("case_index") == case_idx:
                merged = dict(c)
                merged["requirement_key"] = req_key
                merged["coverage_value"] = req.get("coverage_value")
                merged["coverage_value_note"] = req.get("coverage_value_note", "")
                return merged
    return None


def _build_eval_panel(evaluation, ext_evals: dict, req_key: str, ci_idx: int) -> str:
    """Build the right-column evaluation panel for a single case."""
    sections: list[str] = []

    # ── Hard-rule section ──
    ce = evaluation.case_results.get((req_key, ci_idx))
    hr_failed = ce.failed_items if ce else []
    hr_warnings = ce.warning_items if ce else []
    hr_all_passed = (not hr_failed and not hr_warnings)

    sections.append(f"""
      <div class="eval-section">
        <div class="eval-header" style="border-left-color:{EVAL_COLORS['hardrule']}">
          <b>Hard-Rule</b>{_badge(hr_all_passed)}
        </div>""")

    if hr_failed:
        sections.append(f'<div class="eval-items fail">')
        sections.append('<div class="eval-subtitle">FAIL</div>')
        for item_id in hr_failed:
            desc, cat = CHECKLIST.get(item_id, (item_id, ""))
            sections.append(
                f'<div class="eval-item">'
                f'<span class="eval-item-id fail">{item_id}</span> '
                f'<span class="eval-item-desc">{desc}</span>'
                f'</div>'
            )
        sections.append('</div>')

    if hr_warnings:
        sections.append(f'<div class="eval-items warn">')
        sections.append('<div class="eval-subtitle">WARNING</div>')
        for item_id in hr_warnings:
            desc, cat = CHECKLIST.get(item_id, (item_id, ""))
            sections.append(
                f'<div class="eval-item">'
                f'<span class="eval-item-id warn">{item_id}</span> '
                f'<span class="eval-item-desc">{desc}</span>'
                f'</div>'
            )
        sections.append('</div>')

    if hr_all_passed:
        sections.append('<div class="eval-all-pass">All 40 items passed</div>')

    sections.append('</div>')

    # ── AI evaluator sections ──
    for name, label in EVAL_LABELS.items():
        if name == "hardrule":
            continue
        ev = ext_evals.get(name)
        if ev is None:
            continue
        cr = _get_case_result(ev, req_key, ci_idx)

        if _is_new_format(ev):
            sections.append(_render_dimension_scores(name, label, cr))
        else:
            sections.append(_render_legacy_items(name, label, cr))

    return "".join(sections)


def _render_dimension_scores(name: str, label: str, cr: dict | None) -> str:
    """Render dimension score panel."""
    parts: list[str] = []
    parts.append(f"""
      <div class="eval-section">
        <div class="eval-header" style="border-left-color:{EVAL_COLORS[name]}">
          <b>{label}</b>
        </div>""")

    if cr is None:
        parts.append('<span style="font-size:0.7rem;color:#888">No score available</span></div>')
        return "".join(parts)

    parts.append('<div class="dim-scores">')
    for dim in DIM_ORDER:
        score = cr.get(dim, 0)
        note = cr.get(f"{dim}_note", "")
        label_text = DIM_LABELS.get(dim, dim)
        color = _score_color(score) if isinstance(score, int) and 1 <= score <= 5 else "#888"
        parts.append(
            f'<div class="dim-row">'
            f'<span class="dim-label">{label_text}</span>'
            f'<span class="dim-score" style="color:{color};font-weight:700">{score}</span>'
            + (f'<div class="dim-note">{note}</div>' if note else '')
            + f'</div>'
        )
    parts.append('</div></div>')
    return "".join(parts)


def _render_legacy_items(name: str, label: str, cr: dict | None) -> str:
    """Render old-format checklist item pass/fail panel."""
    parts: list[str] = []

    if cr is None:
        return f"""
          <div class="eval-section">
            <div class="eval-header muted">
              <b>{label}</b> <span style="font-size:0.7rem;color:#888">—</span>
            </div>
          </div>"""

    failed_items = [it for it in cr.get("items", []) if it["result"] == "fail"]
    warning_items = [it for it in cr.get("items", []) if it["result"] == "warning"]
    all_passed = not failed_items and not warning_items

    parts.append(f"""
      <div class="eval-section">
        <div class="eval-header" style="border-left-color:{EVAL_COLORS[name]}">
          <b>{label}</b>{_badge(all_passed)}
        </div>""")

    if failed_items:
        parts.append('<div class="eval-items fail">')
        parts.append('<div class="eval-subtitle">FAIL</div>')
        for it in failed_items:
            item_id = it.get("item_id", "")
            desc, cat = CHECKLIST.get(item_id, (item_id, ""))
            note = it.get("note", "")
            parts.append(
                f'<div class="eval-item">'
                f'<span class="eval-item-id fail">{item_id}</span> '
                f'<span class="eval-item-desc">{desc}</span>'
                + (f'<div class="eval-note">{note}</div>' if note else '')
                + f'</div>'
            )
        parts.append('</div>')

    if warning_items:
        parts.append('<div class="eval-items warn">')
        parts.append('<div class="eval-subtitle">WARNING</div>')
        for it in warning_items:
            item_id = it.get("item_id", "")
            desc, cat = CHECKLIST.get(item_id, (item_id, ""))
            note = it.get("note", "")
            parts.append(
                f'<div class="eval-item">'
                f'<span class="eval-item-id warn">{item_id}</span> '
                f'<span class="eval-item-desc">{desc}</span>'
                + (f'<div class="eval-note">{note}</div>' if note else '')
                + f'</div>'
            )
        parts.append('</div>')

    if all_passed:
        parts.append('<div class="eval-all-pass">All 40 items passed</div>')

    parts.append('</div>')
    return "".join(parts)


def _build_bottom_dims_section(ev: dict, label: str) -> str:
    """Build HTML section showing the 3 dimensions with the lowest average scores."""
    dim_avgs = ev.get("dimension_averages", {})
    if not dim_avgs:
        return ""

    sorted_dims = sorted(dim_avgs.items(), key=lambda x: x[1])
    bottom_3 = sorted_dims[:3]

    rows = ""
    for rank, (dim, score) in enumerate(bottom_3, 1):
        dim_label = DIM_LABELS.get(dim, dim)
        color = _score_color(score) if isinstance(score, int) and 1 <= score <= 5 else "#888"
        rows += (
            f'<tr>'
            f'<td style="text-align:center;font-weight:700">{rank}</td>'
            f'<td>{dim_label}</td>'
            f'<td style="font-weight:700;color:{color}">{score}</td>'
            f'</tr>'
        )

    return f"""
    <div style="background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:24px;max-width:480px">
      <b style="color:#ef4444">Lowest 3 Dimensions — {label}</b>
      <table style="margin-top:8px">
        <tr><th style="width:30px;text-align:center">#</th><th>Dimension</th><th style="width:60px;text-align:center">Avg</th></tr>
        {rows}
      </table>
    </div>"""


def generate_round_html(round_dir: Path, round_num: int) -> float | None:
    """Generate cases_report.html combining all evaluators.

    Returns the hard-rule case pass rate, or None if no data.
    """
    cases_path = round_dir / "generated_cases.json"
    if not cases_path.exists():
        print(f"No generated_cases.json in {round_dir}")
        return None

    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    # Hard-rule evaluation (always available, freshly computed)
    evaluation = evaluate_generated_cases(data)
    total_passed = evaluation.total_passed
    total_failed = evaluation.total_cases - evaluation.total_passed

    # Load optional external evaluations
    ext_evals = load_all_evaluations(round_dir)

    # ── Build summary cards ────────────────────────────────────────────
    cards = ""
    for name, label in EVAL_LABELS.items():
        ev = ext_evals.get(name)
        if ev and _is_new_format(ev):
            score = ev.get("overall_weighted", 0)
            total = ev.get("total_requirements", ev.get("total_cases", 0))
            color = EVAL_COLORS[name]
            cards += (
                f'<div class="summary-card">'
                f'<div class="value" style="color:{color}">{score}</div>'
                f'<div class="label">{label} weighted / 5 ({total} requirements)</div>'
                f'</div>'
            )
        elif ev:
            rate = ev.get("case_pass_rate", 0)
            passed = ev.get("total_passed", 0)
            total = ev.get("total_cases", 0)
            color = EVAL_COLORS[name]
            cards += (
                f'<div class="summary-card">'
                f'<div class="value" style="color:{color}">{rate}%</div>'
                f'<div class="label">{label} ({passed}/{total})</div>'
                f'</div>'
            )
        elif name == "hardrule":
            rate = evaluation.case_pass_rate
            passed = total_passed
            total = evaluation.total_cases
            color = EVAL_COLORS[name]
            cards += (
                f'<div class="summary-card">'
                f'<div class="value" style="color:{color}">{rate}%</div>'
                f'<div class="label">{label} ({passed}/{total})</div>'
                f'</div>'
            )

    # ── Bottom 3 dimensions (from first available AI evaluator) ─────────
    bottom_dims_html = ""
    for name in ("deepseek", "chatgpt"):
        ev = ext_evals.get(name)
        if ev and _is_new_format(ev) and ev.get("dimension_averages"):
            bottom_dims_html = _build_bottom_dims_section(ev, EVAL_LABELS[name])
            break

    # ── Top failed items (from hard-rule as baseline) ──────────────────
    top_fail_rows = ""
    sorted_fails = sorted(
        evaluation.item_fail_counts.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:10]
    for item_id, count in sorted_fails:
        if count == 0:
            continue
        desc, cat = CHECKLIST.get(item_id, (item_id, ""))
        rate = round((1 - count / evaluation.total_cases) * 100, 1) if evaluation.total_cases else 100
        top_fail_rows += (
            f"<tr><td>{item_id}</td><td>{desc}</td><td>{cat}</td>"
            f"<td style='font-weight:700;color:var(--fail)'>{rate}%</td>"
            f"<td>{count}/{evaluation.total_cases}</td></tr>"
        )

    # ── Per-requirement blocks ─────────────────────────────────────────
    req_blocks = []

    for req in data:
        req_key = req["requirement_key"]
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
            eval_panel = _build_eval_panel(evaluation, ext_evals, req_key, ci_idx)

            # Steps table
            steps_rows = ""
            for s in case["steps"]:
                exp_display = s["expected"] if s["expected"] else '<span style="color:#ef4444;font-style:italic">null</span>'
                steps_rows += f'<tr><td style="text-align:center;color:#888">{s["order"]}</td><td>{s["action"]}</td><td>{exp_display}</td></tr>'

            case_blocks.append(f"""
        <div class="case-block">
          <div class="case-main">
            <h4 style="margin:0 0 6px 0">Case {ci_idx + 1} — {case["title"]}</h4>
            <p style="margin:4px 0"><b>Related Requirement:</b> {case.get("related_requirement", "")}</p>
            <p style="margin:4px 0"><b>Objective:</b> {case["objective"]}</p>
            <p style="margin:4px 0"><b>Precondition:</b> {case["precondition"]}</p>
            <table style="width:100%;border-collapse:collapse;margin:8px 0;font-size:0.85rem">
              <thead><tr style="background:#f5f5f5"><th style="width:40px;text-align:center">#</th><th style="width:45%">Action</th><th>Expected Result</th></tr></thead>
              <tbody>{steps_rows}</tbody>
            </table>
            <p style="margin:4px 0"><b>Postcondition:</b> {case["postcondition"]}</p>
          </div>
          <div class="case-eval">
            {eval_panel}
          </div>
        </div>""")

        req_blocks.append(f"""
    <div style="border:2px solid #2563eb; border-radius:8px; padding:18px; margin-bottom:24px; page-break-inside:avoid">
      <h2 style="margin:0 0 4px 0;color:#2563eb">{req_key}</h2>
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

    # ── Build HTML ─────────────────────────────────────────────────────
    pass_rate = evaluation.case_pass_rate
    model_names = ", ".join(
        f"{EVAL_LABELS[n]}" for n in ext_evals if n != "hardrule"
    ) or "none"

    top_fail_html_section = ""
    if top_fail_rows:
        top_fail_html_section = f"""
<h2>失败最多的检查项（硬规则）</h2>
<table>
  <tr><th>#</th><th>检查项</th><th>分类</th><th>通过率</th><th>影响范围</th></tr>
  {top_fail_rows}
</table>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BMS Test Cases — Round {round_num} — Testcase Agent</title>
<style>
  :root {{ --pass: #22c55e; --fail: #ef4444; --warn: #f59e0b; }}
  body {{ font-family: system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 24px; color: #111; line-height: 1.5; background: #fafafa; }}
  h1 {{ color: #2563eb; }}
  h2 {{ margin-top: 24px; }}
  footer {{ color: #888; font-size: 0.8rem; margin-top: 32px; text-align: center; }}
  @media print {{ body {{ background: #fff; }} }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border-bottom: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
  .summary {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }}
  .summary-card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 14px; text-align: center; }}
  .summary-card .value {{ font-size: 1.8rem; font-weight: 700; }}
  .summary-card .label {{ color: #888; font-size: 0.82rem; margin-top: 2px; }}

  /* Two-column case layout */
  .case-block {{ display: flex; gap: 16px; border: 1px solid #ddd; border-radius: 6px; padding: 14px; margin-bottom: 10px; page-break-inside: avoid; }}
  .case-main {{ flex: 1 1 65%; min-width: 0; }}
  .case-eval {{ flex: 0 0 320px; max-width: 380px; }}

  /* Evaluation panel */
  .eval-section {{ background: #f8f9fa; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; margin-bottom: 8px; font-size: 0.82rem; }}
  .eval-header {{ border-left: 3px solid #6366f1; padding: 2px 0 2px 8px; margin-bottom: 6px; }}
  .eval-header.muted {{ border-left-color: #ccc; }}
  .eval-all-pass {{ color: #16a34a; font-weight: 600; font-size: 0.8rem; padding: 2px 8px; }}
  .eval-subtitle {{ font-weight: 700; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin: 4px 0 2px; }}
  .eval-subtitle:has(+ .eval-item) {{ color: #ef4444; }}
  .eval-items {{ margin: 2px 0; }}
  .eval-items.warn .eval-subtitle {{ color: #f59e0b; }}
  .eval-item {{ margin: 2px 0; padding: 3px 6px; background: #fff; border-radius: 3px; border: 1px solid #f0f0f0; }}
  .eval-item-id {{ font-family: monospace; font-weight: 700; font-size: 0.75rem; padding: 1px 4px; border-radius: 2px; }}
  .eval-item-id.fail {{ background: #fecaca; color: #991b1b; }}
  .eval-item-id.warn {{ background: #fef3c7; color: #92400e; }}
  .eval-item-desc {{ font-size: 0.75rem; color: #555; }}
  .eval-note {{ font-size: 0.72rem; color: #ef4444; margin-top: 1px; padding-left: 4px; border-left: 2px solid #fca5a5; }}

  /* Dimension scores */
  .dim-scores {{ display: flex; flex-direction: column; gap: 4px; }}
  .dim-row {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; padding: 3px 6px; background: #fff; border-radius: 3px; border: 1px solid #f0f0f0; }}
  .dim-label {{ font-size: 0.72rem; color: #888; min-width: 100px; }}
  .dim-score {{ font-size: 0.85rem; font-weight: 700; min-width: 20px; }}
  .dim-note {{ font-size: 0.7rem; color: #666; flex-basis: 100%; padding-left: 4px; border-left: 2px solid #e5e7eb; }}
</style>
</head>
<body>
<h1>BMS HIL Test Cases — Round {round_num}</h1>
<p style="color:#888">Generated by Testcase Agent — {datetime.now().strftime("%Y-%m-%d %H:%M")} | AI evaluators: {model_names}</p>

<div class="summary">
  <b>Case Summary:</b> {evaluation.total_cases} total |
  <span style="color:#16a34a"><b>{total_passed} PASS</b></span> |
  <span style="color:#ef4444"><b>{total_failed} FAIL</b></span> |
  Hard-rule pass rate: <b>{pass_rate}%</b>
</div>

<h2>Evaluator Scores</h2>
<div class="summary-grid">
  {cards}
</div>

{bottom_dims_html}

{top_fail_html_section}

<h2>Test Cases</h2>
{"".join(req_blocks)}

<footer>Generated with Testcase Agent — prompt optimization run</footer>
</body>
</html>"""

    report_path = round_dir / "cases_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"Round {round_num}: {total_passed}P / {total_failed}F ({pass_rate}%) -> {report_path}")
    return pass_rate


def main():
    run_dir = Path("optimization_runs/run_20260518_233620")
    for rn in range(1, 6):
        generate_round_html(run_dir / f"round_0{rn}", rn)


if __name__ == "__main__":
    main()
