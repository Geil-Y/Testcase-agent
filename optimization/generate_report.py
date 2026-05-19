"""Generate evaluation HTML report - case-level pass rate as primary metric."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from generate_case_html import (
    CHECKLIST,
    _enrich_req_info,
    evaluate_case,
    evaluate_missing_info_hard_gates,
)


def generate_report(round_dir: Path, round_num: int, max_rounds: int = 5, prev_rate: float | None = None) -> float:
    cases_path = round_dir / "generated_cases.json"
    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    total_cases = 0
    case_failures = []  # list of (case_key, failed_items)
    item_fail_counts = Counter()
    item_warning_counts = Counter()

    for req in data:
        base_info = _enrich_req_info(req)

        for ci_idx, case in enumerate(req["cases"]):
            total_cases += 1
            coverage = ""
            if ci_idx < len(req["analysis"]["case_intents"]):
                coverage = req["analysis"]["case_intents"][ci_idx]["coverage"]

            req_info = dict(base_info)
            req_info["case_coverage"] = coverage
            failed, warnings = evaluate_case(case, req_info, {})
            if failed:
                case_failures.append((f"{req['requirement_key']} :: {case['title'][:60]}", failed))
                for item in failed:
                    item_fail_counts[item] += 1
            for w in warnings:
                item_warning_counts[w] += 1

    # Missing information hard gates
    hard_gate_records = evaluate_missing_info_hard_gates(data)

    total_passed = total_cases - len(case_failures)
    case_pass_rate = round(total_passed / total_cases * 100, 1) if total_cases else 0
    req_count = len(data)

    # Per-item pass rates
    item_data = []
    cat_rates = {
        "1. 结构完整性": [],
        "2. 领域正确性": [],
        "3. NEEDS REVIEW规范": [],
        "4. 步骤质量": [],
        "5. 覆盖维度": [],
        "6. 测试工程深度": [],
    }
    for item_id, (desc, cat) in CHECKLIST.items():
        fail_count = item_fail_counts.get(item_id, 0)
        item_pass_rate = round((1 - fail_count / total_cases) * 100, 1) if total_cases else 100
        status = "pass" if item_pass_rate >= 90 else "fail"
        item_data.append((item_id, desc, cat, item_pass_rate, status, fail_count))
        if cat in cat_rates:
            cat_rates[cat].append(item_pass_rate)

    cat_avg = {}
    for cat, rates in cat_rates.items():
        cat_avg[cat] = round(sum(rates) / len(rates), 1) if rates else 100

    # Build HTML
    overall_color = "#22c55e" if case_pass_rate >= 90 else "#f59e0b" if case_pass_rate >= 70 else "#ef4444"
    improvement_str = "—"
    if prev_rate is not None:
        delta = round(case_pass_rate - prev_rate, 1)
        sign = "+" if delta > 0 else ""
        improvement_str = f"{sign}{delta}%"

    # Category rows
    cat_rows = []
    for name, rate in cat_avg.items():
        color = "#22c55e" if rate >= 90 else "#f59e0b" if rate >= 75 else "#ef4444"
        fill = "pass" if rate >= 90 else "fail"
        cat_rows.append(
            f'<tr><td>{name}</td>'
            f'<td style="color:{color};font-weight:700">{rate}%</td>'
            f'<td>90%</td>'
            f'<td><div class="progress-bar" style="width:120px"><div class="progress-fill {fill}" style="width:{rate}%"></div></div></td></tr>'
        )

    # Item rows
    item_rows = []
    for item_id, desc, cat, rate, status, fail_count in item_data:
        badge = "pass" if status == "pass" else "fail"
        stext = "PASS" if status == "pass" else "FAIL"
        color = "var(--pass)" if status == "pass" else "var(--fail)"
        item_rows.append(
            f'<tr><td>{item_id}</td><td>{desc}</td><td>{cat}</td>'
            f'<td style="font-weight:700;color:{color}">{rate}%</td>'
            f'<td><span class="badge {badge}">{stext}</span></td>'
            f'<td>{fail_count} cases failed</td></tr>'
        )

    # Top failures
    top_fail_items = sorted(item_data, key=lambda x: x[4])[:12]  # lowest pass rate
    top_rows = []
    for item_id, desc, cat, rate, status, fail_count in top_fail_items:
        if fail_count == 0:
            continue
        top_rows.append(
            f'<tr><td>{item_id}</td><td>{desc}</td>'
            f'<td style="color:var(--fail);font-weight:700">{rate}%</td>'
            f'<td>{fail_count}/{total_cases} cases</td></tr>'
        )
    top_fail_html = "\n".join(top_rows[:10])

    # Failed case samples
    failed_case_html = ""
    for case_key, failed_items in case_failures[:8]:
        items_str = ", ".join(failed_items)
        failed_case_html += f'<tr><td>{case_key}</td><td style="color:var(--fail)">{len(failed_items)}</td><td style="font-size:0.82rem">{items_str}</td></tr>'

    status_text = "达标" if case_pass_rate >= 90 else "未达标"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>评估报告 — Round {round_num} / {max_rounds} — Testcase Agent</title>
<style>
  :root {{
    --pass: #22c55e; --fail: #ef4444; --warn: #f59e0b;
    --bg: #f8fafc; --card: #ffffff; --border: #e2e8f0;
    --text: #1e293b; --muted: #64748b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.75rem; margin-bottom: 4px; }}
  h2 {{ font-size: 1.25rem; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 2px solid var(--border); }}
  .subtitle {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 24px; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }}
  .summary-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; text-align: center; }}
  .summary-card .value {{ font-size: 2rem; font-weight: 700; }}
  .summary-card .label {{ color: var(--muted); font-size: 0.85rem; margin-top: 4px; }}
  .progress-bar {{ height: 24px; background: #e2e8f0; border-radius: 12px; overflow: hidden; margin: 8px 0; }}
  .progress-fill {{ height: 100%; border-radius: 12px; }}
  .progress-fill.pass {{ background: var(--pass); }}
  .progress-fill.fail {{ background: var(--fail); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 16px; font-size: 0.88rem; }}
  th, td {{ padding: 10px 14px; text-align: left; }}
  th {{ background: #f1f5f9; font-weight: 600; border-bottom: 2px solid var(--border); }}
  td {{ border-bottom: 1px solid var(--border); }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 600; }}
  .badge.pass {{ background: #dcfce7; color: #166534; }}
  .badge.fail {{ background: #fecaca; color: #991b1b; }}
  .note {{ background: #fefce8; border-left: 4px solid var(--warn); border-radius: 4px; padding: 12px 16px; margin: 16px 0; font-size: 0.9rem; }}
</style>
</head>
<body>
<div class="container">

<h1>BMS HIL 测试用例质量评估报告</h1>
<p class="subtitle">
  Round <strong>{round_num} / {max_rounds}</strong>
  | Cases: <strong>{total_cases}</strong>
  | Reqs: <strong>{req_count}</strong>
  | Time: <strong>{datetime.now().strftime("%Y-%m-%d %H:%M")}</strong>
</p>

<div class="note">
  <strong>评估方式:</strong> Case 级通过率 = CHECKLIST 项全部 PASS 的 case 数 / 总 case 数。
  一个 case 只要有一项不通过即算 FAIL。WARNING 项不计入通过率。
</div>

<div class="summary-grid">
  <div class="summary-card">
    <div class="value" style="color:{overall_color}">{case_pass_rate}%</div>
    <div class="label">Case 级通过率 (目标 ≥90%)</div>
  </div>
  <div class="summary-card">
    <div class="value">{total_passed} / {total_cases}</div>
    <div class="label">全 PASS case / 总 case</div>
  </div>
  <div class="summary-card">
    <div class="value">{len(case_failures)}</div>
    <div class="label">有缺陷的 case</div>
  </div>
  <div class="summary-card">
    <div class="value">{improvement_str}</div>
    <div class="label">较上轮变化</div>
  </div>
</div>

<div class="progress-bar">
  <div class="progress-fill {"pass" if case_pass_rate>=90 else "fail"}" style="width:{max(case_pass_rate, 2)}%"></div>
</div>
<p style="text-align:center;color:var(--muted);font-size:0.85rem;margin-top:4px">
  目标: 90% | {status_text} ({case_pass_rate}% {"≥" if case_pass_rate>=90 else "<"} 90%)
</p>

<h2>检查项通过率（参考）</h2>
<table>
  <tr><th>分类</th><th>Item-Avg 通过率</th><th>目标</th><th></th></tr>
  {"".join(cat_rows)}
</table>

<h2>失败最多的检查项</h2>
<table>
  <tr><th>#</th><th>检查项</th><th>通过率</th><th>影响范围</th></tr>
  {top_fail_html}
</table>

<h2>全部检查项</h2>
<table>
  <tr><th>#</th><th>检查项</th><th>分类</th><th>通过率</th><th>状态</th><th>失败数</th></tr>
  {"".join(item_rows)}
</table>

{_render_warning_items(item_warning_counts, total_cases)}

<h2>失败 case 样例</h2>
<table>
  <tr><th>Case</th><th>失败项数</th><th>失败项</th></tr>
  {failed_case_html}
</table>

<h2>Missing Information Hard Gates</h2>
<p style="color:var(--muted);font-size:0.88rem;margin-bottom:8px">
  比较 Prompt Evaluation Set 的 expected_missing_categories 与 LLM#1 实际输出的 missing_info_items。
  仅适用于通过 <code>--requirement-set</code> 生成的 run。
</p>
{_render_hard_gate_section(hard_gate_records)}

</div>
</body>
</html>"""

    report_path = round_dir / "evaluation_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"Round {round_num}: case_pass_rate={case_pass_rate}% ({total_passed}/{total_cases}) -> {report_path}")
    return case_pass_rate


