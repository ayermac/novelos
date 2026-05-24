import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  FileText,
  Loader2,
  Play,
  Settings,
  Sparkles,
  Square,
  Wrench,
  XCircle,
  Zap,
} from 'lucide-react'
import { get, post, apiUrl, getApiBase } from '../../lib/api'
import { normalizeOperationResult, isBusinessSuccess } from '../../lib/statusSemantics'
import { tSessionStopLabel, tActionKey, tStepResult, tWorkflowNodeLabel } from '../../lib/state-labels'
import { Checkbox, InlineMessage, LoadingButton, NumberInput, SkeletonStack, useToast } from '../ui'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ProjectSummary {
  project_id: string
  name: string
  genre?: string
  description?: string
  total_chapters_planned: number
  target_words: number
}

interface WorkspaceStats {
  total_chapters: number
  total_words: number
  status_counts: Record<string, number>
}

interface ContextStatus {
  ready: boolean
  score: number
  missing: string[]
  actions: { label: string; path: string }[]
}

interface ProductionNextAction {
  key: string
  label: string
  description: string
  primary: boolean
  action_url: string
  method: string
  requires_confirmation: boolean
  target_chapter?: number
}

interface ProductionHealth {
  has_project: boolean
  has_genesis: boolean
  has_approved_genesis: boolean
  has_world_settings: boolean
  has_characters: boolean
  has_outlines: boolean
  has_instructions_for_current_chapter: boolean
  has_pending_memory_updates: boolean
  has_blocking_chapter: boolean
  has_stuck_run: boolean
  has_running_chapter_workflow: boolean
  target_chapter?: number
  has_running_target_workflow?: boolean
  target_workflow_run_id?: string | null
  target_workflow_current_node?: string | null
  target_workflow_elapsed_minutes?: number | null
  target_workflow_stale?: boolean
}

interface MissingItem {
  key: string
  label: string
  severity: 'blocking' | 'warning'
  manual_url: string
  ai_action: { key: string; label: string }
}

interface ProductionNext {
  project_id: string
  current_chapter: number
  next_action: ProductionNextAction
  health: ProductionHealth
  missing: MissingItem[]
  actions: { key: string; label: string; description: string; action_url: string; method: string }[]
}

interface ProductionHealthItem {
  key: string
  severity: 'blocking' | 'attention' | 'warning'
  label: string
  description: string
  action_label: string
  action_url: string
  run_id?: string
  session_id?: string
  chapter_number?: number
}

interface ProductionHealthSummary {
  project_id: string
  status: 'ok' | 'attention' | 'blocking'
  summary: {
    blocking: number
    attention: number
    warning: number
    stale_runs: number
    pending_memory_items: number
    obsolete_sessions: number
  }
  items: ProductionHealthItem[]
}

interface AutoRunStep {
  step: number
  action: string
  label: string
  target_chapter?: number
  result: string
  warnings?: string[]
  error?: string
}

interface AutoRunResponse {
  status: string
  steps: AutoRunStep[]
  stop_reason: string
  chapters_touched: number[]
  steps_executed?: number
  domain_result?: Record<string, unknown>
}

interface AutoRunEventData {
  project_id: string
  step?: number
  action?: string
  label?: string
  target_chapter?: number
  result?: string
  warnings?: string[]
  error?: string | null
  stop_reason?: string
  steps_executed?: number
  chapters_touched?: number[]
  status?: string
  steps?: AutoRunStep[]
  final_next_action?: ProductionNextAction | null
  message?: string
}

interface AutoRunSession {
  id: string
  project_id: string
  status: string
  stop_reason?: string
  current_step: number
  chapter_start?: number
  chapter_end?: number
  max_steps: number
  dry_run: number
  last_event?: string
  created_at: string
  updated_at: string
  ended_at?: string
}

interface Props {
  project: ProjectSummary
  stats: WorkspaceStats
  chapterNumber?: number
}

const MAX_AUTO_RECONNECT_ATTEMPTS = 3

/* ------------------------------------------------------------------ */
/*  i18n helpers                                                       */
/* ------------------------------------------------------------------ */


function stepBorderColor(result: string): string {
  if (result === 'success') return 'var(--success)'
  if (result === 'failed') return 'var(--danger)'
  if (result === 'skipped') return 'var(--text-muted)'
  if (result === 'running') return 'var(--primary)'
  return 'var(--warning)'
}

/** Determine responsible party for an action key */
function getResponsibleParty(key: string): 'ai' | 'human' | 'system' {
  if (['review_genesis', 'review_chapter', 'apply_memory_updates'].includes(key)) return 'human'
  if (['recover_blocked_run'].includes(key)) return 'system'
  return 'ai'
}

/** Get the role name from an action key for postmortem display */
function getActionRole(key: string): string {
  const map: Record<string, string> = {
    generate_genesis: '创世设定',
    generate_missing_context: '资料补齐',
    generate_chapter: '编剧/执笔',
    continue_next_chapter: '编剧/执笔',
    generate_arc_plan: '章节规划',
    review_chapter: '审核',
    review_genesis: '审核',
    apply_memory_updates: '记忆应用',
    recover_blocked_run: '系统恢复',
    repair_title_contract: '书名修复',
  }
  return map[key] || key
}

/**
 * Derives display severity for a completed auto-run session.
 * A session can complete while individual steps had warnings (partial/fallback results).
 * Returns 'warning' when completed with step-level warnings, 'success' when fully clean.
 */
function deriveAutoRunSeverity(
  result: AutoRunResponse | null,
  steps: AutoRunStep[],
): 'success' | 'warning' | 'error' {
  if (!result) return 'success'
  if (result.domain_result) {
    const domainResult = normalizeOperationResult(result as unknown as Record<string, unknown>)
    if (domainResult.severity === 'error') return 'error'
    if (!isBusinessSuccess(domainResult) && domainResult.domain_status !== 'pending') return 'warning'
  }
  if (result.status === 'failed') return 'error'
  if (result.status !== 'completed' && result.status !== 'dry_run') return 'warning'
  const effectiveSteps = steps.length > 0 ? steps : result.steps || []
  const hasWarnSteps = effectiveSteps.some((s) => (s.warnings || []).length > 0)
  return hasWarnSteps ? 'warning' : 'success'
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

/** Book title contract summary card */
function BookTitleContractCard({ project }: { project: ProjectSummary }) {
  const items = [
    { label: '书名', value: project.name },
    { label: '题材', value: project.genre || '未设置' },
    { label: '目标', value: `${project.total_chapters_planned} 章 / ${project.target_words.toLocaleString()} 字` },
  ]

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '10px 14px',
        background: 'var(--bg-primary)',
        border: '1px solid var(--border-color)',
        borderRadius: 10,
        marginBottom: 14,
        flexWrap: 'wrap',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <BookOpen size={16} style={{ color: 'var(--primary)', flexShrink: 0 }} />
      {items.map((item) => (
        <div key={item.label} style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{item.label}:</span>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', overflowWrap: 'anywhere' }}>
            {item.value}
          </span>
        </div>
      ))}
      <Link
        to={`?module=genesis`}
        style={{ fontSize: 11, color: 'var(--primary)', marginLeft: 'auto', whiteSpace: 'nowrap' }}
      >
        查看契约详情
      </Link>
    </div>
  )
}

