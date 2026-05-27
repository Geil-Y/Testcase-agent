"""DeepSeek 8-dimension scorer for generated BMS HIL test cases.

The evaluator scores each requirement group, not isolated flattened cases:

- coverage_value is scored once per requirement over the full case set.
- the other seven dimensions are scored per generated case.

Results are saved to deepseek_evaluation.json alongside hard-rule and manual
review scores.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-flash[1m]")
_RUBRICS_PATH = _PROJECT_ROOT / "optimization_runs" / "scoring_rubrics.md"

CASE_LEVEL_DIMS = [
    "requirement_alignment",
    "executability",
    "observability",
    "pass_fail_clarity",
    "information_integrity",
    "state_and_environment_control",
    "automation_readiness",
]
REQUIREMENT_LEVEL_DIMS = ["coverage_value"]
ALL_DIMS = [
    "requirement_alignment",
    "coverage_value",
    "executability",
    "observability",
    "pass_fail_clarity",
    "information_integrity",
    "state_and_environment_control",
    "automation_readiness",
]
WEIGHTS = {
    "requirement_alignment": 0.20,
    "information_integrity": 0.20,
    "executability": 0.15,
    "observability": 0.15,
    "pass_fail_clarity": 0.10,
    "coverage_value": 0.10,
    "state_and_environment_control": 0.05,
    "automation_readiness": 0.05,
}


def _load_rubrics() -> str:
    """Load 8-dimension scoring rubrics from markdown file."""
    if not _RUBRICS_PATH.exists():
        raise FileNotFoundError(f"Rubrics file not found: {_RUBRICS_PATH}")
    return _RUBRICS_PATH.read_text(encoding="utf-8")


# -- Checklist reference (appendix) --------------------------------------

CHECKLIST_APPENDIX_HEADER = """
## Appendix — Checklist v2 Reference

The checklist below provides domain-specific hard-rule guidance. Use it to
inform your scoring judgments, NOT as a mechanical tick-list. Deterministic
hard gates are owned by code, not by the LLM score output.

"""


# -- Output schema --------------------------------------------------------

OUTPUT_SCHEMA = """
## Output Format

Return ONLY a JSON object — no other text. The JSON must follow this structure:

```json
{
  "requirements": [
    {
      "requirement_key": "REQ-BMS-OVP-002",
      "coverage_value": 4,
      "coverage_value_note": "The case set covers trigger and no-trigger paths, but boundary timing is not split.",
      "cases": [
        {
          "case_index": 0,
          "case_title": "Overvoltage detection at threshold",
          "requirement_alignment": 5,
          "requirement_alignment_note": "The case is aligned with the overvoltage requirement.",
          "executability": 4,
          "executability_note": "The set-wait-check flow is executable.",
          "observability": 3,
          "observability_note": "The expected result lacks a concrete observable signal.",
          "pass_fail_clarity": 3,
          "pass_fail_clarity_note": "Activation is clear, but timing remains unspecified.",
          "information_integrity": 5,
          "information_integrity_note": "Missing signal and timing are marked, not invented.",
          "state_and_environment_control": 4,
          "state_and_environment_control_note": "Initial state is clear; reset could be stronger.",
          "automation_readiness": 4,
          "automation_readiness_note": "Steps are mostly atomic and structured."
        }
      ]
    }
  ]
}
```

