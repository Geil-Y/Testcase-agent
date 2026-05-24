"""HTML renderer for review artifacts.

Generates human-readable HTML views from JSON review artifacts.
HTML is the review view only — JSON is the source of truth.
LLM never authors HTML; code generates it from JSON.
"""

from __future__ import annotations

from review_pipeline.artifacts.models import (
    ClarificationReview,
    ClarificationDecision,
    CaseIntentReview,
    CaseIntentDecision,
    CaseIntentItem,
    AmbiguityItem,
    RequirementDecomposition,
)
from review_pipeline.confidence.engine import routing_for_confidence, routing_label


def render_clarification_review(review: ClarificationReview) -> str:
    """Render clarification review as HTML."""
    items_html = ""
    for i, amb in enumerate(review.decomposition.ambiguities):
        dec = _find_clarification_decision(review, amb.item_id)
        decision = dec.decision if dec else "pending"
        decision_color = _decision_color(decision)
        score = _avg_driver_score(amb.confidence_drivers)
        routing = routing_for_confidence(score)
        label = routing_label(score, is_clarification=True)

        items_html += f"""
    <div class="review-item" style="border-left: 4px solid {routing.color}; margin: 8px 0; padding: 8px;">
      <div class="item-header">
        <strong>{amb.item_id}</strong>
        <span class="routing-badge" style="background:{routing.color};color:#fff;padding:2px 8px;border-radius:4px;">{label}</span>
        <span class="decision-badge" style="background:{decision_color};color:#fff;padding:2px 8px;border-radius:4px;margin-left:4px;">{decision}</span>
        <span class="severity">Severity: {amb.severity}</span>
      </div>
      <div class="item-body">
        <p><strong>Affected text:</strong> {_esc(amb.affected_text)}</p>
        <p><strong>Ambiguity type:</strong> {_esc(amb.ambiguity_type)}</p>
        <p><strong>Impact:</strong> {_esc(amb.impact)}</p>
        <p><strong>Question:</strong> {_esc(amb.clarification_question)}</p>
        <p><strong>Safe policy:</strong> {_esc(amb.safe_generation_policy)}</p>
        <p><strong>Reasons:</strong> {_esc(', '.join(amb.reasons))}</p>
        <p><strong>Confidence drivers:</strong> {_esc(_format_drivers(amb.confidence_drivers))}</p>
        <p><strong>Score:</strong> {score:.2f}</p>
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Clarification Review — {_esc(review.requirement_key)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 16px; }}
  .review-item {{ background: #f9f9f9; }}
  .item-header {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  .item-body {{ margin-top: 8px; }}
  .item-body p {{ margin: 4px 0; }}
</style>
</head>
<body>
<h1>Clarification Review</h1>
<p>Requirement: <strong>{_esc(review.requirement_key)}</strong></p>
<p>Session: {_esc(review.review_session_id)}</p>
<p>Created: {_esc(review.created_at)}</p>
<hr>
{items_html}
</body>
</html>"""


def render_case_intent_review(review: CaseIntentReview) -> str:
    """Render case intent review as HTML."""
    items_html = ""
    for intent in review.plan.intents:
        dec = _find_intent_decision(review, intent.intent_id)
        decision = dec.decision if dec else "pending"
        decision_color = _decision_color(decision)
        routing = routing_for_confidence(intent.confidence_score)
        label = routing_label(intent.confidence_score, is_clarification=False)

        items_html += f"""
    <div class="review-item" style="border-left: 4px solid {routing.color}; margin: 8px 0; padding: 8px;">
      <div class="item-header">
        <strong>{intent.intent_id}</strong>
        <span class="routing-badge" style="background:{routing.color};color:#fff;padding:2px 8px;border-radius:4px;">{label}</span>
        <span class="decision-badge" style="background:{decision_color};color:#fff;padding:2px 8px;border-radius:4px;margin-left:4px;">{decision}</span>
        <span class="dimension">[{_esc(intent.coverage_dimension)}]</span>
      </div>
      <div class="item-body">
        <p><strong>Intent:</strong> {_esc(intent.intent_text)}</p>
        <p><strong>Basis refs:</strong> {_esc(', '.join(intent.requirement_basis_refs))}</p>
        <p><strong>Reasons:</strong> {_esc(', '.join(intent.reasons))}</p>
        <p><strong>Confidence drivers:</strong> {_esc(_format_drivers(intent.confidence_drivers))}</p>
        <p><strong>Score:</strong> {intent.confidence_score:.2f}</p>
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Case Intent Review — {_esc(review.requirement_key)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 16px; }}
  .review-item {{ background: #f9f9f9; }}
  .item-header {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  .item-body {{ margin-top: 8px; }}
  .item-body p {{ margin: 4px 0; }}
</style>
</head>
<body>
<h1>Case Intent Review</h1>
<p>Requirement: <strong>{_esc(review.requirement_key)}</strong></p>
<p>Session: {_esc(review.review_session_id)}</p>
<p>Created: {_esc(review.created_at)}</p>
<hr>
{items_html}
</body>
</html>"""


# ── Helpers ────────────────────────────────────────────────────────────────

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
        "pending": "#757575",
    }
    return colors.get(decision, "#757575")


def _format_drivers(drivers: dict[str, float]) -> str:
    return ", ".join(f"{k}={v:.2f}" for k, v in drivers.items())


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
