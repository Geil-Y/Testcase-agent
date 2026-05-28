"""Unified review report generator with inline editing.

Reads all pipeline artifacts from a run directory and produces a single
self-contained review_report.html. Sections 2 (Clarification Review) and
4 (Case Intent Review) are editable — changes write back to the embedded
JSON and can be saved via download button.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from testcase_agent.review_pipeline.confidence.engine import routing_for_confidence, routing_label

_CLARIFICATION_DECISIONS = ["approve", "clarify", "mark_needs_review", "block", "edit"]
_INTENT_DECISIONS = ["approve", "reject", "revise", "merge", "split", "defer"]
_ALL_REASON_CODES = [
    "supported_by_requirement", "safe_to_generate_with_marker",
    "valid_timing_maturity_case", "matches_prior_review_pattern",
    "unsupported_by_requirement", "duplicate_expected_behavior",
    "same_acceptance_evidence", "over_split_condition_combination",
    "invented_recovery_or_fault_behavior", "invalid_response_time_negative_case",
    "too_broad_to_verify", "needs_clarification",
]


def render_unified_report(run_dir: Path) -> str:
    run_name = run_dir.name
    sections: list[str] = []

    req_path = run_dir / "00_requirements.json"
    if req_path.exists():
        sections.append(_render_requirements(req_path))

    cr_path = run_dir / "clarification_review.json"
    cr_data = None
    if cr_path.exists():
        cr_data = _load_json(cr_path)
        sections.append(_render_clarification_section(cr_data))

    ctb_path = run_dir / "clarified_test_basis.json"
    if ctb_path.exists():
        sections.append(_render_basis_section(ctb_path))

    cir_path = run_dir / "case_intent_review.json"
    cir_data = None
    if cir_path.exists():
        cir_data = _load_json(cir_path)
        sections.append(_render_intent_section(cir_data))

    acp_path = run_dir / "approved_case_plan.json"
    if acp_path.exists():
        sections.append(_render_approved_plan_section(acp_path))

    gc_path = run_dir / "generated_cases.json"
    if gc_path.exists():
        sections.append(_render_cases_section(gc_path))

    ev_path = run_dir / "evaluation_summary.json"
    ev_detail_path = run_dir / "evaluation_results.json"
    if ev_path.exists():
        sections.append(_render_evaluation_section(ev_path, ev_detail_path))

    body = "\n".join(sections)
    data_blocks = _embed_data(cr_data, cir_data)

    return _page(run_name, body, data_blocks)


# ── Data embedding ──────────────────────────────────────────────────────────

def _embed_data(cr_data: dict | None, cir_data: dict | None) -> str:
    parts = []
    if cr_data:
        parts.append(
            f'<script type="application/json" id="clarification-data">'
            f'{_esc(json.dumps(cr_data, ensure_ascii=False))}</script>'
        )
    if cir_data:
        parts.append(
            f'<script type="application/json" id="intent-data">'
            f'{_esc(json.dumps(cir_data, ensure_ascii=False))}</script>'
        )
    return "\n".join(parts)


# ── Section renderers ──────────────────────────────────────────────────────

def _render_requirements(path: Path) -> str:
    data = _load(path)
    if isinstance(data, list):
        reqs = data
    elif isinstance(data, dict):
        reqs = data.get("requirements", [data])
    else:
        reqs = []

    rows = ""
    for r in reqs:
        rows += f"""<tr>
          <td class="mono">{_esc(r.get('requirement_key', ''))}</td>
          <td>{_esc(r.get('function_name', ''))}</td>
          <td>{_esc(r.get('requirement_type', ''))}</td>
          <td>{_esc(str(r.get('description', '')))}</td>
        </tr>"""

    return f"""
<h2 id="requirements">1. Requirements</h2>
<table>
  <thead><tr><th>Key</th><th>Function</th><th>Type</th><th>Description</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""


