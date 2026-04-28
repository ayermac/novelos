-- Add token usage tracking to workflow_runs table
-- Migration: 021_v5_2_token_tracking.sql

ALTER TABLE workflow_runs ADD COLUMN prompt_tokens INTEGER DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN completion_tokens INTEGER DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN total_tokens INTEGER DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN duration_ms INTEGER DEFAULT 0;
