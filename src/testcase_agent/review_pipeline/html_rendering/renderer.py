"""HTML renderer for review artifacts.

Generates human-readable HTML views from JSON review artifacts.
HTML is the review view only — JSON is the source of truth.
LLM never authors HTML; code generates it from JSON.
"""

from __future__ import annotations

from collections import Counter

from testcase_agent.review_pipeline.artifacts.legacy_models import (
    ClarificationReview,
    ClarificationDecision,
    CaseIntentReview,
    CaseIntentDecision,
    RequirementDecomposition,
)
from testcase_agent.review_pipeline.confidence.engine import routing_for_confidence, routing_label


def render_clarification_review(review: ClarificationReview) -> str:
    """Render clarification review as HTML with facts, summary, and decision-ready ambiguities."""

    facts_html = _render_facts(review.decomposition)
    summary_html = _render_clarification_summary(review)
    items_html = ""

    for i, amb in enumerate(review.decomposition.ambiguities):
        dec = _find_clarification_decision(review, amb.item_id)
        decision = dec.decision if dec else "pending"
        decision_color = _decision_color(decision)
        score = _avg_driver_score(amb.confidence_drivers)
        routing = routing_for_confidence(score)
        label = routing_label(score, is_clarification=True)

        pending_class = 'pending-decision' if decision == 'pending' else ''
        rec = amb.recommended_review_decision

        items_html += f"""
    <div class="review-item {pending_class}" style="border-left: 4px solid {routing.color}; margin: 8px 0; padding: 8px;" id="{amb.item_id}">
      <div class="item-header">
        <strong>{amb.item_id}</strong>
        <span class="routing-badge" style="background:{routing.color};color:#fff;padding:2px 8px;border-radius:4px;">{label}</span>
        <span class="decision-badge" style="background:{decision_color};color:#fff;padding:2px 8px;border-radius:4px;margin-left:4px;">{decision}</span>
        <span class="severity severity-{amb.severity}">Severity: {amb.severity}</span>
        <span class="rec-decision">rec: {rec}</span>
      </div>
      <div class="item-body">
        <p><strong>Affected text:</strong> <code>{_esc(amb.affected_text)}</code></p>
        <p><strong>Ambiguity type:</strong> {_esc(amb.ambiguity_type)}</p>
        <p><strong>Impact:</strong> {_esc(amb.impact)}</p>
        <p><strong>Question:</strong> {_esc(amb.clarification_question)}</p>
        <p><strong>Safe policy:</strong> {_esc(amb.safe_generation_policy)}</p>
        <p><strong>Reasons:</strong> {_esc(', '.join(amb.reasons))}</p>
        <p class="drivers"><strong>Confidence drivers:</strong> {_esc(_format_drivers(amb.confidence_drivers))}</p>
        <p><strong>Score:</strong> {score:.2f}</p>
      </div>
    </div>"""

    return _base_html(
        title=f"Clarification Review — {_esc(review.requirement_key)}",
        body=f"""
<h1>Clarification Review</h1>
<p>Requirement: <strong>{_esc(review.requirement_key)}</strong> &mdash; Session: {_esc(review.review_session_id)} &mdash; Created: {_esc(review.created_at)}</p>
{summary_html}
{facts_html}
<h2>Ambiguities ({len(review.decomposition.ambiguities)})</h2>
{items_html}
"""
    )


