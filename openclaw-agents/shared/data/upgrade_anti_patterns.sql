-- 问题模式表升级脚本
-- 执行方式：sqlite3 shared/data/novel_factory.db < shared/data/upgrade_anti_patterns.sql
-- 日期：2026-04-05

-- 问题模式表（原 anti_patterns.json）
CREATE TABLE IF NOT EXISTS anti_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL,
    pattern TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    alternatives TEXT,
    check_rules TEXT,
    examples TEXT,
    enabled INTEGER DEFAULT 1,
    frequency INTEGER DEFAULT 0,
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 上下文规则表
CREATE TABLE IF NOT EXISTS context_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium')),
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_anti_patterns_category ON anti_patterns(category);
CREATE INDEX IF NOT EXISTS idx_anti_patterns_severity ON anti_patterns(severity);
CREATE INDEX IF NOT EXISTS idx_anti_patterns_enabled ON anti_patterns(enabled);
CREATE INDEX IF NOT EXISTS idx_anti_patterns_code ON anti_patterns(code);
CREATE INDEX IF NOT EXISTS idx_context_rules_category ON context_rules(category);

-- ============================================
-- 迁移 anti_patterns.json 数据
-- ============================================

-- AI痕迹 (ai_trace)
INSERT OR IGNORE INTO anti_patterns (category, code, pattern, description, severity, alternatives) VALUES
('ai_trace', 'AT001', '冷笑', '角色频繁冷笑，是 AI 最滥用的表情动作', 'high', '["嗤笑", "嘲讽地勾起嘴角", "眼中闪过一丝讥讽", "不屑地哼了一声"]'),
('ai_trace', 'AT002', '嘴角微扬/嘴角勾起', '微笑的刻板表达，缺乏个性', 'medium', '["笑了", "眼角弯了弯", "露出一排白牙", "脸上浮现出笑意"]'),
('ai_trace', 'AT003', '眼中闪过一丝.*寒芒/冷意', '眼神描写的陈词滥调', 'high', '["目光骤然锐利", "眼神沉了下来", "眼底一片冰凉"]'),
('ai_trace', 'AT004', '倒吸一口凉气', '过度使用的惊讶反应', 'medium', '["心下一惊", "猛地一怔", "脸色骤变", "瞳孔微缩"]'),
('ai_trace', 'AT005', '不仅.*而且.*更是', '排比句式滥用，说教感强', 'medium', '["拆成多个短句", "用具体行为替代", "删除空洞描述"]'),
('ai_trace', 'AT006', '夜色.*笼罩/夜幕降临', '环境描写的陈词滥调', 'low', '["天黑透了", "街灯亮起", "窗外一片漆黑"]'),
('ai_trace', 'AT007', '心中暗想/心道', '心理活动的刻板引入', 'medium', '["直接写想法", "用动作暗示", "省略引入词"]'),
('ai_trace', 'AT008', '丝毫不(把|将)', '过度使用的否定句式', 'low', '["根本没把", "完全无视", "当不存在"]');

-- 逻辑漏洞 (logic)
INSERT OR IGNORE INTO anti_patterns (category, code, pattern, description, severity, check_rules, examples) VALUES
('logic', 'LG001', '反派降智', '反派为了主角胜利而变得愚蠢', 'critical', 
 '["反派的每个行动必须有合理的利益动机", "反派的专业能力必须得到尊重", "主角的胜利必须建立在信息差或底牌上"]',
 '["老谋深算的反派突然做出低级错误", "专业高管被主角轻易忽悠", "反派在关键时刻掉链子"]'),
('logic', 'LG002', '机械降神', '危机由外部力量突然解决', 'critical',
 '["解决方案必须在危机前有铺垫", "救场角色必须之前有出场", "道具必须之前有提及"]',
 '["主角陷入绝境时突然出现救星", "恰好发现的隐藏道具解决所有问题", "敌人突然内讧或撤退"]'),
('logic', 'LG003', '数值崩坏', '战力/资源体系前后矛盾', 'high',
 '["每章必须参考上一章的 chapter_state", "资源消耗必须与获得平衡", "能力提升必须有合理途径"]',
 NULL),
('logic', 'LG004', '时间线混乱', '事件时间顺序不合理', 'medium',
 NULL,
 '["白天发生的事引用晚上的信息", "角色在两个地点同时出现", "倒叙未标明"]'),
('logic', 'LG005', '空间逻辑错误', '场景位置描述不一致', 'medium',
 NULL,
 '["房间布局前后矛盾", "距离描述不合理", "方向感混乱"]');

-- 设定冲突 (setting)
INSERT OR IGNORE INTO anti_patterns (category, code, pattern, description, severity, check_rules) VALUES
('setting', 'ST001', '角色OOC', '角色行为与已建立的设定不符', 'high',
 '["核心动机必须一致", "性格底线不能突破", "能力范围不能突变"]'),
('setting', 'ST002', '世界观自相矛盾', '设定规则前后冲突', 'high', NULL),
('setting', 'ST003', '伏笔遗忘', '已埋设的伏笔在应兑现时未提及', 'medium',
 '["每章必须检查 plots_to_resolve", "伏笔兑现必须有明确触发", "未兑现的伏笔不能凭空消失"]');

-- 毒点 (poison)
INSERT OR IGNORE INTO anti_patterns (category, code, pattern, description, severity, examples) VALUES
('poison', 'PN001', '圣母行为', '主角在不应原谅时原谅敌人', 'critical',
 '["放过杀害亲人的凶手", "帮助曾经陷害自己的人", "对敌人讲道义"]'),
('poison', 'PN002', '无脑退婚流', '老套的打脸剧情模板', 'high',
 '["女方家族无脑羞辱男主", "退婚理由极其牵强", "打脸过于刻意"]'),
('poison', 'PN003', '主角光环过度', '运气成分超过努力成分', 'medium',
 '["连续的巧合解决问题", "敌人主动送机会", "不需要付出代价的收获"]'),
('poison', 'PN004', '价值观输出', '作者借角色之口说教', 'high',
 '["章节末尾的人生道理", "角色不自然的道德说教", "强行上价值"]');

-- 节奏问题 (pacing)
INSERT OR IGNORE INTO anti_patterns (category, code, pattern, description, severity, check_rules) VALUES
('pacing', 'PC001', '节奏拖沓', '剧情推进过于缓慢', 'medium',
 '["每500字应有小反馈", "每章应有明确的推进目标", "避免重复的日常描写"]'),
('pacing', 'PC002', '高潮不足', '期待感构建后未达预期', 'high',
 '["高潮场景需要更多篇幅", "冲突解决要有层次感", "情绪释放要充分"]'),
('pacing', 'PC003', '钩子缺失', '章节结尾没有悬念', 'high',
 '["每章结尾必须有钩子", "可以是危机、悬念或期待", "让读者想看下一章"]');

-- ============================================
-- 迁移 context_rules 数据
-- ============================================

INSERT OR IGNORE INTO context_rules (rule, category, severity) VALUES
('老丈人刚当众骂完赘婿，两人不能同坐一辆车', 'logic', 'high'),
('刚打过架的敌人不能立刻和解', 'logic', 'high'),
('死亡的角色不能在无伏笔情况下复活', 'setting', 'critical');

-- 验证
SELECT 'anti_patterns 表记录数: ' || COUNT(*) FROM anti_patterns;
SELECT 'context_rules 表记录数: ' || COUNT(*) FROM context_rules;
