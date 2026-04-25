"""
上下文组装器 - 为 Agent 构建完整的上下文

核心功能：
1. 按 Token 限制智能组装上下文
2. 必须片段优先（状态卡、指令）
3. 可选片段按优先级填充
4. 超出限制时压缩非必要内容

优先级：
1. 死刑红线（AI烂词列表）- 必须
2. 写作指令 - 必须
3. 上一章状态卡 - 必须
4. 伏笔验证要求 - 必须
5. 问题模式库 - 高优先
6. 角色设定 - 中优先
7. 世界观设定 - 中优先
8. 大纲 - 低优先
"""

import json
from typing import Dict, List, Optional, Any
from pathlib import Path
import sqlite3


class ContextBuilder:
    """上下文组装器"""
    
    # Token 估算系数（中文约 0.5 token/字符）
    TOKEN_RATIO = 0.5
    
    # 片段优先级（数字越小优先级越高）
    PRIORITY = {
        'death_penalty': 0,      # 死刑红线
        'instruction': 1,        # 写作指令
        'state_card': 2,         # 状态卡
        'plot_verification': 3,  # 伏笔验证要求
        'anti_patterns': 4,      # 问题模式
        'best_practices': 5,     # 最佳实践（高分范例）
        'characters': 6,         # 角色
        'world_settings': 7,     # 世界观
        'outlines': 8,           # 大纲
        'factions': 9,           # 势力
        'pending_plots': 10,     # 待处理伏笔
    }
    
    # 必须片段（不可裁剪）
    MUST_INCLUDE = {'death_penalty', 'instruction', 'state_card', 'plot_verification'}
    
    def __init__(self, db_path: str, token_limit: int = 8000):
        """
        初始化上下文组装器
        
        Args:
            db_path: 数据库路径
            token_limit: Token 限制（默认 8000）
        """
        self.db_path = db_path
        self.token_limit = token_limit
    
    def build_for_author(self, project_id: str, chapter: int) -> str:
        """
        为 Author 构建上下文
        
        Args:
            project_id: 项目 ID
            chapter: 章节号
        
        Returns:
            完整的上下文字符串
        """
        fragments = self._collect_author_fragments(project_id, chapter)
        return self._assemble(fragments)
    
    def build_for_editor(self, project_id: str, chapter: int) -> str:
        """
        为 Editor 构建上下文
        
        Args:
            project_id: 项目 ID
            chapter: 章节号
        
        Returns:
            完整的上下文字符串
        """
        fragments = self._collect_editor_fragments(project_id, chapter)
        return self._assemble(fragments)
    
    def build_for_planner(self, project_id: str, chapter: int) -> str:
        """
        为 Planner 构建上下文
        
        Args:
            project_id: 项目 ID
            chapter: 章节号
        
        Returns:
            完整的上下文字符串
        """
        fragments = self._collect_planner_fragments(project_id, chapter)
        return self._assemble(fragments)
    
    def _collect_author_fragments(self, project_id: str, chapter: int) -> Dict[str, str]:
        """收集 Author 需要的片段"""
        fragments = {}
        conn = self._get_connection()
        
        try:
            # 1. 死刑红线（必须）
            fragments['death_penalty'] = self._get_death_penalty()
            
            # 2. 写作指令（必须）
            instruction = self._get_instruction(conn, project_id, chapter)
            if instruction:
                fragments['instruction'] = instruction
            
            # 3. 上一章状态卡（必须）
            prev_state = self._get_chapter_state(conn, project_id, chapter - 1)
            if prev_state:
                fragments['state_card'] = f"【上一章状态卡】\n{prev_state}"
            
            # 4. 伏笔验证要求（必须）
            plot_req = self._get_plot_requirements(conn, project_id, chapter)
            if plot_req:
                fragments['plot_verification'] = f"【伏笔要求】\n{plot_req}"
            
            # 5. 问题模式库（高优先）
            anti_patterns = self._get_anti_patterns(conn)
            if anti_patterns:
                fragments['anti_patterns'] = f"【避坑指南】\n{anti_patterns}"
            
            # 6. 最佳实践（高分范例）
            practices = self._get_best_practices(conn, project_id)
            if practices:
                fragments['best_practices'] = f"【高分范例】\n{practices}"
            
            # 7. 角色设定（中优先）
            characters = self._get_characters(conn, project_id)
            if characters:
                fragments['characters'] = f"【角色设定】\n{characters}"
            
            # 8. 世界观（中优先）
            world = self._get_world_settings(conn, project_id)
            if world:
                fragments['world_settings'] = f"【世界观】\n{world}"
            
            # 9. 待处理伏笔（低优先）
            pending_plots = self._get_pending_plots(conn, project_id)
            if pending_plots:
                fragments['pending_plots'] = f"【待处理伏笔】\n{pending_plots}"
            
        finally:
            conn.close()
        
        return fragments
    
    def _collect_editor_fragments(self, project_id: str, chapter: int) -> Dict[str, str]:
        """收集 Editor 需要的片段"""
        fragments = {}
        conn = self._get_connection()
        
        try:
            # 1. 死刑红线（必须）
            fragments['death_penalty'] = self._get_death_penalty()
            
            # 2. 写作指令（必须）
            instruction = self._get_instruction(conn, project_id, chapter)
            if instruction:
                fragments['instruction'] = instruction
            
            # 3. 上一章状态卡（必须）
            prev_state = self._get_chapter_state(conn, project_id, chapter - 1)
            if prev_state:
                fragments['state_card'] = f"【上一章状态卡】\n{prev_state}"
            
            # 4. 伏笔验证要求（必须）
            plot_req = self._get_plot_requirements(conn, project_id, chapter)
            if plot_req:
                fragments['plot_verification'] = f"【伏笔验证要求】\n{plot_req}"
            
            # 5. 问题模式库（高优先）
            anti_patterns = self._get_anti_patterns(conn, all_patterns=True)
            if anti_patterns:
                fragments['anti_patterns'] = f"【问题模式库】\n{anti_patterns}"
            
            # 6. 角色设定（中优先）
            characters = self._get_characters(conn, project_id)
            if characters:
                fragments['characters'] = f"【角色设定】\n{characters}"
            
            # 7. 世界观（中优先）
            world = self._get_world_settings(conn, project_id)
            if world:
                fragments['world_settings'] = f"【世界观】\n{world}"
            
            # 8. 章节内容（必须单独处理）
            content = self._get_chapter_content(conn, project_id, chapter)
            if content:
                fragments['chapter_content'] = f"【本章正文】\n{content}"
            
        finally:
            conn.close()
        
        return fragments
    
    def _collect_planner_fragments(self, project_id: str, chapter: int) -> Dict[str, str]:
        """收集 Planner 需要的片段"""
        fragments = {}
        conn = self._get_connection()
        
        try:
            # 1. 上一章状态卡（必须）
            prev_state = self._get_chapter_state(conn, project_id, chapter - 1)
            if prev_state:
                fragments['state_card'] = f"【上一章状态卡】\n{prev_state}"
            else:
                fragments['state_card'] = "【初始状态】第一章，无上一章状态卡"
            
            # 2. 角色设定
            characters = self._get_characters(conn, project_id)
            if characters:
                fragments['characters'] = f"【角色设定】\n{characters}"
            
            # 3. 世界观
            world = self._get_world_settings(conn, project_id)
            if world:
                fragments['world_settings'] = f"【世界观】\n{world}"
            
            # 4. 势力
            factions = self._get_factions(conn, project_id)
            if factions:
                fragments['factions'] = f"【势力设定】\n{factions}"
            
            # 5. 大纲
            outlines = self._get_outlines(conn, project_id)
            if outlines:
                fragments['outlines'] = f"【大纲】\n{outlines}"
            
            # 6. 待处理伏笔
            pending_plots = self._get_pending_plots(conn, project_id)
            if pending_plots:
                fragments['pending_plots'] = f"【待处理伏笔】\n{pending_plots}"
            
            # 7. 待处理消息
            messages = self._get_pending_messages(conn, project_id)
            if messages:
                fragments['messages'] = f"【待处理异议】\n{messages}"
            
        finally:
            conn.close()
        
        return fragments
    
    def _assemble(self, fragments: Dict[str, str]) -> str:
        """
        组装上下文
        
        按优先级组装，Token 限制时裁剪低优先级内容
        """
        # 按优先级排序
        sorted_fragments = sorted(
            fragments.items(),
            key=lambda x: self.PRIORITY.get(x[0], 99)
        )
        
        result = []
        current_tokens = 0
        
        for key, content in sorted_fragments:
            content_tokens = self._estimate_tokens(content)
            
            # 必须片段不可裁剪
            if key in self.MUST_INCLUDE:
                result.append(content)
                current_tokens += content_tokens
            # 可选片段检查 Token 限制
            elif current_tokens + content_tokens <= self.token_limit:
                result.append(content)
                current_tokens += content_tokens
            else:
                # 超出限制，尝试压缩
                compressed = self._compress(content, self.token_limit - current_tokens)
                if compressed:
                    result.append(compressed)
                    current_tokens += self._estimate_tokens(compressed)
                    break  # 压缩后也超限，停止
        
        return "\n\n---\n\n".join(result)
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 Token 数量"""
        return int(len(text) * self.TOKEN_RATIO)
    
    def _compress(self, text: str, max_tokens: int) -> Optional[str]:
        """
        压缩文本以适应 Token 限制
        
        策略：保留关键信息，删除详细描述
        """
        if max_tokens < 100:
            return None
        
        max_chars = int(max_tokens / self.TOKEN_RATIO)
        
        # 简单截断（可优化为摘要）
        if len(text) > max_chars:
            return text[:max_chars - 50] + "\n...[已压缩]"
        
        return text
    
    # ========== 数据获取方法 ==========
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_death_penalty(self) -> str:
        """获取死刑红线（AI烂词列表）"""
        return """【死刑红线 - 触发即总分=50】

