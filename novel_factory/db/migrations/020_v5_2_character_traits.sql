-- Add traits column to characters table
-- Migration: 020_v5_2_character_traits.sql

ALTER TABLE characters ADD COLUMN traits TEXT;
