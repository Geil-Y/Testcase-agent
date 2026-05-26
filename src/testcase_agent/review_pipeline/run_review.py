# DEBUG SCRIPT — temporary, do not rely on in production
"""一次性调试脚本：跳过人工审批，用 OLLAMA 真实模型跑完整 pipeline。

Usage: python -m testcase_agent.review_pipeline.run_review

从 prompt_eval_v1.json 取 5 条需求，所有产物放在同一个时间戳 run 目录。
  LLM-A → auto-approve → validate → LLM-B → auto-approve → validate → LLM-C → evaluate
最后生成二级菜单的统一 review_report.html。
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from testcase_agent.config import get_settings
from testcase_agent.provider.factory import create_provider
from testcase_agent.review_pipeline.artifacts.io import read_json, write_json

# ── Config ──────────────────────────────────────────────────────────────────────

REQUIREMENT_KEYS = [
    "REQ-BMS-OVP-009",  # complete_information_baseline
    "REQ-BMS-OVP-001",  # threshold_timing_boundary_cases
    "REQ-BMS-STM-005",  # missing_information_traps
    "REQ-BMS-THM-007",  # multi_branch_and_multi_mode_cases
    "REQ-BMS-FLT-001",  # state_observation_and_diagnostic_cases
]

REQUIREMENTS_SOURCE = Path("optimization_runs/requirement_sets/prompt_eval_v1.json")
OUT_ROOT = Path("reviews")

# ── Helpers ─────────────────────────────────────────────────────────────────────

def _find_requirement(key: str) -> dict:
    data = read_json(str(REQUIREMENTS_SOURCE))
    for entry in data.get("entries", []):
        if entry["requirement_key"] == key:
            return entry
    raise KeyError(f"Requirement {key} not found in {REQUIREMENTS_SOURCE}")


def _make_run_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    existing = sorted([d for d in OUT_ROOT.iterdir() if d.is_dir() and d.name.startswith(ts[:8])])
    seq = len(existing) + 1
    run_dir = OUT_ROOT / f"{ts}_run_{seq:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


# ── Stage helpers: swap files in/out for per-requirement pipeline calls ─────────

_STAGE_FILES = [
    "clarification_review.json",
    "clarification_review.html",
    "clarified_test_basis.json",
    "case_intent_review.json",
    "case_intent_review.html",
    "approved_case_plan.json",
    "generated_cases.json",
    "evaluation_results.json",
    "evaluation_summary.json",
]


def _stash(run_dir: Path, key: str) -> None:
    """Rename stage outputs to key-suffixed versions."""
    for name in _STAGE_FILES:
        p = run_dir / name
        if p.exists():
            shutil.move(str(p), run_dir / f"{name.replace('.json', '')}_{key}.json" if name.endswith(".json") else f"{name.replace('.html', '')}_{key}.html")


def _unstash(run_dir: Path, key: str, names: list[str]) -> None:
    """Copy key-suffixed files back to the names expected by pipeline stages."""
    for name in names:
        suffix = f"{name.replace('.json', '')}_{key}.json" if name.endswith(".json") else f"{name.replace('.html', '')}_{key}.html"
        src = run_dir / suffix
        if src.exists():
            shutil.copy2(str(src), run_dir / name)


# ── Auto-approve ────────────────────────────────────────────────────────────────

def _auto_approve_clarification(path: Path) -> None:
    data = read_json(str(path))
    for dec in data.get("decisions", []):
        conf = dec.get("confidence_before_review")
        dec["decision"] = "approve"
        dec["reason_codes"] = []
        dec["reason_text"] = "DEBUG: auto-approved" if (conf is not None and conf < 0.4) else ""
        dec["clarified_value"] = ""
        dec.pop("edited_content", None)
    write_json(path, data)


def _auto_approve_intent(path: Path) -> None:
    data = read_json(str(path))
    for dec in data.get("decisions", []):
        conf = dec.get("confidence_before_review")
        dec["decision"] = "approve"
        dec["reason_codes"] = []
        dec["reason_text"] = "DEBUG: auto-approved" if (conf is not None and conf < 0.4) else ""
        dec["revised_intent_text"] = ""
        dec["merge_target_id"] = ""
        dec["split_children"] = []
    write_json(path, data)


# ── Orchestration ───────────────────────────────────────────────────────────────

def run_one(key: str, provider, run_dir: Path, tmp_input: Path) -> dict:
    """Run full pipeline for one requirement within the shared run_dir. Returns summary dict."""
    from testcase_agent.review_pipeline.stages.decompose_requirement import prepare_clarification_review
    from testcase_agent.review_pipeline.stages.validate_clarification import validate_clarification_review
    from testcase_agent.review_pipeline.stages.plan_case_intents import prepare_intent_review
    from testcase_agent.review_pipeline.stages.validate_case_intent import validate_case_intent_review
    from testcase_agent.review_pipeline.stages.write_cases import generate_cases
    from testcase_agent.review_pipeline.stages.evaluate import evaluate_run

    result = {"key": key}

    # Stage 1: LLM-A decompose → clarification_review.json + .html
    try:
        review = prepare_clarification_review(str(tmp_input), str(run_dir), provider=provider)
        result["facts"] = len(review.decomposition.facts)
        result["ambiguities"] = len(review.decomposition.ambiguities)
        result["stage1"] = "OK"
    except Exception as e:
        result["stage1"] = f"FAIL: {e}"
        result["stage2"] = result["stage3"] = result["stage4"] = result["stage5"] = "SKIP"
        _stash(run_dir, key)
        return result
    _stash(run_dir, key)

    # Auto-approve + validate → clarified_test_basis.json
    try:
        _unstash(run_dir, key, ["clarification_review.json"])
        _auto_approve_clarification(run_dir / "clarification_review.json")
        vr, basis = validate_clarification_review(str(run_dir / "clarification_review.json"))
        _stash(run_dir, key)
        if basis and basis.blocked:
            result["stage2"] = "BLOCKED"
            result["stage3"] = result["stage4"] = result["stage5"] = "SKIP"
            _clean_stage_temp(run_dir)
            return result
        result["stage2"] = "OK"
    except Exception as e:
        result["stage2"] = f"FAIL: {e}"
        result["stage3"] = result["stage4"] = result["stage5"] = "SKIP"
        _clean_stage_temp(run_dir)
        return result
    _clean_stage_temp(run_dir)

    # Stage 3: LLM-B plan intents → case_intent_review.json + .html
    try:
        _unstash(run_dir, key, ["clarified_test_basis.json", "clarification_review.json"])
        ir = prepare_intent_review(str(run_dir), provider=provider)
        result["intents"] = len(ir.plan.intents)
        _stash(run_dir, key)
        if ir.plan.planning_blocked:
            result["stage3"] = "BLOCKED"
            result["stage4"] = result["stage5"] = "SKIP"
            _clean_stage_temp(run_dir)
            return result
        result["stage3"] = "OK"
    except Exception as e:
        result["stage3"] = f"FAIL: {e}"
        result["stage4"] = result["stage5"] = "SKIP"
        _clean_stage_temp(run_dir)
        return result
    _clean_stage_temp(run_dir)

    # Auto-approve + validate case intents → approved_case_plan.json
    try:
        _unstash(run_dir, key, ["case_intent_review.json"])
        _auto_approve_intent(run_dir / "case_intent_review.json")
        vr2, plan = validate_case_intent_review(str(run_dir / "case_intent_review.json"))
        result["approved"] = len(plan.approved_intents) if plan else 0
        _stash(run_dir, key)
        result["stage4"] = "OK"
    except Exception as e:
        result["stage4"] = f"FAIL: {e}"
        result["stage5"] = "SKIP"
        _clean_stage_temp(run_dir)
        return result
    _clean_stage_temp(run_dir)

    # Stage 5: LLM-C generate cases → generated_cases.json
    try:
        _unstash(run_dir, key, ["approved_case_plan.json", "clarified_test_basis.json"])
        case_set = generate_cases(str(run_dir), provider=provider)
        result["cases"] = len(case_set.cases)
        _stash(run_dir, key)
        result["stage5"] = "OK"
    except Exception as e:
        result["stage5"] = f"FAIL: {e}"
        _clean_stage_temp(run_dir)
        return result
    _clean_stage_temp(run_dir)

    # Stage 6: Evaluate → evaluation_results.json + evaluation_summary.json
    try:
        _unstash(run_dir, key, ["generated_cases.json"])
        evaluate_run(str(run_dir))
        _stash(run_dir, key)
        summary = read_json(str(run_dir / f"evaluation_summary_{key}.json"))
        result["pass_rate"] = f"{summary['pass_rate']:.0%}"
        result["eval_ok"] = summary["passed"]
        result["eval_total"] = summary["total_cases"]
    except Exception as e:
        result["eval_ok"] = 0
        result["eval_total"] = 0
        result["eval_error"] = str(e)
    _clean_stage_temp(run_dir)

    return result


def _clean_stage_temp(run_dir: Path) -> None:
    """Remove any remaining un-stashed stage files to avoid cross-contamination."""
    for name in _STAGE_FILES:
        p = run_dir / name
        if p.exists():
            p.unlink()


# ── Batch Report ────────────────────────────────────────────────────────────────

def _render_batch_report(run_dir: Path, results: list[dict], req_entries: dict[str, dict]) -> str:
    rows = ""
    details = ""
    for i, r in enumerate(results):
        key = r["key"]
        entry = req_entries.get(key, {})
        bucket = entry.get("evaluation_bucket", "")
        facts = r.get("facts", "-")
        ambs = r.get("ambiguities", "-")
        intents = r.get("intents", "-")
        cases = r.get("cases", "-")
        ev = f"{r.get('eval_ok', '?')}/{r.get('eval_total', '?')}" if r.get("eval_ok") is not None else r.get("eval_error", "-")
        s1 = _short(r.get("stage1", ""))
        s2 = _short(r.get("stage2", ""))
        s3 = _short(r.get("stage3", ""))
        s4 = _short(r.get("stage4", ""))
        s5 = _short(r.get("stage5", ""))

        rows += f"""
        <tr class="summary-row" onclick="toggleDetail('detail-{i}')">
          <td class="mono">{_esc(key)}</td>
          <td>{_esc(bucket)}</td>
          <td>{s1}/{s2}/{s3}/{s4}/{s5}</td>
          <td style="text-align:center">{facts}</td>
          <td style="text-align:center">{ambs}</td>
          <td style="text-align:center">{intents}</td>
          <td style="text-align:center">{cases}</td>
          <td style="text-align:center">{ev}</td>
        </tr>"""

        details += _render_requirement_detail(i, key, run_dir)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Batch Review Report — {_esc(run_dir.name)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; color: #222; }}
  h1 {{ border-bottom: 3px solid #1565c0; padding-bottom: 8px; }}
  h2 {{ background: #e3f2fd; padding: 8px 12px; border-left: 5px solid #1565c0; margin-top: 24px; cursor: pointer; user-select: none; }}
  h2:hover {{ background: #bbdefb; }}
  h3 {{ margin-top: 20px; color: #333; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.9em; }}
  th {{ background: #e0e0e0; text-align: left; padding: 6px 8px; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }}
  tr:hover {{ background: #f5f5f5; }}
  tr.summary-row {{ cursor: pointer; }}
  tr.summary-row:hover {{ background: #e3f2fd; }}
  .badge {{ display: inline-block; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; white-space: nowrap; }}
  .tag {{ display: inline-block; background: #e0e0e0; padding: 1px 6px; border-radius: 3px; font-size: 0.8em; margin: 1px; }}
  code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }}
  .mono {{ font-family: monospace; font-size: 0.85em; }}
  .section-empty {{ color: #9e9e9e; font-style: italic; }}
  .detail-section {{ display: none; margin: 0 0 20px 0; padding: 0 16px; border-left: 3px solid #1565c0; }}
  .detail-section.open {{ display: block; }}
  .case-card {{ background: #f9f9f9; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px; margin: 10px 0; }}
  .case-card h4 {{ margin: 0 0 8px 0; color: #1565c0; }}
  .step {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 4px; padding: 6px 10px; margin: 4px 0; }}
  .step-num {{ display: inline-block; background: #1565c0; color: #fff; border-radius: 50%; width: 22px; height: 22px; text-align: center; line-height: 22px; font-size: 0.8em; margin-right: 8px; }}
  .eval-pass {{ color: #2e7d32; font-weight: bold; }}
  .eval-fail {{ color: #c62828; font-weight: bold; }}
  .skip {{ color: #9e9e9e; }}
  .fail {{ color: #c62828; }}
  .block {{ color: #e65100; }}
  hr {{ margin: 16px 0; border: none; border-top: 1px solid #e0e0e0; }}
</style>
</head>
<body>

<h1>Batch Review Report — {_esc(run_dir.name)}</h1>

<h2 onclick="toggleDetail('summary-table-wrap')">&#9660; Summary ({len(results)} requirements)</h2>
<div id="summary-table-wrap" class="detail-section open">
<table>
  <thead><tr>
    <th>Requirement</th><th>Bucket</th><th>Stages (A/V/B/V/C)</th>
    <th style="text-align:center">Facts</th><th style="text-align:center">Ambiguities</th>
    <th style="text-align:center">Intents</th><th style="text-align:center">Cases</th>
    <th style="text-align:center">Eval</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
</div>

{details}

<script>
function toggleDetail(id) {{
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
}}
</script>
</body></html>"""


