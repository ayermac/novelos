import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Boxes,
  CheckCircle2,
  ClipboardCheck,
  FlaskConical,
  LayoutGrid,
  ListChecks,
  PackageCheck,
  PlayCircle,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Workflow,
  XCircle,
} from 'lucide-react'
import { get, post, del } from '../../lib/api'
import { DataTable, FormField, InlineMessage, Select, TextArea, TextInput } from '../ui'
import './SkillVisibilityPanel.css'

interface SkillMount {
  agent: string
  stage: string
}

interface SkillInfo {
  id: string
  name?: string
  enabled: boolean
  kind?: string
  type?: string
  version?: string | null
  package?: string
  class_name?: string
  class?: string
  description?: string
  mounted_to: SkillMount[]
  is_mounted: boolean
}

interface ValidateResult {
  ok: boolean
  errors: string[]
  warnings: string[]
}

interface MountMap {
  [agent: string]: {
    [stage: string]: string[]
  }
}

interface MatrixSkill {
  id: string
  name?: string | null
  enabled: boolean
  missing: boolean
  package?: string | null
  legacy: boolean
  kind?: string | null
}

interface MatrixStage {
  stage: string
  skill_ids: string[]
  skills: MatrixSkill[]
  warnings: { code: string; message: string }[]
}

interface MatrixAgent {
  agent: string
  stages: MatrixStage[]
}

interface AgentMatrix {
  agents: MatrixAgent[]
  unmounted_enabled_skills: MatrixSkill[]
  warnings: { code: string; message: string; skill_id?: string }[]
}

interface TestSkillResult {
  ok: boolean
  error?: string | null
  data?: {
    passed?: number
    failed?: number
    total?: number
    cases?: unknown[]
  }
}

interface TestAllResult {
  total: number
  passed: number
  failed: number
  skipped: number
  skipped_ids: string[]
  results: Record<string, TestSkillResult>
}

interface RunResult {
  skill_id: string
  result: TestSkillResult
}

interface ConfigSkill {
  id: string
  name: string
  enabled: boolean
  kind?: string | null
  package?: string | null
  legacy: boolean
  class_name?: string | null
  allowed_targets?: SkillMount[]
  mountable_targets?: SkillMount[]
}

interface SkillConfig {
  agents: string[]
  stages: Record<string, string[]>
  agent_skills: MountMap
  available_skills: ConfigSkill[]
  missing_skills: { id: string; agent: string; stage: string }[]
  disabled_skills: { id: string; name: string }[]
  config_path: string
  total_skills: number
  total_mounted: number
}

interface SkillEnabledResult {
  skill_id: string
  enabled: boolean
  mounted_to: SkillMount[]
  is_mounted: boolean
}

interface SkillReviewFinding {
  severity: 'pass' | 'warn' | 'block'
  code: string
  message: string
}

interface SkillReviewResult {
  skill_id: string
  agent?: string | null
  stage?: string | null
  verdict: 'pass' | 'warn' | 'block'
  enabled: boolean
  package?: string | null
  imported: boolean
  manifest: boolean
  findings: SkillReviewFinding[]
  recommended_actions: string[]
  allowed_targets: SkillMount[]
  mountable_targets: SkillMount[]
}

type SkillConsoleView = 'overview' | 'enable' | 'mounts' | 'test' | 'catalog'
type CapabilityFilter = 'all' | 'enabled' | 'disabled' | 'mounted' | 'unmounted' | 'risky' | 'legacy'

const CAPABILITY_FILTERS: { key: CapabilityFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'enabled', label: '已启用' },
  { key: 'disabled', label: '已禁用' },
  { key: 'mounted', label: '已挂载' },
  { key: 'unmounted', label: '未挂载' },
  { key: 'risky', label: '缺失/风险' },
  { key: 'legacy', label: 'Legacy' },
]

const AGENT_GROUPS = [
  { key: 'creative', label: 'Creative Agents', agents: ['planner', 'screenwriter', 'author', 'polisher', 'editor'] },
  { key: 'support', label: 'Support Agents', agents: ['memory_curator', 'continuity_checker', 'publisher', 'archive'] },
  { key: 'diagnostic', label: 'Diagnostic/Research Agents', agents: ['scout', 'architect', 'secretary'] },
]

const sectionTitleStyle: CSSProperties = {
  fontSize: 'var(--text-sm)',
  fontWeight: 'var(--font-semibold)',
  margin: '0 0 var(--space-3) 0',
  color: 'var(--text-primary)',
}

const compactCodeStyle: CSSProperties = {
  fontSize: '12px',
  whiteSpace: 'normal',
  overflowWrap: 'anywhere',
}

function statusChipStyle(kind: 'ok' | 'warn' | 'danger' | 'muted' = 'ok'): CSSProperties {
  const palette = {
    ok: { background: 'rgba(34, 197, 94, 0.12)', color: '#166534' },
    warn: { background: '#fef3c7', color: '#92400e' },
    danger: { background: '#fee2e2', color: '#991b1b' },
    muted: { background: '#e5e7eb', color: '#6b7280' },
  }[kind]

  return {
    ...palette,
    display: 'inline-flex',
    alignItems: 'center',
    maxWidth: '100%',
    padding: '2px 8px',
    borderRadius: '4px',
    fontSize: '12px',
    fontWeight: 500,
    overflowWrap: 'anywhere',
  }
}

function getRequestErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

