"""Active Run discovery, naming, status inference, and artifact state."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

_REVIEWS_DIR = Path(__file__).resolve().parents[3] / "reviews"

# Artifact file names in dependency order (upstream to downstream)
_ARTIFACT_ORDER = [
    "00_requirements.json",
    "clarification_review.json",
    "clarified_test_basis.json",
    "case_intent_review.json",
    "approved_case_plan.json",
    "generated_cases.json",
    "evaluation_summary.json",
    "evaluation_results.json",
]

# Each upstream artifact maps to downstream artifacts it invalidates
_DOWNSTREAM_MAP: dict[str, list[str]] = {
    "00_requirements.json": [
        "clarification_review.json",
        "clarified_test_basis.json",
        "case_intent_review.json",
        "approved_case_plan.json",
        "generated_cases.json",
        "evaluation_summary.json",
        "evaluation_results.json",
    ],
    "clarification_review.json": [
        "clarified_test_basis.json",
        "case_intent_review.json",
        "approved_case_plan.json",
        "generated_cases.json",
        "evaluation_summary.json",
        "evaluation_results.json",
    ],
    "clarified_test_basis.json": [
        "case_intent_review.json",
        "approved_case_plan.json",
        "generated_cases.json",
        "evaluation_summary.json",
        "evaluation_results.json",
    ],
    "case_intent_review.json": [
        "approved_case_plan.json",
        "generated_cases.json",
        "evaluation_summary.json",
        "evaluation_results.json",
    ],
    "approved_case_plan.json": [
        "generated_cases.json",
        "evaluation_summary.json",
        "evaluation_results.json",
    ],
    "generated_cases.json": [
        "evaluation_summary.json",
        "evaluation_results.json",
    ],
}

# ── Slug generation ───────────────────────────────────────────────────────


def _slugify(text: str, max_len: int = 40) -> str:
    """Make a filesystem-safe slug from arbitrary text."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9一-鿿]+", "_", slug)  # keep CJK
    slug = slug.strip("_")
    slug = slug[:max_len] if slug else "untitled"
    return slug.rstrip("_")


def _slugify_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", key).strip("_")[:60]


# ── Run naming ────────────────────────────────────────────────────────────


