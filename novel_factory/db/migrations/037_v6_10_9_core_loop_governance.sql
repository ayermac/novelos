-- v6.10.9: 核心循环前置约束与事实锁感知
-- 为 scene_beats 表添加 is_reward_beat, dialogue_slots, character_states 字段
-- 为 instructions 表添加 core_loop, dialogue_target_ratio, fact_locks 字段

-- Scene beats: v6.10.9 新增字段
ALTER TABLE scene_beats ADD COLUMN is_reward_beat INTEGER DEFAULT 0;
ALTER TABLE scene_beats ADD COLUMN dialogue_slots TEXT DEFAULT '[]';
ALTER TABLE scene_beats ADD COLUMN character_states TEXT DEFAULT '{}';

-- Instructions: v6.10.9 新增字段
ALTER TABLE instructions ADD COLUMN core_loop TEXT DEFAULT '{}';
ALTER TABLE instructions ADD COLUMN dialogue_target_ratio REAL DEFAULT 0.15;
ALTER TABLE instructions ADD COLUMN fact_locks TEXT DEFAULT '[]';
