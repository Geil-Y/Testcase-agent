"""CLI for evaluation and legacy optimization helpers.

The old batch generation command has been removed. Use
``python -m testcase_agent.review_pipeline.cli`` for new clarification-first generation runs.
Existing report/evaluation helpers remain for reading completed rounds.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

# Add project root to path so we can import testcase_agent
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from openpyxl import load_workbook  # noqa: E402

from testcase_agent.review_pipeline.artifacts.models import RequirementInput  # noqa: E402

_VALID_CATEGORIES = {"signal", "threshold", "timing", "state", "observation"}


def _cell_str(row: tuple, index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    val = row[index]
    return str(val).strip() if val is not None else ""


def read_excel(
    file_path: str,
    requirement_key_col: str,
    description_col: str,
    type_col: str,
    function_name_col: str,
) -> list[dict]:
    """Read all rows from Excel, returning list with type preserved."""
    wb = load_workbook(file_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    headers = [str(c.value) if c.value is not None else "" for c in ws[1]]
    wb.close()

    key_idx = headers.index(requirement_key_col) if requirement_key_col in headers else -1
    desc_idx = headers.index(description_col) if description_col in headers else -1
    type_idx = headers.index(type_col) if type_col in headers else -1
    func_idx = headers.index(function_name_col) if function_name_col in headers else -1

    results: list[dict] = []
    for row_idx, row in enumerate(rows, start=2):
        req_type = _cell_str(row, type_idx)
        results.append({
            "requirement_key": _cell_str(row, key_idx),
            "description": _cell_str(row, desc_idx),
            "type": req_type,
            "function_name": _cell_str(row, func_idx),
            "source_row": row_idx,
        })
    return results


def build_requirement_inputs(rows: list[dict]) -> list[RequirementInput]:
    """Convert rows to RequirementInput list, injecting heading/info context.

    Only rows with type='Requirement' produce a RequirementInput.
    Each requirement gets its preceding headings (hierarchy stack) and info rows
    as supplementary context.
    """
    heading_stack: list[str] = []
    pending_info: list[str] = []
    inputs: list[RequirementInput] = []

    for row in rows:
        row_type = row["type"].lower()

        if row_type == "heading":
            # Reset or update heading hierarchy based on heading text
            heading_text = row["description"]
            # Simple hierarchy tracking: if it starts with a lower number, it's a new section
            heading_stack.append(heading_text)
            pending_info.clear()

        elif row_type == "info":
            pending_info.append(row["description"])

        elif row_type in ("requirement", ""):
            # Build context
            context_parts: list[str] = []
            if heading_stack:
                context_parts.append("Section: " + " > ".join(heading_stack))
            if pending_info:
                context_parts.append("Context: " + " | ".join(pending_info))

            # If the requirement has a function_name, note it
            if row.get("function_name"):
                context_parts.insert(0, f"Function: {row['function_name']}")

            inputs.append(RequirementInput(
                requirement_key=row["requirement_key"],
                description=row["description"],
                function_name=row.get("function_name", ""),
                supplementary_info="\n".join(context_parts) if context_parts else "",
            ))

            # Don't clear heading_stack on requirement — same section may have more reqs
            pending_info.clear()

    return inputs


def sample_requirements(
    inputs: list[RequirementInput],
    sample_size: int,
    seed: int | None = None,
) -> list[RequirementInput]:
    """Randomly sample requirements."""
    if seed is not None:
        random.seed(seed)
    if len(inputs) <= sample_size:
        return inputs[:]
    return random.sample(inputs, sample_size)


# ── Requirement set loading ──────────────────────────────────────────────


def load_requirement_set(path: str) -> dict:
    """Load and validate a requirement set JSON file.

    Returns the parsed dict on success. Raises ValueError with a
    human-readable message on failure.
    """
    set_path = Path(path)
    if not set_path.exists():
        raise ValueError(f"Requirement set file not found: {path}")

    try:
        data = json.loads(set_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Requirement set file is not valid JSON: {exc}") from exc

    validate_requirement_set(data, path)
    return data


def validate_requirement_set(data: dict, path: str) -> None:
    """Validate a loaded requirement set dict in-place. Raises ValueError."""
    if not isinstance(data, dict):
        raise ValueError(f"Requirement set must be a JSON object, got {type(data).__name__}")

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Requirement set is missing a non-empty 'name' field")

    entries = data.get("entries")
    if not isinstance(entries, list) or len(entries) == 0:
        raise ValueError(f"Requirement set '{name}' has no 'entries' list")

    keys_seen: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {i} in '{name}' is not a JSON object")

        key = entry.get("requirement_key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"Entry {i} in '{name}' is missing a valid 'requirement_key'")

        if key in keys_seen:
            raise ValueError(f"Duplicate requirement_key '{key}' at entry {i} in '{name}'")
        keys_seen.add(key)

        bucket = entry.get("evaluation_bucket")
        if not isinstance(bucket, str) or not bucket.strip():
            raise ValueError(f"Entry '{key}' in '{name}' is missing 'evaluation_bucket'")

        cats = entry.get("expected_missing_categories")
        if not isinstance(cats, list):
            raise ValueError(
                f"Entry '{key}' in '{name}': 'expected_missing_categories' must be a list"
            )
        invalid = [c for c in cats if c not in _VALID_CATEGORIES]
        if invalid:
            raise ValueError(
                f"Entry '{key}' in '{name}': invalid expected_missing_categories {invalid}. "
                f"Allowed: {sorted(_VALID_CATEGORIES)}"
            )

        # Validate inline content (only required for self-contained sets)
        desc = entry.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            raise ValueError(
                f"Entry '{key}' in '{name}' is missing 'description'. "
                f"Requirement sets must be self-contained with inline content."
            )


def build_requirements_from_set(req_set_data: dict) -> list[RequirementInput]:
    """Build RequirementInput list directly from a self-contained requirement set.

    Each entry must have: requirement_key, description.
    Optional: function_name, supplementary_info.
    """
    selected: list[RequirementInput] = []
    for entry in req_set_data["entries"]:
        selected.append(RequirementInput(
            requirement_key=entry["requirement_key"],
            description=entry["description"],
            function_name=entry.get("function_name", ""),
            supplementary_info=entry.get("supplementary_info", ""),
        ))
    return selected


def select_by_requirement_set(
    all_inputs: list[RequirementInput],
    req_set_data: dict,
) -> list[RequirementInput]:
    """Select and order RequirementInputs by a requirement set from Excel.

    Preserves the order in the set. Raises ValueError if any requirement
    key in the set is not found in all_inputs.

    Only used when --excel is provided alongside --requirement-set.
    """
    lookup: dict[str, RequirementInput] = {
        ri.requirement_key: ri for ri in all_inputs
    }
    entries = req_set_data["entries"]
    selected: list[RequirementInput] = []
    missing: list[str] = []

    for entry in entries:
        key = entry["requirement_key"]
        req = lookup.get(key)
        if req is None:
            missing.append(key)
        else:
            selected.append(req)

    if missing:
        raise ValueError(
            f"{len(missing)} requirement key(s) from the set not found in Excel: "
            + ", ".join(missing)
        )

    return selected


# ── Core pipeline ────────────────────────────────────────────────────────


def archive_prompts(round_dir: Path) -> None:
    """Copy current review-pipeline prompt files into round_dir/prompts/."""
    prompts_dir = round_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    project_root = Path(__file__).resolve().parents[1]
    source_dir = project_root / "src" / "testcase_agent" / "review_pipeline" / "prompts"

    for src in sorted(source_dir.glob("*.html")):
        # Strip .html extension for the archived copy.
        dest_name = src.stem + ".md"
        shutil.copy2(src, prompts_dir / dest_name)
        print(f"  Archived prompt: {src.name} -> {dest_name}")


def _serialize_case_for_output(
    case,
    report,
    *,
    sanitize_enabled: bool,
    sanitize_replacements: list[str],
) -> dict:
    """Serialize one generated case for generated_cases.json."""
    return {
        "title": case.title,
        "objective": case.objective,
        "precondition": case.precondition,
        "postcondition": case.postcondition,
        "related_requirement": case.related_requirement,
        "steps": [
            {"order": s.order, "action": s.action, "expected": s.expected}
            for s in case.steps
        ],
        "raw_html": case.raw_html,
        "sanitize": {
            "enabled": sanitize_enabled,
            "replacement_count": len(sanitize_replacements),
            "replacements": sanitize_replacements,
        },
        "quality": {
            "passed": report.passed,
            "failures": report.failures,
            "warnings": report.warnings,
        },
    }


def run_batch(
    requirements: list[RequirementInput],
    output_dir: Path,
    sanitize: bool = False,
    requirement_set_data: dict | None = None,
    run_eval: bool = False,
) -> dict:
    """Legacy batch generation entry point.

    Kept only as an importable guard for older helper code. New generation must
    start from ``python -m testcase_agent.review_pipeline.cli prepare-clarification-review``.
    """
    raise RuntimeError(
        "optimization.cli run_batch was removed with the legacy generation "
        "pipeline. Use python -m testcase_agent.review_pipeline.cli for generation."
    )


def main():
    parser = argparse.ArgumentParser(description="Testcase Agent optimization CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = sub.add_parser("run", help="Generate cases for sampled requirements")
    run_parser.add_argument("--excel", default=None, help="Path to Excel requirements file (optional if --requirement-set provides inline content)")
    run_parser.add_argument("--output-dir", required=True, help="Output directory for this round")
    run_parser.add_argument("--sample", type=int, default=20, help="Number of requirements to sample (default: 20, ignored with --requirement-set)")
    run_parser.add_argument("--seed", type=int, default=None, help="Random seed for sampling (for reproducibility)")
    run_parser.add_argument("--requirement-set", default=None, help="Path to a requirement set JSON file (e.g. prompt_eval_v1.json)")
    run_parser.add_argument("--key-col", default="Requirement ID")
    run_parser.add_argument("--desc-col", default="Requirement Description")
    run_parser.add_argument("--type-col", default="Type")
    run_parser.add_argument("--func-col", default="function")
    run_parser.add_argument("--limit", type=int, default=None, help="Limit to first N requirements (for quick testing, works with --requirement-set)")
    run_parser.add_argument("--no-sanitize", action="store_true", help="Disable post-processing that replaces invented numeric values with [NEEDS REVIEW] (sanitize is ON by default)")
    run_parser.add_argument("--eval", action="store_true", help="Run DeepSeek 8-dimension evaluation after generation and generate complete report")

    # evaluate command
    eval_parser = sub.add_parser("evaluate", help="Run AI evaluation against checklist_v2.md")
    eval_parser.add_argument("--round-dir", required=True, help="Path to a round directory containing generated_cases.json")
    eval_parser.add_argument("--model", default=None, help="Model ID (default: from ANTHROPIC_MODEL env or deepseek-v4-flash[1m])")
    eval_parser.add_argument("--delay", type=float, default=0.5, help="Seconds between API calls (default: 0.5)")
    eval_parser.add_argument("--report", action="store_true", help="Regenerate cases_report.html from existing evaluation files")

    args = parser.parse_args()

    if args.command == "run":
        parser.error(
            "optimization.cli run was removed with the legacy generation "
            "pipeline. Use python -m testcase_agent.review_pipeline.cli "
            "prepare-clarification-review instead."
        )

    elif args.command == "evaluate":
        round_dir = Path(args.round_dir)
        if not round_dir.is_absolute():
            round_dir = _PROJECT_ROOT / round_dir

        if args.report:
            from optimization.generate_case_html import generate_round_html
            generate_round_html(round_dir, 1)
        else:
            from optimization.claude_evaluator import DEFAULT_MODEL, run_full_evaluation
            run_full_evaluation(
                round_dir,
                model=args.model or DEFAULT_MODEL,
                delay=args.delay,
            )


if __name__ == "__main__":
    main()
