-- v6.10.18: Add new ChapterBrief fields to instructions table
-- Migration 039
-- Adds: conflict, notes, payoff_points, required_beats
-- (emotion_tone already exists in base schema)

ALTER TABLE instructions ADD COLUMN conflict TEXT DEFAULT '';
ALTER TABLE instructions ADD COLUMN notes TEXT DEFAULT '';
ALTER TABLE instructions ADD COLUMN payoff_points TEXT DEFAULT '[]';
ALTER TABLE instructions ADD COLUMN required_beats TEXT DEFAULT '[]';
