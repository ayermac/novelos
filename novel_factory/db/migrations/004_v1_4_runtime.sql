-- Migration 004: v1.4 runtime hardening
-- Add structured revision_target field to reviews table

-- Add revision_target column if not exists
-- SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN, so we use a try-catch approach
-- We'll check if the column exists first
-- This migration is idempotent: safe to run multiple times

-- First, check if revision_target column exists
-- We'll use a PRAGMA to check table info
-- Note: SQLite doesn't support procedural logic in migrations, so we'll rely on the
-- _is_migration_applied_by_schema function in connection.py to detect if this migration
-- has already been applied.

-- The actual column addition
-- We'll add the column unconditionally; if it already exists, this will fail
-- but the migration tracking will prevent re-execution
ALTER TABLE reviews ADD COLUMN revision_target TEXT;

-- Update existing rows where summary contains revision_target=...
-- This is a one-time data migration for existing data
UPDATE reviews 
SET revision_target = 
    CASE 
        WHEN summary LIKE '%revision_target=author%' THEN 'author'
        WHEN summary LIKE '%revision_target=polisher%' THEN 'polisher'
        WHEN summary LIKE '%revision_target=planner%' THEN 'planner'
        ELSE NULL
    END
WHERE revision_target IS NULL AND summary IS NOT NULL;

-- Clean up summary field by removing revision_target=... prefix if present
-- This keeps the summary as a true summary field
UPDATE reviews 
SET summary = 
    CASE 
        WHEN summary LIKE 'revision_target=%' THEN 
            TRIM(SUBSTR(summary, INSTR(summary, ',') + 1))
        WHEN summary LIKE '%,revision_target=%' THEN 
            REPLACE(summary, SUBSTR(summary, INSTR(summary, ',revision_target=')), '')
        ELSE summary
    END
WHERE summary LIKE '%revision_target=%';