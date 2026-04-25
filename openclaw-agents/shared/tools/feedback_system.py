#!/usr/bin/env python3
"""
Agent 反馈升级系统

核心设计原则：
1. 这是"异步消息队列"，Agent 不直接通知彼此
2. Dispatcher 在调度 Agent 时检查 pending messages
3. 保持"调度器驱动"架构，不破坏"禁止直接通信"规则

使用方式：
- Editor 审校后发现非写作问题 → 写入 agent_messages
- Dispatcher 调度 Planner 时 → 检查是否有待处理消息
- Planner 处理完消息 → 标记 resolved

数据库位置：shared/data/novel_factory.db
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Literal
import os
import sys

# 添加共享工具目录到路径
_shared_tools = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import DB_PATH, get_connection

# 消息类型
MessageType = Literal[
    "REQUEST_REVIEW",   # 请求审查
    "FLAG_ISSUE",       # 标记问题
    "ESCALATE",         # 升级问题
    "SUGGEST",          # 建议修改
    "NOTIFY",           # 通知
    "RESPONSE"          # 响应
]

Priority = Literal["low", "normal", "high", "urgent"]

IssueOwner = Literal["author", "planner", "editor", "system", "worldbuilding"]


class AgentMessenger:
    """Agent 间消息系统"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH

    def _get_conn(self):
        return get_connection()

    def send(
        self,
        project_id: str,
        from_agent: str,
        to_agent: str,
        msg_type: MessageType,
        content: Dict,
        priority: Priority = "normal",
        chapter_number: int = None
    ) -> int:
        """
        发送异步消息（注意：不会实时通知，只是写入队列）

        Args:
            project_id: 项目ID
            from_agent: 发送方 Agent ID (e.g., 'editor', 'dispatcher')
            to_agent: 接收方 Agent ID (e.g., 'planner', 'author')
            msg_type: 消息类型
            content: 消息内容（字典）
            priority: 优先级
            chapter_number: 关联章节号（可选）

        Returns:
            消息 ID
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                INSERT INTO agent_messages (project_id, from_agent, to_agent, type, priority, content, chapter_number)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (project_id, from_agent, to_agent, msg_type, priority, json.dumps(content, ensure_ascii=False), chapter_number))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_pending(self, project_id: str = None, to_agent: str = None, priority: Priority = None) -> List[Dict]:
        """
        获取待处理消息

        Args:
            project_id: 项目ID（可选，None 表示全部）
            to_agent: 接收方（可选，None 表示全部）
            priority: 优先级过滤（可选）

        Returns:
            待处理消息列表
        """
        conn = self._get_conn()
        try:
            query = "SELECT * FROM agent_messages WHERE status = 'pending'"
            params = []

            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)

            if to_agent:
                query += " AND to_agent = ?"
                params.append(to_agent)

            if priority:
                query += " AND priority = ?"
                params.append(priority)

            query += " ORDER BY priority DESC, created_at ASC"

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def resolve(self, message_id: int, result: Dict = None):
        """标记消息为已解决"""
        conn = self._get_conn()
        try:
            conn.execute("""
                UPDATE agent_messages
                SET status = 'resolved', processed_at = datetime('now', '+8 hours'), result = ?
                WHERE id = ?
            """, (json.dumps(result or {}), message_id))
            conn.commit()
        finally:
            conn.close()


class FeedbackEscalator:
    """
    反馈升级系统

    核心设计：
    1. 问题归属分析 - 判断问题是谁的责任
    2. 异步升级 - 写入 agent_messages，不实时通知
    3. Dispatcher 集成 - 下次调度时检查并处理

    注意：这不会触发即时通知，保持"调度器驱动"架构
    """

    # 问题归属到负责 Agent 的映射
    OWNER_AGENT_MAP = {
        "author": "author",       # 写作问题 → 执笔修改
        "planner": "planner",     # 指令/设定问题 → 总编调整
        "editor": "editor",       # 审校标准问题 → 质检自查
        "system": "dispatcher",   # 系统问题 → 调度器处理
        "worldbuilding": "planner"  # 世界观问题 → 总编调整
    }

    # 升级阈值
    ESCALATION_THRESHOLDS = {
        "same_chapter_revision": 2,  # 同一章节退回 2 次 → 检查指令
        "same_chapter_circuit": 3,   # 同一章节退回 3 次 → 熔断，人工介入
        "pattern_repeat": 3,         # 相同问题重复 3 次 → 记录模式
    }

    def __init__(self, messenger: AgentMessenger = None):
        self.messenger = messenger or AgentMessenger()

    def classify_issue(self, issue: Dict) -> IssueOwner:
        """
        分析问题归属

        Args:
            issue: 质检问题

        Returns:
            问题归属
        """
        issue_type = issue.get("type", "")
        desc = issue.get("desc", "").lower()

        # 写作问题
        writing_keywords = ["ai痕迹", "冷笑", "嘴角", "文字", "句式", "排比"]
        if any(kw in desc for kw in writing_keywords):
            return "author"

        # 逻辑问题
        logic_keywords = ["逻辑", "降智", "反派", "动机"]
        if any(kw in desc for kw in logic_keywords):
            return "author"

        # 指令问题
        instruction_keywords = ["指令", "伏笔", "状态卡", "设定"]
        if any(kw in desc for kw in instruction_keywords):
            return "planner"

        # 设定问题
        setting_keywords = ["世界观", "力量体系", "角色设定"]
        if any(kw in desc for kw in setting_keywords):
            return "worldbuilding"

        # 系统问题
        system_keywords = ["数据库", "状态卡", "数值"]
        if any(kw in desc for kw in system_keywords):
            return "system"

        # 默认归 Author
        return "author"

    def should_escalate(
        self,
        project: str,
        chapter: int,
        issue_owner: IssueOwner
    ) -> Dict:
        """
        判断是否需要升级

        Returns:
            {"escalate": bool, "level": str, "reason": str}
        """
        conn = get_connection()
        try:
            # 查询该章节的退回次数
            cursor = conn.execute("""
                SELECT COUNT(*) as revision_count
                FROM task_status
                WHERE project_id = ? AND chapter_number = ? AND task_type = 'revise'
            """, (project, chapter))
            revision_count = cursor.fetchone()["revision_count"]

            # 判断升级级别
            if revision_count >= self.ESCALATION_THRESHOLDS["same_chapter_circuit"]:
                return {
                    "escalate": True,
                    "level": "circuit_breaker",
                    "target": "chief-editor",
                    "reason": f"第 {chapter} 章已退回 {revision_count} 次，触发熔断"
                }

            if revision_count >= self.ESCALATION_THRESHOLDS["same_chapter_revision"]:
                return {
                    "escalate": True,
                    "level": "instruction_review",
                    "target": "planner",
                    "reason": f"第 {chapter} 章已退回 {revision_count} 次，需审查指令"
                }

            # 问题归属非 Author，也需要升级
            if issue_owner not in ["author"]:
                return {
                    "escalate": True,
                    "level": "owner_escalation",
                    "target": self.OWNER_AGENT_MAP.get(issue_owner, "planner"),
                    "reason": f"问题归属 {issue_owner}，需对应 Agent 处理"
                }

            return {"escalate": False}

        finally:
            conn.close()

    def escalate(
        self,
        project: str,
        chapter: int,
        issue: Dict,
        from_agent: str = "editor"
    ) -> int:
        """
        执行升级

        Returns:
            消息 ID
        """
        # 分类问题归属
        issue_owner = self.classify_issue(issue)

        # 增强问题信息
        enhanced_issue = {
            **issue,
            "owner": issue_owner,
            "project": project,
            "chapter": chapter
        }

        # 判断是否升级
        escalation = self.should_escalate(project, chapter, issue_owner)

        if escalation["escalate"]:
            # 发送升级消息
            return self.messenger.send(
                from_agent=from_agent,
                to_agent=escalation["target"],
                msg_type="ESCALATE",
                content={
                    "issue": enhanced_issue,
                    "level": escalation["level"],
                    "reason": escalation["reason"]
                },
                priority="high"
            )

        # 不升级，发送普通通知
        target = self.OWNER_AGENT_MAP.get(issue_owner, "author")
        return self.messenger.send(
            from_agent=from_agent,
            to_agent=target,
            msg_type="FLAG_ISSUE",
            content=enhanced_issue,
            priority="normal"
        )


class PatternLearner:
    """问题模式学习器"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH

    def _get_conn(self):
        return get_connection()

    def record_pattern(
        self,
        project: str,
        chapter: int,
        category: str,
        pattern: str
    ) -> int:
        """
        记录问题模式（供 Editor 调用）

        Args:
            project: 项目ID
            chapter: 章节号
            category: 问题类别 (ai_trace, logic, setting, poison, pacing)
            pattern: 问题模式描述

        Returns:
            记录ID
        """
        conn = self._get_conn()
        try:
            # 检查是否已存在相同模式
            cursor = conn.execute("""
                SELECT id, frequency FROM learned_patterns
                WHERE project_id = ? AND category = ? AND pattern = ?
            """, (project, category, pattern))
            existing = cursor.fetchone()

            if existing:
                # 更新频率
                conn.execute("""
                    UPDATE learned_patterns
                    SET frequency = frequency + 1, last_seen = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (existing["id"],))
                conn.commit()
                return existing["id"]
            else:
                # 新增模式
                cursor = conn.execute("""
                    INSERT INTO learned_patterns (project_id, chapter_number, category, pattern)
                    VALUES (?, ?, ?, ?)
                """, (project, chapter, category, pattern))
                conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    def get_patterns(self, project: str = None, category: str = None, min_frequency: int = 1) -> List[Dict]:
        """
        获取问题模式列表

        Args:
            project: 项目ID（可选，None 表示全部）
            category: 问题类别（可选）
            min_frequency: 最小出现次数

        Returns:
            模式列表
        """
        conn = self._get_conn()
        try:
            query = "SELECT * FROM learned_patterns WHERE frequency >= ? AND enabled = 1"
            params = [min_frequency]

            if project:
                query += " AND project_id = ?"
                params.append(project)

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " ORDER BY frequency DESC, last_seen DESC"

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def disable_pattern(self, pattern_id: int):
        """禁用某个模式（已解决或误报）"""
        conn = self._get_conn()
        try:
            conn.execute("UPDATE learned_patterns SET enabled = 0 WHERE id = ?", (pattern_id,))
            conn.commit()
        finally:
            conn.close()


class VersionManager:
    """章节版本管理器"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH

    def _get_conn(self):
        return get_connection()

    def save_version(
        self,
        project: str,
        chapter: int,
        content: str,
        created_by: str = "author",
        review_id: int = None,
        notes: str = None
    ) -> int:
        """保存章节版本"""
        conn = self._get_conn()
        try:
            # 获取当前版本号
            cursor = conn.execute("""
                SELECT MAX(version) as max_version
                FROM chapter_versions
                WHERE project_id = ? AND chapter = ?
            """, (project, chapter))
            max_version = cursor.fetchone()["max_version"] or 0

            # 插入新版本
            cursor = conn.execute("""
                INSERT INTO chapter_versions
                (project_id, chapter, version, content, word_count, created_by, review_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (project, chapter, max_version + 1, content, len(content), created_by, review_id, notes))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def list_versions(self, project: str, chapter: int) -> List[Dict]:
        """列出版本历史"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT * FROM chapter_versions
                WHERE project_id = ? AND chapter = ?
                ORDER BY version DESC
            """, (project, chapter))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_version(self, project: str, chapter: int, version: int) -> Optional[Dict]:
        """获取指定版本"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT * FROM chapter_versions
                WHERE project_id = ? AND chapter = ? AND version = ?
            """, (project, chapter, version))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def rollback(self, project: str, chapter: int, version: int) -> bool:
        """回滚到指定版本"""
        # 获取指定版本内容
        version_data = self.get_version(project, chapter, version)
        if not version_data:
            return False

        conn = self._get_conn()
        try:
            # 更新章节表
            conn.execute("""
                UPDATE chapters SET draft = ?, word_count = ?
                WHERE project_id = ? AND chapter_number = ?
            """, (version_data["content"], version_data["word_count"], project, chapter))

            # 保存回滚版本
            self.save_version(
                project, chapter,
                version_data["content"],
                created_by="rollback",
                notes=f"回滚到版本 {version}"
            )

            conn.commit()
            return True
        finally:
            conn.close()

    def compare_versions(
        self,
        project: str,
        chapter: int,
        v1: int,
        v2: int
    ) -> Dict:
        """比较两个版本"""
        ver1 = self.get_version(project, chapter, v1)
        ver2 = self.get_version(project, chapter, v2)

        if not ver1 or not ver2:
            return {"error": "版本不存在"}

        # 简单的差异统计
        content1 = ver1["content"] or ""
        content2 = ver2["content"] or ""

        return {
            "v1": {
                "version": v1,
                "word_count": ver1["word_count"],
                "created_at": ver1["created_at"],
                "created_by": ver1["created_by"]
            },
            "v2": {
                "version": v2,
                "word_count": ver2["word_count"],
                "created_at": ver2["created_at"],
                "created_by": ver2["created_by"]
            },
            "diff": {
                "word_count_change": ver2["word_count"] - ver1["word_count"],
                "length_change": len(content2) - len(content1)
            }
        }


class StateHistoryManager:
    """状态卡历史管理器"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH

    def _get_conn(self):
        return get_connection()

    def save_state(
        self,
        project: str,
        chapter: int,
        state: Dict,
        changed_fields: Dict = None,
        reason: str = None
    ) -> int:
        """保存状态卡历史"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                INSERT INTO state_history (project_id, chapter, state_json, changed_fields, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (
                project, chapter,
                json.dumps(state, ensure_ascii=False),
                json.dumps(changed_fields or {}, ensure_ascii=False),
                reason
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_history(self, project: str, field: str = None) -> List[Dict]:
        """获取状态变更历史"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT * FROM state_history
                WHERE project_id = ?
                ORDER BY created_at DESC
            """, (project,))
            results = [dict(row) for row in cursor.fetchall()]

            # 如果指定字段，过滤
            if field:
                filtered = []
                for r in results:
                    changed = json.loads(r["changed_fields"] or "{}")
                    if field in changed:
                        filtered.append({
                            **r,
                            "field": field,
                            "change": changed[field]
                        })
                return filtered

            return results
        finally:
            conn.close()

    def diff_states(self, project: str, chapter1: int, chapter2: int) -> Dict:
        """比较两个章节的状态"""
        conn = self._get_conn()
        try:
            # 获取两个章节最新的状态
            cursor1 = conn.execute("""
                SELECT state_json FROM state_history
                WHERE project_id = ? AND chapter = ?
                ORDER BY created_at DESC LIMIT 1
            """, (project, chapter1))
            state1 = cursor1.fetchone()

            cursor2 = conn.execute("""
                SELECT state_json FROM state_history
                WHERE project_id = ? AND chapter = ?
                ORDER BY created_at DESC LIMIT 1
            """, (project, chapter2))
            state2 = cursor2.fetchone()

            if not state1 or not state2:
                return {"error": "状态不存在"}

            s1 = json.loads(state1["state_json"])
            s2 = json.loads(state2["state_json"])

            # 计算差异
            diff = {}
            all_keys = set(s1.keys()) | set(s2.keys())
            for key in all_keys:
                v1 = s1.get(key)
                v2 = s2.get(key)
                if v1 != v2:
                    diff[key] = {"from": v1, "to": v2}

            return {
                "chapter1": chapter1,
                "chapter2": chapter2,
                "diff": diff
            }
        finally:
            conn.close()


# 便捷函数（供 db.py 调用）
def cmd_send_message(args):
    """发送 Agent 消息：db.py send_message <from> <to> <type> <content_json>"""
    if len(args) < 4:
        print(json.dumps({"error": "Usage: db.py send_message <from> <to> <type> <content_json>"}, ensure_ascii=False))
        return

    messenger = AgentMessenger()
    msg_id = messenger.send(
        from_agent=args[0],
        to_agent=args[1],
        msg_type=args[2],
        content=json.loads(args[3]),
        priority=args[4] if len(args) > 4 else "normal"
    )
    print(json.dumps({"success": True, "message_id": msg_id}, ensure_ascii=False))


def cmd_get_messages(args):
    """获取待处理消息：db.py get_messages [to_agent] [priority]"""
    messenger = AgentMessenger()
    to_agent = args[0] if len(args) > 0 else None
    priority = args[1] if len(args) > 1 else None
    messages = messenger.get_pending(to_agent, priority)
    print(json.dumps(messages, ensure_ascii=False, indent=2))


def cmd_resolve_message(args):
    """解决消息：db.py resolve_message <message_id> [result_json]"""
    if len(args) < 1:
        print(json.dumps({"error": "Usage: db.py resolve_message <message_id> [result_json]"}, ensure_ascii=False))
        return

    messenger = AgentMessenger()
    result = json.loads(args[1]) if len(args) > 1 else None
    messenger.resolve(int(args[0]), result)
    print(json.dumps({"success": True}, ensure_ascii=False))


def cmd_save_version(args):
    """保存章节版本：db.py save_version <project> <chapter> <content_file> [created_by]"""
    if len(args) < 3:
        print(json.dumps({"error": "Usage: db.py save_version <project> <chapter> <content_file> [created_by]"}, ensure_ascii=False))
        return

    project, chapter = args[0], int(args[1])
    content_file = args[2]
    created_by = args[3] if len(args) > 3 else "author"

    with open(content_file, 'r', encoding='utf-8') as f:
        content = f.read()

    vm = VersionManager()
    version_id = vm.save_version(project, chapter, content, created_by)
    print(json.dumps({"success": True, "version_id": version_id}, ensure_ascii=False))


def cmd_list_versions(args):
    """列出版本历史：db.py list_versions <project> <chapter>"""
    if len(args) < 2:
        print(json.dumps({"error": "Usage: db.py list_versions <project> <chapter>"}, ensure_ascii=False))
        return

    vm = VersionManager()
    versions = vm.list_versions(args[0], int(args[1]))
    print(json.dumps(versions, ensure_ascii=False, indent=2))


def cmd_rollback(args):
    """回滚版本：db.py rollback <project> <chapter> <version>"""
    if len(args) < 3:
        print(json.dumps({"error": "Usage: db.py rollback <project> <chapter> <version>"}, ensure_ascii=False))
        return

    vm = VersionManager()
    success = vm.rollback(args[0], int(args[1]), int(args[2]))
    print(json.dumps({"success": success}, ensure_ascii=False))


def cmd_state_history(args):
    """查看状态变更历史：db.py state_history <project> [field]"""
    if len(args) < 1:
        print(json.dumps({"error": "Usage: db.py state_history <project> [field]"}, ensure_ascii=False))
        return

    shm = StateHistoryManager()
    field = args[1] if len(args) > 1 else None
    history = shm.get_history(args[0], field)
    print(json.dumps(history, ensure_ascii=False, indent=2))


def cmd_record_pattern(args):
    """记录问题模式：db.py record_pattern <project> <chapter> <category> <pattern>"""
    if len(args) < 4:
        print(json.dumps({"error": "Usage: db.py record_pattern <project> <chapter> <category> <pattern>"}, ensure_ascii=False))
        return

    learner = PatternLearner()
    pattern_id = learner.record_pattern(args[0], int(args[1]), args[2], args[3])
    print(json.dumps({"success": True, "pattern_id": pattern_id}, ensure_ascii=False))


def cmd_get_patterns(args):
    """获取问题模式：db.py get_patterns [project] [category] [min_frequency]"""
    learner = PatternLearner()
    project = args[0] if len(args) > 0 else None
    category = args[1] if len(args) > 1 else None
    min_frequency = int(args[2]) if len(args) > 2 else 1
    patterns = learner.get_patterns(project, category, min_frequency)
    print(json.dumps(patterns, ensure_ascii=False, indent=2))


def cmd_disable_pattern(args):
    """禁用模式：db.py disable_pattern <pattern_id>"""
    if len(args) < 1:
        print(json.dumps({"error": "Usage: db.py disable_pattern <pattern_id>"}, ensure_ascii=False))
        return

    learner = PatternLearner()
    learner.disable_pattern(int(args[0]))
    print(json.dumps({"success": True}, ensure_ascii=False))


# 导出命令映射
COMMANDS = {
    'send_message': cmd_send_message,
    'get_messages': cmd_get_messages,
    'resolve_message': cmd_resolve_message,
    'save_version': cmd_save_version,
    'list_versions': cmd_list_versions,
    'rollback': cmd_rollback,
    'state_history': cmd_state_history,
    'record_pattern': cmd_record_pattern,
    'get_patterns': cmd_get_patterns,
    'disable_pattern': cmd_disable_pattern,
}
