"""AI Style Detector Skill for detecting AI-generated text patterns.

This skill analyzes text for common AI writing patterns and provides
a score indicating how "AI-like" the text appears.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ValidatorSkill


class AIStyleDetectorSkill(ValidatorSkill):
    """Detect AI-style patterns in Chinese text.
    
    Analyzes text for:
    - Template phrases (模板句式)
    - Connector density (连接词密度)
    - Vague emotions (空泛情绪)
    - Sentence repetition (句式重复)
    - Over-explanation (过度解释)
    """
    
    skill_id = "ai-style-detector"
    version = "1.0.0"
    
    # AI-style patterns to detect
    TEMPLATE_PHRASES = [
        r"然而，",
        r"但是，",
        r"不过，",
        r"与此同时",
        r"不仅如此",
        r"由此可见",
        r"总而言之",
        r"综上所述",
        r"毫无疑问",
        r"众所周知",
        r"不言而喻",
        r"令人惊讶的是",
        r"让人意想不到的是",
        r"出乎意料的是",
    ]
    
    VAGUE_EMOTIONS = [
        r"心中.*?涌起.*?感觉",
        r"一股.*?涌上心头",
        r"内心.*?复杂",
        r"心情.*?难以言喻",
        r"说不出的.*?感",
        r"莫名.*?感动",
        r"深深的.*?触动",
        r"强烈的.*?冲击",
    ]
    
    CONNECTOR_WORDS = [
        "然后", "接着", "随后", "于是", "因此", "所以", "但是", "然而",
        "不过", "而且", "并且", "或者", "虽然", "尽管", "因为", "由于",
    ]
    
    REPETITIVE_PATTERNS = [
        r"他.*?地.*?了",
        r"她.*?地.*?了",
        r"它.*?地.*?了",
    ]
    
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Detect AI-style patterns in text.
        
        Args:
            payload: Must contain 'text' or 'content' key with text to analyze
            
        Returns:
            Envelope with AI trace score and detected issues
        """
        # Support both 'text' and 'content' for compatibility
        content = payload.get("text") or payload.get("content", "")
        if not content:
            return {
                "ok": False,
                "error": "No text or content provided",
                "data": {},
            }
        
        # Calculate individual scores
        template_score = self._detect_template_phrases(content)
        connector_score = self._detect_connector_density(content)
        emotion_score = self._detect_vague_emotions(content)
        repetition_score = self._detect_repetition(content)
        explanation_score = self._detect_over_explanation(content)
        
        # Calculate overall AI trace score (weighted average)
        overall_score = (
            template_score * 0.25 +
            connector_score * 0.20 +
            emotion_score * 0.25 +
            repetition_score * 0.15 +
            explanation_score * 0.15
        )
        
        # Determine risk level
        warn_threshold = self.config.get("warn_threshold", 45)
        fail_threshold = self.config.get("fail_threshold", 70)
        
        if overall_score >= fail_threshold:
            risk_level = "high"
            blocking = True
        elif overall_score >= warn_threshold:
            risk_level = "medium"
            blocking = False
        else:
            risk_level = "low"
            blocking = False
        
        # Collect issues
        issues = []
        if template_score > 50:
            issues.append({
                "type": "template_phrases",
                "score": template_score,
                "description": "检测到较多模板句式",
            })
        
        if connector_score > 50:
            issues.append({
                "type": "connector_density",
                "score": connector_score,
                "description": "连接词密度过高",
            })
        
        if emotion_score > 50:
            issues.append({
                "type": "vague_emotions",
                "score": emotion_score,
                "description": "存在空泛情绪描写",
            })
        
        if repetition_score > 50:
            issues.append({
                "type": "sentence_repetition",
                "score": repetition_score,
                "description": "句式重复度较高",
            })
        
        if explanation_score > 50:
            issues.append({
                "type": "over_explanation",
                "score": explanation_score,
                "description": "存在过度解释",
            })
        
        # Generate suggestions
        suggestions = []
        if template_score > 50:
            suggestions.append("减少使用固定句式模板")
        if connector_score > 50:
            suggestions.append("减少连接词使用，让句子更自然")
        if emotion_score > 50:
            suggestions.append("用具体细节替代空泛情绪描写")
        if repetition_score > 50:
            suggestions.append("丰富句式变化")
        if explanation_score > 50:
            suggestions.append("减少不必要的解释")
        
        return {
            "ok": True,
            "error": None,
            "data": {
                "ai_trace_score": int(overall_score),
                "risk_level": risk_level,
                "blocking": blocking,
                "template_phrase_score": int(template_score),
                "connector_density_score": int(connector_score),
                "vague_emotion_score": int(emotion_score),
                "sentence_repetition_score": int(repetition_score),
                "over_explanation_score": int(explanation_score),
                "issues": issues,
                "warnings": [],
                "suggestions": suggestions,
            },
        }
    
    def _detect_template_phrases(self, content: str) -> float:
        """Detect template phrases. Returns score 0-100."""
        count = 0
        for pattern in self.TEMPLATE_PHRASES:
            matches = re.findall(pattern, content)
            count += len(matches)
        
        # Normalize by text length (per 1000 chars)
        text_length = max(len(content), 1)
        density = (count / text_length) * 1000
        
        # Score: 0 occurrences = 0, 10+ per 1000 chars = 100
        return min(density * 10, 100)
    
    def _detect_connector_density(self, content: str) -> float:
        """Detect connector word density. Returns score 0-100."""
        count = 0
        for connector in self.CONNECTOR_WORDS:
            count += content.count(connector)
        
        text_length = max(len(content), 1)
        density = (count / text_length) * 1000
        
        # Score: 0 = 0, 15+ per 1000 chars = 100
        return min(density * 6.67, 100)
    
    def _detect_vague_emotions(self, content: str) -> float:
        """Detect vague emotion patterns. Returns score 0-100."""
        count = 0
        for pattern in self.VAGUE_EMOTIONS:
            matches = re.findall(pattern, content)
            count += len(matches)
        
        text_length = max(len(content), 1)
        density = (count / text_length) * 1000
        
        # Score: 0 = 0, 5+ per 1000 chars = 100
        return min(density * 20, 100)
    
    def _detect_repetition(self, content: str) -> float:
        """Detect repetitive sentence patterns. Returns score 0-100."""
        count = 0
        for pattern in self.REPETITIVE_PATTERNS:
            matches = re.findall(pattern, content)
            count += len(matches)
        
        text_length = max(len(content), 1)
        density = (count / text_length) * 1000
        
        # Score: 0 = 0, 8+ per 1000 chars = 100
        return min(density * 12.5, 100)
    
    def _detect_over_explanation(self, content: str) -> float:
        """Detect over-explanation patterns. Returns score 0-100."""
        # Look for explanatory patterns like "之所以...是因为..."
        patterns = [
            r"之所以.*?是因为",
            r"之所以.*?是由于",
            r"原因.*?在于",
            r"这.*?意味着",
            r"也就是说",
            r"换句话说",
        ]
        
        count = 0
        for pattern in patterns:
            matches = re.findall(pattern, content)
            count += len(matches)
        
        text_length = max(len(content), 1)
        density = (count / text_length) * 1000
        
        # Score: 0 = 0, 6+ per 1000 chars = 100
        return min(density * 16.67, 100)