Rules:
- Output every requirement from the input. Do not skip any.
- Output every case under its requirement. Do not skip any case.
- `case_index` is the 0-based index of the case within its requirement's case list.
- Every score must be an integer 1-5.
- Every score must have a matching `_note` field explaining the score.
- Keep notes concise and write in Chinese (中文).
- If a dimension scores below 3, the note MUST clearly state the main flaw.
- Do not output `overall_score`, `overall_weighted`, or `decision`.
"""


# -- Prompt builders ------------------------------------------------------

def _build_system_prompt(checklist: str) -> str:
    rubrics = _load_rubrics()
    return (
        "You are a BMS HIL test case quality reviewer. Evaluate each "
        "requirement group using the 8-dimension 1-5 rubric below. "
        "coverage_value is scored once per requirement case set; the other "
        "seven dimensions are scored per case. Judge holistically and do NOT "
        "do mechanical string matching or item counting.\n\n"
        + rubrics
        + "\n\n---\n\n"
        + CHECKLIST_APPENDIX_HEADER
        + checklist
        + "\n\n---\n\n"
        + OUTPUT_SCHEMA
    )


def build_system_prompt() -> str:
    """Build and return the system prompt from checklist_v2.md.

    The result can be reused across multiple score_batch() calls so the
    checklist and rubrics are loaded only once.
    """
    checklist_path = _PROJECT_ROOT / "optimization_runs" / "checklist_v2.md"
    checklist = checklist_path.read_text(encoding="utf-8")
    return _build_system_prompt(checklist)


def _fmt_list(values: list[Any]) -> str:
    clean = [str(v).strip() for v in values if str(v).strip()]
    return ", ".join(clean) if clean else "none"


def _fmt_missing_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "none"
    lines: list[str] = []
    for item in items:
        cat = str(item.get("category", "")).strip()
        desc = str(item.get("description", "")).strip()
        if cat:
            lines.append(f"- [{cat}] {desc}")
        elif desc:
            lines.append(f"- {desc}")
    return "\n".join(lines) if lines else "none"


def _build_user_prompt(requirements: list[dict], start_idx: int, total: int) -> str:
    """Build user prompt for a batch of requirement groups — case content only."""
    parts = [
        f"Evaluate the following {len(requirements)} requirement group(s) "
        f"(batch {start_idx + 1}-{start_idx + len(requirements)} of {total} total).\n",
    ]

    for offset, req in enumerate(requirements):
        parts.append(
            f"## Requirement Group {start_idx + offset}: {req.get('requirement_key', '')}\n"
            f"Function: {req.get('function_name', '')}\n"
            f"Description: {req.get('description', '')}\n"
        )

        for ci, case in enumerate(req.get("cases", [])):
            steps_text = "\n".join(
                f"    {s.get('order', j + 1)}. Action: {s.get('action', '')} | "
                f"Expected: {s.get('expected', 'none')}"
                for j, s in enumerate(case.get("steps", []))
            )
            parts.append(
                f"### Case {ci} — {case.get('title', '')}\n"
                f"Objective: {case.get('objective', '')}\n"
                f"Precondition: {case.get('precondition', '')}\n"
                f"Postcondition: {case.get('postcondition', '')}\n"
                f"Steps:\n{steps_text}\n"
            )

    return "\n".join(parts)


# -- API client -----------------------------------------------------------

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


# -- Result types ---------------------------------------------------------

def _valid_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return score if 1 <= score <= 5 else 0


@dataclass
class CaseScore:
    requirement_key: str
    case_index: int
    case_title: str
    requirement_alignment: int = 0
    requirement_alignment_note: str = ""
    executability: int = 0
    executability_note: str = ""
    observability: int = 0
    observability_note: str = ""
    pass_fail_clarity: int = 0
    pass_fail_clarity_note: str = ""
    information_integrity: int = 0
    information_integrity_note: str = ""
    state_and_environment_control: int = 0
    state_and_environment_control_note: str = ""
    automation_readiness: int = 0
    automation_readiness_note: str = ""

    def to_dict(self, *, coverage_value: int | None = None, coverage_value_note: str = "") -> dict[str, Any]:
        data: dict[str, Any] = {
            "requirement_key": self.requirement_key,
            "case_index": self.case_index,
            "case_title": self.case_title,
        }
        if coverage_value is not None:
            data["coverage_value"] = coverage_value
            data["coverage_value_note"] = coverage_value_note
        for dim in CASE_LEVEL_DIMS:
            data[dim] = getattr(self, dim)
            data[f"{dim}_note"] = getattr(self, f"{dim}_note")
        return data


@dataclass
class RequirementScore:
    requirement_key: str
    coverage_value: int = 0
    coverage_value_note: str = ""
    cases: list[CaseScore] = field(default_factory=list)

    def avg_case_dim(self, dim: str) -> float:
        scores = [getattr(c, dim) for c in self.cases if getattr(c, dim) > 0]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    def min_case_dim(self, dim: str) -> int:
        scores = [getattr(c, dim) for c in self.cases if getattr(c, dim) > 0]
        return min(scores) if scores else 0

    @property
    def weighted_score(self) -> float:
        total = self.coverage_value * WEIGHTS["coverage_value"]
        for dim in CASE_LEVEL_DIMS:
            total += self.avg_case_dim(dim) * WEIGHTS[dim]
        return round(total, 2)

    @property
    def case_dimension_averages(self) -> dict[str, float]:
        return {dim: self.avg_case_dim(dim) for dim in CASE_LEVEL_DIMS}

    @property
    def case_dimension_mins(self) -> dict[str, int]:
        return {dim: self.min_case_dim(dim) for dim in CASE_LEVEL_DIMS}


@dataclass
class EvalResult:
    requirements: list[RequirementScore] = field(default_factory=list)
    errors: int = 0
    model_used: str = ""

    @property
    def total_requirements(self) -> int:
        return len(self.requirements)

    @property
    def total_cases(self) -> int:
        return sum(len(r.cases) for r in self.requirements)

    @property
    def dimension_averages(self) -> dict[str, float]:
        values: dict[str, list[float]] = {dim: [] for dim in ALL_DIMS}
        for req in self.requirements:
            if req.coverage_value > 0:
                values["coverage_value"].append(float(req.coverage_value))
            for dim in CASE_LEVEL_DIMS:
                avg = req.avg_case_dim(dim)
                if avg > 0:
                    values[dim].append(avg)
        return {
            dim: round(sum(scores) / len(scores), 1) if scores else 0.0
            for dim, scores in values.items()
        }

    @property
    def dimension_mins(self) -> dict[str, int]:
        mins: dict[str, int] = {}
        for dim in ALL_DIMS:
            scores: list[int] = []
            for req in self.requirements:
                if dim == "coverage_value":
                    if req.coverage_value > 0:
                        scores.append(req.coverage_value)
                else:
                    val = req.min_case_dim(dim)
                    if val > 0:
                        scores.append(val)
            mins[dim] = min(scores) if scores else 0
        return mins

    @property
    def overall_weighted(self) -> float:
        scores = [r.weighted_score for r in self.requirements if r.weighted_score > 0]
        return round(sum(scores) / len(scores), 1) if scores else 0.0


# -- Core evaluation ------------------------------------------------------

def _parse_requirement_scores(parsed: dict) -> list[RequirementScore]:
    """Extract validated RequirementScore list from parsed LLM JSON."""
    scores: list[RequirementScore] = []
    for r in parsed.get("requirements", []):
        req_key = str(r.get("requirement_key", ""))
        req_score = RequirementScore(
            requirement_key=req_key,
            coverage_value=_valid_score(r.get("coverage_value", 0)),
            coverage_value_note=str(r.get("coverage_value_note", "")),
        )
        for c in r.get("cases", []):
            case_score = CaseScore(
                requirement_key=req_key,
                case_index=int(c.get("case_index", -1)),
                case_title=str(c.get("case_title", "")),
                requirement_alignment=_valid_score(c.get("requirement_alignment", 0)),
                requirement_alignment_note=str(c.get("requirement_alignment_note", "")),
                executability=_valid_score(c.get("executability", 0)),
                executability_note=str(c.get("executability_note", "")),
                observability=_valid_score(c.get("observability", 0)),
                observability_note=str(c.get("observability_note", "")),
                pass_fail_clarity=_valid_score(c.get("pass_fail_clarity", 0)),
                pass_fail_clarity_note=str(c.get("pass_fail_clarity_note", "")),
                information_integrity=_valid_score(c.get("information_integrity", 0)),
                information_integrity_note=str(c.get("information_integrity_note", "")),
                state_and_environment_control=_valid_score(c.get("state_and_environment_control", 0)),
                state_and_environment_control_note=str(c.get("state_and_environment_control_note", "")),
                automation_readiness=_valid_score(c.get("automation_readiness", 0)),
                automation_readiness_note=str(c.get("automation_readiness_note", "")),
            )
            req_score.cases.append(case_score)
        scores.append(req_score)
    return scores


def score_batch(
    batch: list[dict],
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    start_idx: int = 0,
    total: int | None = None,
) -> list[RequirementScore]:
    """Score a batch of requirement groups in a single LLM call.

    Raises RuntimeError if the LLM response cannot be parsed.
    """
    if total is None:
        total = len(batch)
    user_prompt = _build_user_prompt(batch, start_idx, total)
    raw = _call_llm(system_prompt, user_prompt, model)
    parsed = _extract_json(raw)
    if parsed is None:
        raise RuntimeError(f"Failed to parse JSON from LLM response")
    return _parse_requirement_scores(parsed)


def _print_requirement_score(idx: int, total: int, req_key: str, r: "RequirementScore | None"):
    """Print a single requirement's DeepSeek score line."""
    if r is None:
        print(f"  DeepSeek [{idx + 1}/{total}] {req_key} MISSING (not in batch response)")
        return
    avgs = r.case_dimension_averages
    print(
        f"  DeepSeek [{idx + 1}/{total}] {req_key}  "
        f"w={r.weighted_score}  cov={r.coverage_value}  "
        f"al={avgs['requirement_alignment']}  ex={avgs['executability']}  "
        f"ob={avgs['observability']}  pf={avgs['pass_fail_clarity']}  "
        f"in={avgs['information_integrity']}  st={avgs['state_and_environment_control']}  "
        f"ar={avgs['automation_readiness']}"
    )


