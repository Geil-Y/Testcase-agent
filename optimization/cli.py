"""CLI for batch generation and optimization loop support.

Usage:
    python -m optimization.cli run \
        --excel path/to/requirements.xlsx \
        --sample 20 \
        --output-dir optimization_runs/run_20260518_140000/round_01

    python -m optimization.cli run \
        --excel path/to/requirements.xlsx \
        --requirement-set optimization_runs/requirement_sets/prompt_eval_v1.json \
        --output-dir optimization_runs/run_20260519_eval/round_01

The script:
1. Reads the Excel, separating heading/info rows (kept as context) from requirement rows.
2. Selects requirements via random --sample or a fixed --requirement-set.
3. Injects preceding heading/info as supplementary context.
4. Saves current prompt files to <round_dir>/prompts/ for archival.
5. Runs the pipeline for each requirement.
6. Saves generated_cases.json in the round directory.
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

from openpyxl import load_workbook

from testcase_agent.config import get_settings
from testcase_agent.pipeline.generate import RequirementInput, run_pipeline
from testcase_agent.pipeline.post_process import sanitize_numeric_values
from testcase_agent.provider.factory import create_provider
from testcase_agent.quality.gate import evaluate_cases

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

            existing_supp = ""
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
        raise ValueError(f"Requirement set is missing a non-empty 'name' field")

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


def select_by_requirement_set(
    all_inputs: list[RequirementInput],
    req_set_data: dict,
) -> list[RequirementInput]:
    """Select and order RequirementInputs by a requirement set.

    Preserves the order in the set. Raises ValueError if any requirement
    key in the set is not found in all_inputs.
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
    """Copy current prompt files into round_dir/prompts/ for archival."""
    prompts_dir = round_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    project_root = Path(__file__).resolve().parents[1]
    source_dir = project_root / "prompts"

    for src in sorted(source_dir.glob("*.html")):
        # Strip .html extension for the archived copy (e.g. generate_case.system.html -> generate_case.system.md)
        dest_name = src.stem + ".md"
        shutil.copy2(src, prompts_dir / dest_name)
        print(f"  Archived prompt: {src.name} -> {dest_name}")


