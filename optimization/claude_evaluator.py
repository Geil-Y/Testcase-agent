"""DeepSeek 4-dimension scorer for generated test cases.

Calls DeepSeek API to score each case on executability, observability,
coverage_value, and missing_information_detection (1-5 scale). Results are
saved to deepseek_evaluation.json alongside hard-rule and human-review scores.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash[1m]")
MAX_CASES_PER_CALL = 100
_RUBRICS_PATH = _PROJECT_ROOT / "optimization_runs" / "scoring_rubrics.md"


def _load_rubrics() -> str:
    """Load 4-dimension scoring rubrics from markdown file."""
    if not _RUBRICS_PATH.exists():
        raise FileNotFoundError(f"Rubrics file not found: {_RUBRICS_PATH}")
    return _RUBRICS_PATH.read_text(encoding="utf-8")


# ── Checklist reference (appendix) ──────────────────────────────────────

CHECKLIST_APPENDIX_HEADER = """
## Appendix — Checklist v2 Reference

The checklist below provides domain-specific rules. Use it to inform your
scoring judgments, NOT as a mechanical tick-list. A single checklist item
may affect multiple dimensions.

"""


# ── Output schema ───────────────────────────────────────────────────────

OUTPUT_SCHEMA = """
## Output Format

Return ONLY a JSON object — no other text. The JSON must follow this structure:

```json
{
  "cases": [
    {
      "requirement_key": "REQ-BMS-OVP-002",
      "case_index": 0,
      "case_title": "Overvoltage detection at threshold → BMS_CellOV_Flag set",
      "executability": 3,
      "executability_note": "Step 1 'for a duration of' conflates action and timing",
      "observability": 3,
      "observability_note": "Expected uses '!= null' instead of concrete field comparison",
      "coverage_value": 3,
      "coverage_value_note": "Covers trigger path but no non-trigger counterpart case found in set",
      "missing_information_detection": 4,
      "missing_information_detection_note": "No semantic gaps missed; [NEEDS REVIEW] usage correct"
    }
  ]
}
```