def _render_requirement_detail(idx: int, key: str, run_dir: Path) -> str:
    """Render detail section for one requirement by reading its stashed artifacts."""
    parts = []

    # Clarification Review
    cr_path = run_dir / f"clarification_review_{key}.json"
    if cr_path.exists():
        data = read_json(str(cr_path))
        parts.append(_render_clarify_section(data))

    # Clarified Test Basis
    ctb_path = run_dir / f"clarified_test_basis_{key}.json"
    if ctb_path.exists():
        data = read_json(str(ctb_path))
        parts.append(_render_basis_section(data))

    # Case Intent Review
    cir_path = run_dir / f"case_intent_review_{key}.json"
    if cir_path.exists():
        data = read_json(str(cir_path))
        parts.append(_render_intent_section(data))

    # Approved Case Plan
    acp_path = run_dir / f"approved_case_plan_{key}.json"
    if acp_path.exists():
        data = read_json(str(acp_path))
        parts.append(f"""<h3>Approved Case Plan</h3>
        <p>{len(data.get('approved_intents', []))} approved intents</p>""")

    # Generated Cases
    gc_path = run_dir / f"generated_cases_{key}.json"
    if gc_path.exists():
        data = read_json(str(gc_path))
        cases = data if isinstance(data, list) else [data]
        parts.append(_render_cases_section(cases))

    # Evaluation
    ev_path = run_dir / f"evaluation_summary_{key}.json"
    er_path = run_dir / f"evaluation_results_{key}.json"
    if ev_path.exists():
        parts.append(_render_eval_section(ev_path, er_path))

    body = "\n".join(parts) if parts else '<p class="section-empty">No artifacts found</p>'

    return f"""
<h2 onclick="toggleDetail('detail-{idx}')" id="hdetail-{idx}">&#9654; {_esc(key)}</h2>
<div class="detail-section" id="detail-{idx}">
{body}
</div>"""


