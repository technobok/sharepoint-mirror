-- Migration 002: Change document unique constraint from (sharepoint_item_id)
-- to composite (sharepoint_item_id, sharepoint_drive_id) so multiple drives
-- can contain items with the same ID.

PRAGMA foreign_keys = OFF;

-- Recreate document table with composite unique constraint
CREATE TABLE document_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sharepoint_item_id TEXT NOT NULL,
    sharepoint_drive_id TEXT NOT NULL,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    web_url TEXT,
    created_by TEXT,
    last_modified_by TEXT,
    sharepoint_created_at TEXT,
    sharepoint_modified_at TEXT,
    file_blob_id INTEGER,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (file_blob_id) REFERENCES file_blob(id) ON DELETE SET NULL,
    UNIQUE(sharepoint_item_id, sharepoint_drive_id)
);

-- Copy existing data
INSERT INTO document_new
    SELECT id, sharepoint_item_id, sharepoint_drive_id, name, path,
           mime_type, file_size, web_url, created_by, last_modified_by,
           sharepoint_created_at, sharepoint_modified_at, file_blob_id,
           is_deleted, synced_at, created_at, updated_at
    FROM document;

-- Drop old table and rename
DROP TABLE document;
ALTER TABLE document_new RENAME TO document;

-- Recreate indexes
CREATE INDEX idx_document_item_id ON document(sharepoint_item_id);
CREATE INDEX idx_document_drive_id ON document(sharepoint_drive_id);
CREATE INDEX idx_document_path ON document(path);
CREATE INDEX idx_document_name ON document(name);
CREATE INDEX idx_document_is_deleted ON document(is_deleted);
CREATE INDEX idx_document_blob ON document(file_blob_id);

-- Recreate FTS triggers (dropping table cascades removes them)
CREATE TRIGGER document_ai AFTER INSERT ON document BEGIN
    INSERT INTO document_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
END;

CREATE TRIGGER document_ad AFTER DELETE ON document BEGIN
    INSERT INTO document_fts(document_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
END;

CREATE TRIGGER document_au AFTER UPDATE ON document BEGIN
    INSERT INTO document_fts(document_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
    INSERT INTO document_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
END;

-- Rebuild FTS index to match new table
INSERT INTO document_fts(document_fts) VALUES ('rebuild');

-- Update schema version
UPDATE db_metadata SET value = '2' WHERE key = 'schema_version';

PRAGMA foreign_keys = ON;
