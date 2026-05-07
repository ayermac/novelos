-- v5.5.9: Auto-Run Resilience — session recovery fields

ALTER TABLE auto_run_sessions ADD COLUMN last_event TEXT;