def _render_clarify_section(data: dict) -> str:
    decomp = data.get("decomposition", {})
    facts = decomp.get("facts", [])
    ambs = decomp.get("ambiguities", [])
    decisions = {d["item_id"]: d for d in data.get("decisions", [])}

    fact_rows = ""
    for f in facts:
        fact_rows += f"""<tr>
          <td class="mono">{_esc(f['item_id'])}</td>
          <td>{_esc(f['fact_text'])}</td>
          <td style="text-align:center">{f.get('confidence', 1.0):.0%}</td>
        </tr>"""

    amb_rows = ""
    for a in ambs:
        dec = decisions.get(a["item_id"], {})
        d = dec.get("decision", "pending")
        sev = a.get("severity", "")
        amb_rows += f"""<tr>
          <td class="mono">{_esc(a['item_id'])}</td>
          <td><code>{_esc(a.get('affected_text', '')[:100])}</code></td>
          <td>{_esc(a.get('ambiguity_type', ''))}</td>
          <td>{_esc(sev)}</td>
          <td><span class="badge" style="background:{_dec_color(d)}">{_esc(d)}</span></td>
          <td style="font-size:0.85em">{_esc(a.get('clarification_question', ''))}</td>
        </tr>"""

    return f"""<h3>Clarification Review</h3>
<h4>Facts ({len(facts)})</h4>
<table><thead><tr><th>ID</th><th>Fact</th><th>Conf</th></tr></thead><tbody>{fact_rows}</tbody></table>
<h4>Ambiguities ({len(ambs)})</h4>
<table><thead><tr><th>ID</th><th>Affected Text</th><th>Type</th><th>Severity</th><th>Decision</th><th>Question</th></tr></thead><tbody>{amb_rows}</tbody></table>"""


