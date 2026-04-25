"""
系统监控器 - 收集指标、检查告警、生成健康报告

使用方式：
1. Python 脚本导入：
   from monitoring import SystemMonitor
   monitor = SystemMonitor()
   metrics = monitor.collect_metrics('novel_001')

2. 命令行调用：
   python3 monitoring/system_monitor.py novel_001
   python3 monitoring/system_monitor.py novel_001 --report
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Metric:
    """指标数据类"""
    name: str
    value: Any
    unit: str
    description: str
    threshold: Optional[float] = None
    alert_level: Optional[AlertLevel] = None


@dataclass
class Alert:
    """告警数据类"""
    level: AlertLevel
    message: str
    metric: str
    value: Any
    threshold: Any
    suggestion: str


class SystemMonitor:
    """系统监控器"""
    
    # 告警阈值
    ALERT_THRESHOLDS = {
        'task_failure_rate': {'warning': 0.05, 'error': 0.1, 'critical': 0.2},
        'avg_review_score': {'warning': 85, 'error': 75, 'critical': 60},
        'plot_resolution_rate': {'warning': 0.7, 'error': 0.5, 'critical': 0.3},
        'fuse_count': {'warning': 1, 'error': 2, 'critical': 3},
        'message_backlog': {'warning': 5, 'error': 10, 'critical': 20},
        'task_timeout_rate': {'warning': 0.1, 'error': 0.2, 'critical': 0.3},
        'revision_rate': {'warning': 0.3, 'error': 0.5, 'critical': 0.7},
    }
    
    def __init__(self, db_path: str = None):
        """
        初始化监控器
        
        Args:
            db_path: 数据库路径
        """
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "novel_factory.db")
        self.db_path = db_path
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def collect_metrics(self, project_id: str = None) -> Dict[str, Metric]:
        """
        收集系统指标
        
        Args:
            project_id: 项目 ID（可选，不传则收集全局指标）
        
        Returns:
            指标字典
        """
        metrics = {}
        conn = self._get_connection()
        
        try:
            if project_id:
                # 项目级指标
                metrics.update(self._collect_project_metrics(conn, project_id))
            else:
                # 全局指标
                metrics.update(self._collect_global_metrics(conn))
        finally:
            conn.close()
        
        return metrics
    
    def _collect_project_metrics(self, conn, project_id: str) -> Dict[str, Metric]:
        """收集项目级指标"""
        metrics = {}
        
        # 1. 任务失败率
        total_tasks = conn.execute("""
            SELECT COUNT(*) as cnt FROM task_status WHERE project_id=?
        """, (project_id,)).fetchone()['cnt']
        
        failed_tasks = conn.execute("""
            SELECT COUNT(*) as cnt FROM task_status 
            WHERE project_id=? AND status='failed'
        """, (project_id,)).fetchone()['cnt']
        
        failure_rate = failed_tasks / total_tasks if total_tasks > 0 else 0
        metrics['task_failure_rate'] = Metric(
            name='task_failure_rate',
            value=round(failure_rate * 100, 1),
            unit='%',
            description='任务失败率',
            threshold=self.ALERT_THRESHOLDS['task_failure_rate']
        )
        
        # 2. 平均质检分数
        avg_score = conn.execute("""
            SELECT AVG(score) as avg FROM reviews r
            JOIN chapters c ON r.chapter_id = c.id
            WHERE c.project_id=?
        """, (project_id,)).fetchone()['avg']
        
        metrics['avg_review_score'] = Metric(
            name='avg_review_score',
            value=round(avg_score, 1) if avg_score else 0,
            unit='分',
            description='平均质检分数',
            threshold=self.ALERT_THRESHOLDS['avg_review_score']
        )
        
        # 3. 伏笔兑现率
        total_plots = conn.execute("""
            SELECT COUNT(*) as cnt FROM plot_holes WHERE project_id=?
        """, (project_id,)).fetchone()['cnt']
        
        resolved_plots = conn.execute("""
            SELECT COUNT(*) as cnt FROM plot_holes 
            WHERE project_id=? AND status='resolved'
        """, (project_id,)).fetchone()['cnt']
        
        resolution_rate = resolved_plots / total_plots if total_plots > 0 else 1
        metrics['plot_resolution_rate'] = Metric(
            name='plot_resolution_rate',
            value=round(resolution_rate * 100, 1),
            unit='%',
            description='伏笔兑现率',
            threshold=self.ALERT_THRESHOLDS['plot_resolution_rate']
        )
        
        # 4. 熔断触发次数
        fuse_count = conn.execute("""
            SELECT COUNT(*) as cnt FROM task_status 
            WHERE project_id=? AND retry_count >= 3
        """, (project_id,)).fetchone()['cnt']
        
        metrics['fuse_count'] = Metric(
            name='fuse_count',
            value=fuse_count,
            unit='次',
            description='熔断触发次数',
            threshold=self.ALERT_THRESHOLDS['fuse_count']
        )
        
        # 5. 消息队列积压
        message_backlog = conn.execute("""
            SELECT COUNT(*) as cnt FROM agent_messages 
            WHERE project_id=? AND status='pending'
        """, (project_id,)).fetchone()['cnt']
        
        metrics['message_backlog'] = Metric(
            name='message_backlog',
            value=message_backlog,
            unit='条',
            description='消息队列积压',
            threshold=self.ALERT_THRESHOLDS['message_backlog']
        )
        
        # 6. 章节完成率
        total_chapters = conn.execute("""
            SELECT COUNT(*) as cnt FROM chapters WHERE project_id=?
        """, (project_id,)).fetchone()['cnt']
        
        published_chapters = conn.execute("""
            SELECT COUNT(*) as cnt FROM chapters 
            WHERE project_id=? AND status='published'
        """, (project_id,)).fetchone()['cnt']
        
        completion_rate = published_chapters / total_chapters if total_chapters > 0 else 0
        metrics['chapter_completion_rate'] = Metric(
            name='chapter_completion_rate',
            value=round(completion_rate * 100, 1),
            unit='%',
            description='章节完成率'
        )
        
        # 7. 退回率
        revision_count = conn.execute("""
            SELECT COUNT(*) as cnt FROM task_status 
            WHERE project_id=? AND task_type='revise'
        """, (project_id,)).fetchone()['cnt']
        
        create_count = conn.execute("""
            SELECT COUNT(*) as cnt FROM task_status 
            WHERE project_id=? AND task_type='create'
        """, (project_id,)).fetchone()['cnt']
        
        revision_rate = revision_count / create_count if create_count > 0 else 0
        metrics['revision_rate'] = Metric(
            name='revision_rate',
            value=round(revision_rate * 100, 1),
            unit='%',
            description='退回重写率',
            threshold=self.ALERT_THRESHOLDS['revision_rate']
        )
        
        return metrics
    
    def _collect_global_metrics(self, conn) -> Dict[str, Metric]:
        """收集全局指标"""
        metrics = {}
        
        # 项目数量
        project_count = conn.execute("SELECT COUNT(*) as cnt FROM projects").fetchone()['cnt']
        metrics['project_count'] = Metric(
            name='project_count',
            value=project_count,
            unit='个',
            description='项目总数'
        )
        
        # 章节总数
        chapter_count = conn.execute("SELECT COUNT(*) as cnt FROM chapters").fetchone()['cnt']
        metrics['chapter_count'] = Metric(
            name='chapter_count',
            value=chapter_count,
            unit='章',
            description='章节总数'
        )
        
        # 问题模式命中率
        total_hits = conn.execute("SELECT SUM(frequency) as total FROM anti_patterns").fetchone()['total'] or 0
        metrics['pattern_hit_count'] = Metric(
            name='pattern_hit_count',
            value=total_hits,
            unit='次',
            description='问题模式命中次数'
        )
        
        return metrics
    
    def check_alerts(self, metrics: Dict[str, Metric]) -> List[Alert]:
        """
        检查告警
        
        Args:
            metrics: 指标字典
        
        Returns:
            告警列表
        """
        alerts = []
        
        for name, metric in metrics.items():
            if metric.threshold is None:
                continue
            
            value = metric.value
            thresholds = metric.threshold
            
            # 检查告警级别
            alert_level = None
            if 'critical' in thresholds and self._check_threshold(name, value, thresholds['critical'], 'critical'):
                alert_level = AlertLevel.CRITICAL
            elif 'error' in thresholds and self._check_threshold(name, value, thresholds['error'], 'error'):
                alert_level = AlertLevel.ERROR
            elif 'warning' in thresholds and self._check_threshold(name, value, thresholds['warning'], 'warning'):
                alert_level = AlertLevel.WARNING
            
            if alert_level:
                alerts.append(Alert(
                    level=alert_level,
                    message=f"{metric.description}异常: {value}{metric.unit}",
                    metric=name,
                    value=value,
                    threshold=thresholds.get(alert_level.value, thresholds.get('warning')),
                    suggestion=self._get_suggestion(name, alert_level)
                ))
        
        return alerts
    
    def _check_threshold(self, metric_name: str, value: float, threshold: float, level: str) -> bool:
        """检查是否超过阈值"""
        # 有些指标是越低越好，有些是越高越好
        lower_is_better = ['task_failure_rate', 'fuse_count', 'message_backlog', 
                          'revision_rate', 'task_timeout_rate']
        
        if metric_name in lower_is_better:
            return value >= threshold
        else:
            return value <= threshold
    
    def _get_suggestion(self, metric_name: str, level: AlertLevel) -> str:
        """获取告警建议"""
        suggestions = {
            'task_failure_rate': '检查任务日志，确认失败原因',
            'avg_review_score': '查看质检报告，分析低分原因',
            'plot_resolution_rate': '检查伏笔列表，确保伏笔及时兑现',
            'fuse_count': '检查熔断原因，可能需要人工介入',
            'message_backlog': '处理积压的异议消息',
            'revision_rate': '优化写作指令，提高一次通过率',
        }
        return suggestions.get(metric_name, '请检查相关指标')
    
    def generate_report(self, project_id: str = None) -> Dict[str, Any]:
        """
        生成健康报告
        
        Args:
            project_id: 项目 ID（可选）
        
        Returns:
            报告字典
        """
        metrics = self.collect_metrics(project_id)
        alerts = self.check_alerts(metrics)
        
        # 计算健康状态
        if any(a.level == AlertLevel.CRITICAL for a in alerts):
            status = 'critical'
        elif any(a.level == AlertLevel.ERROR for a in alerts):
            status = 'error'
        elif any(a.level == AlertLevel.WARNING for a in alerts):
            status = 'warning'
        else:
            status = 'healthy'
        
        return {
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'project_id': project_id,
            'metrics': {name: {
                'value': m.value,
                'unit': m.unit,
                'description': m.description
            } for name, m in metrics.items()},
            'alerts': [{
                'level': a.level.value,
                'message': a.message,
                'metric': a.metric,
                'value': a.value,
                'threshold': a.threshold,
                'suggestion': a.suggestion
            } for a in alerts],
            'summary': self._generate_summary(status, metrics, alerts)
        }
    
    def _generate_summary(self, status: str, metrics: Dict[str, Metric], alerts: List[Alert]) -> str:
        """生成摘要"""
        if status == 'healthy':
            return "系统运行正常，所有指标在正常范围内。"
        
        alert_msgs = [f"{a.message}" for a in alerts[:3]]
        return f"发现 {len(alerts)} 个告警: " + "; ".join(alert_msgs)


# ========== 命令行入口 ==========

if __name__ == "__main__":
    import sys
    
    db_path = str(Path(__file__).parent.parent / "data" / "novel_factory.db")
    monitor = SystemMonitor(db_path)
    
    project_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    if '--report' in sys.argv:
        report = monitor.generate_report(project_id)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        metrics = monitor.collect_metrics(project_id)
        alerts = monitor.check_alerts(metrics)
        
        print("="*60)
        print(f"系统监控报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        print("\n【指标】")
        for name, m in metrics.items():
            print(f"  {m.description}: {m.value}{m.unit}")
        
        if alerts:
            print("\n【告警】")
            for a in alerts:
                print(f"  [{a.level.value.upper()}] {a.message}")
                print(f"    建议: {a.suggestion}")
        else:
            print("\n【告警】无")
