-- 035_v6_8_3_plot_hole_status_repair.sql
-- v6.8.3: Repair legacy plot hole status inconsistencies caused by the
-- same-batch resolve/update overwrite bug (fixed in v6.8.3 Phase 1).
--
-- This migration is a DATA repair (no schema change). It is idempotent:
-- running it again is a no-op once all rows are consistent.

-- 1. Rows that have a resolved_chapter but were knocked back to a
--    non-terminal status: restore them to resolved.
UPDATE plot_holes
SET status = 'resolved'
WHERE resolved_chapter IS NOT NULL
  AND status NOT IN ('resolved', 'abandoned');

-- 2. Normalize the illegal legacy status 'validated' to 'planted'
--    (canonical statuses are planted/resolved/abandoned).
UPDATE plot_holes
SET status = 'planted'
WHERE status = 'validated';
