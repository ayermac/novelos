"""v6.10.19: Data migration scripts for field consolidation.

Migration 001: Merge deprecated ChapterBrief fields → new fields (conflict, notes,
payoff_points, required_beats) in chapter_briefs.brief_data JSON.
Supports --dry-run for preview. Backup stored in _chapter_briefs_migration_backup.
"""