def _render_clarification_section(data: dict) -> str:
    decomp = data.get("decomposition", {})
    decisions = {d["item_id"]: d for d in data.get("decisions", [])}
    facts = decomp.get("facts", [])
    ambs = decomp.get("ambiguities", [])

    fact_rows = ""
    for f in facts:
        fact_rows += f"""<tr>
          <td class="mono">{_esc(f['item_id'])}</td>
          <td>{_esc(f['fact_text'])}</td>
          <td style="text-align:center">{f.get('confidence', 1.0):.0%}</td>
        </tr>"""

    dec_counts = Counter()
    routing_counts = Counter()
    for a in ambs:
        dec = decisions.get(a["item_id"], {})
        dec_counts[dec.get("decision", "") or "pending"] += 1
        score = _avg_drivers(a.get("confidence_drivers", {}))
        routing_counts[routing_label(score, is_clarification=True)] += 1

    summary = _summary_bar("Ambiguities", len(ambs), routing_counts, dec_counts)

    amb_rows = ""
    for a in ambs:
        did = a["item_id"]
        dec = decisions.get(did, {})
        cur_d = dec.get("decision", "")
        score = _avg_drivers(a.get("confidence_drivers", {}))
        routing = routing_for_confidence(score)
        rec = a.get("recommended_review_decision", "")
        cur_rc = ", ".join(dec.get("reason_codes", []))
        cur_rt = _esc(dec.get("reason_text", ""))
        cur_cv = _esc(dec.get("clarified_value", ""))

        amb_rows += f"""<tr data-item-id="{_esc(did)}" data-type="clarification">
          <td class="mono">{_esc(did)}</td>
          <td><code>{_esc(a.get('affected_text', '')[:120])}</code></td>
          <td><span class="badge" style="background:{routing.color}">{_esc(routing_label(score, is_clarification=True))}</span></td>
          <td class="severity-{_esc(a.get('severity', ''))}">{_esc(a.get('severity', ''))}</td>
          <td><select class="dec-select" data-item="{_esc(did)}" data-type="clarification">
            <option value="">--</option>
            {_options_html(_CLARIFICATION_DECISIONS, cur_d)}
          </select></td>
          <td style="font-size:0.8em;color:#757575">{_esc(rec)}</td>
          <td style="font-size:0.8em">{_esc(a.get('clarification_question', ''))}</td>
        </tr>
        <tr data-item-id="{_esc(did)}" data-type="clarification" class="edit-row">
          <td colspan="7">
            <div class="edit-fields">
              <label>Reason codes: <input type="text" class="rc-input" data-item="{_esc(did)}" data-type="clarification"
                value="{_esc(cur_rc)}" placeholder="comma-separated"
                list="rc-datalist-clarify"></label>
              <label>Reason text: <input type="text" class="rt-input" data-item="{_esc(did)}" data-type="clarification"
                value="{cur_rt}" placeholder="why this decision"></label>
              <label class="cv-label" style="display:{'inline' if cur_d == 'clarify' else 'none'}">Clarified value:
                <input type="text" class="cv-input" data-item="{_esc(did)}" data-type="clarification"
                value="{cur_cv}" placeholder="resolved value"></label>
            </div>
          </td>
        </tr>"""

    return f"""
<h2 id="clarification">2. Clarification Review — <span class="section-badge editable-badge">EDITABLE</span></h2>
<div id="clarification-summary">{summary}</div>
<h3>Facts ({len(facts)})</h3>
<table>
  <thead><tr><th>ID</th><th>Fact</th><th>Conf</th></tr></thead>
  <tbody>{fact_rows}</tbody>
</table>
<h3>Ambiguities ({len(ambs)})</h3>
<table>
  <thead><tr><th>ID</th><th>Affected Text</th><th>Routing</th><th>Severity</th><th>Decision</th><th>Rec</th><th>Question</th></tr></thead>
  <tbody>{amb_rows}</tbody>
</table>
<datalist id="rc-datalist-clarify">
  {''.join(f'<option value="{_esc(c)}">' for c in _ALL_REASON_CODES)}
</datalist>"""


