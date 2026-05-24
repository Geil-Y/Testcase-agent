"""Validation scaffolding with human-readable errors."""

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
