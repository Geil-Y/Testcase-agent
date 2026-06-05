from __future__ import annotations

import sqlite3

from ..provider.base import LlmProvider
from .pipeline_runner import run_llm_b, run_llm_c
from .review_state import can_advance, accept_stage


def advance_run(run_id: int, provider: LlmProvider, db: sqlite3.Connection) -> None:
    """
    Advance to the next pipeline stage. Auto-chains through consecutive
    auto-approve stages.

    Logic:
    1. extraction_ready -> check LLM-A accepted, exec LLM-B.
       Then if review_llm_c==0, auto-accept and chain LLM-C.
    2. intents_ready -> check LLM-B accepted, exec LLM-C.
    3. cases_ready -> no-op.
    """
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    status = run["status"]

    if status == "extraction_ready":
        if run["review_llm_a"] == 1 and run["llm_a_accepted"] == 0:
            raise ValueError("LLM-A stage not yet accepted")
        run_llm_b(run_id, provider, db)
        run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run["review_llm_b"] == 0 and run["review_llm_c"] == 0:
            accept_stage(db, run_id, "c")
            run_llm_c(run_id, provider, db)

    elif status == "intents_ready":
        if run["review_llm_b"] == 1 and run["llm_b_accepted"] == 0:
            raise ValueError("LLM-B stage not yet accepted")
        if run["review_llm_c"] == 0:
            accept_stage(db, run_id, "c")
        run_llm_c(run_id, provider, db)

    elif status == "cases_ready" or status == "evaluated":
        pass  # nothing to advance

    else:
        raise ValueError(f"Cannot advance run in status: {status}")
