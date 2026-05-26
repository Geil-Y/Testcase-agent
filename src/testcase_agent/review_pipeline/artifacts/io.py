"""JSON read/write helpers that preserve UTF-8 content."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> dict[str, Any]:
    """Read a JSON file with UTF-8 encoding."""
    raw = Path(path).read_text(encoding="utf-8")
    return json.loads(raw)


def write_json(path: str | Path, data: dict[str, Any] | list[Any], *, indent: int = 2) -> None:
    """Write data as JSON with UTF-8 encoding and consistent formatting."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, indent=indent)
    Path(path).write_text(raw, encoding="utf-8")