def _render_basis_section(path: Path) -> str:
    data = _load(path)
    blocked = data.get("blocked", False)
    reasons = data.get("block_reasons", [])
    ambs = data.get("resolved_ambiguities", [])

    banner = ""
    if blocked:
        rlist = "".join(f"<li>{_esc(r)}</li>" for r in reasons)
        banner = f'<div class="blocked-banner">BLOCKED<ul>{rlist}</ul></div>'

    rows = ""
    for a in ambs:
        rows += f"""<tr>
          <td class="mono">{_esc(a.get('item_id', ''))}</td>
          <td><span class="badge" style="background:{_decision_color(a.get('decision', ''))}">{_esc(a.get('decision', ''))}</span></td>
          <td>{_esc(a.get('clarified_value', ''))}</td>
          <td class="mono" style="font-size:0.8em">{_esc(', '.join(a.get('reason_codes', [])))}</td>
        </tr>"""

    return f"""
<h2 id="basis">3. Clarified Test Basis</h2>
{banner}
<table>
  <thead><tr><th>Item</th><th>Decision</th><th>Clarified Value</th><th>Reason Codes</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""


def _render_intent_section(data: dict) -> str:
    plan = data.get("plan", {})
    decisions = {d["intent_id"]: d for d in data.get("decisions", [])}
    intents = plan.get("intents", [])
    blocked = plan.get("planning_blocked", False)
    block_reason = plan.get("planning_block_reason", "")

    banner = ""
    if blocked:
        banner = f'<div class="blocked-banner">PLANNING BLOCKED: {_esc(block_reason)}</div>'

    dec_counts = Counter()
    routing_counts = Counter()
    for it in intents:
        dec = decisions.get(it["intent_id"], {})
        dec_counts[dec.get("decision", "") or "pending"] += 1
        routing_counts[routing_label(it.get("confidence_score", 0.5), is_clarification=False)] += 1

    summary = _summary_bar("Intents", len(intents), routing_counts, dec_counts)

    rows = ""
    for it in intents:
        did = it["intent_id"]
        dec = decisions.get(did, {})
        cur_d = dec.get("decision", "")
        routing = routing_for_confidence(it.get("confidence_score", 0.5))
        rec = it.get("recommended_review_decision", "")
        cur_rc = ", ".join(dec.get("reason_codes", []))
        cur_rt = _esc(dec.get("reason_text", ""))
        cur_rev = _esc(dec.get("revised_intent_text", ""))

        rows += f"""<tr data-item-id="{_esc(did)}" data-type="intent">
          <td class="mono">{_esc(did)}</td>
          <td>{_esc(it.get('intent_text', ''))}</td>
          <td><span class="tag">{_esc(it.get('coverage_dimension', ''))}</span></td>
          <td><span class="badge" style="background:{routing.color}">{_esc(routing_label(it.get('confidence_score', 0.5), is_clarification=False))}</span></td>
          <td><select class="dec-select" data-item="{_esc(did)}" data-type="intent">
            <option value="">--</option>
            {_options_html(_INTENT_DECISIONS, cur_d)}
          </select></td>
          <td style="font-size:0.8em;color:#757575">{_esc(rec)}</td>
        </tr>
        <tr data-item-id="{_esc(did)}" data-type="intent" class="edit-row">
          <td colspan="6">
            <div class="edit-fields">
              <label>Reason codes: <input type="text" class="rc-input" data-item="{_esc(did)}" data-type="intent"
                value="{_esc(cur_rc)}" placeholder="comma-separated"
                list="rc-datalist-intent"></label>
              <label>Reason text: <input type="text" class="rt-input" data-item="{_esc(did)}" data-type="intent"
                value="{cur_rt}" placeholder="why this decision"></label>
              <label class="rev-label" style="display:{'inline' if cur_d == 'revise' else 'none'}">Revised text:
                <input type="text" class="rev-input" data-item="{_esc(did)}" data-type="intent"
                value="{cur_rev}" placeholder="revised intent text"></label>
            </div>
          </td>
        </tr>"""

    return f"""
<h2 id="intents">4. Case Intent Review — <span class="section-badge editable-badge">EDITABLE</span></h2>
{banner}
<div id="intent-summary">{summary}</div>
<table>
  <thead><tr><th>ID</th><th>Intent</th><th>Dimension</th><th>Routing</th><th>Decision</th><th>Rec</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<datalist id="rc-datalist-intent">
  {''.join(f'<option value="{_esc(c)}">' for c in _ALL_REASON_CODES)}
