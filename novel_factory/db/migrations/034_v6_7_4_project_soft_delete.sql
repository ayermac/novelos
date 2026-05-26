-- v6.7.4: Soft delete projects to preserve child records and avoid FK failures.

ALTER TABLE projects ADD COLUMN deleted INTEGER DEFAULT 0;
ALTER TABLE projects ADD COLUMN deleted_at DATETIME;

