"""Import batch persistence under reviews/imports/."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..pipeline.import_requirements import ColumnMapping, ParsedRequirement, parse_requirements

_REVIEWS_DIR = Path(__file__).resolve().parents[3] / "reviews"
_IMPORTS_DIR = _REVIEWS_DIR / "imports"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _batch_dir(batch_id: str) -> Path:
    return _IMPORTS_DIR / batch_id


def _ensure_imports_dir() -> None:
    _IMPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _unlink_temp(tmp_path: str) -> None:
    """Remove a temp file; ignore file-locking errors on Windows."""
    try:
        Path(tmp_path).unlink(missing_ok=True)
    except PermissionError:
        pass  # Windows may hold a brief lock after openpyxl reads


def save_batch(
    *,
    filename: str,
    requirements: list[dict[str, Any]],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    """Persist a confirmed import as a timestamped batch directory."""
    _ensure_imports_dir()
    now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    batch_id = f"{now_ts}_batch_{short_id}"

    batch_dir = _batch_dir(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "id": batch_id,
        "filename": filename,
        "created_at": _now_utc(),
        "requirements_count": len(requirements),
        "column_mapping": mapping,
    }

    (_batch_dir(batch_id) / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (_batch_dir(batch_id) / "requirements.json").write_text(
        json.dumps(requirements, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        **metadata,
        "requirements": requirements,
    }


def list_batches() -> list[dict[str, Any]]:
    """List all import batches, newest first."""
    _ensure_imports_dir()
    batches: list[dict[str, Any]] = []
    for d in sorted(_IMPORTS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta = d / "metadata.json"
        if meta.exists():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                batches.append(data)
            except json.JSONDecodeError:
                continue
    return batches


def get_latest_batch() -> dict[str, Any] | None:
    """Return the latest import batch with requirements, or None."""
    batches = list_batches()
    if not batches:
        return None
    return get_batch(batches[0]["id"])


def get_batch(batch_id: str) -> dict[str, Any] | None:
    """Return a full import batch with requirements, or None if not found."""
    batch_dir = _batch_dir(batch_id)
    meta_path = batch_dir / "metadata.json"
    reqs_path = batch_dir / "requirements.json"
    if not meta_path.exists():
        return None

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if reqs_path.exists():
        metadata["requirements"] = json.loads(reqs_path.read_text(encoding="utf-8"))
    else:
        metadata["requirements"] = []
    return metadata


def preview_excel(file_path: str) -> dict[str, Any] | None:
    """Preview an Excel file: return sheets and column headers."""
    from ..pipeline.import_requirements import list_columns, list_sheets

    try:
        sheets = list_sheets(file_path)
        if not sheets:
            return None
        columns = list_columns(file_path, sheets[0])
        return {"sheets": sheets, "columns": columns}
    except Exception:
        return None


def confirm_import(
    *,
    tmp_path: str,
    sheet: str | None,
    mapping_data: dict[str, Any],
    filename: str,
) -> dict[str, Any]:
    """Parse requirements from Excel and persist as an import batch."""
    mapping = ColumnMapping(
        requirement_key_col=mapping_data.get("requirement_key_col", ""),
        description_col=mapping_data.get("description_col", ""),
        function_name_col=mapping_data.get("function_name_col", ""),
        requirement_type_col=mapping_data.get("requirement_type_col", ""),
        supplementary_info_cols=mapping_data.get("supplementary_info_cols", []),
    )

    reqs: list[ParsedRequirement] = parse_requirements(tmp_path, mapping, sheet or None)

    req_list: list[dict[str, Any]] = []
    for i, r in enumerate(reqs):
        req_list.append({
            "id": i,
            "requirement_key": r.requirement_key,
            "description": r.description,
            "function_name": r.function_name,
            "requirement_type": r.requirement_type,
            "supplementary_info": r.supplementary_info,
            "is_heading": r.is_heading,
            "is_info": r.is_info,
        })

    _unlink_temp(tmp_path)

    return save_batch(
        filename=filename,
        requirements=req_list,
        mapping=mapping_data,
    )


def list_batches_summary() -> list[dict[str, Any]]:
    """List import batches without loading full requirements."""
    return [
        {k: v for k, v in b.items() if k != "requirements"}
        for b in list_batches()
    ]