表情动作类（禁用）：
- 冷笑（及变体：冷笑一声、嘴角勾起冷笑）
- 嘴角微扬/嘴角勾起一抹XX
- 倒吸一口凉气
- 眼中闪过一道寒芒/冷意/精光
- 不由得/不禁/忍不住 + 心理活动

句式类（禁用）：
- 不仅...而且...更是...
- 夜色笼罩/夜幕降临
- 心中暗想/心道

说教类（禁用）：
- 章节末尾总结人生道理
- 上帝视角的哲理感慨"""
    
    def _get_instruction(self, conn, project_id: str, chapter: int) -> Optional[str]:
        """获取写作指令"""
        cursor = conn.execute("""
            SELECT objective, key_events, ending_hook, plots_to_plant, plots_to_resolve, emotion_tone
            FROM instructions WHERE project_id=? AND chapter_number=?
        """, (project_id, chapter))
        row = cursor.fetchone()
        if not row:
            return None
        
        parts = []
        parts.append(f"目标：{row['objective']}")
        if row['key_events']:
            parts.append(f"关键事件：{row['key_events']}")
        if row['ending_hook']:
            parts.append(f"章末钩子：{row['ending_hook']}")
        if row['plots_to_plant']:
            parts.append(f"埋设伏笔：{row['plots_to_plant']}")
        if row['plots_to_resolve']:
            parts.append(f"兑现伏笔：{row['plots_to_resolve']}")
        if row['emotion_tone']:
            parts.append(f"情绪基调：{row['emotion_tone']}")
        
        return "\n".join(parts)
    
    def _get_chapter_state(self, conn, project_id: str, chapter: int) -> Optional[str]:
        """获取状态卡"""
        cursor = conn.execute("""
            SELECT state_data, summary FROM chapter_state
            WHERE project_id=? AND chapter_number=?
        """, (project_id, chapter))
        row = cursor.fetchone()
        if not row:
            return None
        
        if row['summary']:
            return row['summary']
        elif row['state_data']:
            return row['state_data']
        return None
    
    def _get_plot_requirements(self, conn, project_id: str, chapter: int) -> Optional[str]:
        """获取伏笔验证要求"""
        cursor = conn.execute("""
            SELECT plots_to_plant, plots_to_resolve FROM instructions
            WHERE project_id=? AND chapter_number=?
        """, (project_id, chapter))
        row = cursor.fetchone()
        if not row:
            return None
        
        parts = []
        if row['plots_to_plant'] and row['plots_to_plant'] != '[]':
            parts.append(f"必须埋设：{row['plots_to_plant']}")
        if row['plots_to_resolve'] and row['plots_to_resolve'] != '[]':
            parts.append(f"必须兑现：{row['plots_to_resolve']}")
        
        return "\n".join(parts) if parts else None
    
    def _get_anti_patterns(self, conn, all_patterns: bool = False) -> Optional[str]:
        """获取问题模式"""
        if all_patterns:
            cursor = conn.execute("""
                SELECT code, pattern, description FROM anti_patterns
                WHERE enabled=1 ORDER BY severity, category
            """)
        else:
            cursor = conn.execute("""
                SELECT code, pattern, description FROM anti_patterns
                WHERE enabled=1 AND severity IN ('critical', 'high')
                ORDER BY severity, category
            """)
        
        rows = cursor.fetchall()
        if not rows:
            return None
        
        parts = []
        for row in rows:
            parts.append(f"- [{row['code']}] {row['pattern']}: {row['description']}")
        
        return "\n".join(parts)
    
    def _get_best_practices(self, conn, project_id: str) -> Optional[str]:
        """获取最佳实践（高分范例）"""
        cursor = conn.execute("""
            SELECT category, practice, evidence, source_score, chapter_numbers
            FROM best_practices
            WHERE (project_id = ? OR project_id IS NULL)
            AND source_score >= 85
            ORDER BY source_score DESC, category
            LIMIT 15
        """, (project_id,))
        
        rows = cursor.fetchall()
        if not rows:
            return None
        
        parts = []
        for row in rows:
            cat_name = {
                'hook': '开篇',
                'pacing': '节奏',
                'dialogue': '对话',
                'action': '动作',
                'emotion': '情感',
                'setting': '设定'
            }.get(row['category'], row['category'])
            
            parts.append(f"- 【{cat_name}】{row['practice']}")
            if row['evidence']:
                parts.append(f"  示例：{row['evidence'][:80]}")
            if row['chapter_numbers']:
                parts.append(f"  来源：第{row['chapter_numbers']}章（{row['source_score']}分）")
        
        return "\n".join(parts)
    
    def _get_characters(self, conn, project_id: str) -> Optional[str]:
        """获取角色设定"""
        cursor = conn.execute("""
            SELECT name, role, description FROM characters
            WHERE project_id=? AND status='active'
        """, (project_id,))
        rows = cursor.fetchall()
        if not rows:
            return None
        
        parts = []
        for row in rows:
            parts.append(f"- {row['name']}（{row['role']}）：{row['description']}")
        
        return "\n".join(parts)
    
    def _get_world_settings(self, conn, project_id: str) -> Optional[str]:
        """获取世界观设定"""
        cursor = conn.execute("""
            SELECT category, title, content FROM world_settings
            WHERE project_id=? ORDER BY category
        """, (project_id,))
        rows = cursor.fetchall()
        if not rows:
            return None
        
        parts = []
        current_category = None
        for row in rows:
            if row['category'] != current_category:
                current_category = row['category']
                parts.append(f"\n【{row['category']}】")
            parts.append(f"  {row['title']}: {row['content'][:100]}...")
        
        return "\n".join(parts)
    
    def _get_pending_plots(self, conn, project_id: str) -> Optional[str]:
        """获取待处理伏笔"""
        cursor = conn.execute("""
            SELECT code, title, description, planted_chapter, planned_resolve_chapter
            FROM plot_holes WHERE project_id=? AND status='planted'
            ORDER BY planned_resolve_chapter
        """, (project_id,))
        rows = cursor.fetchall()
        if not rows:
            return None
        
        parts = []
        for row in rows:
            parts.append(f"- [{row['code']}] {row['title']}（埋设：第{row['planted_chapter']}章，计划兑现：第{row['planned_resolve_chapter']}章）")
        
        return "\n".join(parts)
    
    def _get_factions(self, conn, project_id: str) -> Optional[str]:
        """获取势力设定"""
        cursor = conn.execute("""
            SELECT name, type, description, relationship_with_protagonist
            FROM factions WHERE project_id=?
        """, (project_id,))
        rows = cursor.fetchall()
        if not rows:
            return None
        
        parts = []
        for row in rows:
            parts.append(f"- {row['name']}（{row['type']}，{row['relationship_with_protagonist']}）：{row['description']}")
        
        return "\n".join(parts)
    
    def _get_outlines(self, conn, project_id: str) -> Optional[str]:
        """获取大纲"""
        cursor = conn.execute("""
            SELECT level, sequence, title, content, chapters_range
            FROM outlines WHERE project_id=? ORDER BY level, sequence
        """, (project_id,))
        rows = cursor.fetchall()
        if not rows:
            return None
        
        parts = []
        for row in rows:
            range_str = f"（第{row['chapters_range']}章）" if row['chapters_range'] else ""
            parts.append(f"- [{row['level']}] {row['title']}{range_str}: {row['content'][:100]}...")
        
        return "\n".join(parts)
    
    def _get_chapter_content(self, conn, project_id: str, chapter: int) -> Optional[str]:
        """获取章节内容"""
        cursor = conn.execute("""
            SELECT content FROM chapters WHERE project_id=? AND chapter_number=?
        """, (project_id, chapter))
        row = cursor.fetchone()
        return row['content'] if row else None
    
    def _get_pending_messages(self, conn, project_id: str) -> Optional[str]:
        """获取待处理消息"""
        cursor = conn.execute("""
            SELECT from_agent, type, content FROM agent_messages
            WHERE project_id=? AND to_agent='planner' AND status='pending'
        """, (project_id,))
        rows = cursor.fetchall()
        if not rows:
            return None
        
        parts = []
        for row in rows:
            parts.append(f"- [{row['from_agent']}] {row['type']}: {row['content'][:200]}")
        
        return "\n".join(parts)


# ========== 便捷函数 ==========

def build_author_context(project_id: str, chapter: int, db_path: str = None) -> str:
    """为 Author 构建上下文的便捷函数"""
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "data" / "novel_factory.db")
    builder = ContextBuilder(db_path)
    return builder.build_for_author(project_id, chapter)


def build_editor_context(project_id: str, chapter: int, db_path: str = None) -> str:
    """为 Editor 构建上下文的便捷函数"""
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "data" / "novel_factory.db")
    builder = ContextBuilder(db_path)
    return builder.build_for_editor(project_id, chapter)


def build_planner_context(project_id: str, chapter: int, db_path: str = None) -> str:
    """为 Planner 构建上下文的便捷函数"""
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "data" / "novel_factory.db")
    builder = ContextBuilder(db_path)
    return builder.build_for_planner(project_id, chapter)