def run_batch(
    requirements: list[RequirementInput],
    output_dir: Path,
    sanitize: bool = False,
    requirement_set_data: dict | None = None,
) -> dict:
    """Run pipeline for all requirements and save results.

    When requirement_set_data is provided, each requirement entry in
    generated_cases.json is enriched with evaluation_bucket,
    expected_missing_categories, and requirement_set_note from the set.
    """
    settings = get_settings()
    provider = create_provider(settings)

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_prompts(output_dir)

    # Build per-key lookup from the set if provided
    set_lookup: dict[str, dict] = {}
    if requirement_set_data:
        for entry in requirement_set_data["entries"]:
            set_lookup[entry["requirement_key"]] = entry

    all_results: list[dict] = []
    total_cases = 0
    errors: list[dict] = []

    for i, req in enumerate(requirements):
        print(f"[{i+1}/{len(requirements)}] Generating: {req.requirement_key} ...")
        result = run_pipeline(req, provider)

        if result.error:
            errors.append({
                "requirement_key": req.requirement_key,
                "error": result.error,
            })
            print(f"  ERROR: {result.error}")
            continue

        if sanitize and result.analysis:
            sigs = result.analysis.signals
            thr = result.analysis.thresholds
            tim = result.analysis.timing
            sanitized_cases = []
            total_replacements = 0
            for case in result.cases:
                sc, reps = sanitize_numeric_values(
                    case,
                    requirement_description=req.description,
                    supplementary_info=req.supplementary_info,
                    extracted_signals=sigs,
                    extracted_thresholds=thr,
                    extracted_timing=tim,
                )
                sanitized_cases.append(sc)
                total_replacements += len(reps)
            result.cases = sanitized_cases
            if total_replacements:
                print(f"  sanitize: {total_replacements} value(s) replaced with [NEEDS REVIEW]")

        quality_reports = evaluate_cases(result.cases)

        analysis_data = None
        if result.analysis:
            analysis_data = {
                "signals": result.analysis.signals,
                "thresholds": result.analysis.thresholds,
                "timing": result.analysis.timing,
                "states": result.analysis.states,
                "observations": result.analysis.observations,
                "direction": result.analysis.direction,
                "missing_critical_info": result.analysis.missing_critical_info,
                "missing_info_items": [
                    {"category": mi.category, "description": mi.description}
                    for mi in result.analysis.missing_info_items
                ],
                "case_intents": [
                    {"coverage": ci.coverage, "description": ci.description}
                    for ci in result.analysis.case_intents
                ],
            }

        cases_data = []
        for case, report in zip(result.cases, quality_reports):
            cases_data.append({
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
                "quality": {
                    "passed": report.passed,
                    "failures": report.failures,
                    "warnings": report.warnings,
                },
            })

        entry: dict = {
            "requirement_key": req.requirement_key,
            "function_name": req.function_name,
            "description": req.description,
            "supplementary_info": req.supplementary_info,
            "analysis": analysis_data,
            "cases": cases_data,
        }
        # Enrich with requirement set metadata when available
        set_meta = set_lookup.get(req.requirement_key)
        if set_meta:
            entry["evaluation_bucket"] = set_meta["evaluation_bucket"]
            entry["expected_missing_categories"] = set_meta["expected_missing_categories"]
            entry["requirement_set_note"] = set_meta.get("rationale", "")
        all_results.append(entry)
        total_cases += len(cases_data)
        print(f"  {len(cases_data)} cases generated, quality passed: {all(report.passed for report in quality_reports)}")

    # Save generated cases
    cases_path = output_dir / "generated_cases.json"
    cases_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Save sampled requirements list
    req_list = [
        {
            "requirement_key": r.requirement_key,
            "description": r.description,
            "function_name": r.function_name,
        }
        for r in requirements
    ]
    req_path = output_dir / "sampled_requirements.json"
    req_path.write_text(
        json.dumps(req_list, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary: dict = {
        "total_requirements": len(requirements),
        "total_cases": total_cases,
        "errors": len(errors),
        "error_details": errors,
    }
    if requirement_set_data:
        summary["requirement_set_name"] = requirement_set_data.get("name", "")
        summary["requirement_set_path"] = str(
            requirement_set_data.get("_source_path", "")
        )
        summary["total_requirement_set_entries"] = len(
            requirement_set_data.get("entries", [])
        )
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nDone. {len(requirements)} requirements → {total_cases} cases, {len(errors)} errors")
    print(f"Output: {output_dir}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Testcase Agent optimization CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = sub.add_parser("run", help="Generate cases for sampled requirements")
    run_parser.add_argument("--excel", required=True, help="Path to Excel requirements file")
    run_parser.add_argument("--output-dir", required=True, help="Output directory for this round")
    run_parser.add_argument("--sample", type=int, default=20, help="Number of requirements to sample (default: 20, ignored with --requirement-set)")
    run_parser.add_argument("--seed", type=int, default=None, help="Random seed for sampling (for reproducibility)")
    run_parser.add_argument("--requirement-set", default=None, help="Path to a requirement set JSON file (e.g. prompt_eval_v1.json)")
    run_parser.add_argument("--key-col", default="Requirement ID")
    run_parser.add_argument("--desc-col", default="Requirement Description")
    run_parser.add_argument("--type-col", default="Type")
    run_parser.add_argument("--func-col", default="function")
    run_parser.add_argument("--sanitize", action="store_true", help="Post-process cases to replace invented numeric values with [NEEDS REVIEW]")

    args = parser.parse_args()

    if args.command == "run":
        print(f"Reading: {args.excel}")
        rows = read_excel(
            args.excel,
            requirement_key_col=args.key_col,
            description_col=args.desc_col,
            type_col=args.type_col,
            function_name_col=args.func_col,
        )
        all_inputs = build_requirement_inputs(rows)
        print(f"Parsed {len(all_inputs)} requirements from {len(rows)} total rows")

        requirement_set_data: dict | None = None

        if args.requirement_set:
            set_path = args.requirement_set
            if not Path(set_path).is_absolute():
                # Resolve relative to project root (where the CLI is invoked from)
                set_path = str(_PROJECT_ROOT / set_path)
            requirement_set_data = load_requirement_set(set_path)
            requirement_set_data["_source_path"] = set_path
            name = requirement_set_data["name"]
            count = len(requirement_set_data["entries"])
            print(f"Using requirement set: {name} ({count} entries)")

            selected = select_by_requirement_set(all_inputs, requirement_set_data)
            print(f"Matched {len(selected)}/{count} requirements from set")
        else:
            selected = sample_requirements(all_inputs, args.sample, args.seed)
            print(f"Sampled {len(selected)} requirements (seed={args.seed})")

        run_batch(
            selected,
            Path(args.output_dir),
            sanitize=args.sanitize,
            requirement_set_data=requirement_set_data,
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
