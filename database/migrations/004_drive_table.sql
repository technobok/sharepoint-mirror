-- Migration 004: Add drive lookup table
-- Maps Graph API drive IDs to human-readable library names

CREATE TABLE IF NOT EXISTS drive (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    web_url TEXT,
    updated_at TEXT NOT NULL
);

UPDATE db_metadata SET value = '4' WHERE key = 'schema_version';
