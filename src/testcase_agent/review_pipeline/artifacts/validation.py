"""Validation for the simplified reviewed pipeline.

Downstream stages require reviewed artifacts and block on ``blocking_gaps``.
Legacy artifacts are detected and rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationError:
    artifact_path: str
    field_path: str
    message: str


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, artifact_path: str, field_path: str, message: str) -> None:
        self.errors.append(ValidationError(artifact_path, field_path, message))

    def format_errors(self) -> str:
        lines: list[str] = []
        for e in self.errors:
            lines.append(f"{e.artifact_path}: {e.field_path}: {e.message}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy artifact detection
# ═══════════════════════════════════════════════════════════════════════════════

_LEGACY_ARTIFACT_NAMES = frozenset({
    "clarification_review.json",
    "clarified_test_basis.json",
    "case_intent_review.json",
    "approved_case_plan.json",
})


def is_legacy_run_dir(run_dir: str | Path) -> bool:
    """Check whether a run directory contains legacy artifacts."""
    p = Path(run_dir)
    for name in _LEGACY_ARTIFACT_NAMES:
        if (p / name).exists():
            return True
    return False


def get_legacy_unsupported_message(run_dir: str | Path) -> str:
    """Human-readable message explaining that a legacy run cannot proceed."""
    p = Path(run_dir)
    found = [name for name in _LEGACY_ARTIFACT_NAMES if (p / name).exists()]
    names = ", ".join(found) if found else "unknown legacy artifacts"
    return (
        f"Run directory {p.name} contains legacy artifacts ({names}) "
        f"that are not supported by the simplified pipeline. "
        f"Please regenerate this run through the new artifact flow."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Reviewed-artifact validation
# ═══════════════════════════════════════════════════════════════════════════════

_REQUIRED_REVIEWED_ARTIFACTS = {
    # downstream_stage -> required reviewed artifact
    "plan_intents": "reviewed_extracted_test_basis.json",
    "write_cases": "reviewed_extracted_test_basis.json",
    "write_cases_intents": "reviewed_case_intents.json",
}


def validate_reviewed_artifact(
    artifact_path: str | Path,
    *,
    artifact_label: str = "",
) -> ValidationResult:
    """Check that a reviewed artifact exists and has no blocking_gaps."""
    result = ValidationResult()
    p = Path(artifact_path)
    label = artifact_label or p.name

    if not p.exists():
        result.add_error(str(p), "exists",
                         f"Reviewed artifact '{label}' is required but missing. "
                         f"Run Accept All on the upstream stage first.")
        return result

    try:
        from .io import read_json
        data = read_json(p)
    except Exception as exc:
        result.add_error(str(p), "read", f"Cannot read '{label}': {exc}")
        return result

    blocking = data.get("blocking_gaps", [])
    if blocking:
        result.add_error(str(p), "blocking_gaps",
                         f"'{label}' has blocking gaps that prevent downstream stages: "
                         f"{'; '.join(blocking)}")
    return result


def validate_accept_all_no_blocking_gaps(
    unreviewed_path: str | Path,
    *,
    artifact_label: str = "",
) -> ValidationResult:
    """Check that Accept All is not attempted when the artifact has blocking_gaps."""
    result = ValidationResult()
    p = Path(unreviewed_path)
    label = artifact_label or p.name

    if not p.exists():
        result.add_error(str(p), "exists",
                         f"Artifact '{label}' does not exist.")
        return result

    try:
        from .io import read_json
        data = read_json(p)
    except Exception as exc:
        result.add_error(str(p), "read", f"Cannot read '{label}': {exc}")
        return result

    blocking = data.get("blocking_gaps", [])
    if blocking:
        result.add_error(str(p), "blocking_gaps",
                         f"Cannot Accept All: '{label}' has blocking gaps. "
                         f"Review and remove them first: {'; '.join(blocking)}")
    return result


def validate_downstream_run(run_dir: str | Path, stage: str) -> ValidationResult:
    """Full downstream validation: check legacy status and required reviewed artifacts."""
    result = ValidationResult()
    p = Path(run_dir)

    # Legacy check
    if is_legacy_run_dir(p):
        result.add_error(str(p), "legacy", get_legacy_unsupported_message(p))
        return result

    # Required reviewed artifact check
    required = _REQUIRED_REVIEWED_ARTIFACTS.get(stage)
    if required:
        artifact_result = validate_reviewed_artifact(
            p / required, artifact_label=required)
        result.errors.extend(artifact_result.errors)

    return result
