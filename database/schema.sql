-- SharePoint Mirror Database Schema
-- All datetimes stored as ISO 8601 UTC strings

PRAGMA foreign_keys = ON;

-- Database metadata for versioning
CREATE TABLE IF NOT EXISTS db_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO db_metadata (key, value) VALUES ('schema_version', '1');

-- Application settings
CREATE TABLE IF NOT EXISTS app_setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT
);

-- File blobs (deduplicated content-addressed storage)
-- Path derived from hash: {BLOB_DIRECTORY}/{hash[:2]}/{hash[2:4]}/{hash}
CREATE TABLE IF NOT EXISTS file_blob (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256_hash TEXT UNIQUE NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    reference_count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_file_blob_hash ON file_blob(sha256_hash);

-- SharePoint documents
CREATE TABLE IF NOT EXISTS document (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- SharePoint identifiers (stable across renames)
    sharepoint_item_id TEXT UNIQUE NOT NULL,
    sharepoint_drive_id TEXT NOT NULL,
    -- Current metadata
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    -- SharePoint metadata
    web_url TEXT,
    created_by TEXT,
    last_modified_by TEXT,
    sharepoint_created_at TEXT,
    sharepoint_modified_at TEXT,
    -- Reference to blob content
    file_blob_id INTEGER,
    -- Tracking
    is_deleted INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (file_blob_id) REFERENCES file_blob(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_document_item_id ON document(sharepoint_item_id);
CREATE INDEX IF NOT EXISTS idx_document_drive_id ON document(sharepoint_drive_id);
CREATE INDEX IF NOT EXISTS idx_document_path ON document(path);
CREATE INDEX IF NOT EXISTS idx_document_name ON document(name);
CREATE INDEX IF NOT EXISTS idx_document_is_deleted ON document(is_deleted);
CREATE INDEX IF NOT EXISTS idx_document_blob ON document(file_blob_id);

-- Full-text search for documents
CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(
    name,
    path,
    content='document',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS document_ai AFTER INSERT ON document BEGIN
    INSERT INTO document_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
END;

CREATE TRIGGER IF NOT EXISTS document_ad AFTER DELETE ON document BEGIN
    INSERT INTO document_fts(document_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
END;

CREATE TRIGGER IF NOT EXISTS document_au AFTER UPDATE ON document BEGIN
    INSERT INTO document_fts(document_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
    INSERT INTO document_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
END;

-- Sync run history
CREATE TABLE IF NOT EXISTS sync_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'running',  -- running, completed, failed
    started_at TEXT NOT NULL,
    completed_at TEXT,
    is_full_sync INTEGER NOT NULL DEFAULT 0,
    -- Counts
    files_added INTEGER NOT NULL DEFAULT 0,
    files_modified INTEGER NOT NULL DEFAULT 0,
    files_removed INTEGER NOT NULL DEFAULT 0,
    files_unchanged INTEGER NOT NULL DEFAULT 0,
    files_skipped INTEGER NOT NULL DEFAULT 0,
    bytes_downloaded INTEGER NOT NULL DEFAULT 0,
    -- Error info
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_run_status ON sync_run(status);
CREATE INDEX IF NOT EXISTS idx_sync_run_started ON sync_run(started_at);

-- Individual sync events (add/remove/modify)
CREATE TABLE IF NOT EXISTS sync_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_run_id INTEGER NOT NULL,
    document_id INTEGER,
    event_type TEXT NOT NULL,  -- add, remove, modify_add, modify_remove
    -- Snapshot of document state at event time
    sharepoint_item_id TEXT NOT NULL,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    file_size INTEGER,
    file_blob_id INTEGER,
    -- Metadata
    logged_at TEXT NOT NULL,
    FOREIGN KEY (sync_run_id) REFERENCES sync_run(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES document(id) ON DELETE SET NULL,
    FOREIGN KEY (file_blob_id) REFERENCES file_blob(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_event_run ON sync_event(sync_run_id);
CREATE INDEX IF NOT EXISTS idx_sync_event_document ON sync_event(document_id);
CREATE INDEX IF NOT EXISTS idx_sync_event_type ON sync_event(event_type);
CREATE INDEX IF NOT EXISTS idx_sync_event_logged ON sync_event(logged_at);

-- Delta tokens for Graph API (per drive)
CREATE TABLE IF NOT EXISTS delta_token (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drive_id TEXT UNIQUE NOT NULL,
    delta_link TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_delta_token_drive ON delta_token(drive_id);

-- Default app settings
INSERT OR IGNORE INTO app_setting (key, value, description) VALUES
    ('sync_in_progress', '0', 'Flag to prevent concurrent syncs');
