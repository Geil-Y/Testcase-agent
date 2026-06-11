"""File-backed storage for versioned Learned Prompt Sets."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .contracts import (
    LEARNED_PROMPT_FILES,
    LearnedPromptSetMeta,
    LearnedPromptSetVersion,
    LearnedPromptFile,
    LearnedPromptStageGroup,
    ParsedSummary,
    DataIssue,
)


def _default_root() -> Path:
    """Default root directory for learned prompt sets."""
    return Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "learned"


def _generate_version(created_at: str, root: Path) -> str:
    """Generate a unique version folder name from timestamp.

    Adds a short suffix ("-2", "-3", ...) on collision.
    """
    base = created_at.replace(":", "").replace("-", "").replace("T", "-")
    # e.g. "20260611-143000"
    base = base[:15]  # keep it concise
    if not (root / base).exists():
        return base
    for i in range(2, 100):
        candidate = f"{base}-{i}"
        if not (root / candidate).exists():
            return candidate
    raise RuntimeError("Cannot generate unique version name")


def _serialize_summary(summary: ParsedSummary) -> dict:
    return {
        "requirementCount": summary.requirement_count,
        "refTestCaseCount": summary.ref_test_case_count,
        "validLinkCount": summary.valid_link_count,
        "noTestRequirementCount": summary.no_test_requirement_count,
        "styleOnlyCaseCount": summary.style_only_case_count,
        "dataIssueCount": summary.data_issue_count,
        "dataIssues": [
            {
                "fileType": i.file_type,
                "sheet": i.sheet,
                "row": i.row,
                "issueType": i.issue_type,
                "message": i.message,
            }
            for i in summary.data_issues
        ],
    }


def save_learned_prompt_set(
    meta: LearnedPromptSetMeta,
    rationale: str,
    prompt_files: dict[str, str],  # filename -> content
    *,
    root: Optional[Path] = None,
) -> str:
    """Atomically save a Learned Prompt Set version.

    Writes to a temporary folder first, then renames to the official version
    folder. Returns the version folder name.
    """
    base = root or _default_root()
    base.mkdir(parents=True, exist_ok=True)

    if meta.version:
        version = meta.version
    else:
        version = _generate_version(meta.created_at, base)

    target = base / version
    if target.exists():
        # If target somehow exists after generate_version, add suffix
        version = _generate_version(meta.created_at, base)
        target = base / version

    tmp = base / f".tmp-{version}"
    if tmp.exists():
        shutil.rmtree(tmp)

    try:
        tmp.mkdir(parents=True)

        # Write metadata.json
        meta_dict = {
            "version": version,
            "createdAt": meta.created_at,
            "provider": meta.provider,
            "model": meta.model,
        }
        if meta.learning_instruction:
            meta_dict["learningInstruction"] = meta.learning_instruction
        meta_dict["summary"] = _serialize_summary(meta.summary)
        (tmp / "metadata.json").write_text(
            json.dumps(meta_dict, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Write rationale.md
        (tmp / "rationale.md").write_text(rationale, encoding="utf-8")

        # Write prompt files
        for filename, content in prompt_files.items():
            (tmp / filename).write_text(content, encoding="utf-8")

        # Atomic rename
        os.replace(tmp, target)
        return version
    except Exception:
        if tmp.exists():
            shutil.rmtree(tmp)
        raise


def list_versions(*, root: Optional[Path] = None) -> list[LearnedPromptSetMeta]:
    """List all official Learned Prompt Set versions, newest first."""
    base = root or _default_root()
    if not base.exists():
        return []

    versions: list[tuple[str, LearnedPromptSetMeta]] = []
    for entry in sorted(base.iterdir(), reverse=True):
        if not entry.is_dir() or entry.name.startswith(".tmp-"):
            continue
        meta_file = entry / "metadata.json"
        if not meta_file.exists():
            continue
        try:
            meta = _read_meta(entry.name, meta_file)
            versions.append((entry.name, meta))
        except (json.JSONDecodeError, KeyError):
            continue

    # Sort by created_at descending
    versions.sort(key=lambda v: v[1].created_at, reverse=True)
    return [m for _, m in versions]


def read_version(
    version: str, *, root: Optional[Path] = None
) -> Optional[LearnedPromptSetVersion]:
    """Read a full Learned Prompt Set version including all prompt files."""
    base = root or _default_root()
    vdir = base / version
    if not vdir.is_dir():
        return None

    meta_file = vdir / "metadata.json"
    if not meta_file.exists():
        return None

    try:
        meta = _read_meta(version, meta_file)
    except (json.JSONDecodeError, KeyError):
        return None

    rationale = (vdir / "rationale.md").read_text(encoding="utf-8")

    # Group prompt files by ABC stage
    stage_defs = [
        ("A", "Analyze Test Basis", "analyze_test_basis"),
        ("B", "Plan Case Intents", "plan_case_intents"),
        ("C", "Generate Case", "generate_case"),
    ]
    groups: list[LearnedPromptStageGroup] = []
    for stage, label, prefix in stage_defs:
        sys_file = vdir / f"{prefix}.system.html"
        usr_file = vdir / f"{prefix}.user.html"
        groups.append(LearnedPromptStageGroup(
            stage=stage,
            stage_label=label,
            system_prompt=LearnedPromptFile(
                filename=f"{prefix}.system.html",
                content=sys_file.read_text(encoding="utf-8") if sys_file.exists() else "",
            ),
            user_prompt=LearnedPromptFile(
                filename=f"{prefix}.user.html",
                content=usr_file.read_text(encoding="utf-8") if usr_file.exists() else "",
            ),
        ))

    return LearnedPromptSetVersion(
        meta=meta,
        rationale=rationale,
        prompt_groups=groups,
    )


def _read_meta(version: str, meta_file: Path) -> LearnedPromptSetMeta:
    raw = json.loads(meta_file.read_text(encoding="utf-8"))
    summary_raw = raw.get("summary", {})
    data_issues = [
        DataIssue(
            file_type=i["fileType"],
            sheet=i["sheet"],
            row=i.get("row"),
            issue_type=i["issueType"],
            message=i["message"],
        )
        for i in summary_raw.get("dataIssues", [])
    ]
    return LearnedPromptSetMeta(
        version=version,
        created_at=raw["createdAt"],
        provider=raw["provider"],
        model=raw["model"],
        learning_instruction=raw.get("learningInstruction"),
        summary=ParsedSummary(
            requirement_count=summary_raw.get("requirementCount", 0),
            ref_test_case_count=summary_raw.get("refTestCaseCount", 0),
            valid_link_count=summary_raw.get("validLinkCount", 0),
            no_test_requirement_count=summary_raw.get("noTestRequirementCount", 0),
            style_only_case_count=summary_raw.get("styleOnlyCaseCount", 0),
            data_issue_count=summary_raw.get("dataIssueCount", 0),
            data_issues=data_issues,
        ),
    )
