-- v5.3.5 Memory Reliability
-- Adds error_message column to memory_update_items for per-item failure tracking.

ALTER TABLE memory_update_items ADD COLUMN error_message TEXT;
