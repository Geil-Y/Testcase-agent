-- Review Memory SQLite schema.
-- Stores human-reviewed clarification and case intent decisions
-- with derived pattern tags for future retrieval.

CREATE TABLE IF NOT EXISTS review_sessions (
    session_id      TEXT PRIMARY KEY,
    requirement_key TEXT NOT NULL,
    source_requirement_hash TEXT NOT NULL DEFAULT '',
    test_basis_hash TEXT NOT NULL DEFAULT '',
    source_type     TEXT NOT NULL DEFAULT '',
    source_ref      TEXT NOT NULL DEFAULT '',
    overall_status  TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clarification_memory_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES review_sessions(session_id),
    item_id         TEXT NOT NULL,
    decision        TEXT NOT NULL,
    reason_codes    TEXT NOT NULL DEFAULT '[]',
    reason_text     TEXT NOT NULL DEFAULT '',
    clarified_value TEXT NOT NULL DEFAULT '',
    severity        TEXT NOT NULL DEFAULT 'medium',
    ambiguity_type  TEXT NOT NULL DEFAULT '',
    confidence_score REAL NOT NULL DEFAULT 0.0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS case_intent_memory_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES review_sessions(session_id),
    intent_id       TEXT NOT NULL,
    decision        TEXT NOT NULL,
    reason_codes    TEXT NOT NULL DEFAULT '[]',
    reason_text     TEXT NOT NULL DEFAULT '',
    coverage_dimension TEXT NOT NULL DEFAULT '',
    confidence_score REAL NOT NULL DEFAULT 0.0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_item_tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type       TEXT NOT NULL CHECK(item_type IN ('clarification', 'case_intent')),
    item_ref        TEXT NOT NULL,
    memory_item_id  INTEGER NOT NULL,
    session_id      TEXT NOT NULL REFERENCES review_sessions(session_id),
    tag             TEXT NOT NULL,
    tag_strength    TEXT NOT NULL DEFAULT 'confirmed',
    source          TEXT NOT NULL DEFAULT '',
    rule_id         TEXT NOT NULL DEFAULT '',
    evidence_text   TEXT NOT NULL DEFAULT '',
    confidence      REAL NOT NULL DEFAULT 1.0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_clarification_session ON clarification_memory_items(session_id);
CREATE INDEX IF NOT EXISTS idx_case_intent_session ON case_intent_memory_items(session_id);
CREATE INDEX IF NOT EXISTS idx_tags_session ON memory_item_tags(session_id);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON memory_item_tags(tag);
CREATE INDEX IF NOT EXISTS idx_sessions_hash ON review_sessions(source_requirement_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_basis_hash ON review_sessions(test_basis_hash);