</datalist>"""


def _render_approved_plan_section(path: Path) -> str:
    data = _load(path)
    intents = data.get("approved_intents", [])
    trace = data.get("traceability", [])

    rows = ""
    for it in intents:
        rows += f"""<tr>
          <td class="mono">{_esc(it.get('intent_id', ''))}</td>
          <td>{_esc(it.get('intent_text', ''))}</td>
          <td><span class="tag">{_esc(it.get('coverage_dimension', ''))}</span></td>
          <td>{it.get('confidence_score', 0):.0%}</td>
        </tr>"""

    trace_rows = ""
    for t in trace:
        trace_rows += f"""<tr>
          <td class="mono">{_esc(t.get('intent_id', ''))}</td>
          <td><span class="badge" style="background:{_decision_color(t.get('decision', ''))}">{_esc(t.get('decision', ''))}</span></td>
          <td class="mono" style="font-size:0.8em">{_esc(', '.join(t.get('reason_codes', [])))}</td>
        </tr>"""

    return f"""
<h2 id="approved">5. Approved Case Plan</h2>
<p>{len(intents)} approved intents</p>
<table>
  <thead><tr><th>ID</th><th>Intent</th><th>Dimension</th><th>Confidence</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<h3>Traceability</h3>
<table>
  <thead><tr><th>Intent</th><th>Decision</th><th>Reason Codes</th></tr></thead>
  <tbody>{trace_rows}</tbody>
</table>"""


def _render_cases_section(path: Path) -> str:
    data = _load(path)
    if isinstance(data, dict) and "cases" in data:
        cases = data["cases"]
    elif isinstance(data, list):
        cases = data
    else:
        cases = []

    rows = ""
    for c in cases:
        steps = c.get("steps", [])
        steps_html = ""
        for s in steps:
            steps_html += f'<div><strong>A:</strong> {_esc(s.get("action", ""))}</div>'
            steps_html += f'<div><strong>E:</strong> {_esc(s.get("expected_result", ""))}</div>'

        rows += f"""<tr>
          <td class="mono">{_esc(c.get('case_id', ''))}</td>
          <td>{_esc(c.get('title', ''))}</td>
          <td><span class="tag">{_esc(c.get('coverage_dimension', ''))}</span></td>
          <td style="font-size:0.85em">{steps_html}</td>
          <td>{_esc(c.get('post_condition', ''))}</td>
        </tr>"""

    return f"""
<h2 id="cases">6. Generated Cases ({len(cases)})</h2>
<table>
  <thead><tr><th>Case ID</th><th>Title</th><th>Dimension</th><th>Steps</th><th>Post-condition</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""


