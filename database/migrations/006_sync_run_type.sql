-- Add sync_type column to sync_run to distinguish sync vs metadata refresh
ALTER TABLE sync_run ADD COLUMN sync_type TEXT NOT NULL DEFAULT 'sync';

UPDATE db_metadata SET value = '6' WHERE key = 'schema_version';
