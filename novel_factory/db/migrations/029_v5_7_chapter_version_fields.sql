-- v5.7: Extend chapter_versions for daily writing editing and versioning.
-- Adds: source, base_version_id, summary, metadata columns.
-- All columns are nullable for backward compatibility with existing rows.

ALTER TABLE chapter_versions ADD COLUMN source TEXT DEFAULT 'ai_generation';
ALTER TABLE chapter_versions ADD COLUMN base_version_id INTEGER REFERENCES chapter_versions(id);
ALTER TABLE chapter_versions ADD COLUMN summary TEXT;
ALTER TABLE chapter_versions ADD COLUMN metadata TEXT;

-- Index for fast latest-version lookup
CREATE INDEX IF NOT EXISTS idx_chapter_versions_latest
    ON chapter_versions(project_id, chapter, version DESC);