def _score_requirements_parallel(
    data: list[dict],
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    batch_size: int = 5,
    max_concurrency: int = 3,
    submit_delay: float = 0.1,
) -> tuple[list[RequirementScore], int]:
    """Score requirements in parallel, batching multiple entries per API call.

    Returns (all_scores_in_original_order, error_count).
    Prints per-requirement results as they complete.
    """
    total = len(data)
    results: dict[int, list[RequirementScore]] = {}
    errors = 0

    # Split into batches
    batches: list[tuple[list[int], list[dict]]] = []
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batches.append((list(range(start, end)), data[start:end]))

    def _score_batch(indices: list[int], entries: list[dict]):
        try:
            scores = score_batch(entries, system_prompt, model, start_idx=indices[0] + 1, total=total)
            return indices, scores, None
        except Exception as exc:
            return indices, [], exc

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_to_indices: dict = {}
        for indices, entries in batches:
            future = executor.submit(_score_batch, indices, entries)
            future_to_indices[future] = indices
            if submit_delay and len(future_to_indices) < len(batches):
                time.sleep(submit_delay)

        for future in as_completed(future_to_indices):
            indices = future_to_indices[future]
            try:
                _, scores, exc = future.result()
                if exc:
                    for idx in indices:
                        req_key = data[idx].get("requirement_key", f"#{idx}")
                        print(f"  DeepSeek [{idx + 1}/{total}] {req_key} FAILED: {exc}")
                        errors += 1
                else:
                    score_by_key = {s.requirement_key: s for s in scores}
                    for idx in indices:
                        req_key = data[idx].get("requirement_key", f"#{idx}")
                        s = score_by_key.get(req_key)
                        if s:
                            results[idx] = [s]
                            _print_requirement_score(idx, total, req_key, s)
                        else:
                            _print_requirement_score(idx, total, req_key, None)
                            errors += 1
                sys.stdout.flush()
            except Exception as exc:
                for idx in indices:
                    req_key = data[idx].get("requirement_key", f"#{idx}")
                    print(f"  DeepSeek [{idx + 1}/{total}] {req_key} FAILED: {exc}")
                    errors += 1
                sys.stdout.flush()

    all_scores: list[RequirementScore] = []
    for i in sorted(results.keys()):
        all_scores.extend(results[i])

    return all_scores, errors


