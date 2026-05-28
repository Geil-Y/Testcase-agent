"""Shared helpers for parsing LLM JSON responses and formatting prompt sections.

Used by all three pipeline stages (LLM-A, LLM-B, LLM-C).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from testcase_agent.review_pipeline.artifacts.models import ExtractedTestBasis


def parse_json_response(raw_response: str) -> dict[str, Any]:
    """Parse raw model output, stripping a markdown code fence if present."""
    text = raw_response.strip()
    if text.startswith("```"):
        text = _strip_markdown_fence(text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed


def _strip_markdown_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def dump_raw_response(run_dir: Path, raw_response: str, label: str) -> None:
    """Write raw LLM response to a debug file in the run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"{label}_raw_response.txt").write_text(raw_response, encoding="utf-8")


def format_known_items(basis: ExtractedTestBasis, section: str) -> str:
    """Format known items from one extraction section for prompt rendering."""
    items = basis.known_items(section)
    if not items:
        return ""
    return "\n".join(f"- [{it.item_id}] {it.content}" for it in items)


def format_unresolved_items(basis: ExtractedTestBasis) -> str:
    """Format all needs_review items across all sections for prompt rendering."""
    items = basis.all_needs_review_items()
    if not items:
        return ""
    return "\n".join(f"- [{it.item_id}] {it.need}" for it in items)