export default function SkillVisibilityPanel() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [agentMatrix, setAgentMatrix] = useState<AgentMatrix | null>(null)
  const [skillConfig, setSkillConfig] = useState<SkillConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [validating, setValidating] = useState(false)
  const [validateResult, setValidateResult] = useState<ValidateResult | null>(null)

  const [testingAll, setTestingAll] = useState(false)
  const [testAllResult, setTestAllResult] = useState<TestAllResult | null>(null)
  const [testAllError, setTestAllError] = useState('')
  const [testingSkill, setTestingSkill] = useState<string | null>(null)
  const [testSingleResult, setTestSingleResult] = useState<Record<string, TestSkillResult>>({})

  const [runSkillId, setRunSkillId] = useState('')
  const [runText, setRunText] = useState('')
  const [runPayload, setRunPayload] = useState('')
  const [runPayloadError, setRunPayloadError] = useState('')
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<RunResult | null>(null)

  // Mount editor state
  const [savingMount, setSavingMount] = useState(false)
  const [mountError, setMountError] = useState('')
  const [selectedAddSkill, setSelectedAddSkill] = useState<Record<string, string>>({})

  // Skill enabled state
  const [togglingSkill, setTogglingSkill] = useState<string | null>(null)
  const [skillEnableError, setSkillEnableError] = useState('')
  const [reviewingSkill, setReviewingSkill] = useState<string | null>(null)
  const [skillReviewError, setSkillReviewError] = useState('')
  const [skillReviewResults, setSkillReviewResults] = useState<Record<string, SkillReviewResult>>({})
  const [activeView, setActiveView] = useState<SkillConsoleView>('overview')
  const [skillSearch, setSkillSearch] = useState('')
  const [capabilityFilter, setCapabilityFilter] = useState<CapabilityFilter>('all')

  const load = async () => {
    setLoading(true)
    setError('')

    try {
      const [skillsRes, matrixRes, configRes] = await Promise.all([
        get<{ skills: SkillInfo[] }>('/skills'),
        get<AgentMatrix>('/skills/agent-matrix'),
        get<SkillConfig>('/skills/config'),
      ])

      if (skillsRes.ok && skillsRes.data) {
        setSkills(skillsRes.data.skills)
      } else {
        setError(skillsRes.error?.message || '获取 Skill 列表失败')
      }

      if (matrixRes.ok && matrixRes.data) {
        setAgentMatrix(matrixRes.data)
      }

      if (configRes.ok && configRes.data) {
        setSkillConfig(configRes.data)
      }
    } catch (err) {
      setError(getRequestErrorMessage(err, '获取 Skill 信息失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleValidate = async () => {
    setValidating(true)
    setValidateResult(null)

    try {
      const res = await post<ValidateResult>('/skills/validate')

      if (res.ok && res.data) {
        setValidateResult(res.data)
      } else {
        setValidateResult({ ok: false, errors: [res.error?.message || '验证请求失败'], warnings: [] })
      }
    } catch (err) {
      setValidateResult({ ok: false, errors: [getRequestErrorMessage(err, '验证请求失败')], warnings: [] })
    } finally {
      setValidating(false)
    }
  }

  const handleTestAll = async () => {
    setTestingAll(true)
    setTestAllResult(null)
    setTestAllError('')

    try {
      const res = await post<TestAllResult>('/skills/test', { all: true })

      if (res.ok && res.data) {
        setTestAllResult(res.data)
      } else {
        setTestAllResult({ total: 0, passed: 0, failed: 0, skipped: 0, skipped_ids: [], results: {} })
        setTestAllError(res.error?.message || '测试全部 Package Skill 失败')
      }
    } catch (err) {
      setTestAllResult({ total: 0, passed: 0, failed: 0, skipped: 0, skipped_ids: [], results: {} })
      setTestAllError(getRequestErrorMessage(err, '测试全部 Package Skill 失败'))
    } finally {
      setTestingAll(false)
    }
  }

  const handleTestSingle = async (skillId: string) => {
    setTestingSkill(skillId)

    try {
      const res = await post<{ skill_id: string; result: TestSkillResult }>('/skills/test', {
        skill_id: skillId,
      })

      if (res.ok && res.data) {
        setTestSingleResult((prev) => ({ ...prev, [skillId]: res.data!.result }))
      } else {
        setTestSingleResult((prev) => ({
          ...prev,
          [skillId]: { ok: false, error: res.error?.message || '测试失败' },
        }))
      }
    } catch (err) {
      setTestSingleResult((prev) => ({
        ...prev,
        [skillId]: { ok: false, error: getRequestErrorMessage(err, '测试失败') },
      }))
    } finally {
      setTestingSkill(null)
    }
  }

  const handleRun = async () => {
    if (!runSkillId) return
    setRunPayloadError('')

    const hasText = runText.trim().length > 0
    const hasPayload = runPayload.trim().length > 0
    if (!hasText && !hasPayload) {
      setRunResult({
        skill_id: runSkillId,
        result: { ok: false, error: '请输入文本或 payload' },
      })
      return
    }

    let customPayload: Record<string, unknown> | undefined
    if (hasPayload) {
      try {
        customPayload = JSON.parse(runPayload) as Record<string, unknown>
      } catch {
        setRunPayloadError('JSON 格式错误，请检查输入')
        return
      }
    }

    setRunning(true)
    setRunResult(null)

    const reqBody: { skill_id: string; text?: string; payload?: Record<string, unknown> } = {
      skill_id: runSkillId,
    }
    if (hasText) reqBody.text = runText
    if (customPayload) reqBody.payload = customPayload

    try {
      const res = await post<RunResult>('/skills/run', reqBody)

      if (res.ok && res.data) {
        setRunResult(res.data)
      } else {
        setRunResult({
          skill_id: runSkillId,
          result: { ok: false, error: res.error?.message || '运行失败' },
        })
      }
    } catch (err) {
      setRunResult({
        skill_id: runSkillId,
        result: { ok: false, error: getRequestErrorMessage(err, '运行失败') },
      })
    } finally {
      setRunning(false)
    }
  }

  // Mount editor handlers
  const handleMount = async (agent: string, stage: string, skillId: string) => {
    if (!skillId) return
    setSavingMount(true)
    setMountError('')

    try {
      const res = await post<{ agent: string; stage: string; skill_id: string }>('/skills/mount', {
        agent,
        stage,
        skill_id: skillId,
      })

      if (res.ok && res.data) {
        setSelectedAddSkill((prev) => ({ ...prev, [`${agent}-${stage}`]: '' }))
        await load()
      } else {
        setMountError(res.error?.message || '挂载失败')
      }
    } catch (err) {
      setMountError(getRequestErrorMessage(err, '挂载失败'))
    } finally {
      setSavingMount(false)
    }
  }

  const handleUnmount = async (agent: string, stage: string, skillId: string) => {
    setSavingMount(true)
    setMountError('')

    try {
      const res = await del<{ agent: string; stage: string; skill_id: string }>('/skills/mount', {
        agent,
        stage,
        skill_id: skillId,
      })

      if (res.ok && res.data) {
        await load()
      } else {
        setMountError(res.error?.message || '卸载失败')
      }
    } catch (err) {
      setMountError(getRequestErrorMessage(err, '卸载失败'))
    } finally {
      setSavingMount(false)
    }
  }

  const handleMove = async (agent: string, stage: string, skillId: string, direction: 'up' | 'down') => {
    const current = skillConfig?.agent_skills[agent]?.[stage] || []
    const idx = current.indexOf(skillId)
    if (idx === -1) return
    const newIdx = direction === 'up' ? idx - 1 : idx + 1
    if (newIdx < 0 || newIdx >= current.length) return

    const reordered = [...current]
    const temp = reordered[idx]
    reordered[idx] = reordered[newIdx]
    reordered[newIdx] = temp

    setSavingMount(true)
    setMountError('')

    try {
      const res = await post<{ agent: string; stage: string; skill_ids: string[] }>('/skills/reorder', {
        agent,
        stage,
        skill_ids: reordered,
      })

      if (res.ok && res.data) {
        await load()
      } else {
        setMountError(res.error?.message || '排序失败')
      }
    } catch (err) {
      setMountError(getRequestErrorMessage(err, '排序失败'))
    } finally {
      setSavingMount(false)
    }
  }

  const handleSkillEnabled = async (skillId: string, enabled: boolean) => {
    setTogglingSkill(skillId)
    setSkillEnableError('')

    try {
      const res = await post<SkillEnabledResult>('/skills/enabled', {
        skill_id: skillId,
        enabled,
      })

      if (res.ok && res.data) {
        await load()
      } else {
        setSkillEnableError(res.error?.message || '更新 Skill 启用状态失败')
      }
    } catch (err) {
      setSkillEnableError(getRequestErrorMessage(err, '更新 Skill 启用状态失败'))
    } finally {
      setTogglingSkill(null)
    }
  }

  const handleSkillReview = async (skillId: string) => {
    setReviewingSkill(skillId)
    setSkillReviewError('')

    try {
      const res = await post<SkillReviewResult>('/skills/review', {
        skill_id: skillId,
      })

      if (res.ok && res.data) {
        setSkillReviewResults((prev) => ({ ...prev, [skillId]: res.data! }))
      } else {
        setSkillReviewError(res.error?.message || 'Skill 安全审查失败')
      }
    } catch (err) {
      setSkillReviewError(getRequestErrorMessage(err, 'Skill 安全审查失败'))
    } finally {
      setReviewingSkill(null)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 'var(--space-5)', textAlign: 'center', color: 'var(--text-charcoal)' }}>
        加载 Skill 信息...
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 'var(--space-5)', color: 'var(--danger)' }}>
        {error}
        <button onClick={load} className="btn btn-secondary" style={{ marginLeft: 12 }}>
          重试
        </button>
      </div>
    )
  }

  const skillMountById = new Map(skills.map((skill) => [skill.id, skill]))
  const configSkillById = new Map((skillConfig?.available_skills || []).map((skill) => [skill.id, skill]))
  const mountedIds = new Set<string>()
  Object.values(skillConfig?.agent_skills || {}).forEach((stages) => {
    Object.values(stages).forEach((ids) => ids.forEach((id) => mountedIds.add(id)))
  })
  skills.forEach((skill) => {
    if (skill.is_mounted) mountedIds.add(skill.id)
  })
  const allCapabilityIds = Array.from(new Set([
    ...skills.map((skill) => skill.id),
    ...(skillConfig?.available_skills || []).map((skill) => skill.id),
    ...(skillConfig?.missing_skills || []).map((skill) => skill.id),
  ])).sort()
  const missingIds = new Set(skillConfig?.missing_skills.map((skill) => skill.id) || [])
  agentMatrix?.agents.forEach((agent) => {
    agent.stages.forEach((stage) => {
      stage.skills.forEach((skill) => {
        if (skill.missing) missingIds.add(skill.id)
      })
    })
  })
  const enabledCount = skills.filter((skill) => skill.enabled).length
  const mountedSkillCount = mountedIds.size
  const disabledCount = skillConfig?.disabled_skills.length ?? skills.filter((skill) => !skill.enabled).length
  const enabledUnmounted = allCapabilityIds
    .map((id) => ({ id, runtime: skillMountById.get(id), config: configSkillById.get(id) }))
    .filter(({ runtime, config, id }) => (runtime?.enabled ?? config?.enabled ?? false) && !mountedIds.has(id))
  const mountedDisabled = allCapabilityIds
    .map((id) => ({ id, runtime: skillMountById.get(id), config: configSkillById.get(id) }))
    .filter(({ runtime, config, id }) => mountedIds.has(id) && (runtime?.enabled === false || config?.enabled === false))
  const matrixStats = agentMatrix
    ? {
        agents: agentMatrix.agents.length,
        stages: agentMatrix.agents.reduce((total, agent) => total + agent.stages.length, 0),
        mounted: agentMatrix.agents.reduce(
          (total, agent) => total + agent.stages.reduce((stageTotal, stage) => stageTotal + stage.skills.length, 0),
          0,
        ),
        missing: agentMatrix.agents.reduce(
          (total, agent) => total + agent.stages.reduce(
            (stageTotal, stage) => stageTotal + stage.skills.filter((skill) => skill.missing).length,
            0,
          ),
          0,
        ),
      }
    : null
  const validationIssueCount = validateResult && !validateResult.ok ? validateResult.errors.length : 0
  const matrixWarningCount = agentMatrix?.warnings.length ?? 0
  const warningCount = matrixWarningCount + enabledUnmounted.length + mountedDisabled.length + missingIds.size + validationIssueCount

  // Build available skills for each agent/stage from config
  const getAvailableSkillsForStage = (agent: string, stage: string) => {
    if (!skillConfig) return []
    const mountedSet = new Set(skillConfig.agent_skills[agent]?.[stage] || [])
    return skillConfig.available_skills.filter((s) => {
      if (mountedSet.has(s.id)) return false
      if (!s.enabled) return false
      const targetKey = `${agent}:${stage}`
      const mountableTargets = (s.mountable_targets || []).map((target) => `${target.agent}:${target.stage}`)
      return mountableTargets.includes(targetKey)
    })
  }

  const normalizedSearch = skillSearch.trim().toLowerCase()
  const searchMatchesSkill = (skill: { id: string; name?: string | null; package?: string | null; class_name?: string | null; class?: string | null; description?: string | null }) => {
    if (!normalizedSearch) return true
    return [
      skill.id,
      skill.name || '',
      skill.package || '',
      skill.class_name || '',
      skill.class || '',
      skill.description || '',
    ].some((value) => value.toLowerCase().includes(normalizedSearch))
  }
  const capabilities = allCapabilityIds.map((id) => {
    const runtime = skillMountById.get(id)
    const config = configSkillById.get(id)
    const review = skillReviewResults[id]
    const enabled = runtime?.enabled ?? config?.enabled ?? false
    const isMounted = mountedIds.has(id)
    const legacy = config?.legacy ?? !runtime?.package
    return {
      id,
      name: runtime?.name || config?.name || id,
      description: runtime?.description || '',
      kind: runtime?.kind || runtime?.type || config?.kind || 'skill',
      package: runtime?.package || config?.package || '',
      class_name: runtime?.class_name || runtime?.class || config?.class_name || '',
      enabled,
      isMounted,
      legacy,
      missing: missingIds.has(id),
      review,
      allowed_targets: review?.allowed_targets || config?.allowed_targets || [],
      mountable_targets: review?.mountable_targets || config?.mountable_targets || [],
    }
  })
  const filteredCapabilities = capabilities
    .filter(searchMatchesSkill)
    .filter((skill) => {
      if (capabilityFilter === 'enabled') return skill.enabled
      if (capabilityFilter === 'disabled') return !skill.enabled
      if (capabilityFilter === 'mounted') return skill.isMounted
      if (capabilityFilter === 'unmounted') return !skill.isMounted
      if (capabilityFilter === 'legacy') return skill.legacy
      if (capabilityFilter === 'risky') {
        const reviewRisk = skill.review
          ? skill.review.verdict === 'warn' || skill.review.verdict === 'block' || !skill.review.manifest || !skill.review.imported
          : false
        return skill.missing || (skill.isMounted && !skill.enabled) || reviewRisk
      }
      return true
    })
  const filteredRuntimeSkills = skills.filter(searchMatchesSkill)
  const getStagesForAgents = (agents: string[]) => {
    const seen = new Set<string>()
    const stages: string[] = []
    agents.forEach((agent) => {
      const agentStages = skillConfig?.stages[agent] || []
      agentStages.forEach((stage) => {
        if (!seen.has(stage)) {
          seen.add(stage)
          stages.push(stage)
        }
      })
    })
    return stages
  }
  const groupAgents = AGENT_GROUPS.map((group) => ({
    ...group,
    agents: group.agents.filter((agent) => skillConfig?.agents.includes(agent)),
  })).filter((group) => group.agents.length > 0)
  const groupedKnownAgents = new Set(groupAgents.flatMap((group) => group.agents))
  const otherAgents = (skillConfig?.agents || []).filter((agent) => !groupedKnownAgents.has(agent))
  const agentGroups = otherAgents.length > 0
    ? [...groupAgents, { key: 'other', label: 'Other Agents', agents: otherAgents }]
    : groupAgents
  const overviewIssues = [
    {
      key: 'validation',
      tone: validationIssueCount > 0 ? 'danger' : validateResult?.warnings.length ? 'warn' : 'ok',
      icon: validationIssueCount > 0 ? <XCircle size={16} /> : <ClipboardCheck size={16} />,
      title: validationIssueCount > 0 ? '配置验证失败' : validateResult ? '配置已验证' : '尚未验证配置',
      count: validateResult ? (validationIssueCount || validateResult.warnings.length) : 0,
      detail: validateResult ? (validationIssueCount > 0 ? validateResult.errors[0] : validateResult.warnings[0] || '当前没有验证阻塞项。') : '运行一次验证，先确认配置文件没有结构性问题。',
      target: 'test' as SkillConsoleView,
    },
    {
      key: 'enabled-unmounted',
      tone: enabledUnmounted.length > 0 ? 'warn' : 'ok',
      icon: <PackageCheck size={16} />,
      title: '已启用但未挂载',
      count: enabledUnmounted.length,
      detail: enabledUnmounted.length > 0 ? `${enabledUnmounted[0].id} 等能力尚未进入任何 Agent 阶段。` : '已启用能力都有明确去向。',
      target: 'mounts' as SkillConsoleView,
    },
    {
      key: 'mounted-disabled',
      tone: mountedDisabled.length > 0 ? 'danger' : 'ok',
      icon: <AlertTriangle size={16} />,
      title: '已挂载但被禁用',
      count: mountedDisabled.length,
      detail: mountedDisabled.length > 0 ? `${mountedDisabled[0].id} 正在挂载位中但不可执行。` : '挂载链路没有禁用能力。',
      target: 'mounts' as SkillConsoleView,
    },
    {
      key: 'missing',
      tone: missingIds.size > 0 ? 'danger' : 'ok',
      icon: <XCircle size={16} />,
      title: '缺失引用',
      count: missingIds.size,
      detail: missingIds.size > 0 ? `${Array.from(missingIds)[0]} 在挂载配置中找不到可用 Skill。` : '未发现缺失引用。',
      target: 'mounts' as SkillConsoleView,
    },
    {
      key: 'matrix-warning',
      tone: matrixWarningCount > 0 ? 'warn' : 'ok',
      icon: <Workflow size={16} />,
      title: '编排警告',
      count: matrixWarningCount,
      detail: matrixWarningCount > 0 ? agentMatrix!.warnings[0].message : 'Agent × Stage 编排没有额外警告。',
      target: 'mounts' as SkillConsoleView,
    },
  ]
  const consoleViews: { key: SkillConsoleView; label: string; hint: string; icon: JSX.Element; badge?: string }[] = [
    { key: 'overview', label: '总览', hint: '健康状态与待处理事项', icon: <LayoutGrid size={16} />, badge: warningCount ? `${warningCount}` : undefined },
    { key: 'enable', label: '能力库', hint: '查找、启停、审查与目标范围', icon: <ShieldCheck size={16} />, badge: `${enabledCount}/${skills.length}` },
    { key: 'mounts', label: 'Agent 编排', hint: 'Agent × Stage 挂载矩阵', icon: <Workflow size={16} />, badge: `${mountedSkillCount}` },
    { key: 'test', label: 'Review/Test', hint: '验证、安全审查、fixtures 与手动试运行', icon: <FlaskConical size={16} /> },
    { key: 'catalog', label: '目录', hint: '完整清单与描述', icon: <Boxes size={16} />, badge: `${skills.length}` },
  ]

  return (
    <div className="skill-console">
      <div className="skill-console-hero">
        <div>
          <div className="skill-console-kicker"><SlidersHorizontal size={14} /> Skill Operations</div>
          <h3>Skill 管理工作台</h3>
          <p>按启用、挂载、测试和目录分区管理创作技能，避免在一个长页面里处理所有配置。</p>
        </div>
        <div className="skill-console-actions">
          <button onClick={handleValidate} className="btn btn-secondary" disabled={validating}>
            {validating ? '验证中...' : '验证配置'}
          </button>
          <button onClick={load} className="btn btn-secondary" disabled={loading || savingMount}>
            <RefreshCw size={14} /> 刷新
          </button>
        </div>
      </div>

      <div className="skill-console-metrics">
        <div className="skill-console-metric">
          <span className="metric-icon"><Boxes size={16} /></span>
          <span className="metric-label">已加载</span>
          <strong>{skills.length}</strong>
        </div>
        <div className="skill-console-metric">
          <span className="metric-icon success"><CheckCircle2 size={16} /></span>
          <span className="metric-label">已启用</span>
          <strong>{enabledCount}</strong>
        </div>
        <div className="skill-console-metric">
          <span className="metric-icon info"><Workflow size={16} /></span>
          <span className="metric-label">已挂载</span>
          <strong>{mountedSkillCount}</strong>
        </div>
        <div className="skill-console-metric">
          <span className="metric-icon muted"><Activity size={16} /></span>
          <span className="metric-label">禁用</span>
          <strong>{disabledCount}</strong>
        </div>
      </div>

      <div className="skill-console-shell">
        <aside className="skill-console-nav" aria-label="Skill 管理分区">
          {consoleViews.map((view) => (
            <button
              key={view.key}
              type="button"
              className={`skill-console-nav-item ${activeView === view.key ? 'active' : ''}`}
              onClick={() => setActiveView(view.key)}
            >
              <span className="nav-icon">{view.icon}</span>
              <span className="nav-copy">
                <span>{view.label}</span>
                <small>{view.hint}</small>
              </span>
              {view.badge && <span className="nav-badge">{view.badge}</span>}
            </button>
          ))}
        </aside>

        <main className="skill-console-main">
          <div className="skill-console-toolbar">
            <div>
              <strong>{consoleViews.find((view) => view.key === activeView)?.label}</strong>
              <span>{consoleViews.find((view) => view.key === activeView)?.hint}</span>
            </div>
            <label className="skill-search">
              <Search size={14} />
              <TextInput
                aria-label="搜索 Skill"
                value={skillSearch}
                onChange={(event) => setSkillSearch(event.target.value)}
                placeholder="搜索 id、名称、package、描述或 class"
              />
            </label>
          </div>

          {validateResult && (
            <div className={`skill-inline-status ${validateResult.ok ? 'ok' : 'danger'}`}>
              {validateResult.ok ? 'Skill 配置有效' : `发现 ${validateResult.errors.length} 个错误`}
            </div>
          )}

      {validateResult && !validateResult.ok && (
        <InlineMessage variant="danger" className="skill-validation-message">
          {validateResult.errors.map((e, i) => (
            <div key={`err-${i}`} style={{ marginBottom: 4 }}>
              {e}
            </div>
          ))}
          {validateResult.warnings.map((w, i) => (
            <div key={`warn-${i}`} style={{ color: '#92400e', marginBottom: 4 }}>
              {w}
            </div>
          ))}
        </InlineMessage>
      )}

      {validateResult && validateResult.ok && validateResult.warnings.length > 0 && (
        <InlineMessage variant="warning" className="skill-validation-message">
          {validateResult.warnings.map((w, i) => (
            <div key={`warn-${i}`} style={{ marginBottom: 4 }}>
              {w}
            </div>
          ))}
        </InlineMessage>
      )}

          {activeView === 'overview' && (
            <div className="skill-overview-grid">
              {overviewIssues.map((issue) => (
                <button
                  key={issue.key}
                  type="button"
                  className={`skill-overview-card issue-${issue.tone}`}
                  onClick={() => setActiveView(issue.target)}
                >
                  <div className="overview-card-title">{issue.icon} {issue.title}</div>
                  <div className="overview-card-number">{issue.count}</div>
                  <p>{issue.detail}</p>
                </button>
              ))}
              <div className="skill-overview-card primary">
                <div className="overview-card-title"><ListChecks size={16} /> 下一步建议</div>
                <div className="overview-card-number">{warningCount > 0 ? '需处理' : '健康'}</div>
                <p>{warningCount > 0 ? '优先处理红色和黄色 issue，再进入 Agent 编排或 Review/Test。' : '当前没有明显阻塞项，可以继续扩展能力库或运行 fixtures。'}</p>
                <button onClick={handleValidate} className="btn btn-secondary" disabled={validating}>
                  {validating ? '验证中...' : '重新验证'}
                </button>
              </div>
            </div>
          )}

          {activeView === 'enable' && (
            <div className="skill-section-panel">
              <div className="skill-filter-row" role="group" aria-label="能力筛选">
                {CAPABILITY_FILTERS.map((filter) => (
                  <button
                    key={filter.key}
                    type="button"
                    className={`skill-filter-chip ${capabilityFilter === filter.key ? 'active' : ''}`}
                    onClick={() => setCapabilityFilter(filter.key)}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>

              {(skillEnableError || skillReviewError) && (
                <div className="skill-message danger">
                  {skillEnableError || skillReviewError}
                  <button type="button" onClick={() => { setSkillEnableError(''); setSkillReviewError('') }}>
                    清除
                  </button>
                </div>
              )}

              <div className="capability-grid">
                {filteredCapabilities.map((skill) => (
                  <article key={`cap-${skill.id}`} className={`capability-card ${skill.enabled ? 'enabled' : 'disabled'} ${skill.missing ? 'missing' : ''}`}>
                    <div className="capability-card-head">
                      <div className="capability-title">
                        <code>{skill.id}</code>
                        <strong>{skill.name}</strong>
                      </div>
                      <span className={`capability-state ${skill.enabled ? 'on' : 'off'}`}>
                        {skill.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </div>
                    <p>{skill.description || '暂无描述。'}</p>
                    <div className="capability-tags">
                      <span>{skill.kind}</span>
                      <span>{skill.package || 'legacy'}</span>
                      <span>{skill.isMounted ? 'Mounted' : 'Unmounted'}</span>
                      {skill.missing && <span className="danger">Missing</span>}
                      {skill.legacy && <span>Legacy</span>}
                      {skill.review && (
                        <span className={skill.review.verdict === 'block' ? 'danger' : skill.review.verdict === 'warn' ? 'warn' : 'ok'}>
                          Review {skill.review.verdict}
                        </span>
                      )}
                    </div>
                    <div className="capability-meta">
                      <span>Class</span>
                      <code>{skill.class_name || '-'}</code>
                    </div>
                    <div className="capability-targets">
                      <span>可挂载目标</span>
                      <div>
                        {(skill.mountable_targets.length > 0 ? skill.mountable_targets : skill.allowed_targets).slice(0, 6).map((target) => (
                          <small key={`${skill.id}-${target.agent}-${target.stage}`}>{target.agent}.{target.stage}</small>
                        ))}
                        {(skill.mountable_targets.length === 0 && skill.allowed_targets.length === 0) && <small>未声明</small>}
                      </div>
                    </div>
                    <div className="capability-actions">
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => handleSkillReview(skill.id)}
                        disabled={reviewingSkill === skill.id || skill.missing}
                      >
                        <ShieldCheck size={13} /> {reviewingSkill === skill.id ? '审查中...' : '审查'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => handleSkillEnabled(skill.id, !skill.enabled)}
                        disabled={togglingSkill === skill.id || skill.missing}
                      >
                        {skill.enabled ? <XCircle size={13} /> : <CheckCircle2 size={13} />}
                        {togglingSkill === skill.id ? '保存中...' : skill.enabled ? '禁用' : '启用'}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              {filteredCapabilities.length === 0 && (
                <div className="skill-empty-panel">没有匹配当前搜索和筛选条件的 Skill。</div>
              )}
            </div>
          )}

      {activeView === 'mounts' && skillConfig && (
        <div className="skill-section-panel orchestration-panel">
          <div className="matrix-header">
            <div>
              <h4>Agent × Stage Orchestration</h4>
              <p>按 Agent 和执行阶段编排能力，挂载顺序即运行顺序。</p>
            </div>
            {matrixStats && (
              <div className="matrix-stats">
                <span>{matrixStats.agents} agents</span>
                <span>{matrixStats.stages} stages</span>
                <span>{matrixStats.mounted} mounted</span>
                {matrixStats.missing > 0 && <span className="danger">{matrixStats.missing} missing</span>}
              </div>
            )}
          </div>

          {mountError && (
            <div className="skill-message danger">
              {mountError}
              <button type="button" onClick={() => setMountError('')}>清除</button>
            </div>
          )}
          {savingMount && <div className="skill-message info">正在保存挂载变更...</div>}
          {agentMatrix?.warnings.length ? (
            <div className="skill-message warn">
              {agentMatrix.warnings.slice(0, 4).map((warning, index) => (
                <div key={`${warning.code}-${index}`}>{warning.message}</div>
              ))}
            </div>
          ) : null}

          <div className="orchestration-scroll">
            {agentGroups.map((group) => {
              const groupStages = getStagesForAgents(group.agents)
              return (
              <section key={group.key} className="agent-group-section">
                <div className="agent-group-heading">
                  <h5>{group.label}</h5>
                  {groupStages.length > 4 && <span>可横向滚动查看全部阶段</span>}
                </div>
                <div
                  className="orchestration-matrix"
                  role="table"
                  aria-label={`${group.label} Skill matrix`}
                  style={{
                    '--stage-count': groupStages.length,
                    '--matrix-min-width': `${140 + groupStages.length * 220}px`,
                  } as CSSProperties}
                >
                  <div className="matrix-row matrix-head-row" role="row">
                    <div className="matrix-agent-cell" role="columnheader">Agent</div>
                    {groupStages.map((stage) => (
                      <div key={stage} className="matrix-stage-head" role="columnheader">{stage}</div>
                    ))}
                  </div>
                  {group.agents.map((agent) => {
                    const agentMounts = skillConfig.agent_skills[agent] || {}
                    return (
                      <div key={agent} className="matrix-row" role="row">
                        <div className="matrix-agent-cell" role="rowheader">
                          <strong>{agent}</strong>
                        </div>
                        {groupStages.map((stage) => {
                          const stageAllowed = (skillConfig.stages[agent] || []).includes(stage)
                          const mountedSkills = agentMounts[stage] || []
                          const available = stageAllowed ? getAvailableSkillsForStage(agent, stage) : []
                          const selectKey = `${agent}-${stage}`
                          return (
                            <div key={`${agent}-${stage}`} className={`matrix-stage-cell ${stageAllowed ? '' : 'not-applicable'}`} role="cell">
                              {stageAllowed ? (
                                <>
                                  <div className="matrix-chip-stack">
                                    {mountedSkills.length > 0 ? mountedSkills.map((skillId, idx) => {
                                      const skillInfo = configSkillById.get(skillId)
                                      const missing = !skillInfo
                                      const disabled = skillInfo?.enabled === false
                                      return (
                                        <div key={skillId} className={`matrix-skill-chip ${missing ? 'missing' : ''} ${disabled ? 'disabled' : ''}`}>
                                          <span title={skillId}>{skillId}</span>
                                          {missing && <small>missing</small>}
                                          {disabled && <small>disabled</small>}
                                          {skillInfo?.legacy && <small>legacy</small>}
                                          <div className="matrix-chip-actions">
                                            <button type="button" onClick={() => handleMove(agent, stage, skillId, 'up')} disabled={savingMount || idx === 0} title="上移" aria-label={`${skillId} 上移`}>
                                              <ArrowUp size={12} />
                                            </button>
                                            <button type="button" onClick={() => handleMove(agent, stage, skillId, 'down')} disabled={savingMount || idx === mountedSkills.length - 1} title="下移" aria-label={`${skillId} 下移`}>
                                              <ArrowDown size={12} />
                                            </button>
                                            <button type="button" onClick={() => handleUnmount(agent, stage, skillId)} disabled={savingMount} title="移除" aria-label={`${skillId} 移除`}>
                                              <Trash2 size={12} />
                                            </button>
                                          </div>
                                        </div>
                                      )
                                    }) : (
                                      <span className="matrix-empty">未挂载</span>
                                    )}
                                  </div>
                                  {available.length > 0 ? (
                                    <div className="matrix-add-control">
                                      <Select
                                        value={selectedAddSkill[selectKey] || ''}
                                        onChange={(event) => setSelectedAddSkill((prev) => ({ ...prev, [selectKey]: event.target.value }))}
                                        disabled={savingMount}
                                        aria-label={`${agent} ${stage} 添加 Skill`}
                                      >
                                        <option value="">添加 Skill</option>
                                        {available.map((skill) => (
                                          <option key={skill.id} value={skill.id}>{skill.id}</option>
                                        ))}
                                      </Select>
                                      <button
                                        type="button"
                                        className="btn btn-secondary"
                                        onClick={() => handleMount(agent, stage, selectedAddSkill[selectKey] || '')}
                                        disabled={savingMount || !selectedAddSkill[selectKey]}
                                        aria-label={`${agent} ${stage} 确认添加`}
                                      >
                                        <Plus size={13} />
                                      </button>
                                    </div>
                                  ) : (
                                    <span className="matrix-no-options">无可添加 Skill</span>
                                  )}
                                </>
                              ) : (
                                <span className="matrix-empty">—</span>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )
                  })}
                </div>
              </section>
            )})}
          </div>
        </div>
      )}

      {activeView === 'test' && (
        <div className="review-console-grid">
          <section className="skill-section-panel">
            <div className="test-section-title"><ClipboardCheck size={16} /> Config validation</div>
            <p className="test-section-copy">先检查 Skill 配置结构、缺失引用和可恢复警告。</p>
            <button onClick={handleValidate} className="btn btn-secondary" disabled={validating}>
              {validating ? '验证中...' : '运行配置验证'}
            </button>
            {validateResult && (
              <div className={`test-summary ${validateResult.ok ? 'ok' : 'danger'}`}>
                <strong>{validateResult.ok ? '验证通过' : `${validateResult.errors.length} 个错误`}</strong>
                {[...validateResult.errors, ...validateResult.warnings].slice(0, 4).map((item, index) => (
                  <span key={`validation-${index}`}>{item}</span>
                ))}
              </div>
            )}
          </section>

          <section className="skill-section-panel">
            <div className="test-section-title"><ShieldCheck size={16} /> Safety review</div>
            <p className="test-section-copy">审查 manifest、导入状态、package 安全信息和目标范围。</p>
            {skillReviewError && (
              <div className="skill-message danger">
                {skillReviewError}
                <button type="button" onClick={() => setSkillReviewError('')}>清除</button>
              </div>
            )}
            <div className="review-list">
              {filteredCapabilities.slice(0, 8).map((skill) => {
                const review = skillReviewResults[skill.id]
                return (
                  <div key={`review-${skill.id}`} className="review-row">
                    <div>
                      <code>{skill.id}</code>
                      <span>{skill.package || 'legacy'}</span>
                    </div>
                    {review && (
                      <span className={`review-verdict ${review.verdict}`}>
                        {review.verdict}
                      </span>
                    )}
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => handleSkillReview(skill.id)}
                      disabled={reviewingSkill === skill.id || skill.missing}
                    >
                      {reviewingSkill === skill.id ? '审查中...' : '审查'}
                    </button>
                  </div>
                )
              })}
            </div>
          </section>
        </div>
      )}

      {activeView === 'test' && (
      <div className="skill-section-panel">
        <div className="test-section-title"><FlaskConical size={16} /> Fixtures tests</div>
        <p className="test-section-copy">运行 package Skill 的 fixtures，快速确认输入输出契约仍然可用。</p>
        <div
          style={{
            marginBottom: 'var(--space-3)',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <button onClick={handleTestAll} className="btn btn-secondary" disabled={testingAll}>
            {testingAll ? '测试中...' : '测试全部 Package Skill'}
          </button>
          {testAllResult && (
            <span style={{ fontSize: '13px', fontWeight: 500 }}>
              {testAllResult.failed === 0 ? (
                <span style={{ color: 'var(--success)' }}>
                  {testAllResult.passed}/{testAllResult.total} 通过
                  {testAllResult.skipped > 0 && `，${testAllResult.skipped} 个跳过`}
                </span>
              ) : (
                <span style={{ color: 'var(--danger)' }}>
                  {testAllResult.passed}/{testAllResult.total} 通过，{testAllResult.failed} 失败
                  {testAllResult.skipped > 0 && `，${testAllResult.skipped} 个跳过`}
                </span>
              )}
            </span>
          )}
        </div>

        {testAllResult && testAllResult.failed > 0 && (
          <div
            style={{
              marginBottom: 'var(--space-3)',
              padding: '12px',
              borderRadius: '6px',
              background: '#fef2f2',
              color: '#991b1b',
              fontSize: '13px',
            }}
          >
            {Object.entries(testAllResult.results)
              .filter(([, r]) => !r.ok)
              .map(([sid, r]) => (
                <div key={sid} style={{ marginBottom: 4 }}>
                  <strong>{sid}</strong>: {r.error || '未知错误'}
                </div>
              ))}
          </div>
        )}

        {testAllError && (
          <div
            style={{
              marginBottom: 'var(--space-3)',
              padding: '12px',
              borderRadius: '6px',
              background: '#fef2f2',
              color: '#991b1b',
              fontSize: '13px',
            }}
          >
            {testAllError}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 'var(--space-2)' }}>
          {filteredRuntimeSkills.map((skill) => {
            const singleRes = testSingleResult[skill.id]
            return (
              <div
                key={`test-${skill.id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                  padding: '8px 12px',
                  borderRadius: '6px',
                  background: 'var(--paper-surface)',
                  border: '1px solid rgba(30, 58, 95, 0.06)',
                  minWidth: 0,
                }}
              >
                <div style={{ fontSize: '13px', minWidth: 0 }}>
                  <code style={compactCodeStyle}>{skill.id}</code>
                  {singleRes && (
                    <span style={{ display: 'block', marginTop: 3, fontSize: '12px', overflowWrap: 'anywhere' }}>
                      {singleRes.ok ? (
                        <span style={{ color: 'var(--success)' }}>
                          {singleRes.data?.passed ?? 0}/{singleRes.data?.total ?? 0} 通过
                        </span>
                      ) : (
                        <span style={{ color: 'var(--danger)' }}>{singleRes.error || '失败'}</span>
                      )}
                    </span>
                  )}
                </div>
                {skill.package ? (
                  <button
                    onClick={() => handleTestSingle(skill.id)}
                    className="btn btn-secondary"
                    disabled={testingSkill === skill.id}
                    style={{ fontSize: '12px', padding: '4px 10px' }}
                  >
                    {testingSkill === skill.id ? '测试中...' : '测试'}
                  </button>
                ) : (
                  <span
                    style={{
                      fontSize: '12px',
                      color: 'var(--text-muted)',
                      padding: '4px 10px',
                    }}
                  >
                    无 fixtures
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </div>
      )}

      {/* Manual Run Bench */}
      {activeView === 'test' && (
      <div className="skill-section-panel">
        <div className="test-section-title"><PlayCircle size={16} /> Manual run</div>
        <p className="test-section-copy">选择一个 Skill，以文本或 JSON payload 进行一次手动试运行。</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: '12px', marginBottom: '12px' }}>
          <FormField label="选择 Skill">
            <Select
              value={runSkillId}
              onChange={(e) => setRunSkillId(e.target.value)}
            >
              <option value="">-- 请选择 --</option>
              {filteredRuntimeSkills.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="输入文本">
            <TextArea
              rows={4}
              value={runText}
              onChange={(e) => setRunText(e.target.value)}
              placeholder="输入要测试的文本..."
            />
          </FormField>
          <FormField label="Custom Payload (JSON)" error={runPayloadError || undefined} className="manual-run-payload">
            <TextArea
              rows={4}
              value={runPayload}
              onChange={(e) => { setRunPayload(e.target.value); setRunPayloadError('') }}
              placeholder={'例如: {\n  "style_bible": {\n    "tone": "正式"\n  }\n}'}
              invalid={Boolean(runPayloadError)}
            />
          </FormField>
        </div>
        <button
          onClick={handleRun}
          className="btn btn-primary"
          disabled={running || !runSkillId || (!runText.trim() && !runPayload.trim())}
        >
          {running ? '运行中...' : '试运行'}
        </button>

        {runResult && (
          <div style={{ marginTop: 'var(--space-3)' }}>
            <div
              style={{
                padding: '12px',
                borderRadius: '6px',
                background: runResult.result.ok ? '#dcfce7' : '#fef2f2',
                color: runResult.result.ok ? '#166534' : '#991b1b',
                fontSize: '13px',
                marginBottom: 'var(--space-2)',
              }}
            >
              <strong>{runResult.result.ok ? '运行成功' : '运行失败'}</strong>
              {runResult.result.error && (
                <div style={{ marginTop: 4 }}>{runResult.result.error}</div>
              )}
            </div>
            {runResult.result.data && (
              <pre
                style={{
                  background: '#1f2937',
                  color: '#f9fafb',
                  padding: '12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  overflow: 'auto',
                  maxHeight: 300,
                }}
              >
                {JSON.stringify(runResult.result.data, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
      )}

      {/* Skill list table */}
      {activeView === 'catalog' && (
      <div>
        <h4
          style={sectionTitleStyle}
        >
          Skill 列表
        </h4>
        <DataTable
          compact
          data={filteredRuntimeSkills}
          getRowKey={(skill) => skill.id}
          emptyTitle="没有匹配的 Skill"
          columns={[
            { key: 'id', header: 'ID', render: (skill) => <code style={compactCodeStyle}>{skill.id}</code> },
            { key: 'name', header: '名称', render: (skill) => skill.name || '-' },
            { key: 'kind', header: '类型', render: (skill) => skill.kind || skill.type || '-' },
            { key: 'version', header: '版本', render: (skill) => skill.version || '-' },
            { key: 'package', header: 'Package', render: (skill) => <code style={{ ...compactCodeStyle, fontSize: '11px' }}>{skill.package || '-'}</code> },
            { key: 'class', header: 'Class', render: (skill) => <code style={{ ...compactCodeStyle, fontSize: '11px' }}>{skill.class_name || skill.class || '-'}</code> },
            {
              key: 'status',
              header: '状态',
              render: (skill) => (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: skill.enabled ? 'var(--success)' : 'var(--text-muted)',
                    }}
                  />
                  <span style={{ fontSize: '12px' }}>
                    {skill.enabled ? '已启用' : '已禁用'}
                  </span>
                  {skill.enabled && !skill.is_mounted && (
                    <span
                      style={{
                        ...statusChipStyle('warn'),
                        padding: '1px 6px',
                        fontSize: '11px',
                      }}
                    >
                      未挂载
                    </span>
                  )}
                </div>
              ),
            },
          ]}
        />
      </div>
      )}

      {/* Descriptions */}
      {activeView === 'catalog' && (
      <div style={{ marginTop: 'var(--space-4)' }}>
        {filteredRuntimeSkills.map((skill) => (
          <div
            key={`desc-${skill.id}`}
            style={{
              marginBottom: 'var(--space-2)',
              padding: 'var(--space-3)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-secondary)',
              border: '1px solid rgba(30, 58, 95, 0.06)',
            }}
          >
            <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: 4 }}>
              {skill.name || skill.id}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {skill.description || '无描述'}
            </div>
            {skill.mounted_to.length > 0 && (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 4 }}>
                挂载到:{" "}
                {skill.mounted_to.map((m) => `${m.agent}/${m.stage}`).join(', ')}
              </div>
            )}
          </div>
        ))}
      </div>
      )}
        </main>
      </div>
    </div>
  )
}