def _render_basis_section(data: dict) -> str:
    blocked = data.get("blocked", False)
    reasons = data.get("block_reasons", [])
    ambs = data.get("resolved_ambiguities", [])
    banner = ""
    if blocked:
        rlist = "".join(f"<li>{_esc(r)}</li>" for r in reasons)
        banner = f'<div style="background:#ffcdd2;border:2px solid #c62828;color:#b71c1c;padding:10px;margin:10px 0;"><strong>BLOCKED</strong><ul>{rlist}</ul></div>'

    rows = ""
    for a in ambs:
        rows += f"""<tr>
          <td class="mono">{_esc(a.get('item_id', ''))}</td>
          <td><span class="badge" style="background:{_dec_color(a.get('decision', ''))}">{_esc(a.get('decision', ''))}</span></td>
          <td>{_esc(str(a.get('clarified_value', '')))}</td>
        </tr>"""

    return f"""<h3>Clarified Test Basis</h3>
{banner}
<table><thead><tr><th>Item</th><th>Decision</th><th>Clarified Value</th></tr></thead><tbody>{rows}</tbody></table>"""


def _render_intent_section(data: dict) -> str:
    plan = data.get("plan", {})
    intents = plan.get("intents", [])
    decisions = {d["intent_id"]: d for d in data.get("decisions", [])}
    blocked = plan.get("planning_blocked", False)
    banner = f'<div style="background:#ffcdd2;border:2px solid #c62828;color:#b71c1c;padding:10px;margin:10px 0;"><strong>PLANNING BLOCKED</strong></div>' if blocked else ""

    rows = ""
    for it in intents:
        dec = decisions.get(it["intent_id"], {})
        d = dec.get("decision", "pending")
        rows += f"""<tr>
          <td class="mono">{_esc(it['intent_id'])}</td>
          <td>{_esc(it.get('intent_text', ''))}</td>
          <td><span class="tag">{_esc(it.get('coverage_dimension', ''))}</span></td>
          <td><span class="badge" style="background:{_dec_color(d)}">{_esc(d)}</span></td>
        </tr>"""

    return f"""<h3>Case Intent Review ({len(intents)} intents)</h3>
{banner}
<table><thead><tr><th>ID</th><th>Intent</th><th>Dimension</th><th>Decision</th></tr></thead><tbody>{rows}</tbody></table>"""