Rules:
- Output every case from the input. Do not skip any.
- `case_index` is the 0-based index of the case within its requirement's case list.
- Every dimension must have a score (integer 1–5).
- Every dimension must have a `_note` field explaining the score. Keep notes under 100 characters. Write in English.
- If a dimension scores 5, the note can be brief ("All steps directly executable, no issues").
- If a dimension scores below 3, the note MUST clearly state the main flaw.
"""


# ── Prompt builders ─────────────────────────────────────────────────────

def _build_system_prompt(checklist: str) -> str:
    rubrics = _load_rubrics()
    return (
        "You are a BMS HIL test case quality reviewer. Evaluate each test case "
        "on four dimensions using the 1–5 rubrics below. Judge holistically — "
        "do NOT do mechanical string matching or item counting.\n\n"
        + rubrics
        + "\n\n---\n\n"
        + CHECKLIST_APPENDIX_HEADER
        + checklist
        + "\n\n---\n\n"
        + OUTPUT_SCHEMA
    )


def _build_user_prompt(cases: list[dict], start_idx: int, total: int) -> str:
    """Build user prompt for a batch of cases (up to MAX_CASES_PER_CALL)."""
    parts = [
        f"Evaluate the following {len(cases)} test case(s) "
        f"(batch {start_idx + 1}–{start_idx + len(cases)} of {total} total).\n",
    ]

    for i, case in enumerate(cases):
        steps_text = "\n".join(
            f"  {s.get('order', j + 1)}. Action: {s.get('action', '')} | "
            f"Expected: {s.get('expected', 'none')}"
            for j, s in enumerate(case.get("steps", []))
        )
        parts.append(
            f"### Case {start_idx + i} — {case['title']}\n"
            f"Requirement: {case['requirement_key']}\n"
            f"Objective: {case['objective']}\n"
            f"Precondition: {case['precondition']}\n"
            f"Postcondition: {case['postcondition']}\n"
            f"Steps:\n{steps_text}\n"
        )

    return "\n".join(parts)


def _flatten_cases(data: list[dict]) -> list[dict]:
    """Flatten generated_cases.json into a single list of per-case dicts."""
    flat: list[dict] = []
    for req in data:
        req_key = req["requirement_key"]
        for ci, case in enumerate(req.get("cases", [])):
            flat.append({
                "requirement_key": req_key,
                "case_index": ci,
                "title": case.get("title", ""),
                "objective": case.get("objective", ""),
                "precondition": case.get("precondition", ""),
                "postcondition": case.get("postcondition", ""),
                "steps": case.get("steps", []),
            })
    return flat


# ── API client ──────────────────────────────────────────────────────────

def _get_client():
    """Create Anthropic client for DeepSeek endpoint."""
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")

    if not api_key:
        try:
            from testcase_agent.config import get_settings
            settings = get_settings()
            api_key = settings.llm.api_key
        except Exception:
            pass
    if not api_key:
        raise ValueError(
            "No API key found. Run via Claude Code (which sets ANTHROPIC_AUTH_TOKEN) "
            "or set DEEPSEEK_API_KEY in environment."
        )

    from anthropic import Anthropic
    return Anthropic(api_key=api_key, base_url=base_url)


def _extract_json(text: str) -> dict | None:
    """Robust JSON extraction from LLM response."""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _call_llm(system_prompt: str, user_prompt: str, model: str) -> str:
    """Single API call via Anthropic Messages endpoint."""
    client = _get_client()
    response = client.messages.create(
        model=model,
        max_tokens=16384,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        thinking={"type": "disabled"},
    )
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


# ── Result types ────────────────────────────────────────────────────────

@dataclass
class CaseScore:
    requirement_key: str
    case_index: int
    case_title: str
    executability: int = 0
    executability_note: str = ""
    observability: int = 0
    observability_note: str = ""
    coverage_value: int = 0
    coverage_value_note: str = ""
    missing_information_detection: int = 0
    missing_information_detection_note: str = ""


@dataclass
class EvalResult:
    cases: list[CaseScore] = field(default_factory=list)
    errors: int = 0
    model_used: str = ""

    @property
    def total_cases(self) -> int:
        return len(self.cases)

    @property
    def avg_executability(self) -> float:
        scores = [c.executability for c in self.cases if c.executability > 0]
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    @property
    def avg_observability(self) -> float:
        scores = [c.observability for c in self.cases if c.observability > 0]
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    @property
    def avg_coverage_value(self) -> float:
        scores = [c.coverage_value for c in self.cases if c.coverage_value > 0]
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    @property
    def avg_missing_information_detection(self) -> float:
        scores = [c.missing_information_detection for c in self.cases if c.missing_information_detection > 0]
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    @property
    def overall_weighted(self) -> float:
        return round(
            0.20 * self.avg_executability
            + 0.20 * self.avg_observability
            + 0.20 * self.avg_coverage_value
            + 0.40 * self.avg_missing_information_detection,
            1,
        )


# ── Core evaluation ─────────────────────────────────────────────────────

def _parse_case_scores(parsed: dict) -> list[CaseScore]:
    """Extract validated CaseScore list from parsed LLM JSON."""
    scores: list[CaseScore] = []
    for c in parsed.get("cases", []):
        cs = CaseScore(
            requirement_key=str(c.get("requirement_key", "")),
            case_index=int(c.get("case_index", -1)),
            case_title=str(c.get("case_title", "")),
            executability=int(c.get("executability", 0)),
            executability_note=str(c.get("executability_note", "")),
            observability=int(c.get("observability", 0)),
            observability_note=str(c.get("observability_note", "")),
            coverage_value=int(c.get("coverage_value", 0)),
            coverage_value_note=str(c.get("coverage_value_note", "")),
            missing_information_detection=int(c.get("missing_information_detection", 0)),
            missing_information_detection_note=str(c.get("missing_information_detection_note", "")),
        )
        # Validate score ranges
        for dim in ["executability", "observability", "coverage_value", "missing_information_detection"]:
            val = getattr(cs, dim)
            if not (1 <= val <= 5):
                setattr(cs, dim, 0)
        scores.append(cs)
    return scores


def evaluate_round(
    round_dir: Path,
    model: str = DEFAULT_MODEL,
    delay: float = 0.5,
) -> EvalResult:
    """Score all cases in a round using DeepSeek API.

    Processes the entire generated_cases.json in batches of up to 100 cases.
    """
    cases_path = round_dir / "generated_cases.json"
    if not cases_path.exists():
        raise FileNotFoundError(f"generated_cases.json not found in {round_dir}")

    checklist_path = _PROJECT_ROOT / "optimization_runs" / "checklist_v2.md"
    if not checklist_path.exists():
        raise FileNotFoundError(f"Checklist not found: {checklist_path}")

    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)
    checklist = checklist_path.read_text(encoding="utf-8")

    all_cases = _flatten_cases(data)
    total = len(all_cases)
    system_prompt = _build_system_prompt(checklist)

    result = EvalResult(model_used=model)

    for batch_start in range(0, total, MAX_CASES_PER_CALL):
        batch = all_cases[batch_start:batch_start + MAX_CASES_PER_CALL]
        batch_num = batch_start // MAX_CASES_PER_CALL + 1
        total_batches = (total + MAX_CASES_PER_CALL - 1) // MAX_CASES_PER_CALL

        print(f"[Batch {batch_num}/{total_batches}] Evaluating {len(batch)} case(s) "
              f"({batch_start + 1}–{batch_start + len(batch)} of {total}) ...")

        user_prompt = _build_user_prompt(batch, batch_start, total)

        try:
            raw = _call_llm(system_prompt, user_prompt, model)
            parsed = _extract_json(raw)

            if parsed is None:
                print(f"  ERROR: Failed to parse JSON from response")
                print(f"  Raw (first 500 chars): {raw[:500]}")
                result.errors += 1
                continue

            batch_scores = _parse_case_scores(parsed)

            # Fill in requirement_key and case_index from input if LLM omitted them
            for i, cs in enumerate(batch_scores):
                if not cs.requirement_key and i < len(batch):
                    cs.requirement_key = batch[i]["requirement_key"]
                if cs.case_index < 0 and i < len(batch):
                    cs.case_index = batch[i]["case_index"]

            missing = [cs for cs in batch_scores if cs.executability == 0]
            if missing:
                print(f"  WARNING: {len(missing)} case(s) have missing/invalid scores")

            result.cases.extend(batch_scores)
            print(f"  Got {len(batch_scores)} case score(s)")
            sys.stdout.flush()

        except Exception as exc:
            print(f"  ERROR: {exc}")
            result.errors += 1

        # Delay between batches
        if batch_start + MAX_CASES_PER_CALL < total:
            time.sleep(delay)

    return result


# ── Persistence ─────────────────────────────────────────────────────────

def _validate_scores(result: EvalResult) -> None:
    """Raise ValueError if any case has invalid scores."""
    for cs in result.cases:
        if cs.requirement_key == "":
            raise ValueError(f"Case index {cs.case_index}: missing requirement_key")
        for dim in ["executability", "observability", "coverage_value", "missing_information_detection"]:
            val = getattr(cs, dim)
            if not (1 <= val <= 5):
                raise ValueError(
                    f"Case '{cs.requirement_key}'[{cs.case_index}]: "
                    f"{dim}={val} (must be 1–5)"
                )


def save_evaluation(result: EvalResult, round_dir: Path, evaluator_name: str = "deepseek") -> Path:
    """Save 4-dimension scores to {evaluator_name}_evaluation.json."""
    _validate_scores(result)

    output = {
        "checklist_version": "checklist_v2.md",
        "evaluated_by": evaluator_name,
        "model": result.model_used,
        "total_cases": result.total_cases,
        "errors": result.errors,
        "dimension_averages": {
            "executability": result.avg_executability,
            "observability": result.avg_observability,
            "coverage_value": result.avg_coverage_value,
            "missing_information_detection": result.avg_missing_information_detection,
        },
        "overall_weighted": result.overall_weighted,
        "cases": [
            {
                "requirement_key": cs.requirement_key,
                "case_index": cs.case_index,
                "case_title": cs.case_title,
                "executability": cs.executability,
                "executability_note": cs.executability_note,
                "observability": cs.observability,
                "observability_note": cs.observability_note,
                "coverage_value": cs.coverage_value,
                "coverage_value_note": cs.coverage_value_note,
                "missing_information_detection": cs.missing_information_detection,
                "missing_information_detection_note": cs.missing_information_detection_note,
            }
            for cs in result.cases
        ],
    }

    out_path = round_dir / f"{evaluator_name}_evaluation.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path}")
    return out_path


def run_full_evaluation(
    round_dir: Path,
    model: str = DEFAULT_MODEL,
    delay: float = 0.5,
) -> float:
    """Run DeepSeek 4-dimension scoring and save to deepseek_evaluation.json.

    Returns the overall weighted score (0.0–5.0).
    """
    result = evaluate_round(round_dir, model=model, delay=delay)
    save_evaluation(result, round_dir, evaluator_name="deepseek")

    print(
        f"\nDone. DeepSeek weighted={result.overall_weighted} "
        f"(exec={result.avg_executability}, obs={result.avg_observability}, "
        f"cov={result.avg_coverage_value}, missing_info={result.avg_missing_information_detection})"
    )
    return result.overall_weighted
