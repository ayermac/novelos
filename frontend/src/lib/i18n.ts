/**
 * i18n mapping for internal status/code -> Chinese user-facing labels.
 *
 * Rules:
 * - All user-visible status must go through these maps.
 * - CSS class names can still use internal keys.
 * - Unknown keys fall back to the raw key (should not happen in prod).
 */

export const STATUS_MAP: Record<string, string> = {
  // Run / workflow statuses
  completed: '已完成',
  pending: '等待中',
  running: '运行中',
  failed: '失败',
  partial: '迁移中',
  pass: '通过',
  error: '错误',

  // Chapter / review statuses
  review: '待审核',
  approved: '已通过',
  rejected: '需返修',
  blocking: '已阻塞',

  // Chapter pipeline statuses
  planned: '已规划',
  scripted: '已编剧',
  drafted: '已起草',
  polished: '已润色',
  published: '已发布',
  revision: '返修中',

  // Style / gate
  active: '已启用',
  inactive: '已停用',
  warn: '警告',
  block: '阻断',

  // Generic
  unknown: '未知',
  success: '成功',
  missing: '缺失',
}

export const GENRE_MAP: Record<string, string> = {
  fantasy: '奇幻',
  urban: '都市',
  'sci-fi': '科幻',
  scifi: '科幻',
  xianxia: '仙侠',
  romance: '言情',
  mystery: '悬疑',
  'default_web_serial': '默认网文',
  unknown: '未知',
}

export const LLM_MODE_MAP: Record<string, string> = {
  stub: '演示模式',
  real: '真实 LLM',
}

export function tStatus(status: string | undefined | null): string {
  if (!status) return STATUS_MAP.unknown
  return STATUS_MAP[status] || status
}

export function tGenre(genre: string | undefined | null): string {
  if (!genre) return '-'
  return GENRE_MAP[genre] || genre
}

export function tLlmMode(mode: string | undefined | null): string {
  if (!mode) return '-'
  return LLM_MODE_MAP[mode] || mode
}

export function tCapabilityLabel(label: string): string {
  const map: Record<string, string> = {
    // Old labels
    'Chapter Production': '章节生产',
    'Batch Production': '批次生产',
    'Production Queue': '生产队列',
    'Review Workbench': '审核工作台',
    'Style Bible': '风格圣经',
    'Style Gate': '风格门禁',
    'Style Sample Analyzer': '风格样本分析',
    'LLM Profiles & Routing': 'LLM 配置与路由',
    'Skill Package': 'Skill 包',
    'QualityHub': '质量中枢',
    'Web UI Acceptance Console': 'Web UI 验收控制台',
    'Project Workspace': '项目工作台',
    'Onboarding': '项目创建引导',
    'Settings / LLM / Agent Ops Console': '配置中心',
    'Web Acceptance Matrix': 'Web 验收矩阵',
    'First Run Guided Workflow': '首次运行引导',
    // v5.1 capability labels
    'v1.0 CLI Run Chapter': 'v1.0 章节生产 CLI',
    'v2.0 Batch Production': 'v2.0 批次生产',
    'v3.1 LLM Routing': 'v3.1 LLM 路由',
    'v3.4 Production Queue': 'v3.4 生产队列',
    'v3.7 Review Workbench': 'v3.7 审核工作台',
    'v4.0 Style Bible': 'v4.0 风格圣经',
    'v5.0 Feature Acceptance': 'v5.0 功能验收',
    'v5.1 API Backend': 'v5.1 API 后端',
    'v5.1 Frontend': 'v5.1 前端',
  }
  return map[label] || label
}

export function tCapabilityNotes(notes: string): string {
  const map: Record<string, string> = {
    // Version notes
    'MVP complete': 'MVP 已完成',
    'v3.0 implemented': 'v3.0 已实现',
    'v3.4 implemented': 'v3.4 已实现',
    'v3.7 implemented': 'v3.7 已实现',
    'v4.0 implemented': 'v4.0 已实现',
    'v4.1 implemented': 'v4.1 已实现',
    'v4.2 implemented': 'v4.2 已实现',
    'v3.1 implemented': 'v3.1 已实现',
    'v2.3 implemented': 'v2.3 已实现',
    'v2.1 implemented': 'v2.1 已实现',
    'v4.3 implemented': 'v4.3 已实现',
    'v4.7 implemented': 'v4.7 已实现',
    'v4.5 implemented': 'v4.5 已实现',
    'v4.9 implemented': 'v4.9 已实现',
    'v4.8 implemented': 'v4.8 已实现',
    'v4.6 implemented': 'v4.6 已实现',
    // v5.1 capability notes
    'Core CLI workflow for chapter production': '章节生产核心 CLI 工作流',
    'Batch production for multiple chapters': '多章节批次生产',
    'LLM profiles and agent-level routing': 'LLM 档案与 Agent 级路由',
    'Local SQLite production queue': '本地 SQLite 生产队列',
    'Human review workbench': '人工审核工作台',
    'Project-level style configuration': '项目级风格配置',
    'v5.0 verified 16 capabilities via Jinja WebUI. v5.1 preserves CLI, migrates Web to React.':
      'v5.0 通过 Jinja WebUI 验收 16 项能力。v5.1 保留 CLI，Web 迁移至 React。',
    'JSON API backend with unified envelope, error handling, and safety':
      '统一信封格式、错误处理和安全性保障的 JSON API 后端',
    'React + Vite + TypeScript frontend with Chinese UX':
      'React + Vite + TypeScript 前端，中文用户体验',
  }
  return map[notes] || notes
}

/**
 * Return CSS class suffix for a status badge.
 */
export function statusClass(status: string | undefined | null): string {
  if (!status) return 'unknown'
  return status
}

export function tAcceptanceStatus(status: string): { label: string; className: string } {
  const map: Record<string, { label: string; className: string }> = {
    pass: { label: '通过', className: 'status-approved' },
    partial: { label: '迁移中', className: 'status-warn' },
    fail: { label: '失败', className: 'status-rejected' },
    missing: { label: '缺失', className: 'status-rejected' },
    error: { label: '错误', className: 'status-rejected' },
  }
  return map[status] || { label: status, className: 'status-unknown' }
}