def render_case_intent_review(review: CaseIntentReview) -> str:
    """Render case intent review as HTML with summary and decision-ready intents."""

    summary_html = _render_intent_summary(review)
    items_html = ""

    for intent in review.plan.intents:
        dec = _find_intent_decision(review, intent.intent_id)
        decision = dec.decision if dec else "pending"
        decision_color = _decision_color(decision)
        routing = routing_for_confidence(intent.confidence_score)
        label = routing_label(intent.confidence_score, is_clarification=False)

        pending_class = 'pending-decision' if decision == 'pending' else ''
        rec = intent.recommended_review_decision

        items_html += f"""
    <div class="review-item {pending_class}" style="border-left: 4px solid {routing.color}; margin: 8px 0; padding: 8px;" id="{intent.intent_id}">
      <div class="item-header">
        <strong>{intent.intent_id}</strong>
        <span class="routing-badge" style="background:{routing.color};color:#fff;padding:2px 8px;border-radius:4px;">{label}</span>
        <span class="decision-badge" style="background:{decision_color};color:#fff;padding:2px 8px;border-radius:4px;margin-left:4px;">{decision}</span>
        <span class="dimension">[{_esc(intent.coverage_dimension)}]</span>
        <span class="rec-decision">rec: {rec}</span>
      </div>
      <div class="item-body">
        <p><strong>Intent:</strong> {_esc(intent.intent_text)}</p>
        <p><strong>Basis refs:</strong> {_esc(', '.join(intent.requirement_basis_refs))}</p>
        <p><strong>Reasons:</strong> {_esc(', '.join(intent.reasons))}</p>
        <p class="drivers"><strong>Confidence drivers:</strong> {_esc(_format_drivers(intent.confidence_drivers))}</p>
        <p><strong>Score:</strong> {intent.confidence_score:.2f}</p>
      </div>
    </div>"""

    blocked = ""
    if review.plan.planning_blocked:
        blocked = f'<div class="blocked-banner">PLANNING BLOCKED: {_esc(review.plan.planning_block_reason)}</div>'

    return _base_html(
        title=f"Case Intent Review — {_esc(review.requirement_key)}",
        body=f"""
<h1>Case Intent Review</h1>
<p>Requirement: <strong>{_esc(review.requirement_key)}</strong> &mdash; Session: {_esc(review.review_session_id)} &mdash; Created: {_esc(review.created_at)}</p>
{blocked}
{summary_html}
<h2>Intents ({len(review.plan.intents)})</h2>
{items_html}
"""
    )


# ── Section renderers ────────────────────────────────────────────────────────

def _render_facts(decomp: RequirementDecomposition) -> str:
    if not decomp.facts:
        return '<p><em>No facts extracted.</em></p>'
    rows = ""
    for f in decomp.facts:
        rows += f"""
    <tr>
      <td class="fact-id">{_esc(f.item_id)}</td>
      <td class="fact-text">{_esc(f.fact_text)}</td>
      <td class="fact-conf">{f.confidence:.0%}</td>
    </tr>"""
    return f"""
<h2>Facts ({len(decomp.facts)})</h2>
<table class="facts-table">
  <thead><tr><th>ID</th><th>Fact</th><th>Conf</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""


def _render_clarification_summary(review: ClarificationReview) -> str:
    """Summary bar: count by routing, severity, decision status."""
    ambs = review.decomposition.ambiguities
    if not ambs:
        return ""

    routing_counts = Counter()
    severity_counts = Counter()
    decision_counts = Counter()
    for a in ambs:
        s = _avg_driver_score(a.confidence_drivers)
        routing_counts[routing_label(s, is_clarification=True)] += 1
        severity_counts[a.severity] += 1
        dec = _find_clarification_decision(review, a.item_id)
        decision_counts[dec.decision if dec else "pending"] += 1

    return f"""
<div class="summary">
  <div class="summary-group">
    <strong>By routing:</strong> {_render_counts(routing_counts)}
  </div>
  <div class="summary-group">
    <strong>By severity:</strong> {_render_counts(severity_counts)}
  </div>
  <div class="summary-group">
    <strong>By decision:</strong> {_render_counts(decision_counts, highlight_pending=True)}
  </div>
</div>"""


def _render_intent_summary(review: CaseIntentReview) -> str:
    intents = review.plan.intents
    if not intents:
        return ""

    routing_counts = Counter()
    dim_counts = Counter()
    decision_counts = Counter()
    for it in intents:
        routing_counts[routing_label(it.confidence_score, is_clarification=False)] += 1
        dim_counts[it.coverage_dimension] += 1
        dec = _find_intent_decision(review, it.intent_id)
        decision_counts[dec.decision if dec else "pending"] += 1

    return f"""