def _render_cases_section(cases: list) -> str:
    cards = ""
    for c in cases:
        steps_html = ""
        for s in c.get("steps", []):
            steps_html += f"""<div class="step">
              <span class="step-num">{_esc(str(s.get('step_number', '?')))}</span>
              <strong>Action:</strong> {_esc(s.get('action', ''))}<br>
              <strong>Expected:</strong> {_esc(s.get('expected_result', ''))}
            </div>"""
        cards += f"""<div class="case-card">
          <h4>{_esc(c.get('case_id', '?'))} — {_esc(c.get('title', ''))}</h4>
          <p><strong>Dimension:</strong> <span class="tag">{_esc(c.get('coverage_dimension', ''))}</span></p>
          <p><strong>Objective:</strong> {_esc(c.get('objective', ''))}</p>
          <p><strong>Pre-condition:</strong> {_esc(c.get('pre_condition', ''))}</p>
          {steps_html}
          <p><strong>Post-condition:</strong> {_esc(c.get('post_condition', ''))}</p>
        </div>"""

    return f"""<h3>Generated Cases ({len(cases)})</h3>
{cards}"""


def _render_eval_section(summary_path: Path, results_path: Path) -> str:
    s = read_json(str(summary_path))
    rows = ""
    if results_path.exists():
        results = read_json(str(results_path))
        for r in results:
            cls = "eval-pass" if r.get("passed") else "eval-fail"
            checks_html = ""
            for c in r.get("checks", []):
                icon = "&#10004;" if c.get("passed") else "&#10008;"
                checks_html += f'<li class="{"eval-pass" if c.get("passed") else "eval-fail"}">{icon} {_esc(c.get("rule", ""))}: {_esc(c.get("detail", ""))}</li>'
            rows += f"""<tr class="{cls}">
              <td class="mono">{_esc(r.get('case_id', ''))}</td>
              <td>{_esc(r.get('title', ''))}</td>
              <td><ul style="margin:0;padding-left:16px;font-size:0.85em">{checks_html}</ul></td>
            </tr>"""

    return f"""<h3>Evaluation</h3>
<p>Passed: <strong>{s.get('passed', '?')}/{s.get('total_cases', '?')}</strong> ({s.get('pass_rate', 0):.0%})</p>
<table><thead><tr><th>Case</th><th>Title</th><th>Checks</th></tr></thead><tbody>{rows}</tbody></table>"""


