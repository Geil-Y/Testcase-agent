from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import local

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DB_PATH = _PROJECT_ROOT / "pipeline_console.db"

_local = local()


def get_db() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _connect()
    return _local.conn


def init_db(db: sqlite3.Connection | None = None) -> None:
    conn = db or get_db()
    conn.executescript(_SCHEMA)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requirement_key TEXT NOT NULL,
    description TEXT NOT NULL,
    function_name TEXT DEFAULT '',
    requirement_type TEXT DEFAULT 'requirement',
    supplementary_info TEXT DEFAULT '',
    source_row INTEGER DEFAULT 0,
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_requirements_key
    ON requirements(requirement_key);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requirement_id INTEGER NOT NULL REFERENCES requirements(id),
    status TEXT NOT NULL DEFAULT 'extraction_ready',
    review_llm_a INTEGER NOT NULL DEFAULT 0,
    review_llm_b INTEGER NOT NULL DEFAULT 0,
    review_llm_c INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS test_basis_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    section_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS test_basis_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES test_basis_sections(id),
    item_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'known',
    content TEXT DEFAULT '',
    need TEXT DEFAULT '',
    source_text TEXT DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS case_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    intent_id TEXT NOT NULL,
    coverage_dimension TEXT NOT NULL,
    intent_text TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS test_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    intent_id INTEGER REFERENCES case_intents(id),
    title TEXT NOT NULL,
    objective TEXT DEFAULT '',
    precondition TEXT DEFAULT '',
    postcondition TEXT DEFAULT '',
    raw_html TEXT DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS test_case_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES test_cases(id),
    step_order INTEGER NOT NULL,
    action TEXT NOT NULL,
    expected TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES test_cases(id),
    item_id TEXT NOT NULL,
    result TEXT NOT NULL,
    detail TEXT DEFAULT ''
);
"""
