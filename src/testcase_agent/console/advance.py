from __future__ import annotations

import sqlite3

from ..provider.base import LlmProvider
from .pipeline_runner import run_llm_b, run_llm_c


def advance_run(run_id: int, provider: LlmProvider, db: sqlite3.Connection) -> None:
    """
    Advance to the next pipeline stage. Auto-chains through consecutive
    auto-approve stages.

    Logic:
    1. extraction_ready -> always exec LLM-B. Then if review_llm_c==0, chain LLM-C.
    2. intents_ready -> exec LLM-C.
    3. cases_ready -> no-op.
    """
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    status = run["status"]

    if status == "extraction_ready":
        run_llm_b(run_id, provider, db)
        run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run["review_llm_c"] == 0:
            run_llm_c(run_id, provider, db)

    elif status == "intents_ready":
        run_llm_c(run_id, provider, db)

    elif status == "cases_ready" or status == "evaluated":
        pass  # nothing to advance

    else:
        raise ValueError(f"Cannot advance run in status: {status}")
