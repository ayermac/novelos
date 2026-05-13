export interface WorkflowArtifacts {
  summary?: string
  output_preview?: string
  artifact_labels?: unknown
  artifact_count?: unknown
  artifact_types?: unknown
  [key: string]: unknown
}

export const PROCESS_DRAFT_LABEL = '过程稿'

const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  chapter_brief: '章节规划',
  scene_plan: '分场规划',
  draft: '正文初稿',
  polished_draft: '润色稿',
  review: '审稿报告',
  published_chapter: '发布记录',
  memory_update: '记忆更新',
  style_report: '风格报告',
  fact_snapshot: '事实快照',
}

const AGENT_LABELS: Record<string, string> = {
  planner: '规划',
  screenwriter: '编剧',
  author: '执笔',
  polisher: '润色',
  editor: '审稿',
  publish: '发布',
  publisher: '发布',
  human_review: '人工审核',
}

const STEP_ARTIFACT_TITLES: Record<string, string> = {
  planner: '章节规划',
  screenwriter: '分场大纲',
  author: '正文初稿',
  polisher: '润色稿',
  editor: '审稿意见',
  publish: '发布记录',
  publisher: '发布记录',
}

const RAW_ARTIFACT_TOKEN = /^\s*([a-z][a-z0-9_]*)\s*\(([a-z][a-z0-9_]*)\)\s*$/i
const RAW_ARTIFACT_SUMMARY = /[a-z][a-z0-9_]*\s*\([a-z][a-z0-9_]*\)/i

function tArtifactType(value: string): string {
  return ARTIFACT_TYPE_LABELS[value] || value.replace(/_/g, ' ')
}

function tAgent(value: string): string {
  return AGENT_LABELS[value] || value.replace(/_/g, ' ')
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function asCount(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) return Math.floor(value)
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed > 0) return Math.floor(parsed)
  }
  return null
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)))
}

function normalizeRawArtifactLabel(value: string): string {
  const trimmed = value.trim()
  const match = trimmed.match(RAW_ARTIFACT_TOKEN)
  if (!match) return trimmed

  const [, artifactType, agentId] = match
  return `${tArtifactType(artifactType)} · ${tAgent(agentId)}`
}

function formatLabels(labels: string[], count: number | null): string {
  const readableLabels = unique(labels.map(normalizeRawArtifactLabel))
  if (readableLabels.length === 0) return `已生成${PROCESS_DRAFT_LABEL}`

  const countSuffix = count && count > readableLabels.length ? `（${count} 条记录）` : ''
  return `已生成：${readableLabels.join('、')}${countSuffix}`
}

export function getArtifactTitle(stepKey: string, fallbackLabel: string): string {
  return STEP_ARTIFACT_TITLES[stepKey] || `${fallbackLabel}${PROCESS_DRAFT_LABEL}`
}

export function formatArtifactSummary(artifacts: WorkflowArtifacts | null | undefined): string {
  if (!artifacts) return `已生成${PROCESS_DRAFT_LABEL}`

  const count = asCount(artifacts.artifact_count)
  const labels = asStringArray(artifacts.artifact_labels)
  if (labels.length > 0) {
    return formatLabels(labels, count)
  }

  const summary = typeof artifacts.summary === 'string' ? artifacts.summary.trim() : ''
  if (summary && RAW_ARTIFACT_SUMMARY.test(summary)) {
    const rawParts = summary.split(/\s*[,，、]\s*/).filter(Boolean)
    return formatLabels(rawParts, count || rawParts.length)
  }
  if (summary) return summary

  const typeLabels = asStringArray(artifacts.artifact_types).map(tArtifactType)
  return formatLabels(typeLabels, count)
}