def evaluate_round(
    round_dir: Path,
    model: str = DEFAULT_MODEL,
    delay: float = 0.1,
    max_concurrency: int = 5,
) -> EvalResult:
    """Score all requirement groups in a round using DeepSeek API.

    Requirements are scored in parallel with up to max_concurrency workers.
    """
    cases_path = round_dir / "generated_cases.json"
    if not cases_path.exists():
        raise FileNotFoundError(f"generated_cases.json not found in {round_dir}")

    checklist_path = _PROJECT_ROOT / "optimization_runs" / "checklist_v2.md"
    if not checklist_path.exists():
        raise FileNotFoundError(f"Checklist not found: {checklist_path}")

    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    system_prompt = _build_system_prompt(checklist_path.read_text(encoding="utf-8"))
    result = EvalResult(model_used=model)

    result.requirements, result.errors = _score_requirements_parallel(
        data, system_prompt, model,
        batch_size=5,
        max_concurrency=max_concurrency,
        submit_delay=delay,
    )

    return result


# -- Persistence ----------------------------------------------------------

def _validate_scores(result: EvalResult) -> None:
    """Raise ValueError if any requirement or case has invalid scores."""
    for req in result.requirements:
        if req.requirement_key == "":
            raise ValueError("Requirement score missing requirement_key")
        if not (1 <= req.coverage_value <= 5):
            raise ValueError(
                f"Requirement '{req.requirement_key}': coverage_value={req.coverage_value} (must be 1-5)"
            )
        for cs in req.cases:
            if cs.case_index < 0:
                raise ValueError(f"Requirement '{req.requirement_key}': case missing case_index")
            for dim in CASE_LEVEL_DIMS:
                val = getattr(cs, dim)
                if not (1 <= val <= 5):
                    raise ValueError(
                        f"Case '{req.requirement_key}'[{cs.case_index}]: "
                        f"{dim}={val} (must be 1-5)"
                    )