def make_run_name(requirement_key: str, description: str) -> str:
    """Build a timestamped human-readable run directory name."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    key_slug = _slugify_key(requirement_key) if requirement_key else "unknown"
    desc_slug = _slugify(description) if description else "untitled"
    return f"{ts}_run_{key_slug}_{desc_slug}"


def make_run_dir(requirement_key: str, description: str) -> Path:
    """Create a uniquely named run directory, handling collisions."""
    base_name = make_run_name(requirement_key, description)
    run_dir = _REVIEWS_DIR / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    # Collision: append counter
    for i in range(2, 100):
        alt = _REVIEWS_DIR / f"{base_name}_{i}"
        if not alt.exists():
            alt.mkdir(parents=True, exist_ok=True)
            return alt
    raise RuntimeError(f"Too many collisions for run name: {base_name}")


# ── Run input artifact ────────────────────────────────────────────────────


def write_run_input(run_dir: Path, requirement: dict[str, Any]) -> None:
    """Write the single-Requirement input artifact for a new Active Run."""
    req_input = {
        "requirement_key": requirement["requirement_key"],
        "description": requirement.get("description", ""),
        "function_name": requirement.get("function_name", ""),
        "requirement_type": requirement.get("requirement_type", ""),
        "supplementary_info": requirement.get("supplementary_info", ""),
    }
    (run_dir / "00_requirements.json").write_text(
        json.dumps([req_input], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Run discovery ─────────────────────────────────────────────────────────


def discover_runs() -> list[dict[str, Any]]:
    """Discover all run directories (new and old-style) from the reviews area."""
    if not _REVIEWS_DIR.exists():
        return []
    runs: list[dict[str, Any]] = []
    for d in sorted(_REVIEWS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        if d.name == "imports":
            continue
        info = _read_run_info(d)
        if info is not None:
            runs.append(info)
    return runs


def get_runs_for_requirement(requirement_key: str) -> list[dict[str, Any]]:
    """Find all historical runs for a given requirement key."""
    runs = discover_runs()
    return [
        r for r in runs
        if r.get("requirement_key") == requirement_key
    ]


def get_latest_run(requirement_key: str) -> dict[str, Any] | None:
    """Return the latest run for a requirement, or None."""
    runs = get_runs_for_requirement(requirement_key)
    return runs[0] if runs else None


def get_run(run_dir_name: str) -> dict[str, Any] | None:
    """Get info for a specific run directory."""
    run_dir = _REVIEWS_DIR / run_dir_name
    if not run_dir.is_dir():
        return None
    return _read_run_info(run_dir)


def _read_run_info(run_dir: Path) -> dict[str, Any] | None:
    """Read run metadata from its input artifact, not its directory name."""
    req_file = run_dir / "00_requirements.json"
    if not req_file.exists():
        return None

    try:
        reqs = json.loads(req_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if not reqs:
        return None

    # Support both single-requirement and multi-requirement input files
    first_req = reqs[0] if isinstance(reqs, list) else reqs

    status, status_detail = _infer_run_status(run_dir, reqs)

    return {
        "run_dir": run_dir.name,
        "run_path": str(run_dir),
        "requirement_key": first_req.get("requirement_key", "unknown"),
        "description": first_req.get("description", ""),
        "function_name": first_req.get("function_name", ""),
        "requirement_count": len(reqs) if isinstance(reqs, list) else 1,
        "status": status,
        "status_detail": status_detail,
        "created_at": _dir_creation_time(run_dir),
        "is_old_style": bool(re.match(r"^run_\d+$", run_dir.name)),
        "artifacts": _list_active_artifacts(run_dir),
    }


def _dir_creation_time(run_dir: Path) -> str:
    """Best-effort creation timestamp."""
    req_file = run_dir / "00_requirements.json"
    try:
        return datetime.fromtimestamp(req_file.stat().st_mtime).isoformat()
    except OSError:
        return datetime.now().isoformat()


# ── Run status inference ──────────────────────────────────────────────────


def _infer_run_status(run_dir: Path, _reqs: list) -> tuple[str, str]:
    """Infer run status from active artifacts. Returns (status, detail)."""
    artifacts = {f.name: f for f in run_dir.iterdir() if f.is_file()}

    has_eval = "evaluation_summary.json" in artifacts
    has_cases = "generated_cases.json" in artifacts
    has_approved = "approved_case_plan.json" in artifacts
    has_intent_review = "case_intent_review.json" in artifacts
    has_clarified = "clarified_test_basis.json" in artifacts
    has_clarification_review = "clarification_review.json" in artifacts

    if has_eval:
        return ("evaluated", "Evaluation complete")
    if has_cases:
        return ("cases_ready", "Cases generated, awaiting evaluation")
    if has_approved:
        return ("cases_ready", "Approved plan ready for case generation")

    # Check for blocked state
    if has_clarified:
        try:
            basis = json.loads((run_dir / "clarified_test_basis.json").read_text(encoding="utf-8"))
            if basis.get("blocked"):
                return ("clarification_blocked", "Clarification review blocked")
        except (json.JSONDecodeError, OSError):
            pass

    if has_intent_review:
        return ("intent_ready", "Case intent review ready")
    if has_clarified and not has_clarification_review:
        return ("intent_ready", "Awaiting case intent planning")
    if has_clarification_review:
        return ("clarification_ready", "Clarification review ready")
    return ("new", "Run created, awaiting first stage")


def infer_run_status(run_dir: str | Path) -> str:
    """Public API: infer run status from a run directory path."""
    p = Path(run_dir) if isinstance(run_dir, str) else run_dir
    status, _ = _infer_run_status(p, [])
    return status


# ── Active artifact listing ───────────────────────────────────────────────


def _list_active_artifacts(run_dir: Path) -> list[str]:
    """List active (non-archived) JSON artifacts in pipeline order."""
    artifacts = []
    for name in _ARTIFACT_ORDER:
        if (run_dir / name).exists():
            artifacts.append(name)
    return artifacts


def get_downstream_artifacts(artifact_name: str) -> list[str]:
    """Return downstream artifact names that would be invalidated."""
    return _DOWNSTREAM_MAP.get(artifact_name, [])


def artifacts_to_archive(upstream_artifact: str, run_dir: Path) -> list[str]:
    """List active downstream artifacts that exist and would be archived."""
    downstream = get_downstream_artifacts(upstream_artifact)
    return [a for a in downstream if (run_dir / a).exists()]


# ── Content hashing ───────────────────────────────────────────────────────


def content_hash(data: dict[str, Any] | list[Any]) -> str:
    """Compute a normalized SHA-256 hash of JSON-serializable content."""
    normalized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def artifact_hash(artifact_path: str | Path) -> str | None:
    """Compute the content hash of an artifact file."""
    p = Path(artifact_path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return content_hash(data)
    except (json.JSONDecodeError, OSError):
        return None


def has_changed(old_hash: str | None, new_data: dict[str, Any] | list[Any]) -> bool:
    """Check whether new content differs from a stored hash."""
    if old_hash is None:
        return True
    return content_hash(new_data) != old_hash


# ── Archive ────────────────────────────────────────────────────────────────


def archive_artifacts(
    run_dir: Path, artifact_names: list[str]
) -> list[str]:
    """Move active artifacts to an archive subdirectory. Returns archived paths."""
    if not artifact_names:
        return []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = run_dir / "archived" / ts
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived: list[str] = []
    for name in artifact_names:
        src = run_dir / name
        if src.exists():
            dst = archive_dir / name
            shutil.move(str(src), str(dst))
            archived.append(str(dst))

    return archived


def list_archived(run_dir: Path) -> list[dict[str, Any]]:
    """List archived artifact sets with timestamps."""
    archive_root = run_dir / "archived"
    if not archive_root.exists():
        return []
    results = []
    for d in sorted(archive_root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        files = [f.name for f in d.iterdir() if f.is_file()]
        results.append({
            "timestamp": d.name,
            "artifacts": files,
        })
    return results
