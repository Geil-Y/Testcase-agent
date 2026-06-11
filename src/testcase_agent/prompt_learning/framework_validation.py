"""Prompt Learning Framework Validation.

Validates that learned prompts are compatible with the ABC Pipeline contract:
correct filenames, required template variables, and output format requirements.
"""

from __future__ import annotations

import re

from .contracts import (
    LEARNED_PROMPT_FILES,
    FrameworkValidationError,
    FrameworkValidationResult,
)

# Required Jinja2 template variables for each ABC stage (from pipeline/generate.py)
_REQUIRED_VARS: dict[str, set[str]] = {
    "analyze_test_basis": {"requirement_key", "description"},
    "plan_case_intents": {
        "requirement_key", "description",
        "allowed_signals", "allowed_thresholds", "allowed_timing",
        "allowed_states", "allowed_observations", "missing_info",
    },
    "generate_case": {
        "requirement_key", "description", "supplementary_info",
        "coverage_dimension", "case_intent", "review_comment",
        "extracted_signals", "extracted_thresholds", "extracted_timing",
        "extracted_states", "extracted_observations",
        "missing_info", "missing_info_items",
    },
}

# All valid template variables (including those not required for a given stage)
_ALL_VALID_VARS: dict[str, set[str]] = {
    **{k: set(v) for k, v in _REQUIRED_VARS.items()},
}

# Accumulate superset of all valid variables
_ALL_VALID_VARS["analyze_test_basis"] |= {
    "function_name", "requirement_type", "supplementary_info",
}
_ALL_VALID_VARS["plan_case_intents"] |= {
    "function_name", "requirement_type", "supplementary_info",
}
_ALL_VALID_VARS["generate_case"] |= {
    "function_name", "requirement_type",
}

# Jinja2 variable pattern: {{ variable_name }}
_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# Prohibited variable patterns (variables reserved for the other stages)
# This is a soft approximation — we check that variables in each stage
# are valid for that stage's contract.


def validate_prompt_set(
    prompt_files: dict[str, str],  # filename -> content
) -> FrameworkValidationResult:
    """Validate a learned prompt set against the ABC Pipeline framework.

    Returns a FrameworkValidationResult with all errors found.
    """
    errors: list[FrameworkValidationError] = []

    # 1. Exactly six required files
    present = set(prompt_files.keys())
    required = set(LEARNED_PROMPT_FILES)
    missing = required - present
    extra = present - required
    for f in sorted(missing):
        errors.append(FrameworkValidationError(
            filename=f,
            message=f"Missing required prompt file: {f}",
        ))
    for f in sorted(extra):
        errors.append(FrameworkValidationError(
            filename=f,
            message=f"Unknown prompt file (not in ABC Pipeline): {f}",
        ))

    if missing:
        # Cannot continue validation without files
        return FrameworkValidationResult(valid=False, errors=errors)

    # 2. Check template variables for each stage
    for pair_name, filename_vars in [
        ("analyze_test_basis", ("analyze_test_basis.system.html", "analyze_test_basis.user.html")),
        ("plan_case_intents", ("plan_case_intents.system.html", "plan_case_intents.user.html")),
        ("generate_case", ("generate_case.system.html", "generate_case.user.html")),
    ]:
        sys_file, usr_file = filename_vars
        combined = prompt_files.get(sys_file, "") + "\n" + prompt_files.get(usr_file, "")
        vars_found = set(_VAR_PATTERN.findall(combined))

        required_vars = _REQUIRED_VARS.get(pair_name, set())
        valid_vars = _ALL_VALID_VARS.get(pair_name, set())

        # Check missing required variables
        for var in sorted(required_vars - vars_found):
            errors.append(FrameworkValidationError(
                filename=pair_name,
                message=f"Missing required template variable '{{{{ {var} }}}}'",
            ))

        # Check unknown variables (not in any valid set)
        for var in sorted(vars_found - valid_vars):
            # Allow common variables like 'requirement_key' that might appear
            # in any stage by checking the global superset
            all_valid = set().union(*_ALL_VALID_VARS.values())
            if var not in all_valid:
                errors.append(FrameworkValidationError(
                    filename=pair_name,
                    message=f"Unknown template variable '{{{{ {var} }}}}' — not provided by ABC Pipeline",
                ))

    # 3. LLM-A and LLM-B must require JSON output
    for stage_name, stage_label in [("analyze_test_basis", "LLM-A"), ("plan_case_intents", "LLM-B")]:
        sys_content = prompt_files.get(f"{stage_name}.system.html", "")
        usr_content = prompt_files.get(f"{stage_name}.user.html", "")
        combined = (sys_content + " " + usr_content).lower()
        if "json" not in combined:
            errors.append(FrameworkValidationError(
                filename=stage_name,
                message=f"{stage_label} prompt must require JSON output format",
            ))

    # 4. LLM-C must require <testcase> HTML tag (use angle-bracket form only)
    c_sys = prompt_files.get("generate_case.system.html", "").lower()
    c_usr = prompt_files.get("generate_case.user.html", "").lower()
    if "<testcase" not in c_sys and "<testcase" not in c_usr:
        errors.append(FrameworkValidationError(
            filename="generate_case",
            message="LLM-C prompt must require <testcase> HTML tag output",
        ))

    return FrameworkValidationResult(
        valid=len(errors) == 0,
        errors=errors,
    )
