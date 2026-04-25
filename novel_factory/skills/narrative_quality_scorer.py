"""NarrativeQualityScorer: 叙事质量评分Skill

评价章节叙事质量，包括：
- 冲突强度
- 钩子强度
- 信息密度
- 节奏控制
- 对话自然度
- 场景沉浸感
- 人物动机清晰度
"""

import re
from typing import Any

from .base import ValidatorSkill


class NarrativeQualityScorer(ValidatorSkill):
    """叙事质量评分Skill
    
    继承自ValidatorSkill，用于评价章节的叙事质量。
    
    配置项：
    - min_conflict_score: 最低冲突分要求（默认40）
    - min_hook_score: 最低钩子分要求（默认50）
    - min_dialogue_ratio: 最低对话比例（默认0.1）
    """
    
    # 冲突相关关键词
    CONFLICT_KEYWORDS = [
        "冲突", "矛盾", "争执", "争吵", "对抗", "对立", "敌对",
        "威胁", "危机", "危险", "挑战", "困境", "难题", "障碍",
        "争斗", "搏斗", "战斗", "打斗", "厮杀", "交锋",
        "反对", "抵抗", "反抗", "反击", "回击",
    ]
    
    # 钩子相关模式
    HOOK_PATTERNS = [
        r"然而[，,]?$",  # 章末转折
        r"但是[，,]?$",  # 章末转折
        r"就在这时[，,]?$",  # 章末悬念
        r"突然[，,]?$",  # 章末悬念
        r"意想不到的是[，,]?$",  # 章末悬念
        r"他.{1,5}不知道的是[，,]?$",  # 章末悬念
        r"等待他的将是[，,]?$",  # 章末悬念
        r"命运.{1,5}转折[，,]?$",  # 章末悬念
        r"\?\s*$",  # 章末疑问
        r"！\s*$",  # 章末感叹
    ]
    
    # 信息密集词（名词、动词、形容词）
    INFO_DENSE_POS = ["n", "v", "a", "vn", "an"]
    
    # 场景描写关键词
    SCENE_KEYWORDS = [
        "光线", "阳光", "月光", "灯光", "阴影", "黑暗",
        "声音", "响声", "噪音", "寂静", "沉默",
        "气味", "香味", "臭味", "气息",
        "温度", "寒冷", "炎热", "温暖", "凉爽",
        "触感", "粗糙", "光滑", "柔软", "坚硬",
        "颜色", "红色", "蓝色", "绿色", "黄色",
        "空间", "宽敞", "狭窄", "开阔", "封闭",
    ]
    
    # 人物动机关键词
    MOTIVATION_KEYWORDS = [
        "为了", "想要", "希望", "渴望", "追求", "目标",
        "必须", "需要", "不得不", "只能", "只能",
        "决心", "决定", "立志", "发誓", "承诺",
        "梦想", "理想", "愿望", "期盼", "期待",
    ]
    
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """执行叙事质量评分
        
        Args:
            payload: 包含以下字段：
                - text: 章节文本（必需）
                - chapter_number: 章节号（可选）
                - config: 覆盖配置（可选）
        
        Returns:
            {
                "ok": bool,
                "error": str | None,
                "data": {
                    "scores": {
                        "conflict_intensity": float,
                        "hook_strength": float,
                        "information_density": float,
                        "pacing_control": float,
                        "dialogue_naturalness": float,
                        "scene_immersion": float,
                        "character_motivation": float,
                        "overall_score": float
                    },
                    "issues": list[dict],
                    "suggestions": list[str],
                    "grade": str
                }
            }
        """
        # 提取输入
        text = payload.get("text", "")
        
        if not text:
            return {
                "ok": False,
                "error": "缺少text字段",
                "data": None
            }
        
        # 获取配置
        config = {**self.config, **payload.get("config", {})}
        
        # 计算各项分数
        scores = {
            "conflict_intensity": self._score_conflict_intensity(text),
            "hook_strength": self._score_hook_strength(text),
            "information_density": self._score_information_density(text),
            "pacing_control": self._score_pacing_control(text),
            "dialogue_naturalness": self._score_dialogue_naturalness(text),
            "scene_immersion": self._score_scene_immersion(text),
            "character_motivation": self._score_character_motivation(text),
        }
        
        # 计算总分
        scores["overall_score"] = sum(scores.values()) / len(scores)
        
        # 生成问题列表
        issues = self._identify_issues(text, scores, config)
        
        # 生成建议
        suggestions = self._generate_suggestions(scores, issues)
        
        # 计算等级
        grade = self._calculate_grade(scores["overall_score"])
        
        return {
            "ok": True,
            "error": None,
            "data": {
                "scores": scores,
                "issues": issues,
                "suggestions": suggestions,
                "grade": grade
            }
        }
    
    def _score_conflict_intensity(self, text: str) -> float:
        """评分冲突强度
        
        检测文本中的冲突关键词密度和冲突场景
        """
        # 统计冲突关键词出现次数
        conflict_count = 0
        for keyword in self.CONFLICT_KEYWORDS:
            conflict_count += text.count(keyword)
        
        # 计算冲突密度（每千字冲突词数）
        char_count = len(text)
        conflict_density = (conflict_count / max(char_count, 1)) * 1000
        
        # 检测冲突场景（对话中的冲突）
        dialogue_pattern = r'["「『]([^"」』]+)["」』]'
        dialogues = re.findall(dialogue_pattern, text)
        
        conflict_dialogues = 0
        for dialogue in dialogues:
            for keyword in self.CONFLICT_KEYWORDS:
                if keyword in dialogue:
                    conflict_dialogues += 1
                    break
        
        # 计算分数（0-100）
        # 冲突密度得分（0-50分）
        density_score = min(conflict_density * 5, 50)
        
        # 冲突对话得分（0-50分）
        dialogue_score = min(conflict_dialogues * 10, 50)
        
        total_score = density_score + dialogue_score
        
        return round(total_score, 2)
    
    def _score_hook_strength(self, text: str) -> float:
        """评分钩子强度
        
        检测章末是否有悬念、转折等钩子
        """
        # 获取最后几句话
        sentences = re.split(r'[。！？\n]', text)
        last_sentences = [s.strip() for s in sentences[-5:] if s.strip()]
        
        if not last_sentences:
            return 0.0
        
        # 检测章末钩子模式
        hook_score = 0.0
        
        for sentence in last_sentences[-2:]:  # 检查最后两句话
            for pattern in self.HOOK_PATTERNS:
                if re.search(pattern, sentence):
                    hook_score += 25
                    break
        
        # 检测章末疑问句
        if last_sentences and last_sentences[-1].endswith("?"):
            hook_score += 20
        
        # 检测章末感叹句
        if last_sentences and last_sentences[-1].endswith("！"):
            hook_score += 15
        
        # 检测章末未完成感（省略号）
        if last_sentences and "..." in last_sentences[-1]:
            hook_score += 15
        
        return round(min(hook_score, 100), 2)
    
    def _score_information_density(self, text: str) -> float:
        """评分信息密度
        
        检测文本中的信息量（名词、动词、形容词密度）
        """
        # 简化版：统计实词比例
        # 移除标点符号
        text_no_punct = re.sub(r'[^\w\s]', '', text)
        
        # 统计字符数
        char_count = len(text_no_punct)
        
        # 统计标点符号数（用于判断句子密度）
        punct_count = len(re.findall(r'[，。！？、；：]', text))
        
        # 统计数字和专有名词（简化检测）
        number_count = len(re.findall(r'\d+', text))
        
        # 统计引号（对话和引用）
        quote_count = len(re.findall(r'["「『」』"]', text))
        
        # 计算信息密度得分
        # 句子密度（每千字标点数）
        sentence_density = (punct_count / max(char_count, 1)) * 1000
        
        # 数字和引用密度
        info_elements = number_count + quote_count / 2
        info_density = (info_elements / max(char_count, 1)) * 1000
        
        # 综合得分
        density_score = min(sentence_density * 2 + info_density * 5, 100)
        
        return round(density_score, 2)
    
    def _score_pacing_control(self, text: str) -> float:
        """评分节奏控制
        
        检测文本的节奏变化（句子长度变化、段落长度变化）
        """
        # 统计句子长度
        sentences = re.split(r'[。！？]', text)
        sentence_lengths = [len(s.strip()) for s in sentences if s.strip()]
        
        if len(sentence_lengths) < 3:
            return 50.0  # 句子太少，给中等分
        
        # 计算句子长度标准差（变化程度）
        avg_length = sum(sentence_lengths) / len(sentence_lengths)
        variance = sum((l - avg_length) ** 2 for l in sentence_lengths) / len(sentence_lengths)
        std_dev = variance ** 0.5
        
        # 标准差适中为好（既不单调也不过于混乱）
        # 理想标准差在10-30之间
        if std_dev < 5:
            pacing_score = 40  # 过于单调
        elif std_dev < 15:
            pacing_score = 80  # 节奏良好
        elif std_dev < 30:
            pacing_score = 70  # 节奏尚可
        else:
            pacing_score = 50  # 过于混乱
        
        # 检测段落长度变化
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        if len(paragraphs) > 1:
            para_lengths = [len(p) for p in paragraphs]
            para_avg = sum(para_lengths) / len(para_lengths)
            para_variance = sum((l - para_avg) ** 2 for l in para_lengths) / len(para_lengths)
            para_std = para_variance ** 0.5
            
            # 段落变化也有助于节奏
            if para_std > 20:
                pacing_score += 10
        
        return round(min(pacing_score, 100), 2)
    
    def _score_dialogue_naturalness(self, text: str) -> float:
        """评分对话自然度
        
        检测对话的比例和自然程度
        """
        # 提取对话
        dialogue_pattern = r'["「『]([^"」』]+)["」』]'
        dialogues = re.findall(dialogue_pattern, text)
        
        if not dialogues:
            return 30.0  # 没有对话，给低分
        
        # 计算对话比例
        dialogue_chars = sum(len(d) for d in dialogues)
        total_chars = len(text)
        dialogue_ratio = dialogue_chars / max(total_chars, 1)
        
        # 对话比例得分（理想比例0.2-0.4）
        if dialogue_ratio < 0.1:
            ratio_score = 40
        elif dialogue_ratio < 0.3:
            ratio_score = 80
        elif dialogue_ratio < 0.5:
            ratio_score = 70
        else:
            ratio_score = 50  # 对话过多
        
        # 检测对话自然度
        natural_score = 0
        
        for dialogue in dialogues:
            # 检测口语化表达
            if any(marker in dialogue for marker in ["啊", "呢", "吧", "嘛", "哦", "呀"]):
                natural_score += 5
            
            # 检测对话长度（适中为好）
            if 5 <= len(dialogue) <= 30:
                natural_score += 3
        
        natural_score = min(natural_score / max(len(dialogues), 1) * 10, 30)
        
        total_score = ratio_score + natural_score
        
        return round(min(total_score, 100), 2)
    
    def _score_scene_immersion(self, text: str) -> float:
        """评分场景沉浸感
        
        检测场景描写的丰富程度
        """
        # 统计场景关键词出现次数
        scene_count = 0
        for keyword in self.SCENE_KEYWORDS:
            scene_count += text.count(keyword)
        
        # 计算场景密度（每千字场景词数）
        char_count = len(text)
        scene_density = (scene_count / max(char_count, 1)) * 1000
        
        # 场景密度得分（0-70分）
        density_score = min(scene_density * 7, 70)
        
        # 检测场景描写段落
        paragraphs = text.split('\n\n')
        scene_paragraphs = 0
        
        for para in paragraphs:
            # 如果段落包含多个场景关键词，认为是场景描写
            keyword_count = sum(1 for kw in self.SCENE_KEYWORDS if kw in para)
            if keyword_count >= 2:
                scene_paragraphs += 1
        
        # 场景段落得分（0-30分）
        para_score = min(scene_paragraphs * 5, 30)
        
        total_score = density_score + para_score
        
        return round(min(total_score, 100), 2)
    
    def _score_character_motivation(self, text: str) -> float:
        """评分人物动机清晰度
        
        检测人物动机的表达
        """
        # 统计动机关键词出现次数
        motivation_count = 0
        for keyword in self.MOTIVATION_KEYWORDS:
            motivation_count += text.count(keyword)
        
        # 计算动机密度（每千字动机词数）
        char_count = len(text)
        motivation_density = (motivation_count / max(char_count, 1)) * 1000
        
        # 动机密度得分（0-60分）
        density_score = min(motivation_density * 6, 60)
        
        # 检测动机表达句式
        motivation_patterns = [
            r'他.{1,5}为了.{1,20}',
            r'她.{1,5}为了.{1,20}',
            r'他.{1,5}想要.{1,20}',
            r'她.{1,5}想要.{1,20}',
            r'他.{1,5}希望.{1,20}',
            r'她.{1,5}希望.{1,20}',
        ]
        
        pattern_count = 0
        for pattern in motivation_patterns:
            pattern_count += len(re.findall(pattern, text))
        
        # 动机句式得分（0-40分）
        pattern_score = min(pattern_count * 10, 40)
        
        total_score = density_score + pattern_score
        
        return round(min(total_score, 100), 2)
    
    def _identify_issues(
        self, 
        text: str, 
        scores: dict[str, float],
        config: dict[str, Any]
    ) -> list[dict]:
        """识别问题"""
        issues = []
        
        # 检测冲突不足
        min_conflict = config.get("min_conflict_score", 40)
        if scores["conflict_intensity"] < min_conflict:
            issues.append({
                "type": "low_conflict",
                "severity": "warning",
                "score": scores["conflict_intensity"],
                "threshold": min_conflict,
                "message": f"冲突强度不足（{scores['conflict_intensity']} < {min_conflict}）"
            })
        
        # 检测钩子不足
        min_hook = config.get("min_hook_score", 50)
        if scores["hook_strength"] < min_hook:
            issues.append({
                "type": "weak_hook",
                "severity": "warning",
                "score": scores["hook_strength"],
                "threshold": min_hook,
                "message": f"章末钩子强度不足（{scores['hook_strength']} < {min_hook}）"
            })
        
        # 检测对话不足
        dialogue_pattern = r'["「『]([^"」』]+)["」』]'
        dialogues = re.findall(dialogue_pattern, text)
        dialogue_ratio = sum(len(d) for d in dialogues) / max(len(text), 1)
        
        min_dialogue = config.get("min_dialogue_ratio", 0.1)
        if dialogue_ratio < min_dialogue:
            issues.append({
                "type": "low_dialogue",
                "severity": "info",
                "ratio": round(dialogue_ratio, 3),
                "threshold": min_dialogue,
                "message": f"对话比例较低（{round(dialogue_ratio * 100, 1)}% < {min_dialogue * 100}%）"
            })
        
        # 检测场景描写不足
        if scores["scene_immersion"] < 30:
            issues.append({
                "type": "low_scene",
                "severity": "info",
                "score": scores["scene_immersion"],
                "message": "场景描写较少，可增加感官细节"
            })
        
        # 检测人物动机不清晰
        if scores["character_motivation"] < 30:
            issues.append({
                "type": "unclear_motivation",
                "severity": "info",
                "score": scores["character_motivation"],
                "message": "人物动机表达不够清晰"
            })
        
        return issues
    
    def _generate_suggestions(
        self, 
        scores: dict[str, float],
        issues: list[dict]
    ) -> list[str]:
        """生成改进建议"""
        suggestions = []
        
        # 根据分数和问题生成建议
        if scores["conflict_intensity"] < 40:
            suggestions.append("建议增加人物之间的冲突或矛盾，提升戏剧张力")
        
        if scores["hook_strength"] < 50:
            suggestions.append("建议在章末增加悬念、转折或疑问，吸引读者继续阅读")
        
        if scores["information_density"] < 40:
            suggestions.append("建议增加具体细节和描写，提升信息密度")
        
        if scores["pacing_control"] < 50:
            suggestions.append("建议调整句子和段落长度，优化叙事节奏")
        
        if scores["dialogue_naturalness"] < 50:
            suggestions.append("建议增加对话，并使用口语化表达提升自然度")
        
        if scores["scene_immersion"] < 40:
            suggestions.append("建议增加视觉、听觉、嗅觉等感官描写，增强沉浸感")
        
        if scores["character_motivation"] < 40:
            suggestions.append("建议明确表达人物的行为动机和目标")
        
        return suggestions
    
    def _calculate_grade(self, overall_score: float) -> str:
        """计算等级
        
        Args:
            overall_score: 总分（0-100）
        
        Returns:
            等级（S/A/B/C/D/F）
        """
        if overall_score >= 90:
            return "S"
        elif overall_score >= 80:
            return "A"
        elif overall_score >= 70:
            return "B"
        elif overall_score >= 60:
            return "C"
        elif overall_score >= 50:
            return "D"
        else:
            return "F"