def _dec_color(decision: str) -> str:
    colors = {
        "approve": "#2e7d32", "reject": "#c62828", "revise": "#e65100",
        "merge": "#1565c0", "split": "#6a1b9a", "defer": "#546e7a",
        "clarify": "#e65100", "mark_needs_review": "#f9a825",
        "block": "#c62828", "edit": "#1565c0", "pending": "#b71c1c",
    }
    return colors.get(decision, "#757575")


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _short(status: str) -> str:
    if status == "OK": return "OK"
    if status == "SKIP": return "SKIP"
    if status == "BLOCKED": return "BLOCK"
    if status.startswith("FAIL"): return "FAIL"
    return status[:6]


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    settings = get_settings()
    print(f"Provider: {settings.llm.provider}")
    print(f"Model:    {settings.llm.model_name}")
    print(f"Base URL: {settings.llm.base_url}")
    print(f"Requirements: {len(REQUIREMENT_KEYS)} selected")
    print()

    try:
        provider = create_provider(settings)
    except Exception as e:
        print(f"FATAL: Cannot create provider — {e}")
        print("Is OLLAMA running? Try: ollama serve")
        return 2

    run_dir = _make_run_dir()
    print(f"Run directory: {run_dir}")

    # Write all requirements to input file
    all_reqs = []
    req_entries: dict[str, dict] = {}
    for key in REQUIREMENT_KEYS:
        entry = _find_requirement(key)
        req_entries[key] = entry
        all_reqs.append({
            "requirement_key": entry["requirement_key"],
            "description": entry["description"],
            "function_name": entry.get("function_name", ""),
            "requirement_type": entry.get("requirement_type", ""),
            "supplementary_info": entry.get("supplementary_info", ""),
        })
    all_input = run_dir / "00_requirements.json"
    write_json(all_input, all_reqs)

    results = []
    for i, key in enumerate(REQUIREMENT_KEYS):
        print(f"[{i+1}/{len(REQUIREMENT_KEYS)}] {key} ", end="", flush=True)
        entry = req_entries[key]
        tmp = run_dir / f"_tmp_{key}.json"
        write_json(tmp, [{
            "requirement_key": entry["requirement_key"],
            "description": entry["description"],
            "function_name": entry.get("function_name", ""),
            "requirement_type": entry.get("requirement_type", ""),
            "supplementary_info": entry.get("supplementary_info", ""),
        }])
        try:
            r = run_one(key, provider, run_dir, tmp)
        finally:
            if tmp.exists():
                tmp.unlink()
        results.append(r)
        stages = f"s1={r.get('stage1','?')} s2={r.get('stage2','?')} s3={r.get('stage3','?')} s4={r.get('stage4','?')} s5={r.get('stage5','?')}"
        cases = r.get("cases", 0)
        ev = f"{r.get('eval_ok', '?')}/{r.get('eval_total', '?')}"
        print(f"→ {stages} | cases={cases} | eval={ev}")

    # Generate batch report
    report_path = run_dir / "review_report.html"
    report_path.write_text(_render_batch_report(run_dir, results, req_entries), encoding="utf-8")

    # Summary table
    print()
    print(f"Report: {report_path}")
    print(f"{'Key':<24s} {'S1':<6s} {'S2':<6s} {'S3':<6s} {'S4':<6s} {'S5':<6s} {'Cases':<7s} {'Eval'}")
    print("-" * 85)
    for r in results:
        s1 = _short(r.get("stage1", ""))
        s2 = _short(r.get("stage2", ""))
        s3 = _short(r.get("stage3", ""))
        s4 = _short(r.get("stage4", ""))
        s5 = _short(r.get("stage5", ""))
        cases = str(r.get("cases", "-"))
        ev = f"{r.get('eval_ok', '?')}/{r.get('eval_total', '?')}"
        print(f"{r['key']:<24s} {s1:<6s} {s2:<6s} {s3:<6s} {s4:<6s} {s5:<6s} {cases:<7s} {ev}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
