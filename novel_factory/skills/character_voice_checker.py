"""CharacterVoiceChecker: 检测角色口吻一致性。

检测维度：
- 角色口吻一致性
- 动机合理性
- 工具人风险

输入：content, characters（来自 repo）
规则层：检测同一角色对话风格突变、角色是否长期未出场。
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .base import ValidatorSkill


class CharacterVoiceChecker(ValidatorSkill):
    """检查角色口吻一致性和工具人风险。"""

    skill_id = "character-voice-check"
    skill_type = "validator"
    version = "1.0.0"

    # 语气词和口吻标记
    TONE_MARKERS = {
        "formal": ("在下", "鄙人", "阁下", "您", "请", "敢问"),
        "casual": ("我", "你", "他", "咱", "哥们", "兄弟", "老铁"),
        "arrogant": ("本少", "本王", "朕", "孤", "寡人", "尔等", "蝼蚁"),
        "humble": ("小的", "奴才", "草民", "在下", "不敢", "岂敢"),
        "aggressive": ("滚", "闭嘴", "找死", "混蛋", "该死", "去死"),
        "gentle": ("请", "劳烦", "麻烦", "辛苦", "抱歉", "不好意思"),
    }

    # 对话标记
    DIALOGUE_PATTERN = re.compile(r'[""「」\'\'"]([^""「」\'\'"]{2,})[""「」\'\'"]')

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content") or "")
        characters = payload.get("characters") or []

        if not content:
            return {
                "ok": False,
                "error": "缺少 content 字段",
                "data": {
                    "passed": False,
                    "score": 0,
                    "findings": [{"severity": "blocking", "code": "EMPTY_CONTENT", "message": "正文为空", "suggestion": "请提供章节正文"}],
                    "summary": "正文为空，无法进行角色口吻检查",
                },
            }

        findings = []
        score = 100

        # 1. 提取对话并分析口吻
        dialogues = self._extract_dialogues(content)
        
        if not dialogues:
            findings.append({
                "severity": "info",
                "code": "NO_DIALOGUE",
                "message": "章节中未检测到对话",
                "suggestion": "考虑增加对话以丰富角色互动",
            })
            return 100, findings

        # 2. 检查角色口吻一致性
        voice_score, voice_findings = self._check_voice_consistency(dialogues, characters)
        findings.extend(voice_findings)
        score = min(score, voice_score)

        # 3. 检查工具人风险
        tool_score, tool_findings = self._check_tool_character_risk(content, characters, dialogues)
        findings.extend(tool_findings)
        score = min(score, tool_score)

        # 4. 检查角色出场均衡性
        balance_score, balance_findings = self._check_character_balance(content, characters)
        findings.extend(balance_findings)
        score = min(score, balance_score)

        passed = score >= 70
        summary = f"角色口吻检查{'通过' if passed else '未通过'}，得分: {score}"

        return {
            "ok": True,
            "error": None,
            "data": {
                "passed": passed,
                "score": score,
                "findings": findings,
                "summary": summary,
            },
        }

    def _extract_dialogues(self, content: str) -> list[dict]:
        """提取对话内容。"""
        dialogues = []
        matches = self.DIALOGUE_PATTERN.finditer(content)
        
        for match in matches:
            dialogue_text = match.group(1)
            # 尝试识别说话者（简化版：找对话前的"说""道"等动词）
            before_text = content[:match.start()]
            speaker = self._identify_speaker(before_text)
            
            dialogues.append({
                "text": dialogue_text,
                "speaker": speaker,
                "position": match.start() / len(content),
            })
        
        return dialogues

    def _identify_speaker(self, before_text: str) -> str:
        """识别说话者（简化版）。"""
        # 找最后一个出现的人名
        # 这里简化处理，实际应该结合characters列表
        name_pattern = re.compile(r'([\u4e00-\u9fff]{2,4})(?:说|道|问|答|喊|叫|笑|叹)')
        matches = name_pattern.findall(before_text)
        return matches[-1] if matches else "未知"

    def _check_voice_consistency(self, dialogues: list[dict], characters: list[dict]) -> tuple[int, list[dict]]:
        """检查角色口吻一致性。"""
        findings = []

        # 按角色分组对话
        speaker_dialogues = defaultdict(list)
        for d in dialogues:
            speaker_dialogues[d["speaker"]].append(d["text"])

        # 检查每个角色的口吻
        for speaker, texts in speaker_dialogues.items():
            if len(texts) < 2:
                continue

            # 分析口吻类型
            tone_scores = defaultdict(int)
            for text in texts:
                for tone, markers in self.TONE_MARKERS.items():
                    for marker in markers:
                        if marker in text:
                            tone_scores[tone] += 1

            # 检查口吻是否突变
            if tone_scores:
                dominant_tone = max(tone_scores, key=tone_scores.get)
                dominant_count = tone_scores[dominant_tone]
                total_markers = sum(tone_scores.values())
                
                # 如果主导语气占比低于60%，可能存在口吻不一致
                if total_markers > 0 and dominant_count / total_markers < 0.6:
                    findings.append({
                        "severity": "warning",
                        "code": "INCONSISTENT_VOICE",
                        "message": f"角色"{speaker}"口吻不一致",
                        "suggestion": f"保持角色"{speaker}"的语气风格统一",
                    })
                    return 70, findings

        return 100, findings

    def _check_tool_character_risk(self, content: str, characters: list[dict], dialogues: list[dict]) -> tuple[int, list[dict]]:
        """检查工具人风险。"""
        findings = []

        if not characters:
            return 100, findings

        # 统计每个角色的出场次数
        character_mentions = {}
        for char in characters:
            name = char.get("name", "")
            if name:
                count = content.count(name)
                character_mentions[name] = count

        # 检查是否有角色出场次数过少（工具人风险）
        for name, count in character_mentions.items():
            if count < 3:
                findings.append({
                    "severity": "info",
                    "code": "LOW_CHARACTER_PRESENCE",
                    "message": f"角色"{name}"出场次数较少（{count}次）",
                    "suggestion": f"考虑增加"{name}"的戏份或删除该角色",
                })
                return 85, findings

        return 100, findings

    def _check_character_balance(self, content: str, characters: list[dict]) -> tuple[int, list[dict]]:
        """检查角色出场均衡性。"""
        findings = []

        if len(characters) < 2:
            return 100, findings

        # 统计每个角色的出场次数
        character_mentions = {}
        for char in characters:
            name = char.get("name", "")
            if name:
                count = content.count(name)
                character_mentions[name] = count

        if not character_mentions:
            return 100, findings

        # 计算出场次数的变异系数
        counts = list(character_mentions.values())
        if len(counts) > 1:
            mean_count = sum(counts) / len(counts)
            if mean_count > 0:
                variance = sum((c - mean_count) ** 2 for c in counts) / len(counts)
                cv = variance ** 0.5 / mean_count
                
                # 变异系数过高表示角色出场不均衡
                if cv > 1.5:
                    findings.append({
                        "severity": "info",
                        "code": "UNBALANCED_CHARACTERS",
                        "message": "角色出场次数不均衡",
                        "suggestion": "考虑调整各角色的戏份分配",
                    })
                    return 85, findings

        return 100, findings