def _render_evaluation_section(summary_path: Path, detail_path: Path) -> str:
    summary = _load(summary_path)
    details = _load(detail_path) if detail_path.exists() else []

    total = summary.get("total_cases", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    rate = summary.get("pass_rate", 0)

    cls = "summary"
    if failed > 0:
        cls = "summary blocked"
    elif rate < 1.0:
        cls = "summary warn"

    detail_rows = ""
    if isinstance(details, list):
        for d in details:
            detail_rows += f"""<tr>
              <td class="mono">{_esc(d.get('case_id', ''))}</td>
              <td>{_esc(str(d.get('check', '')))}</td>
              <td><span class="badge" style="background:{'#2e7d32' if d.get('passed', True) else '#c62828'}">{'PASS' if d.get('passed', True) else 'FAIL'}</span></td>
              <td style="font-size:0.8em">{_esc(str(d.get('detail', '')))}</td>
            </tr>"""

    return f"""
<h2 id="evaluation">7. Evaluation</h2>
<div class="{cls}">
  <strong>Total:</strong> {total}
  &nbsp;|&nbsp; <strong>Passed:</strong> {passed}
  &nbsp;|&nbsp; <strong>Failed:</strong> {failed}
  &nbsp;|&nbsp; <strong>Pass Rate:</strong> {rate:.0%}
</div>
<table>
  <thead><tr><th>Case ID</th><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
  <tbody>{detail_rows}</tbody>
</table>"""


# ── Helpers ────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _avg_drivers(drivers: dict[str, float]) -> float:
    if not drivers:
        return 0.5
    return sum(drivers.values()) / len(drivers)


def _decision_color(decision: str) -> str:
    colors = {
        "approve": "#2e7d32", "reject": "#c62828", "revise": "#e65100",
        "merge": "#1565c0", "split": "#6a1b9a", "defer": "#546e7a",
        "clarify": "#e65100", "mark_needs_review": "#f9a825",
        "block": "#c62828", "edit": "#1565c0", "pending": "#b71c1c",
    }
    return colors.get(decision, "#757575")


def _options_html(options: list[str], selected: str) -> str:
    return "".join(
        f'<option value="{_esc(o)}" {"selected" if o == selected else ""}>{_esc(o)}</option>'
        for o in options
    )


def _summary_bar(label: str, total: int, routing: Counter, decisions: Counter) -> str:
    cls = "summary"
    if decisions.get("block", 0) > 0:
        cls = "summary blocked"
    elif decisions.get("", 0) > 0 or decisions.get("pending", 0) > 0:
        cls = "summary warn"

    r_parts = " ".join(
        f'<span class="kv">{_esc(label)}={count}</span>'
        for label, count in routing.most_common()
    ) or '<span class="section-empty">none</span>'
    d_parts = " ".join(
        f'<span class="kv {("alert" if k in ("", "pending") else "")}">{_esc(k or "pending")}={c}</span>'
        for k, c in decisions.most_common()
    ) or '<span class="section-empty">none</span>'

    return f"""<div class="{cls}">
  <strong>{label}:</strong> {total} total
  &nbsp;|&nbsp; <strong>Routing:</strong> {r_parts}
  &nbsp;|&nbsp; <strong>Decisions:</strong> {d_parts}
</div>"""


def _kv_list(counter: Counter, alert_key: str = "") -> str:
    parts = []
    for label, count in counter.most_common():
        cls = 'alert' if alert_key and label == alert_key else ''
        parts.append(f'<span class="kv {cls}">{_esc(label)}={count}</span>')
    return " ".join(parts) if parts else '<span class="section-empty">none</span>'


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── Page template ──────────────────────────────────────────────────────────

def _page(run_name: str, body: str, data_blocks: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Review Report — {_esc(run_name)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; color: #222; }}
  h1 {{ border-bottom: 3px solid #1565c0; padding-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }}
  h2 {{ background: #e3f2fd; padding: 8px 12px; border-left: 5px solid #1565c0; margin-top: 32px; }}
  h3 {{ margin-top: 24px; color: #333; }}
  .meta {{ color: #757575; font-size: 0.9em; margin-bottom: 20px; }}
  .summary {{ background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 6px; padding: 10px 14px; margin: 10px 0; font-size: 0.9em; }}
  .summary.warn {{ background: #fff3e0; border-color: #ffcc80; }}
  .summary.blocked {{ background: #ffebee; border-color: #ef9a9a; }}
  .kv {{ display: inline-block; background: #fff; border: 1px solid #bbb; border-radius: 4px; padding: 1px 6px; margin: 2px; white-space: nowrap; font-size: 0.9em; }}
  .kv.alert {{ background: #fff3e0; border-color: #ff9800; font-weight: bold; color: #e65100; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.9em; }}
  th {{ background: #e0e0e0; text-align: left; padding: 6px 8px; position: sticky; top: 0; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }}
  tr:hover {{ background: #f5f5f5; }}
  tr.edit-row {{ background: #fafafa; }}
  tr.edit-row:hover {{ background: #f0f0f0; }}
  tr.edit-row td {{ padding: 4px 8px 8px 8px; }}
  .badge {{ display: inline-block; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; white-space: nowrap; }}
  .tag {{ display: inline-block; background: #e0e0e0; padding: 1px 6px; border-radius: 3px; font-size: 0.8em; margin: 1px; }}
  code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }}
  .section-empty {{ color: #9e9e9e; font-style: italic; }}
  .blocked-banner {{ background: #ffcdd2; border: 2px solid #c62828; color: #b71c1c; padding: 10px 14px; border-radius: 6px; margin: 10px 0; font-weight: bold; }}
  .drivers {{ font-size: 0.85em; color: #616161; }}
  .mono {{ font-family: monospace; font-size: 0.85em; }}
  .section-badge {{ font-size: 0.7em; padding: 2px 8px; border-radius: 4px; vertical-align: middle; }}
  .editable-badge {{ background: #fff3e0; color: #e65100; border: 1px solid #ff9800; }}

  /* Toolbar */
  #toolbar {{ position: sticky; top: 0; z-index: 100; background: #fff; border-bottom: 2px solid #1565c0; padding: 10px 0; margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
  #toolbar button {{ padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 0.9em; }}
  #toolbar .btn-save {{ background: #1565c0; color: #fff; }}
  #toolbar .btn-save:hover {{ background: #0d47a1; }}
  #toolbar .btn-save:disabled {{ background: #90caf9; cursor: not-allowed; }}
  #toolbar .btn-reset {{ background: #e0e0e0; color: #333; }}
  #toolbar .btn-reset:hover {{ background: #bdbdbd; }}
  #toolbar .changed-count {{ color: #e65100; font-weight: bold; }}
  #toolbar .saved-msg {{ color: #2e7d32; font-weight: bold; opacity: 0; transition: opacity 0.3s; }}
  #toolbar .saved-msg.show {{ opacity: 1; }}

  /* Edit controls */
  select.dec-select {{ padding: 3px 6px; border: 1px solid #bbb; border-radius: 3px; font-size: 0.85em; background: #fff; min-width: 130px; }}
  select.dec-select:focus {{ border-color: #1565c0; outline: none; box-shadow: 0 0 0 2px rgba(21,101,192,0.2); }}
  .edit-fields {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
  .edit-fields label {{ font-size: 0.8em; color: #616161; display: flex; align-items: center; gap: 4px; }}
  .edit-fields input[type="text"] {{ padding: 3px 6px; border: 1px solid #ccc; border-radius: 3px; font-size: 0.85em; min-width: 180px; }}
  .edit-fields input[type="text"]:focus {{ border-color: #1565c0; outline: none; box-shadow: 0 0 0 2px rgba(21,101,192,0.2); }}
  .severity-critical {{ color: #c62828; font-weight: bold; }}
  .severity-high {{ color: #e65100; font-weight: bold; }}
  .severity-medium {{ color: #f9a825; }}
  .severity-low {{ color: #757575; }}
</style>
</head>
<body>

<div id="toolbar">
  <span style="font-weight:bold;font-size:1.1em;">Review Report — {_esc(run_name)}</span>
  <span id="changed-indicator" style="display:none"><span id="changed-count" class="changed-count">0</span> unsaved changes</span>
  <button class="btn-save" id="btn-save" disabled onclick="saveChanges()">Save Changes</button>
  <button class="btn-reset" onclick="resetChanges()">Reset</button>
  <span class="saved-msg" id="saved-msg">Saved</span>
</div>

{body}

{data_blocks}

<script>
// ── Edit engine ──────────────────────────────────────────────────────────

const CLARIFY_DECISIONS = {json.dumps(_CLARIFICATION_DECISIONS)};
const INTENT_DECISIONS = {json.dumps(_INTENT_DECISIONS)};
let changedItems = new Set();

// Load embedded data
let clarifyData = null;
let intentData = null;
const clarifyEl = document.getElementById('clarification-data');
const intentEl = document.getElementById('intent-data');
if (clarifyEl) clarifyData = JSON.parse(clarifyEl.textContent);
if (intentEl) intentData = JSON.parse(intentEl.textContent);

// Build decision lookup helpers
function getDecisions(data, type) {{
    if (!data) return {{}};
    const arr = data.decisions || [];
    const map = {{}};
    const key = type === 'clarification' ? 'item_id' : 'intent_id';
    arr.forEach(d => {{ map[d[key]] = d; }});
    return map;
}}

function findDecision(itemId, type) {{
    const data = type === 'clarification' ? clarifyData : intentData;
    const map = getDecisions(data, type);
    return map[itemId] || null;
}}

function updateDecision(itemId, type, field, value) {{
    const data = type === 'clarification' ? clarifyData : intentData;
    if (!data) return;
    let dec = findDecision(itemId, type);
    if (!dec) {{
        const key = type === 'clarification' ? 'item_id' : 'intent_id';
        dec = {{ [key]: itemId, decision: '', reason_codes: [], reason_text: '', clarified_value: '', revised_intent_text: '' }};
        data.decisions.push(dec);
    }}
    dec[field] = value;
    changedItems.add(type + ':' + itemId);
    updateUI();
}}

// Event: decision select changed
document.querySelectorAll('.dec-select').forEach(sel => {{
    sel.addEventListener('change', function() {{
        const itemId = this.dataset.item;
        const type = this.dataset.type;
        updateDecision(itemId, type, 'decision', this.value);

        // Show/hide conditional fields
        const row = document.querySelector('tr.edit-row[data-item-id="' + itemId + '"][data-type="' + type + '"]');
        if (row) {{
            if (type === 'clarification') {{
                const cvLabel = row.querySelector('.cv-label');
                if (cvLabel) cvLabel.style.display = this.value === 'clarify' ? 'inline' : 'none';
            }}
            if (type === 'intent') {{
                const revLabel = row.querySelector('.rev-label');
                if (revLabel) revLabel.style.display = this.value === 'revise' ? 'inline' : 'none';
            }}
        }}
    }});
}});

// Event: reason codes input changed
document.querySelectorAll('.rc-input').forEach(inp => {{
    inp.addEventListener('input', function() {{
        const itemId = this.dataset.item;
        const type = this.dataset.type;
        const codes = this.value.split(',').map(s => s.trim()).filter(Boolean);
        updateDecision(itemId, type, 'reason_codes', codes);
    }});
}});

// Event: reason text input changed
document.querySelectorAll('.rt-input').forEach(inp => {{
    inp.addEventListener('input', function() {{
        const itemId = this.dataset.item;
        const type = this.dataset.type;
        updateDecision(itemId, type, 'reason_text', this.value);
    }});
}});

// Event: clarified value input changed
document.querySelectorAll('.cv-input').forEach(inp => {{
    inp.addEventListener('input', function() {{
        const itemId = this.dataset.item;
        const type = this.dataset.type;
        updateDecision(itemId, type, 'clarified_value', this.value);
    }});
}});

// Event: revised intent text input changed
document.querySelectorAll('.rev-input').forEach(inp => {{
    inp.addEventListener('input', function() {{
        const itemId = this.dataset.item;
        const type = this.dataset.type;
        updateDecision(itemId, type, 'revised_intent_text', this.value);
    }});
}});

// ── Save / Reset ─────────────────────────────────────────────────────────

function saveChanges() {{
    if (clarifyData) {{
        const blob = new Blob([JSON.stringify(clarifyData, null, 2)], {{type: 'application/json'}});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'clarification_review.json';
        a.click();
        URL.revokeObjectURL(url);
    }}
    if (intentData) {{
        setTimeout(() => {{
            const blob = new Blob([JSON.stringify(intentData, null, 2)], {{type: 'application/json'}});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'case_intent_review.json';
            a.click();
            URL.revokeObjectURL(url);
        }}, 200);
    }}
    changedItems.clear();
    updateUI();
    const msg = document.getElementById('saved-msg');
    msg.classList.add('show');
    setTimeout(() => msg.classList.remove('show'), 2000);
}}

function resetChanges() {{
    if (!confirm('Discard all changes and reload original data?')) return;
    changedItems.clear();
    // Re-parse from embedded data
    if (clarifyEl) clarifyData = JSON.parse(clarifyEl.textContent);
    if (intentEl) intentData = JSON.parse(intentEl.textContent);
    location.reload();
}}

// ── UI update ─────────────────────────────────────────────────────────────

function updateUI() {{
    const count = changedItems.size;
    document.getElementById('changed-count').textContent = count;
    document.getElementById('changed-indicator').style.display = count > 0 ? 'inline' : 'none';
    document.getElementById('btn-save').disabled = count === 0;

    // Refresh summary bars
    if (clarifyData) refreshClarifySummary();
    if (intentData) refreshIntentSummary();
}}

// Routing helpers (must match Python logic)
const ROUTING_LABELS_CLARIFY = {{green: 'Clear', blue: 'Minor ambiguity', orange: 'Review required', red: 'Clarification required'}};
const ROUTING_LABELS_INTENT = {{green: 'Strong intent', blue: 'Review recommended', orange: 'Review required', red: 'Do not generate yet'}};

function avgDrivers(drivers) {{
    if (!drivers || Object.keys(drivers).length === 0) return 0.5;
    const vals = Object.values(drivers).filter(v => typeof v === 'number');
    return vals.length ? vals.reduce((a,b) => a+b, 0) / vals.length : 0.5;
}}

function routingLabel(score, isClarify) {{
    const labels = isClarify ? ROUTING_LABELS_CLARIFY : ROUTING_LABELS_INTENT;
    if (score >= 0.85) return labels.green;
    if (score >= 0.65) return labels.blue;
    if (score >= 0.40) return labels.orange;
    return labels.red;
}}

function refreshClarifySummary() {{
    if (!clarifyData) return;
    const ambs = clarifyData.decomposition?.ambiguities || [];
    const decs = getDecisions(clarifyData, 'clarification');
    const decCounts = {{}};
    const routingCounts = {{}};
    ambs.forEach(a => {{
        const dec = decs[a.item_id] || {{}};
        const d = dec.decision || 'pending';
        decCounts[d] = (decCounts[d] || 0) + 1;
        const score = avgDrivers(a.confidence_drivers);
        const rl = routingLabel(score, true);
        routingCounts[rl] = (routingCounts[rl] || 0) + 1;
    }});
    const el = document.getElementById('clarification-summary');
    if (el) el.innerHTML = buildSummaryHTML('Ambiguities', ambs.length, routingCounts, decCounts);
}}

function refreshIntentSummary() {{
    if (!intentData) return;
    const intents = intentData.plan?.intents || [];
    const decs = getDecisions(intentData, 'intent');
    const decCounts = {{}};
    const routingCounts = {{}};
    intents.forEach(it => {{
        const dec = decs[it.intent_id] || {{}};
        const d = dec.decision || 'pending';
        decCounts[d] = (decCounts[d] || 0) + 1;
        const rl = routingLabel(it.confidence_score || 0.5, false);
        routingCounts[rl] = (routingCounts[rl] || 0) + 1;
    }});
    const el = document.getElementById('intent-summary');
    if (el) el.innerHTML = buildSummaryHTML('Intents', intents.length, routingCounts, decCounts);
}}

function buildSummaryHTML(label, total, routing, decisions) {{
    let cls = 'summary';
    if (decisions['block']) cls = 'summary blocked';
    else if (decisions['pending'] || decisions['']) cls = 'summary warn';

    let rParts = Object.entries(routing).map(([k,v]) => '<span class="kv">' + k + '=' + v + '</span>').join(' ');
    if (!rParts) rParts = '<span class="section-empty">none</span>';
    let dParts = Object.entries(decisions).map(([k,v]) => {{
        const alertCls = (k === 'pending' || k === '') ? ' alert' : '';
        return '<span class="kv' + alertCls + '">' + (k || 'pending') + '=' + v + '</span>';
    }}).join(' ');
    if (!dParts) dParts = '<span class="section-empty">none</span>';

    return '<div class="' + cls + '"><strong>' + label + ':</strong> ' + total + ' total &nbsp;|&nbsp; <strong>Routing:</strong> ' + rParts + ' &nbsp;|&nbsp; <strong>Decisions:</strong> ' + dParts + '</div>';
}}

// Initial UI state
updateUI();
</script>

</body>
</html>"""