<div class="summary">
  <div class="summary-group">
    <strong>By routing:</strong> {_render_counts(routing_counts)}
  </div>
  <div class="summary-group">
    <strong>By dimension:</strong> {_render_counts(dim_counts)}
  </div>
  <div class="summary-group">
    <strong>By decision:</strong> {_render_counts(decision_counts, highlight_pending=True)}
  </div>
</div>"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _render_counts(counter: Counter, highlight_pending: bool = False) -> str:
    parts = []
    for label, count in counter.most_common():
        cls = ""
        if highlight_pending and label == "pending":
            cls = 'class="pending-count"'
        parts.append(f'<span {cls}>{label}={count}</span>')
    return ", ".join(parts)


def _find_clarification_decision(review: ClarificationReview, item_id: str) -> ClarificationDecision | None:
    for d in review.decisions:
        if d.item_id == item_id:
            return d
    return None


def _find_intent_decision(review: CaseIntentReview, intent_id: str) -> CaseIntentDecision | None:
    for d in review.decisions:
        if d.intent_id == intent_id:
            return d
    return None


def _avg_driver_score(drivers: dict[str, float]) -> float:
    if not drivers:
        return 0.5
    return sum(drivers.values()) / len(drivers)


def _decision_color(decision: str) -> str:
    colors = {
        "approve": "#2e7d32",
        "reject": "#c62828",
        "revise": "#e65100",
        "merge": "#1565c0",
        "split": "#6a1b9a",
        "defer": "#546e7a",
        "clarify": "#e65100",
        "mark_needs_review": "#f9a825",
        "block": "#c62828",
        "edit": "#1565c0",
        "pending": "#b71c1c",
    }
    return colors.get(decision, "#757575")


def _format_drivers(drivers: dict[str, float]) -> str:
    return ", ".join(f"{k}={v:.2f}" for k, v in drivers.items())


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _base_html(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 16px; color: #222; }}
  .review-item {{ background: #f9f9f9; }}
  .review-item.pending-decision {{ background: #fff8e1; }}
  .item-header {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  .item-body {{ margin-top: 8px; }}
  .item-body p {{ margin: 4px 0; }}
  .item-body code {{ background: #e8e8e8; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }}
  .severity-critical {{ color: #c62828; font-weight: bold; }}
  .severity-high {{ color: #e65100; font-weight: bold; }}
  .severity-medium {{ color: #f9a825; }}
  .severity-low {{ color: #757575; }}
  .rec-decision {{ color: #757575; font-size: 0.85em; font-style: italic; }}
  .summary {{ background: #e3f2fd; border: 1px solid #90caf9; border-radius: 6px; padding: 10px 14px; margin: 12px 0; display: flex; gap: 24px; flex-wrap: wrap; font-size: 0.9em; }}
  .summary-group {{ display: flex; gap: 6px; align-items: center; }}
  .summary-group span {{ background: #fff; border: 1px solid #bbb; border-radius: 4px; padding: 1px 6px; white-space: nowrap; }}
  .pending-count {{ background: #fff3e0 !important; border-color: #ff9800 !important; font-weight: bold; color: #e65100; }}
  .facts-table {{ width: 100%; border-collapse: collapse; margin: 8px 0 16px 0; font-size: 0.9em; }}
  .facts-table th {{ background: #e0e0e0; text-align: left; padding: 4px 8px; }}
  .facts-table td {{ padding: 4px 8px; border-bottom: 1px solid #e0e0e0; }}
  .fact-id {{ white-space: nowrap; color: #616161; font-family: monospace; width: 1%; }}
  .fact-text {{ }}
  .fact-conf {{ text-align: center; width: 1%; white-space: nowrap; }}
  .blocked-banner {{ background: #ffcdd2; border: 2px solid #c62828; color: #b71c1c; padding: 10px 14px; border-radius: 6px; margin: 12px 0; font-weight: bold; }}
  .drivers {{ font-size: 0.85em; color: #616161; }}
  hr {{ margin: 16px 0; }}
  h2 {{ margin-top: 20px; }}
</style>
</head>
<body>
{body}
</body>
</html>"""
