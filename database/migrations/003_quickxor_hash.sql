-- Add quickxor_hash column to document table
ALTER TABLE document ADD COLUMN quickxor_hash TEXT;

UPDATE db_metadata SET value = '3' WHERE key = 'schema_version';
