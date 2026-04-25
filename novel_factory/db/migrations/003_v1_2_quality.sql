-- Migration 003: v1.2 quality additions
-- - issue_categories column on reviews for structured classification
-- - idempotent: safe for re-execution via Python migration runner

-- Add issue_categories column to reviews
-- Note: SQLite doesn't support IF NOT EXISTS on ALTER TABLE ADD COLUMN,
-- so the Python migration runner handles idempotency via _migrations_applied
-- and _is_migration_applied_by_schema checks.
ALTER TABLE reviews ADD COLUMN issue_categories TEXT DEFAULT '[]';
