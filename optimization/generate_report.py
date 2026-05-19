"""Generate evaluation HTML report - case-level pass rate as primary metric."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from generate_case_html import evaluate_case, CHECKLIST


def generate_report(round_dir: Path, round_num: int, max_rounds: int = 5, prev_rate: float | None = None) -> float:
    cases_path = round_dir / "generated_cases.json"
    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    total_cases = 0
    case_failures = []  # list of (case_key, failed_items)
    item_fail_counts = Counter()

    for req in data:
        signals = req["analysis"]["signals"]
        thresholds = req["analysis"].get("thresholds", [])
        timing = [t for t in req.get("analysis", {}).get("timing", []) if t.strip().lower() != "none found"]
        missing_info = req.get("analysis", {}).get("missing_critical_info", [])

        for ci_idx, case in enumerate(req["cases"]):
            total_cases += 1
            coverage = ""
            if ci_idx < len(req["analysis"]["case_intents"]):
                coverage = req["analysis"]["case_intents"][ci_idx]["coverage"]

            req_info = {
                "signals": signals,
                "thresholds": thresholds,
                "timing": timing,
                "missing_critical_info": missing_info,
                "case_coverage": coverage,
                "requirement_description": req.get("description", ""),
                "supplementary_info": req.get("supplementary_info", ""),
            }
            failed = evaluate_case(case, req_info, {})
            if failed:
                case_failures.append((f"{req['requirement_key']} :: {case['title'][:60]}", failed))
                for item in failed:
                    item_fail_counts[item] += 1

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
  <strong>评估方式:</strong> Case 级通过率 = 35 项 checklist 全部 PASS 的 case 数 / 总 case 数。
  一个 case 只要有一项不通过即算 FAIL。
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

<h2>失败 case 样例</h2>
<table>
  <tr><th>Case</th><th>失败项数</th><th>失败项</th></tr>
  {failed_case_html}
</table>

</div>
</body>
</html>"""

    report_path = round_dir / "evaluation_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"Round {round_num}: case_pass_rate={case_pass_rate}% ({total_passed}/{total_cases}) -> {report_path}")
    return case_pass_rate


def main():
    run_dir = Path("optimization_runs/run_20260518_233620")
    prev_rate = None
    for rn in range(1, 6):
        rd = run_dir / f"round_0{rn}"
        if (rd / "generated_cases.json").exists():
            prev_rate = generate_report(rd, rn, 5, prev_rate)


if __name__ == "__main__":
    main()