/** Postmortem card for blocked/failed production states */
function ProductionPostmortemCard({
  actionKey,
  stopReason,
  sessionStatus,
  lastError,
  targetChapter,
  steps,
}: {
  actionKey: string
  stopReason: string
  sessionStatus: string
  lastError?: string
  targetChapter?: number
  steps?: AutoRunStep[]
}) {
  const role = getActionRole(actionKey)
  const failedSteps = (steps || []).filter((s) => s.result === 'failed')
  const lastFailedStep = failedSteps.length > 0 ? failedSteps[failedSteps.length - 1] : null

  const stopReasonText = tSessionStopLabel(sessionStatus, stopReason)
  const errorText = lastError || lastFailedStep?.error || '未知错误'

  const getSuggestion = (): { text: string; action?: string } => {
    if (stopReason === 'repeated_failure') return { text: '建议打开章节工作流查看失败详情，或手动编辑相关资料后重试', action: '打开章节工作流' }
    if (stopReason === 'consecutive_no_progress') return { text: '连续多次未产生新内容，建议检查资料完整性或调整创作方向', action: '查看资料缺口' }
    if (stopReason === 'blocked') return { text: '生产已阻塞，需要人工确认后才能继续', action: '查看阻塞详情' }
    if (stopReason === 'step_failed') return { text: '步骤执行失败，可重试该步骤或手动处理', action: '重试这一步' }
    if (errorText.includes('CRITICAL') || errorText.includes('死刑红线')) return { text: '内容触发红线审核，需要人工确认方向', action: '查看审核结果' }
    if (errorText.includes('stale state') || errorText.includes('status advance failed')) return { text: '章节状态异常，建议重置章节状态后重试', action: '重置章节' }
    if (errorText.includes('memory apply failed')) return { text: '记忆应用失败，建议检查记忆收件箱并手动处理冲突', action: '查看记忆收件箱' }
    if (errorText.includes('NO_CONTENT_CREATED')) return { text: '未生成有效内容，建议检查资料完整性后重试', action: '查看资料缺口' }
    return { text: '建议查看失败详情后决定下一步操作' }
  }

  const suggestion = getSuggestion()

  return (
    <div
      style={{
        padding: '14px 16px',
        background: 'color-mix(in srgb, var(--warning) 10%, var(--bg-primary))',
        border: '1px solid color-mix(in srgb, var(--warning) 24%, transparent)',
        borderRadius: 8,
        marginBottom: 14,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <AlertCircle size={16} color="var(--warning)" />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--warning)' }}>阻塞复盘</span>
        {targetChapter && (
          <span style={{ fontSize: 12, color: 'var(--warning)', marginLeft: 'auto' }}>第 {targetChapter} 章</span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(160px, 100%), 1fr))', gap: 8, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--warning)', marginBottom: 2 }}>卡在角色</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{role}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--warning)', marginBottom: 2 }}>停止原因</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{stopReasonText}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--warning)', marginBottom: 2 }}>最近错误</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', overflowWrap: 'anywhere', lineHeight: 1.4 }}>{errorText}</div>
        </div>
      </div>

      {failedSteps.length > 0 && (
        <div style={{ fontSize: 12, color: 'var(--warning)', marginBottom: 8 }}>
          系统已尝试 {failedSteps.length} 次: {failedSteps.map((s) => tActionKey(s.action)).join(' → ')}
        </div>
      )}

      <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.5 }}>
        {suggestion.text}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ProjectOverviewModule({ project, stats, chapterNumber }: Props) {
  const navigate = useNavigate()

  const { showToast } = useToast()

  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(null)
  const [productionNext, setProductionNext] = useState<ProductionNext | null>(null)
  const [healthSummary, setHealthSummary] = useState<ProductionHealthSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [filling, setFilling] = useState(false)
  const [primaryActionLoading, setPrimaryActionLoading] = useState(false)
  const [inlineMessage, setInlineMessage] = useState<{ variant: 'success' | 'warning' | 'danger'; children: string } | null>(null)

  /* Auto-run state */
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoResult, setAutoResult] = useState<AutoRunResponse | null>(null)
  const [autoError, setAutoError] = useState<{ code: string; message: string; details?: unknown } | null>(null)
  const [autoConfig, setAutoConfig] = useState({
    maxSteps: 5,
    chapterStart: 1,
    chapterEnd: 10,
    stopOnReview: true,
    dryRun: false,
  })
  const [showAdvancedControls, setShowAdvancedControls] = useState(false)
  const autoConfigInitialized = useRef(false)

  /* SSE stream state */
  const [streamSteps, setStreamSteps] = useState<AutoRunStep[]>([])
  const [streamStatus, setStreamStatus] = useState<'idle' | 'running' | 'completed' | 'stopped' | 'error'>('idle')
  const [streamError, setStreamError] = useState<{ code: string; message: string } | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  /* Session control state */
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<AutoRunSession[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [sessionLoading, setSessionLoading] = useState(false)

  /* Resilience state */
  const [disconnected, setDisconnected] = useState(false)
  const [recovering, setRecovering] = useState(false)
  const reconnectTimerRef = useRef<number | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const manualStreamStopRef = useRef(false)

  /* Reset auto-run state when project changes */
  useEffect(() => {
    autoConfigInitialized.current = false
    setAutoResult(null)
    setAutoError(null)
    setStreamSteps([])
    setStreamStatus('idle')
    setStreamError(null)
    setDisconnected(false)
    setRecovering(false)
    setAutoConfig({ maxSteps: 5, chapterStart: 1, chapterEnd: 10, stopOnReview: true, dryRun: false })
    setShowAdvancedControls(false)
    setProductionNext(null)
    setHealthSummary(null)
    setShowHistory(false)
    setInlineMessage(null)
    reconnectAttemptsRef.current = 0
    manualStreamStopRef.current = false
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [project.project_id])

  /* Cleanup EventSource on unmount */
  useEffect(() => {
    return () => {
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
    }
  }, [])

  /* Only initialise range once so user edits are not overwritten */
  useEffect(() => {
    if (productionNext && !autoConfigInitialized.current && productionNext.project_id === project.project_id) {
      autoConfigInitialized.current = true
      const current = productionNext.current_chapter || 1
      setAutoConfig((prev) => ({ ...prev, chapterStart: current, chapterEnd: current + 9 }))
    }
  }, [productionNext, project.project_id])

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent === true
    if (!silent) setLoading(true)
    const chapterParam = chapterNumber && chapterNumber > 1 ? `?chapter=${chapterNumber}` : ''
    try {
      const [ctxRes, prodRes, healthRes] = await Promise.all([
        get<ContextStatus>(`/projects/${project.project_id}/context-status${chapterParam}`),
        get<ProductionNext>(`/projects/${project.project_id}/production-next`),
        get<ProductionHealthSummary>(`/projects/${project.project_id}/production/health-summary`),
      ])
      if (ctxRes.ok && ctxRes.data) {
        setContextStatus(ctxRes.data)
      } else if (!ctxRes.ok) {
        showToast({ tone: 'danger', title: '加载失败', message: ctxRes.error?.message || '无法获取资料准备状态' })
      }
      if (prodRes.ok && prodRes.data) {
        setProductionNext(prodRes.data)
      } else if (!prodRes.ok) {
        showToast({ tone: 'danger', title: '加载失败', message: prodRes.error?.message || '无法获取生产建议' })
      }
      if (healthRes.ok && healthRes.data) {
        setHealthSummary(healthRes.data)
      } else if (!healthRes.ok) {
        showToast({ tone: 'warning', title: '健康检查失败', message: healthRes.error?.message || '无法获取项目健康状态' })
      }
    } catch (err) {
      showToast({ tone: 'danger', title: '网络错误', message: err instanceof Error ? err.message : '无法连接到后端服务' })
    } finally {
      if (!silent) setLoading(false)
    }
  }, [project.project_id, chapterNumber, showToast])

  /* Check for active session on mount/recovery */
  const checkActiveSession = useCallback(async () => {
    try {
      const res = await get<{ active: boolean; session?: AutoRunSession; steps?: AutoRunStep[] }>(
        `/projects/${project.project_id}/production/run-auto/active-session`
      )
      if (res.ok && res.data && res.data.active && res.data.session) {
        const s = res.data.session
        const steps = (res.data.steps || []).map((st) => ({
          step: st.step,
          action: st.action,
          label: st.label,
          target_chapter: st.target_chapter,
          result: st.result,
          warnings: st.warnings || [],
          error: st.error,
        }))
        const touched = Array.from(
          new Set(steps.map((st) => st.target_chapter).filter((n): n is number => n !== undefined))
        )
        setActiveSessionId(s.id)
        setStreamSteps(steps)
        if (s.status === 'paused' || s.status === 'running') {
          setStreamStatus(s.status === 'running' ? 'running' : 'stopped')
          setAutoRunning(s.status === 'running')
          setAutoResult({
            status: s.status,
            steps,
            stop_reason: s.stop_reason || (s.status === 'paused' ? 'paused' : ''),
            chapters_touched: touched,
            steps_executed: s.current_step,
          })
          if (s.stop_reason === 'client_disconnected' || s.last_event === 'client_disconnected') {
            setDisconnected(true)
            setStreamError({ code: 'DISCONNECTED', message: '连接已断开，可重新接入' })
          }
        }
      } else if (res.ok && res.data && !res.data.active) {
        setActiveSessionId(null)
        setAutoRunning(false)
        setDisconnected(false)
        setRecovering(false)
        setStreamError(null)
        if (streamStatus !== 'running') {
          setStreamStatus('idle')
        }
      }
    } catch {
      // ignore
    }
  }, [project.project_id, streamStatus])

  useEffect(() => {
    load().then(() => checkActiveSession())
  }, [load, checkActiveSession])

  /* ---------------------------------------------------------------- */
  /*  Auto-fill (single entry)                                        */
  /* ---------------------------------------------------------------- */

  const handleAutoFill = async () => {
    setFilling(true)
    setInlineMessage(null)
    try {
      const currentCh = productionNext?.current_chapter || 1
      const res = await post<{ filled: boolean; created: Record<string, number>; warnings: string[] }>(
        `/projects/${project.project_id}/production/auto-fill`,
        { scope: 'missing_context', chapter_start: currentCh, chapter_end: currentCh + 9, confirm: true }
      )
      if (res.ok && res.data) {
        const total = Object.values(res.data.created).reduce((a, b) => a + b, 0)
        const msg = `已自动补齐 ${total} 项资料`
        setInlineMessage({ variant: 'success', children: msg })
        showToast({ tone: 'success', title: '补齐完成', message: msg })
        await load()
      } else {
        const errMsg = res.error?.message || '补齐失败'
        setInlineMessage({ variant: 'danger', children: errMsg })
        showToast({ tone: 'danger', title: '补齐失败', message: errMsg })
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : '网络请求失败'
      setInlineMessage({ variant: 'danger', children: errMsg })
      showToast({ tone: 'danger', title: '请求失败', message: errMsg })
    } finally {
      setFilling(false)
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Execute single next step (primary action)                       */
  /* ---------------------------------------------------------------- */

  const handlePrimaryAction = async () => {
    if (!productionNext) return
    const action = productionNext.next_action

    if (action.key === 'generate_genesis' || action.key === 'review_genesis' || action.key === 'repair_title_contract') {
      navigate(`/projects/${project.project_id}?module=genesis`)
      return
    }

    if (action.key === 'generate_missing_context') {
      await handleAutoFill()
      return
    }

    if (action.key === 'generate_chapter') {
      const ch = productionNext.current_chapter
      navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
      return
    }

    if (action.key === 'continue_next_chapter') {
      const ch = action.target_chapter || productionNext.current_chapter + 1
      navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
      return
    }

    if (action.key === 'view_running_workflow') {
      const ch = action.target_chapter || productionNext.health?.target_chapter || productionNext.current_chapter
      navigate(action.action_url || `/projects/${project.project_id}?module=chapters&chapter=${ch}&view=workflow`)
      return
    }

    if (action.key === 'review_chapter') {
      navigate(`/projects/${project.project_id}?module=chapters&chapter=${productionNext.current_chapter}`)
      return
    }

    if (action.key === 'apply_memory_updates') {
      navigate(`/projects/${project.project_id}?module=memory`)
      return
    }

    if (action.key === 'recover_blocked_run') {
      const ch = action.target_chapter || productionNext.current_chapter
      setPrimaryActionLoading(true)
      setInlineMessage(null)
      try {
        const resetPath = action.action_url.replace(/^\/api/, '')
        const res = await post<{ message: string }>(resetPath, {})
        if (res.ok && res.data) {
          const msg = res.data.message || `第 ${ch} 章已重置`
          setInlineMessage({ variant: 'success', children: msg })
          showToast({ tone: 'success', title: '恢复成功', message: msg })
          await load()
          navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
        } else {
          const errMsg = res.error?.message || '重置失败'
          setInlineMessage({ variant: 'danger', children: errMsg })
          showToast({ tone: 'danger', title: '恢复失败', message: errMsg })
        }
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : '网络请求失败'
        setInlineMessage({ variant: 'danger', children: errMsg })
        showToast({ tone: 'danger', title: '请求失败', message: errMsg })
      } finally {
        setPrimaryActionLoading(false)
      }
      return
    }

    if (action.key === 'generate_arc_plan') {
      setPrimaryActionLoading(true)
      setInlineMessage(null)
      try {
        const nextCh = productionNext.current_chapter + 1
        const res = await post<{ planned: boolean; created: Record<string, number> }>(
          `/projects/${project.project_id}/production/arc-plan`,
          { chapter_start: nextCh, chapter_end: nextCh + 9, confirm: true }
        )
        if (res.ok && res.data) {
          const total = Object.values(res.data.created).reduce((a, b) => a + b, 0)
          const msg = `已生成章节计划，新增 ${total} 项`
          setInlineMessage({ variant: 'success', children: msg })
          showToast({ tone: 'success', title: '计划生成成功', message: msg })
          await load()
        } else {
          const errMsg = res.error?.message || '计划生成失败'
          setInlineMessage({ variant: 'danger', children: errMsg })
          showToast({ tone: 'danger', title: '计划生成失败', message: errMsg })
        }
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : '网络请求失败'
        setInlineMessage({ variant: 'danger', children: errMsg })
        showToast({ tone: 'danger', title: '请求失败', message: errMsg })
      } finally {
        setPrimaryActionLoading(false)
      }
      return
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Auto production runner (POST fallback)                          */
  /* ---------------------------------------------------------------- */

  const handleRunAuto = async (dryRun: boolean = false) => {
    setAutoRunning(true)
    setAutoResult(null)
    setAutoError(null)

    try {
      const res = await post<AutoRunResponse>(`/projects/${project.project_id}/production/run-auto`, {
        max_steps: autoConfig.maxSteps,
        chapter_start: autoConfig.chapterStart,
        chapter_end: autoConfig.chapterEnd,
        stop_on_review: autoConfig.stopOnReview,
        dry_run: dryRun,
        confirm: true,
      })

      if (res.ok && res.data) {
        setAutoResult(res.data)
        // Surface backend domain_result when run-auto completed with warnings/degraded results.
        const rawData = res.data as unknown as Record<string, unknown>
        if ('domain_result' in rawData && rawData.domain_result) {
          const domainResult = normalizeOperationResult(rawData)
          if (!isBusinessSuccess(domainResult) && domainResult.domain_status !== 'pending') {
            setInlineMessage({
              variant: domainResult.severity === 'error' ? 'danger' : 'warning',
              children: domainResult.user_message || domainResult.message || '运行完成但有异常',
            })
          }
        }
        if (!dryRun && res.data.status !== 'failed') {
          load()
        }
      } else {
        setAutoError({
          code: res.error?.code || 'UNKNOWN_ERROR',
          message: res.error?.message || '运行失败',
          details: res.error?.details,
        })
      }
    } catch (err) {
      setAutoError({
        code: 'NETWORK_ERROR',
        message: err instanceof Error ? err.message : '网络请求失败',
      })
    } finally {
      setAutoRunning(false)
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Auto production runner (SSE stream) with session                */
  /* ---------------------------------------------------------------- */

  const scheduleAutoReconnect = (sessionId: string, dryRun: boolean, attempt: number) => {
    if (manualStreamStopRef.current) return
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current)
    }
    if (attempt > MAX_AUTO_RECONNECT_ATTEMPTS) {
      setDisconnected(true)
      setStreamStatus('stopped')
      setStreamError({ code: 'NETWORK_ERROR', message: '实时连接暂时不可用，已切换后台刷新' })
      setAutoRunning(false)
      setRecovering(false)
      return
    }
    reconnectAttemptsRef.current = attempt
    setRecovering(true)
    setStreamStatus('running')
    setStreamError(null)
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null
      handleResumeSession(sessionId, dryRun, attempt)
    }, Math.min(1000 * attempt, 3000))
  }

  const handleRunAutoStream = async (dryRun: boolean = false) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    if (typeof EventSource === 'undefined') {
      handleRunAuto(dryRun)
      return
    }

    setStreamStatus('running')
    setStreamSteps([])
    setStreamError(null)
    setAutoResult(null)
    setAutoError(null)
    setAutoRunning(true)
    setDisconnected(false)
    setRecovering(false)
    reconnectAttemptsRef.current = 0
    manualStreamStopRef.current = false

    try {
      const startRes = await post<{
        session_id: string
        stream_url: string
        status: string
      }>(`/projects/${project.project_id}/production/run-auto/start`, {
        max_steps: autoConfig.maxSteps,
        chapter_start: autoConfig.chapterStart,
        chapter_end: autoConfig.chapterEnd,
        stop_on_review: autoConfig.stopOnReview,
        dry_run: dryRun,
        confirm: true,
      })

      if (!startRes.ok || !startRes.data) {
        setAutoError({
          code: startRes.error?.code || 'START_FAILED',
          message: startRes.error?.message || '启动失败',
        })
        setAutoRunning(false)
        setStreamStatus('error')
        return
      }

      const { session_id, stream_url } = startRes.data
      setActiveSessionId(session_id)

      const es = new EventSource(apiUrl(stream_url.replace(/^\/api/, '')))
      eventSourceRef.current = es

      es.addEventListener('auto_run_started', () => {})

      es.addEventListener('step_started', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamSteps((prev) => [
          ...prev,
          {
            step: data.step!,
            action: data.action!,
            label: data.label!,
            target_chapter: data.target_chapter,
            result: 'running',
            warnings: [],
          },
        ])
      })

      es.addEventListener('step_completed', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamSteps((prev) => {
          const exists = prev.find((s) => s.step === data.step)
          if (exists) {
            return prev.map((s) =>
              s.step === data.step
                ? { ...s, result: data.result!, warnings: data.warnings || [], error: data.error || undefined }
                : s
            )
          }
          return [
            ...prev,
            {
              step: data.step!,
              action: data.action!,
              label: data.label!,
              target_chapter: data.target_chapter,
              result: data.result!,
              warnings: data.warnings || [],
              error: data.error || undefined,
            },
          ]
        })
      })

      es.addEventListener('step_failed', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamSteps((prev) => {
          const exists = prev.find((s) => s.step === data.step)
          if (exists) {
            return prev.map((s) =>
              s.step === data.step
                ? { ...s, result: 'failed', warnings: data.warnings || [], error: data.error || undefined }
                : s
            )
          }
          return [
            ...prev,
            {
              step: data.step!,
              action: data.action!,
              label: data.label!,
              target_chapter: data.target_chapter,
              result: 'failed',
              warnings: data.warnings || [],
              error: data.error || undefined,
            },
          ]
        })
      })

      es.addEventListener('auto_run_stopped', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamStatus('stopped')
        setAutoResult({
          status: data.status || 'stopped',
          steps: data.steps || [],
          stop_reason: data.stop_reason || '',
          chapters_touched: data.chapters_touched || [],
        })
        setAutoRunning(false)
        if (!dryRun) load()
        loadSessions()
        es.close()
        eventSourceRef.current = null
      })

      es.addEventListener('auto_run_completed', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamStatus('completed')
        setAutoResult({
          status: data.status || 'completed',
          steps: data.steps || [],
          stop_reason: data.stop_reason || '',
          chapters_touched: data.chapters_touched || [],
        })
        setAutoRunning(false)
        if (!dryRun) load()
        loadSessions()
        es.close()
        eventSourceRef.current = null
      })

      es.addEventListener('auto_run_error', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamStatus('error')
        setStreamError({
          code: data.error || 'UNKNOWN_ERROR',
          message: data.message || '运行失败',
        })
        setAutoRunning(false)
        loadSessions()
        es.close()
        eventSourceRef.current = null
      })

      es.onerror = () => {
        if (eventSourceRef.current === es) {
          es.close()
          eventSourceRef.current = null
          scheduleAutoReconnect(session_id, dryRun, reconnectAttemptsRef.current + 1)
        }
      }
    } catch (err) {
      setAutoError({
        code: 'NETWORK_ERROR',
        message: err instanceof Error ? err.message : '网络请求失败',
      })
      setAutoRunning(false)
      setStreamStatus('error')
    }
  }

  const handleStopListening = () => {
    manualStreamStopRef.current = true
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setStreamStatus('stopped')
    setAutoRunning(false)
    setStreamError({ code: 'STOPPED_BY_USER', message: '已停止监听' })
  }

  /* ---------------------------------------------------------------- */
  /*  Session control                                                 */
  /* ---------------------------------------------------------------- */

  const loadSessions = useCallback(async () => {
    setSessionLoading(true)
    try {
      const res = await get<{ sessions: AutoRunSession[] }>(
        `/projects/${project.project_id}/production/run-auto/sessions`
      )
      if (res.ok && res.data) {
        setSessions(res.data.sessions)
      }
    } catch {
      // ignore
    } finally {
      setSessionLoading(false)
    }
  }, [project.project_id])

  const handleDeleteSession = async (sessionId: string) => {
    try {
      const res = await fetch(apiUrl(`/projects/${project.project_id}/production/run-auto/sessions/${sessionId}`), {
        method: 'DELETE',
      })
      if (res.ok) {
        await loadSessions()
        return true
      }
    } catch {
      // ignore
    }
    return false
  }

  const handleCleanupSessions = async () => {
    try {
      const res = await post<{ cleaned: boolean; removed_count: number }>(
        `/projects/${project.project_id}/production/run-auto/cleanup`,
        { keep_running: true, days_old: 0 }
      )
      if (res.ok && res.data) {
        loadSessions()
      }
    } catch {
      // ignore
    }
  }

  const handleHealthAction = async (item: ProductionHealthItem) => {
    if (item.action_url.startsWith(getApiBase() + '/')) {
      if (item.key.startsWith('obsolete_session') && item.session_id) {
        const deleted = await handleDeleteSession(item.session_id)
        if (deleted) {
          await load()
        }
      }
      return
    }
    navigate(item.action_url)
  }

  const handleCancelSession = async () => {
    if (!activeSessionId) return
    manualStreamStopRef.current = true
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    try {
      const res = await post<{ cancelled: boolean }>(
        `/projects/${project.project_id}/production/run-auto/sessions/${activeSessionId}/cancel`,
        {}
      )
      if (res.ok && res.data?.cancelled) {
        if (eventSourceRef.current) {
          eventSourceRef.current.close()
          eventSourceRef.current = null
        }
        setStreamStatus('stopped')
        setAutoRunning(false)
        setStreamError({ code: 'CANCELLED', message: '已取消' })
        loadSessions()
      }
    } catch {
      // ignore
    }
  }

  const handlePauseSession = async () => {
    if (!activeSessionId) return
    try {
      const res = await post<{ paused: boolean }>(
        `/projects/${project.project_id}/production/run-auto/sessions/${activeSessionId}/pause`,
        {}
      )
      if (res.ok && res.data?.paused) {
        // Cooperative pause: server stops at next boundary
      }
    } catch {
      // ignore
    }
  }

  const handleResumeSession = async (sessionIdOverride?: string, dryRun: boolean = false, autoAttempt: number = 0) => {
    const sessionId = sessionIdOverride || activeSessionId
    if (!sessionId) return
    manualStreamStopRef.current = false
    setAutoRunning(true)
    setStreamError(null)
    setStreamStatus('running')
    setDisconnected(false)
    setRecovering(true)
    try {
      const res = await post<{ resumed: boolean; stream_url: string }>(
        `/projects/${project.project_id}/production/run-auto/sessions/${sessionId}/resume`,
        {}
      )
      if (!res.ok || !res.data?.resumed) {
        if (autoAttempt > 0 && autoAttempt < MAX_AUTO_RECONNECT_ATTEMPTS) {
          scheduleAutoReconnect(sessionId, dryRun, autoAttempt + 1)
          return
        }
        setAutoRunning(false)
        setRecovering(false)
        setDisconnected(true)
        setStreamStatus('error')
        setStreamError({
          code: res.error?.code || 'RESUME_FAILED',
          message: res.error?.message || '恢复生产失败',
        })
        return
      }
      reconnectAttemptsRef.current = 0
      const es = new EventSource(apiUrl(res.data.stream_url.replace(/^\/api/, '')))
      eventSourceRef.current = es

      es.addEventListener('auto_run_started', () => {})
      es.addEventListener('step_started', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamSteps((prev) => [
          ...prev,
          { step: data.step!, action: data.action!, label: data.label!, target_chapter: data.target_chapter, result: 'running', warnings: [] },
        ])
      })
      es.addEventListener('step_completed', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamSteps((prev) => {
          const exists = prev.find((s) => s.step === data.step)
          if (exists) return prev.map((s) => s.step === data.step ? { ...s, result: data.result!, warnings: data.warnings || [], error: data.error || undefined } : s)
          return [...prev, { step: data.step!, action: data.action!, label: data.label!, target_chapter: data.target_chapter, result: data.result!, warnings: data.warnings || [], error: data.error || undefined }]
        })
      })
      es.addEventListener('step_failed', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamSteps((prev) => {
          const exists = prev.find((s) => s.step === data.step)
          if (exists) return prev.map((s) => s.step === data.step ? { ...s, result: 'failed', warnings: data.warnings || [], error: data.error || undefined } : s)
          return [...prev, { step: data.step!, action: data.action!, label: data.label!, target_chapter: data.target_chapter, result: 'failed', warnings: data.warnings || [], error: data.error || undefined }]
        })
      })
      es.addEventListener('auto_run_stopped', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamStatus('stopped')
        setAutoResult({ status: data.status || 'stopped', steps: data.steps || [], stop_reason: data.stop_reason || '', chapters_touched: data.chapters_touched || [] })
        setAutoRunning(false)
        setRecovering(false)
        setDisconnected(false)
        loadSessions()
        es.close()
        eventSourceRef.current = null
      })
      es.addEventListener('auto_run_completed', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamStatus('completed')
        setAutoResult({ status: data.status || 'completed', steps: data.steps || [], stop_reason: data.stop_reason || '', chapters_touched: data.chapters_touched || [] })
        setAutoRunning(false)
        setRecovering(false)
        setDisconnected(false)
        loadSessions()
        es.close()
        eventSourceRef.current = null
      })
      es.addEventListener('auto_run_error', (e) => {
        const data: AutoRunEventData = JSON.parse((e as MessageEvent).data)
        setStreamStatus('error')
        setStreamError({ code: data.error || 'UNKNOWN_ERROR', message: data.message || '运行失败' })
        setAutoRunning(false)
        setRecovering(false)
        loadSessions()
        es.close()
        eventSourceRef.current = null
      })
      es.onerror = () => {
        if (eventSourceRef.current === es) {
          es.close()
          eventSourceRef.current = null
          scheduleAutoReconnect(sessionId, dryRun, reconnectAttemptsRef.current + 1)
        }
      }
    } catch {
      if (autoAttempt > 0 && autoAttempt < MAX_AUTO_RECONNECT_ATTEMPTS) {
        scheduleAutoReconnect(sessionId, dryRun, autoAttempt + 1)
        return
      }
      setAutoRunning(false)
      setRecovering(false)
      setDisconnected(true)
      setStreamStatus('error')
      setStreamError({ code: 'RESUME_FAILED', message: '恢复生产失败' })
    }
  }

  /* Retry a failed step */
  const handleRetryStep = async (stepNumber: number) => {
    if (!activeSessionId) return
    try {
      const res = await post<{ retried: boolean; result: string; error?: string; warnings?: string[] }>(
        `/projects/${project.project_id}/production/run-auto/sessions/${activeSessionId}/retry-step`,
        { step_number: stepNumber }
      )
      if (res.ok && res.data) {
        setStreamSteps((prev) =>
          prev.map((s) =>
            s.step === stepNumber
              ? { ...s, result: res.data!.result, error: res.data!.error, warnings: res.data!.warnings || [] }
              : s
          )
        )
        loadSessions()
      }
    } catch {
      // ignore
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Derived values                                                  */
  /* ---------------------------------------------------------------- */

  const published = stats.status_counts?.published || 0
  const planned = stats.status_counts?.planned || 0
  const nextActionKey = productionNext?.next_action?.key || 'none'
  const currentCh = productionNext?.current_chapter || 1
  const targetCh = productionNext?.next_action?.target_chapter
    || productionNext?.health?.target_chapter
    || currentCh
  const isTargetWorkflowStale = productionNext?.health?.target_workflow_stale || false
  const completionRate = stats.total_chapters > 0 ? Math.round((published / stats.total_chapters) * 100) : 0
  const responsibleParty = getResponsibleParty(nextActionKey)
  const hasRunningWorkflow = streamStatus === 'running'
    || autoResult?.steps?.some((s) => s.result === 'running')
    || (activeSessionId && autoResult?.status === 'running')
    || productionNext?.health?.has_running_chapter_workflow
    || productionNext?.health?.has_running_target_workflow
    || false
  const runningWorkflowNode = productionNext?.health?.target_workflow_current_node || null
  const disconnectedRunningWorkflow = disconnected && hasRunningWorkflow
  const autoRunStatusLabel = disconnectedRunningWorkflow
    ? '工作流运行中'
    : tSessionStopLabel(streamStatus === 'running' ? 'running' : autoResult?.status || 'idle')
  const autoRunDetailLabel = disconnectedRunningWorkflow
    ? `后台执行中${runningWorkflowNode ? `：${tWorkflowNodeLabel(runningWorkflowNode)}` : ''}`
    : (streamError ? streamError.message : tSessionStopLabel(autoResult?.status || 'stopped', autoResult?.stop_reason))
  const effectiveStreamRunning = streamStatus === 'running' || disconnectedRunningWorkflow
  const isPrimaryNavigationAction = nextActionKey === 'view_running_workflow'

  /* v5.5.15: Check if health-summary reports an obsolete session */
  const obsoleteSessionItem = healthSummary?.items.find(
    (item) => item.key.startsWith('obsolete_session')
  )
  const isSessionObsolete = disconnected && !!obsoleteSessionItem

  /* Determine if we should show postmortem */
  const isBlockedState = autoResult?.stop_reason && ['blocked', 'repeated_failure', 'consecutive_no_progress', 'step_failed'].includes(autoResult.stop_reason)
  const hasCriticalError = streamError?.message?.includes('CRITICAL') || streamError?.message?.includes('死刑红线')
  const showPostmortem = isBlockedState || hasCriticalError

  useEffect(() => {
    if (!disconnectedRunningWorkflow) return
    const timer = window.setInterval(() => {
      load({ silent: true })
      checkActiveSession()
    }, 8000)
    return () => window.clearInterval(timer)
  }, [disconnectedRunningWorkflow, load, checkActiveSession])

  /* ---------------------------------------------------------------- */
  /*  Render                                                          */
  /* ---------------------------------------------------------------- */

  return (
    <div className="project-module project-overview-grid">
      <div className="overview-main">
      {/* ============================================================ */}
      {/*  Book title contract (lightweight)                           */}
      {/* ============================================================ */}
      <BookTitleContractCard project={project} />

      {/* ============================================================ */}
      {/*  Today Production Panel                                       */}
      {/* ============================================================ */}
      <div
        style={{
          background: 'var(--bg-primary)',
          border: '1px solid var(--border-color)',
          borderRadius: 10,
          marginBottom: 14,
          overflow: 'hidden',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '14px 18px',
            borderBottom: '1px solid var(--border-color)',
            background: 'linear-gradient(135deg, var(--bg-primary), var(--bg-tertiary))',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <Zap size={18} style={{ color: 'var(--primary)', flexShrink: 0 }} />
            <div style={{ minWidth: 0 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                今日生产
              </h3>
            </div>
            {loading && <Loader2 size={14} className="spin" style={{ color: 'var(--text-muted)' }} />}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <span
              style={{
                fontSize: 12,
                color: 'var(--text-muted)',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              第 {currentCh} 章
            </span>
            <span
              style={{
                fontSize: 11,
                padding: '2px 8px',
                borderRadius: 4,
                background: 'var(--accent-soft)',
                color: 'var(--primary)',
                fontWeight: 500,
              }}
            >
              全书 {published}/{project.total_chapters_planned} 章
            </span>
            <span
              style={{
                fontSize: 11,
                padding: '2px 8px',
                borderRadius: 4,
                background: completionRate >= 100 ? 'color-mix(in srgb, var(--success) 14%, transparent)' : 'var(--accent-soft)',
                color: completionRate >= 100 ? 'var(--success)' : 'var(--primary)',
                fontWeight: 500,
              }}
            >
              批次 {published}/{stats.total_chapters || 0} 章
            </span>
          </div>
        </div>

        {/* Body */}
        <div style={{ padding: '14px 18px' }}>
          {loading ? (
            <SkeletonStack rows={4} />
          ) : productionNext ? (
            <>
              {/* Next Action Task Card */}
              <div
                style={{
                  padding: '14px 16px',
                  borderRadius: 8,
                  background: nextActionKey === 'none'
                    ? 'color-mix(in srgb, var(--success) 8%, var(--bg-primary))'
                    : 'linear-gradient(135deg, var(--bg-primary), var(--bg-tertiary))',
                  border: `1px solid ${nextActionKey === 'none' ? 'color-mix(in srgb, var(--success) 22%, transparent)' : 'var(--border-color)'}`,
                  marginBottom: 14,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span
                    style={{
                      fontSize: 11,
                      padding: '3px 8px',
                      borderRadius: 4,
                      fontWeight: 600,
                      background: responsibleParty === 'ai' ? 'var(--accent-soft)' : responsibleParty === 'human' ? 'color-mix(in srgb, var(--warning) 16%, transparent)' : 'var(--bg-tertiary)',
                      color: responsibleParty === 'ai' ? 'var(--primary)' : responsibleParty === 'human' ? 'var(--warning)' : 'var(--text-secondary)',
                    }}
                  >
                    {responsibleParty === 'ai' ? 'AI 可自动处理' : responsibleParty === 'human' ? '需要你确认' : '系统处理'}
                  </span>
                  {productionNext.next_action.target_chapter && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>
                      第 {productionNext.next_action.target_chapter} 章
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
                  {productionNext.next_action.label}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.55, marginBottom: 12 }}>
                  {productionNext.next_action.description}
                </div>
                <LoadingButton
                  loading={primaryActionLoading || filling}
                  loadingText="处理中..."
                  variant="primary"
                  onClick={handlePrimaryAction}
                  disabled={autoRunning || nextActionKey === 'none' || (hasRunningWorkflow && !isPrimaryNavigationAction)}
                  style={{ flex: '1 1 220px', minWidth: 0, minHeight: 42 }}
                >
                  <Zap size={14} /> {productionNext.next_action.label}
                </LoadingButton>
              </div>

              {/* Secondary actions */}
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
                {!autoRunning && disconnected && hasRunningWorkflow && !isPrimaryNavigationAction && (
                  <Link
                    to={`?module=chapters&chapter=${targetCh}&view=workflow`}
                    className="btn btn-secondary"
                    style={{ flex: '1 1 180px', minWidth: 0, textDecoration: 'none' }}
                  >
                    <Zap size={14} /> {isTargetWorkflowStale ? `处理第 ${targetCh} 章卡住的运行` : `查看第 ${targetCh} 章实时进度`}
                  </Link>
                )}

                {!autoRunning && disconnected && !hasRunningWorkflow && !isSessionObsolete && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleResumeSession()}
                    disabled={filling || recovering}
                    style={{ flex: '1 1 150px', minWidth: 0 }}
                  >
                    <Play size={14} /> {recovering ? '恢复中...' : '重新接入'}
                  </button>
                )}

                {/* v5.5.15: Obsolete disconnected session → show cleanup instead of reconnect */}
                {!autoRunning && disconnected && !hasRunningWorkflow && isSessionObsolete && obsoleteSessionItem && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleHealthAction(obsoleteSessionItem)}
                    style={{ flex: '1 1 150px', minWidth: 0 }}
                  >
                    <XCircle size={14} /> 清理旧会话
                  </button>
                )}

                {!autoRunning && !disconnected && streamStatus === 'stopped' && autoResult?.stop_reason === 'paused' && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleResumeSession()}
                    disabled={filling}
                    style={{ flex: '1 1 150px', minWidth: 0 }}
                  >
                    <Play size={14} /> 继续生产
                  </button>
                )}

                {!autoRunning && !disconnected && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => setShowAdvancedControls((v) => !v)}
                    disabled={filling}
                    style={{ flex: '0 1 150px', minWidth: 0, minHeight: 42, display: 'flex', alignItems: 'center', gap: 4 }}
                  >
                    <Settings size={14} />
                    {showAdvancedControls ? '收起' : '连续生产'}
                    <ChevronDown size={12} style={{ transform: showAdvancedControls ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.15s' }} />
                  </button>
                )}

                {autoRunning && (
                  <>
                    <button className="btn btn-secondary" onClick={handlePauseSession} style={{ flex: '1 1 120px', minWidth: 0 }}>
                      <Square size={14} /> 暂停
                    </button>
                    <button className="btn btn-secondary" onClick={handleCancelSession} style={{ flex: '1 1 120px', minWidth: 0 }}>
                      <XCircle size={14} /> 取消
                    </button>
                    <button className="btn btn-secondary" onClick={handleStopListening} style={{ flex: '1 1 120px', minWidth: 0 }}>
                      <Square size={14} /> 停止监听
                    </button>
                  </>
                )}
              </div>

              {/* Inline feedback */}
              {inlineMessage && (
                <div style={{ marginBottom: 12 }}>
                  <InlineMessage variant={inlineMessage.variant}>{inlineMessage.children}</InlineMessage>
                </div>
              )}

              {healthSummary && healthSummary.status !== 'ok' && (
                <div
                  style={{
                    padding: '10px 12px',
                    borderRadius: 8,
                    border: '1px solid rgba(217, 119, 6, 0.24)',
                    background: 'color-mix(in srgb, var(--warning) 10%, var(--bg-primary))',
                    marginBottom: 12,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    <AlertCircle size={14} color="var(--warning)" />
                    <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--text-primary)' }}>项目健康需要处理</span>
                    <span style={{ fontSize: 12, color: 'var(--warning)', marginLeft: 'auto' }}>
                      {healthSummary.summary.blocking > 0 ? `${healthSummary.summary.blocking} 项阻塞` : `${healthSummary.summary.attention + healthSummary.summary.warning} 项提醒`}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {healthSummary.items.slice(0, 3).map((item) => (
                      <div
                        key={item.key}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 10,
                          padding: '7px 8px',
                    background: 'color-mix(in srgb, var(--warning) 13%, var(--bg-primary))',
                          borderRadius: 6,
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{item.label}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.35 }}>{item.description}</div>
                        </div>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleHealthAction(item)}
                          style={{ fontSize: 11, flexShrink: 0 }}
                        >
                          <Wrench size={11} /> {item.action_label}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Advanced controls (collapsed by default) */}
              {showAdvancedControls && (
                <>
                  <div
                    style={{
                      display: 'flex',
                      gap: 10,
                      flexWrap: 'wrap',
                      padding: '10px 12px',
                      background: 'var(--bg-tertiary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 6,
                      marginBottom: 10,
                    }}
                  >
                    <button
                      className="btn btn-secondary"
                      onClick={() => handleRunAutoStream(autoConfig.dryRun)}
                      disabled={filling || autoRunning}
                      style={{ flex: '1 1 180px', minWidth: 0, minHeight: 38 }}
                    >
                      {autoConfig.dryRun ? <Sparkles size={14} /> : <Play size={14} />}
                      {autoConfig.dryRun ? '只预览，不执行' : '开始连续生产'}
                    </button>
                    <div style={{ flex: '2 1 260px', fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                      连续生产会按预算逐步执行，遇到审核、阻塞、无进展或重复失败会停下。
                    </div>
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(min(170px, 100%), 1fr))',
                      gap: 12,
                      alignItems: 'center',
                      padding: '10px 12px',
                      background: 'var(--bg-tertiary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 6,
                      marginBottom: 12,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flexWrap: 'wrap' }}>
                      <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>最多执行几步</label>
                      <NumberInput
                        min={1}
                        max={50}
                        value={autoConfig.maxSteps}
                        onChange={(e) => setAutoConfig((prev) => ({ ...prev, maxSteps: parseInt(e.target.value) || 5 }))}
                        disabled={autoRunning || filling}
                        style={{ width: 58, minHeight: 36, padding: '4px 7px', fontSize: 12 }}
                      />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flexWrap: 'wrap' }}>
                      <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>章节范围</label>
                      <NumberInput
                        min={1}
                        value={autoConfig.chapterStart}
                        onChange={(e) => setAutoConfig((prev) => ({ ...prev, chapterStart: parseInt(e.target.value) || 1 }))}
                        disabled={autoRunning || filling}
                        style={{ width: 52, minHeight: 36, padding: '4px 7px', fontSize: 12 }}
                      />
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>-</span>
                      <NumberInput
                        min={1}
                        value={autoConfig.chapterEnd}
                        onChange={(e) => setAutoConfig((prev) => ({ ...prev, chapterEnd: parseInt(e.target.value) || 10 }))}
                        disabled={autoRunning || filling}
                        style={{ width: 52, minHeight: 36, padding: '4px 7px', fontSize: 12 }}
                      />
                    </div>
                    <Checkbox label="遇审核停止" checked={autoConfig.stopOnReview} onChange={(e) => setAutoConfig((prev) => ({ ...prev, stopOnReview: e.target.checked }))} disabled={autoRunning || filling} />
                    <Checkbox label="只预览，不执行" checked={autoConfig.dryRun} onChange={(e) => setAutoConfig((prev) => ({ ...prev, dryRun: e.target.checked }))} disabled={autoRunning || filling} />
                  </div>
                </>
              )}

              {/* Budget status (visible when running or has results) */}
              {(autoRunning || autoResult || streamSteps.length > 0 || streamError || activeSessionId) && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(min(140px, 100%), 1fr))',
                    gap: 10,
                    marginBottom: 12,
                    padding: '10px 12px',
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-color)',
                    borderRadius: 6,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>已执行步数</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {streamSteps.length > 0 ? streamSteps.length : autoResult?.steps_executed || 0} / {autoConfig.maxSteps}
                    </div>
                    <div style={{ height: 4, background: 'var(--border-color)', borderRadius: 2, marginTop: 4, overflow: 'hidden' }}>
                      <div
                        style={{
                          height: '100%',
                          width: `${Math.min(100, ((streamSteps.length > 0 ? streamSteps.length : autoResult?.steps_executed || 0) / Math.max(1, autoConfig.maxSteps)) * 100)}%`,
                          background: effectiveStreamRunning ? 'var(--primary)' : 'var(--success)',
                          borderRadius: 2,
                          transition: 'width 0.3s ease',
                        }}
                      />
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>章节范围</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      第 {autoConfig.chapterStart}-{autoConfig.chapterEnd} 章
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>当前状态</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {autoRunStatusLabel}
                    </div>
                  </div>
                  {(autoResult?.stop_reason || streamError) && (
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>
                        {disconnectedRunningWorkflow ? '后台状态' : '停止原因'}
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--warning)' }}>
                        {autoRunDetailLabel}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Postmortem card for blocked states */}
              {showPostmortem && productionNext && (
                <ProductionPostmortemCard
                  actionKey={autoResult?.steps?.[autoResult.steps.length - 1]?.action || nextActionKey}
                  stopReason={autoResult?.stop_reason || ''}
                  sessionStatus={autoResult?.status || 'stopped'}
                  lastError={streamError?.message || autoResult?.steps?.filter((s) => s.result === 'failed').pop()?.error}
                  targetChapter={autoResult?.steps?.filter((s) => s.result === 'failed').pop()?.target_chapter || currentCh}
                  steps={streamSteps.length > 0 ? streamSteps : autoResult?.steps}
                />
              )}

              {/* Auto-run result / steps timeline */}
              {(autoResult || streamSteps.length > 0 || streamError) && (
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
                  {/* Status bar */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {effectiveStreamRunning && <Loader2 size={14} className="spin" color="var(--primary)" />}
                      {autoResult?.status === 'completed' && (
                        deriveAutoRunSeverity(autoResult, streamSteps) === 'warning'
                          ? <AlertCircle size={14} color="var(--warning)" />
                          : <CheckCircle2 size={14} color="var(--success)" />
                      )}
                      {autoResult?.status === 'failed' && <XCircle size={14} color="var(--danger)" />}
                      {autoResult?.status === 'dry_run' && <Sparkles size={14} color="var(--primary)" />}
                      {autoResult?.status === 'stopped' && !disconnectedRunningWorkflow && <AlertCircle size={14} color="var(--warning)" />}
                      {streamStatus === 'error' && !disconnectedRunningWorkflow && <XCircle size={14} color="var(--danger)" />}
                      <span style={{ fontSize: 13, fontWeight: 500 }}>
                        {effectiveStreamRunning ? '工作流仍在运行'
                          : streamStatus === 'error' ? '出错了'
                          : autoResult?.status === 'completed'
                            ? (deriveAutoRunSeverity(autoResult, streamSteps) === 'warning' ? '已完成（含警告）' : '已完成')
                          : autoResult?.status === 'failed' ? '失败'
                          : autoResult?.status === 'dry_run' ? '预览结果'
                          : '已停止'}
                      </span>
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {autoRunDetailLabel}
                    </span>
                  </div>

                  {/* Steps timeline */}
                  {(streamSteps.length > 0 || (autoResult?.steps && autoResult.steps.length > 0)) && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 240, overflowY: 'auto' }}>
                      {(streamSteps.length > 0 ? streamSteps : autoResult?.steps || []).map((step, idx) => (
                        <div
                          key={idx}
                          style={{
                            padding: '8px 10px',
                            background: 'var(--bg-tertiary)',
                            borderRadius: 6,
                            borderLeft: `3px solid ${stepBorderColor(step.result)}`,
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                            <div style={{ fontSize: 13, fontWeight: 500 }}>
                              步骤 {step.step}: {tActionKey(step.action)}
                              {step.target_chapter && (
                                <span style={{ color: 'var(--text-muted)', marginLeft: 6, fontWeight: 400 }}>
                                  第 {step.target_chapter} 章
                                </span>
                              )}
                            </div>
                            <span
                              style={{
                                fontSize: 11,
                                padding: '2px 6px',
                                borderRadius: 4,
                                  background: step.result === 'success' ? 'color-mix(in srgb, var(--success) 14%, transparent)' : step.result === 'failed' ? 'color-mix(in srgb, var(--danger) 14%, transparent)' : step.result === 'skipped' ? 'var(--bg-tertiary)' : step.result === 'running' ? 'var(--accent-soft)' : 'color-mix(in srgb, var(--warning) 16%, transparent)',
                                color: step.result === 'success' ? 'var(--success)' : step.result === 'failed' ? 'var(--danger)' : step.result === 'skipped' ? 'var(--text-secondary)' : step.result === 'running' ? 'var(--primary)' : 'var(--warning)',
                              }}
                            >
                              {tStepResult(step.result)}
                            </span>
                          </div>
                          {step.error && (
                            <div style={{ fontSize: 12, color: 'var(--danger)', marginTop: 4 }}>{step.error}</div>
                          )}
                          {step.warnings && step.warnings.length > 0 && (
                            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                              {step.warnings.join('; ')}
                            </div>
                          )}
                          {step.result === 'failed' && activeSessionId && (
                            <div style={{ marginTop: 6 }}>
                              <button className="btn btn-secondary btn-sm" onClick={() => handleRetryStep(step.step)} style={{ fontSize: 11 }}>
                                <Wrench size={11} /> 重试这一步
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {autoResult && autoResult.chapters_touched.length > 0 && (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
                      涉及章节: {autoResult.chapters_touched.join(', ')}
                    </div>
                  )}
                </div>
              )}

              {autoError && (
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                    <XCircle size={14} color="var(--danger)" />
                    <span style={{ fontSize: 13, fontWeight: 500 }}>运行失败</span>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>{autoError.message}</span>
                  </div>
                </div>
              )}

              {/* Production history (in advanced section) */}
              {showAdvancedControls && (
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12, marginTop: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
                    <span style={{ fontSize: 13, fontWeight: 500 }}>生产记录</span>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => { loadSessions(); setShowHistory((v) => !v) }}
                        disabled={sessionLoading}
                      >
                        {sessionLoading ? <Loader2 size={12} className="spin" /> : <FileText size={12} />}
                        {showHistory ? '收起' : '查看'}
                      </button>
                    </div>
                  </div>

                  {showHistory && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {sessions.length === 0 && (
                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>暂无历史记录</div>
                      )}
                      {sessions.length > 0 && (
                        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
                          <button className="btn btn-secondary btn-sm" onClick={handleCleanupSessions} style={{ fontSize: 11 }}>
                            清理已完成记录
                          </button>
                        </div>
                      )}
                      {sessions.map((s) => (
                        <div key={s.id} style={{ padding: '8px 10px', background: 'var(--bg-tertiary)', borderRadius: 6, fontSize: 12 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span style={{ fontWeight: 500 }}>
                              {s.chapter_start && s.chapter_end ? `第 ${s.chapter_start}-${s.chapter_end} 章` : '自动范围'}
                            </span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span
                                style={{
                                  fontSize: 11,
                                  padding: '2px 6px',
                                  borderRadius: 4,
                                  background: s.status === 'completed' ? 'color-mix(in srgb, var(--success) 14%, transparent)' : s.status === 'failed' ? 'color-mix(in srgb, var(--danger) 14%, transparent)' : s.status === 'cancelled' ? 'var(--bg-tertiary)' : s.status === 'paused' ? 'color-mix(in srgb, var(--warning) 16%, transparent)' : 'var(--accent-soft)',
                                  color: s.status === 'completed' ? 'var(--success)' : s.status === 'failed' ? 'var(--danger)' : s.status === 'cancelled' ? 'var(--text-secondary)' : s.status === 'paused' ? 'var(--warning)' : 'var(--primary)',
                                }}
                              >
                                {tSessionStopLabel(s.status, s.stop_reason)}
                              </span>
                              {s.status !== 'running' && s.status !== 'paused' && (
                                <button className="btn btn-secondary btn-sm" onClick={() => handleDeleteSession(s.id)} style={{ fontSize: 10, padding: '2px 6px' }} title="删除此记录">
                                  x
                                </button>
                              )}
                            </div>
                          </div>
                          <div style={{ color: 'var(--text-muted)', marginTop: 4 }}>
                            步数: {s.current_step} / {s.max_steps}
                            {s.stop_reason ? ` - ${tSessionStopLabel(s.status, s.stop_reason)}` : ''}
                          </div>
                          <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>{s.created_at}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>无法获取生产建议</div>
          )}
        </div>
      </div>
      </div>{/* end .overview-main */}

      <div className="overview-sidebar">
      {/* ============================================================ */}
      {/*  Secondary info                                              */}
      {/* ============================================================ */}

      <div className="data-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(240px, 100%), 1fr))', marginBottom: 0 }}>
        <div className="data-card" style={{ padding: 12 }}>
          <div className="data-card-title" style={{ fontSize: 13, marginBottom: 4 }}>章节进度</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>
            全书进度：{published} / {project.total_chapters_planned} 章
          </div>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4, color: 'var(--text-secondary)' }}>
            当前批次：{published} / {stats.total_chapters} 章
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            已规划 {planned} 章 · 共 {stats.total_words.toLocaleString()} 字
          </div>
        </div>
        <div className="data-card" style={{ padding: 12 }}>
          <div className="data-card-title" style={{ fontSize: 13, marginBottom: 4 }}>创作目标</div>
          <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 4 }}>
            {project.total_chapters_planned}
            <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 400 }}> 章</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            目标 {project.target_words.toLocaleString()} 字
          </div>
        </div>
      </div>

      {project.description && (
        <div className="data-card" style={{ marginTop: 12, padding: 12 }}>
          <div className="data-card-title" style={{ fontSize: 13, marginBottom: 4 }}>项目简介</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{project.description}</div>
        </div>
      )}

      {/* Context readiness */}
      <div className="data-card" style={{ marginTop: 12, padding: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {contextStatus?.ready ? <CheckCircle2 size={14} color="var(--success)" /> : <AlertCircle size={14} color="var(--warning)" />}
            <span style={{ fontSize: 13, fontWeight: 500 }}>资料准备度</span>
          </div>
          {contextStatus && (
            <span
              style={{
                fontSize: 11,
                padding: '2px 8px',
                borderRadius: 4,
                background: contextStatus.ready ? 'color-mix(in srgb, var(--success) 14%, transparent)' : 'color-mix(in srgb, var(--warning) 14%, transparent)',
                color: contextStatus.ready ? 'var(--success)' : 'var(--warning)',
              }}
            >
              {contextStatus.score}%
            </span>
          )}
        </div>
        {loading ? (
          <SkeletonStack rows={2} />
        ) : contextStatus?.ready ? (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            项目资料已满足章节生成的最低要求。
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              资料不完整，补齐后才能开始生成章节。
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {(contextStatus?.actions || []).map((action) => (
                <Link key={`${action.label}-${action.path}`} className="btn btn-secondary btn-sm" to={action.path} style={{ whiteSpace: 'nowrap' }}>
                  <FileText size={12} /> {action.label}
                </Link>
              ))}
              {(contextStatus?.missing || []).length > 0 && nextActionKey !== 'generate_missing_context' && (
                <LoadingButton
                  loading={filling}
                  loadingText="补齐中..."
                  variant="secondary"
                  className="btn-sm"
                  onClick={handleAutoFill}
                  disabled={autoRunning}
                >
                  <Sparkles size={12} /> 让 AI 补齐缺失资料
                </LoadingButton>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Missing items checklist */}
      {productionNext && productionNext.missing.length > 0 && (
        <div className="data-card" style={{ marginTop: 12, padding: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
            <AlertCircle size={14} color="var(--danger)" />
            <span style={{ fontSize: 13, fontWeight: 500 }}>资料缺口</span>
            <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 4, background: 'color-mix(in srgb, var(--danger) 14%, transparent)', color: 'var(--danger)', marginLeft: 'auto' }}>
              {productionNext.missing.length} 项
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {productionNext.missing.map((item) => (
              <div
                key={item.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '7px 10px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: 6,
                  flexWrap: 'wrap',
                  borderLeft: `3px solid ${item.severity === 'blocking' ? 'var(--danger)' : 'var(--warning)'}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: '50%',
                      background: item.severity === 'blocking' ? 'var(--danger)' : 'var(--warning)',
                      flexShrink: 0,
                    }}
                    aria-hidden="true"
                  />
                  <span style={{ fontSize: 13, overflowWrap: 'anywhere' }}>{item.label}</span>
                </div>
                <Link className="btn btn-secondary btn-sm" to={item.manual_url} style={{ flexShrink: 0, fontSize: 11 }}>
                  <Wrench size={11} /> 手动编辑
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}
      </div>{/* end .overview-sidebar */}
    </div>
  )
}
