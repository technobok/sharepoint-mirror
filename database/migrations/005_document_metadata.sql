-- Migration 005: Custom metadata fields from SharePoint listItem.fields
-- Stores key-value metadata per document, supporting multi-value fields (one row per value).

CREATE TABLE IF NOT EXISTS document_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    field_value TEXT,
    FOREIGN KEY (document_id) REFERENCES document(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_docmeta_document ON document_metadata(document_id);
CREATE INDEX IF NOT EXISTS idx_docmeta_field ON document_metadata(field_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_docmeta_doc_field_value
    ON document_metadata(document_id, field_name, field_value);

UPDATE db_metadata SET value = '5' WHERE key = 'schema_version';