def save_evaluation(result: EvalResult, round_dir: Path, evaluator_name: str = "deepseek") -> Path:
    """Save 8-dimension scores to {evaluator_name}_evaluation.json."""
    _validate_scores(result)

    requirements_payload = []
    flat_cases = []
    for req in result.requirements:
        case_payload = [
            cs.to_dict()
            for cs in req.cases
        ]
        requirements_payload.append({
            "requirement_key": req.requirement_key,
            "coverage_value": req.coverage_value,
            "coverage_value_note": req.coverage_value_note,
            "case_dimension_averages": req.case_dimension_averages,
            "case_dimension_mins": req.case_dimension_mins,
            "weighted_score": req.weighted_score,
            "cases": case_payload,
        })
        flat_cases.extend(
            cs.to_dict(
                coverage_value=req.coverage_value,
                coverage_value_note=req.coverage_value_note,
            )
            for cs in req.cases
        )

    output = {
        "schema_version": "score-v2-8d",
        "checklist_version": "checklist_v2.md",
        "evaluated_by": evaluator_name,
        "model": result.model_used,
        "weights": WEIGHTS,
        "total_requirements": result.total_requirements,
        "total_cases": result.total_cases,
        "errors": result.errors,
        "dimension_averages": result.dimension_averages,
        "dimension_mins": result.dimension_mins,
        "overall_weighted": result.overall_weighted,
        "requirements": requirements_payload,
        "cases": flat_cases,
    }

    out_path = round_dir / f"{evaluator_name}_evaluation.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path}")
    return out_path


def run_full_evaluation(
    round_dir: Path,
    model: str = DEFAULT_MODEL,
    delay: float = 0.1,
    max_concurrency: int = 5,
) -> float:
    """Run DeepSeek 8-dimension scoring and save to deepseek_evaluation.json.

    Returns the overall weighted score (0.0-5.0).
    """
    result = evaluate_round(round_dir, model=model, delay=delay, max_concurrency=max_concurrency)
    save_evaluation(result, round_dir, evaluator_name="deepseek")

    avgs = result.dimension_averages
    print(
        f"\nDone. DeepSeek weighted={result.overall_weighted} "
        f"(align={avgs.get('requirement_alignment', 0)}, "
        f"info={avgs.get('information_integrity', 0)}, "
        f"exec={avgs.get('executability', 0)}, obs={avgs.get('observability', 0)}, "
        f"cov={avgs.get('coverage_value', 0)})"
    )
    return result.overall_weighted