def _render_hard_gate_section(records: list[dict]) -> str:
    """Render the Missing Information Hard Gates HTML."""
    if not records:
        return "<p style='color:var(--muted)'>无 Prompt Evaluation Set 数据。使用 <code>--requirement-set</code> 生成 run 后可显示缺失信息硬门禁评估。</p>"

    rows: list[str] = []
    for rec in records:
        req_key = rec["requirement_key"]
        bucket = rec["evaluation_bucket"]
        expected = ", ".join(rec["expected_missing_categories"]) or "—"
        actual = ", ".join(rec["actual_missing_categories"]) or "—"
        missing = ", ".join(rec["missing_from_actual"])
        extra = ", ".join(rec["extra_in_actual"])
        item_ids = ", ".join(rec.get("item_ids", [])) or "—"

        severity = ""
        issue_color = "var(--muted)"
        if rec["missing_from_actual"]:
            severity = "⚠️ LLM#1 遗漏"
            issue_color = "var(--fail)"
        elif rec["extra_in_actual"]:
            severity = "ℹ️ LLM#1 多报"
            issue_color = "var(--warn)"
        elif rec["case_issues"]:
            severity = "⚠️ case 缺 [NEEDS REVIEW]"
            issue_color = "var(--fail)"
        else:
            severity = "✅ 匹配"
            issue_color = "var(--pass)"

        case_detail = ""
        for ci in rec["case_issues"]:
            item_id = ci.get("item_id", "")
            case_detail += (
                f'<div style="font-size:0.8rem;color:var(--fail);margin-left:16px">'
                f'  [{item_id}] {ci["case_title"][:80]} — {ci["issue"]}'
                f'  ({", ".join(ci["missing_categories"])})'
                f'</div>'
            )

        rows.append(f"""<tr>
          <td>{req_key}</td>
          <td style="font-size:0.82rem">{bucket}</td>
          <td style="font-size:0.85rem">{expected}</td>
          <td style="font-size:0.85rem">{actual}</td>
          <td style="color:{issue_color};font-weight:600">{severity}</td>
          <td style="font-size:0.82rem">{item_ids}</td>
          <td style="font-size:0.82rem">{case_detail if case_detail else '—'}</td>
        </tr>""")

    return f"""<table>
      <tr>
        <th>Requirement</th>
        <th>Bucket</th>
        <th>Expected Missing</th>
        <th>Actual Missing</th>
        <th>Severity</th>
        <th>Item IDs</th>
        <th>Case Issues</th>
      </tr>
      {"".join(rows)}
    </table>"""


