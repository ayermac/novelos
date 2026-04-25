"""HumanizerZhSkill: 中文AI去味Skill

检测并修复中文文本中的AI写作风格，包括：
- 模板化连接词
- 空泛心理描写
- 夸张但无信息量的情绪词
- 三段式排比
- 高频套话
- 机械解释
- 同质句式重复
"""

import re
from typing import Any

from .base import TransformSkill


class HumanizerZhSkill(TransformSkill):
    """中文AI去味Skill
    
    继承自TransformSkill，用于改写文本以降低AI写作痕迹。
    
    配置项：
    - preserve_facts: 是否保护事实（默认True）
    - max_change_ratio: 最大改动比例（默认0.35）
    - fail_on_fact_risk: 发现事实风险时是否失败（默认True）
    """
    
    # AI常用模板连接词
    TEMPLATE_CONNECTORS = [
        r"然而[，,]",
        r"但是[，,]",
        r"不过[，,]",
        r"尽管如此[，,]",
        r"与此同时[，,]",
        r"不仅如此[，,]",
        r"值得注意的是[，,]",
        r"需要指出的是[，,]",
        r"显而易见[，,]",
        r"毫无疑问[，,]",
        r"由此可见[，,]",
        r"综上所述[，,]",
        r"总而言之[，,]",
        r"换句话说[，,]",
        r"换言之[，,]",
    ]
    
    # 空泛心理描写
    VAGUE_PSYCHOLOGY = [
        r"内心.{0,5}复杂",
        r"心情.{0,5}难以言喻",
        r"思绪.{0,5}万千",
        r"心中.{0,5}五味杂陈",
        r"百感交集",
        r"心潮澎湃",
        r"内心.{0,5}挣扎",
        r"心情.{0,5}沉重",
        r"心中.{0,5}涌起",
        r"内心.{0,5}波澜",
    ]
    
    # 夸张情绪词
    EXAGGERATED_EMOTIONS = [
        r"震撼.{0,3}心灵",
        r"令人.{0,3}窒息",
        r"无法.{0,3}自拔",
        r"彻底.{0,3}崩溃",
        r"完全.{0,3}绝望",
        r"瞬间.{0,3}泪目",
        r"感动.{0,3}落泪",
        r"心碎.{0,3}一地",
        r"彻底.{0,3}沦陷",
        r"无法.{0,3}抗拒",
    ]
    
    # 高频套话
    CLICHES = [
        r"命运.{0,5}齿轮",
        r"时间.{0,5}流逝",
        r"岁月.{0,5}痕迹",
        r"人生.{0,5}转折点",
        r"命运.{0,5}安排",
        r"冥冥之中",
        r"命中注定",
        r"天意弄人",
        r"世事无常",
        r"人生如戏",
    ]
    
    # 机械解释模式
    MECHANICAL_EXPLANATIONS = [
        r"这.{1,3}意味着",
        r"这.{1,3}说明",
        r"这.{1,3}表明",
        r"这.{1,3}代表",
        r"这.{1,3}暗示",
        r"这.{1,3}预示",
        r"这.{1,3}反映",
        r"这.{1,3}体现",
    ]
    
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """执行中文AI去味
        
        Args:
            payload: 包含以下字段：
                - text: 原始文本（必需）
                - fact_lock: 事实锁定信息（可选）
                - config: 覆盖配置（可选）
        
        Returns:
            {
                "ok": bool,
                "error": str | None,
                "data": {
                    "humanized_text": str,
                    "changes": list[dict],
                    "change_ratio": float,
                    "risk_level": str,
                    "preserved_facts": list[str]
                }
            }
        """
        # 提取输入
        text = payload.get("text", "")
        fact_lock = payload.get("fact_lock", {})
        
        if not text:
            return {
                "ok": False,
                "error": "缺少text字段",
                "data": None
            }
        
        # 获取配置
        config = {**self.config, **payload.get("config", {})}
        preserve_facts = config.get("preserve_facts", True)
        max_change_ratio = config.get("max_change_ratio", 0.35)
        fail_on_fact_risk = config.get("fail_on_fact_risk", True)
        
        # 执行改写
        humanized_text = text
        changes = []
        
        # 1. 替换模板连接词
        humanized_text, connector_changes = self._replace_template_connectors(humanized_text)
        changes.extend(connector_changes)
        
        # 2. 替换空泛心理描写
        humanized_text, psych_changes = self._replace_vague_psychology(humanized_text)
        changes.extend(psych_changes)
        
        # 3. 替换夸张情绪词
        humanized_text, emotion_changes = self._replace_exaggerated_emotions(humanized_text)
        changes.extend(emotion_changes)
        
        # 4. 替换高频套话
        humanized_text, cliche_changes = self._replace_cliches(humanized_text)
        changes.extend(cliche_changes)
        
        # 5. 替换机械解释
        humanized_text, explain_changes = self._replace_mechanical_explanations(humanized_text)
        changes.extend(explain_changes)
        
        # 6. 检测三段式排比
        humanized_text, parallel_changes = self._fix_parallel_sentences(humanized_text)
        changes.extend(parallel_changes)
        
        # 7. 检测同质句式重复
        humanized_text, repeat_changes = self._fix_sentence_repetition(humanized_text)
        changes.extend(repeat_changes)
        
        # 计算改动比例
        change_ratio = len(changes) / max(len(text.split()), 1)
        
        # 检查事实保护
        preserved_facts = []
        fact_risk = False
        
        if preserve_facts and fact_lock:
            fact_risk, preserved_facts = self._check_fact_preservation(
                text, humanized_text, fact_lock
            )
        
        # 判断风险等级
        risk_level = "low"
        if change_ratio > max_change_ratio:
            risk_level = "high"
        elif change_ratio > max_change_ratio * 0.7:
            risk_level = "medium"
        
        if fact_risk:
            risk_level = "critical"
            if fail_on_fact_risk:
                return {
                    "ok": False,
                    "error": "检测到事实风险，改写失败",
                    "data": {
                        "humanized_text": humanized_text,
                        "changes": changes,
                        "change_ratio": change_ratio,
                        "risk_level": risk_level,
                        "preserved_facts": preserved_facts
                    }
                }
        
        return {
            "ok": True,
            "error": None,
            "data": {
                "humanized_text": humanized_text,
                "changes": changes,
                "change_ratio": change_ratio,
                "risk_level": risk_level,
                "preserved_facts": preserved_facts
            }
        }
    
    def _replace_template_connectors(self, text: str) -> tuple[str, list[dict]]:
        """替换模板连接词"""
        changes = []
        result = text
        
        replacements = {
            r"然而[，,]": "但",
            r"但是[，,]": "但",
            r"不过[，,]": "只是",
            r"尽管如此[，,]": "即便如此，",
            r"与此同时[，,]": "同时，",
            r"不仅如此[，,]": "而且，",
            r"值得注意的是[，,]": "要注意的是，",
            r"需要指出的是[，,]": "需要说明的是，",
            r"显而易见[，,]": "明显，",
            r"毫无疑问[，,]": "无疑，",
            r"由此可见[，,]": "可见，",
            r"综上所述[，,]": "综上，",
            r"总而言之[，,]": "总之，",
            r"换句话说[，,]": "也就是说，",
            r"换言之[，,]": "即",
        }
        
        for pattern, replacement in replacements.items():
            matches = list(re.finditer(pattern, text))
            if matches:
                result = re.sub(pattern, replacement, result)
                for match in matches:
                    changes.append({
                        "type": "template_connector",
                        "original": match.group(),
                        "replacement": replacement,
                        "position": match.start()
                    })
        
        return result, changes
    
    def _replace_vague_psychology(self, text: str) -> tuple[str, list[dict]]:
        """替换空泛心理描写"""
        changes = []
        result = text
        
        replacements = {
            r"内心.{0,5}复杂": "心里有些乱",
            r"心情.{0,5}难以言喻": "说不出是什么滋味",
            r"思绪.{0,5}万千": "想了很多",
            r"心中.{0,5}五味杂陈": "心里五味杂陈",
            r"百感交集": "感慨良多",
            r"心潮澎湃": "心情激动",
            r"内心.{0,5}挣扎": "心里很矛盾",
            r"心情.{0,5}沉重": "心情有些沉重",
            r"心中.{0,5}涌起": "心里涌起",
            r"内心.{0,5}波澜": "心里起了波澜",
        }
        
        for pattern, replacement in replacements.items():
            matches = list(re.finditer(pattern, text))
            if matches:
                result = re.sub(pattern, replacement, result)
                for match in matches:
                    changes.append({
                        "type": "vague_psychology",
                        "original": match.group(),
                        "replacement": replacement,
                        "position": match.start()
                    })
        
        return result, changes
    
    def _replace_exaggerated_emotions(self, text: str) -> tuple[str, list[dict]]:
        """替换夸张情绪词"""
        changes = []
        result = text
        
        replacements = {
            r"震撼.{0,3}心灵": "震撼人心",
            r"令人.{0,3}窒息": "让人透不过气",
            r"无法.{0,3}自拔": "难以自拔",
            r"彻底.{0,3}崩溃": "崩溃",
            r"完全.{0,3}绝望": "绝望",
            r"瞬间.{0,3}泪目": "眼眶湿润",
            r"感动.{0,3}落泪": "感动得流泪",
            r"心碎.{0,3}一地": "心碎",
            r"彻底.{0,3}沦陷": "沦陷",
            r"无法.{0,3}抗拒": "难以抗拒",
        }
        
        for pattern, replacement in replacements.items():
            matches = list(re.finditer(pattern, text))
            if matches:
                result = re.sub(pattern, replacement, result)
                for match in matches:
                    changes.append({
                        "type": "exaggerated_emotion",
                        "original": match.group(),
                        "replacement": replacement,
                        "position": match.start()
                    })
        
        return result, changes
    
    def _replace_cliches(self, text: str) -> tuple[str, list[dict]]:
        """替换高频套话"""
        changes = []
        result = text
        
        replacements = {
            r"命运.{0,5}齿轮": "命运的转折",
            r"时间.{0,5}流逝": "时光流逝",
            r"岁月.{0,5}痕迹": "岁月的印记",
            r"人生.{0,5}转折点": "人生的转折",
            r"命运.{0,5}安排": "命运的安排",
            r"冥冥之中": "冥冥中",
            r"命中注定": "注定",
            r"天意弄人": "造化弄人",
            r"世事无常": "世事难料",
            r"人生如戏": "人生如戏",
        }
        
        for pattern, replacement in replacements.items():
            matches = list(re.finditer(pattern, text))
            if matches:
                result = re.sub(pattern, replacement, result)
                for match in matches:
                    changes.append({
                        "type": "cliche",
                        "original": match.group(),
                        "replacement": replacement,
                        "position": match.start()
                    })
        
        return result, changes
    
    def _replace_mechanical_explanations(self, text: str) -> tuple[str, list[dict]]:
        """替换机械解释"""
        changes = []
        result = text
        
        replacements = {
            r"这.{1,3}意味着": "也就是说",
            r"这.{1,3}说明": "这说明",
            r"这.{1,3}表明": "这表明",
            r"这.{1,3}代表": "这代表",
            r"这.{1,3}暗示": "这暗示",
            r"这.{1,3}预示": "这预示",
            r"这.{1,3}反映": "这反映",
            r"这.{1,3}体现": "这体现",
        }
        
        for pattern, replacement in replacements.items():
            matches = list(re.finditer(pattern, text))
            if matches:
                result = re.sub(pattern, replacement, result)
                for match in matches:
                    changes.append({
                        "type": "mechanical_explanation",
                        "original": match.group(),
                        "replacement": replacement,
                        "position": match.start()
                    })
        
        return result, changes
    
    def _fix_parallel_sentences(self, text: str) -> tuple[str, list[dict]]:
        """修复三段式排比
        
        检测连续三个相似句式，尝试打破重复
        """
        changes = []
        result = text
        
        # 简单检测：连续三个"XX的YY"句式
        pattern = r"([^。！？\n]{5,15}的[^。！？\n]{5,15}[，,。]){3,}"
        matches = list(re.finditer(pattern, text))
        
        if matches:
            # 标记但不自动修复，因为三段式排比有时是文学手法
            for match in matches:
                changes.append({
                    "type": "parallel_sentence",
                    "original": match.group(),
                    "replacement": None,  # 不自动替换，需要人工审核
                    "position": match.start(),
                    "note": "检测到三段式排比，建议人工审核是否需要调整"
                })
        
        return result, changes
    
    def _fix_sentence_repetition(self, text: str) -> tuple[str, list[dict]]:
        """修复同质句式重复
        
        检测连续相似的句式结构
        """
        changes = []
        result = text
        
        # 检测连续相似句式（简化版）
        sentences = re.split(r'[。！？\n]', text)
        
        # 检测连续两个以上相同开头的句子
        for i in range(len(sentences) - 1):
            sent1 = sentences[i].strip()
            sent2 = sentences[i + 1].strip()
            
            if len(sent1) > 5 and len(sent2) > 5:
                # 检测前5个字符是否相同
                if sent1[:5] == sent2[:5]:
                    changes.append({
                        "type": "sentence_repetition",
                        "original": f"{sent1}。{sent2}。",
                        "replacement": None,  # 不自动替换
                        "position": text.find(sent1),
                        "note": f"检测到相似句式开头: '{sent1[:5]}...'"
                    })
        
        return result, changes
    
    def _check_fact_preservation(
        self, 
        original: str, 
        humanized: str, 
        fact_lock: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """检查事实是否被保护
        
        Args:
            original: 原始文本
            humanized: 改写后文本
            fact_lock: 事实锁定信息
        
        Returns:
            (是否有风险, 保留的事实列表)
        """
        preserved_facts = []
        has_risk = False
        
        # 检查伏笔编号是否保留
        foreshadowing_pattern = r'【伏笔[0-9]+】'
        original_foreshadowings = set(re.findall(foreshadowing_pattern, original))
        humanized_foreshadowings = set(re.findall(foreshadowing_pattern, humanized))
        
        if original_foreshadowings != humanized_foreshadowings:
            has_risk = True
        else:
            preserved_facts.extend(list(original_foreshadowings))
        
        # 检查关键事件（从fact_lock中提取）
        if fact_lock:
            key_events = fact_lock.get("key_events", [])
            for event in key_events:
                if event in original and event not in humanized:
                    has_risk = True
                elif event in humanized:
                    preserved_facts.append(event)
        
        # 检查状态卡数值（简化检测）
        state_pattern = r'状态卡[：:][^。\n]{10,50}'
        original_states = set(re.findall(state_pattern, original))
        humanized_states = set(re.findall(state_pattern, humanized))
        
        if original_states != humanized_states:
            has_risk = True
        else:
            preserved_facts.extend(list(original_states))
        
        return has_risk, preserved_facts
