"""Generation progress trace — safe event log for pipeline Console.

Writes append-only JSONL file _trace.jsonl into each run directory.
No private chain-of-thought, no raw prompts, no raw responses.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def write_trace_event(run_dir: str | Path, /, **fields: object) -> None:
    """Append a trace event to the run's _trace.jsonl.

    Required fields: stage, event, message
    Optional: provider, model, duration_ms, detail
    """
    p = Path(run_dir) if isinstance(run_dir, str) else run_dir
    p.mkdir(parents=True, exist_ok=True)

    event: dict[str, object] = {"timestamp": time.time()}
    event.update(fields)

    trace_path = p / "_trace.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with open(trace_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_trace_events(run_dir: str | Path) -> list[dict[str, object]]:
    """Read all trace events from a run directory, newest first."""
    p = Path(run_dir) if isinstance(run_dir, str) else run_dir
    trace_path = p / "_trace.jsonl"
    if not trace_path.exists():
        return []
    events: list[dict[str, object]] = []
    with open(trace_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    events.reverse()  # newest first for API consumption
    return events