def _render_warning_items(warning_counts: Counter, total_cases: int) -> str:
    """Render WARNING-only checklist items that do not count toward pass/fail."""
    if not warning_counts:
        return ""

    rows: list[str] = []
    for item_id in sorted(warning_counts.keys()):
        count = warning_counts[item_id]
        desc, cat = CHECKLIST.get(item_id, (item_id, ""))
        rows.append(
            f"<tr><td>{item_id}</td><td>{desc}</td><td>{cat}</td>"
            f"<td>{count}</td><td style='color:var(--warn);font-weight:600'>WARNING</td></tr>"
        )

    return f"""
    <h2>WARNING 检查项</h2>
    <p style="color:var(--muted);font-size:0.88rem;margin-bottom:8px">
      WARNING 项不计入 case pass/fail。以下展示触发次数供审阅。
    </p>
    <table>
      <tr><th>#</th><th>检查项</th><th>分类</th><th>触发次数</th><th>级别</th></tr>
      {"".join(rows)}
    </table>"""


def main():
    run_dir = Path("optimization_runs/run_20260518_233620")
    prev_rate = None
    for rn in range(1, 6):
        rd = run_dir / f"round_0{rn}"
        if (rd / "generated_cases.json").exists():
            prev_rate = generate_report(rd, rn, 5, prev_rate)


if __name__ == "__main__":
    main()
