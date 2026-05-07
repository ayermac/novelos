import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  Play,
  Settings,
  Sparkles,
  Square,
  Terminal,
  Wrench,
  XCircle,
  Zap,
} from 'lucide-react'
import { get, post } from '../../lib/api'

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

/* ------------------------------------------------------------------ */
/*  i18n helpers                                                       */
/* ------------------------------------------------------------------ */

const STOP_REASON_MAP: Record<string, string> = {
  max_steps_reached: '达到最大步数',
  review_required: '等待人工审核',
  blocked: '已阻塞',
  completed: '当前范围完成',
  unsupported_action: '需要人工处理',
  step_failed: '步骤失败',
  dry_run: '预览模式',
}

const ACTION_KEY_MAP: Record<string, string> = {
  generate_genesis: '生成创世设定',
  review_genesis: '审核创世设定',
  repair_title_contract: '修复书名契约',
  generate_missing_context: '补齐缺失资料',
  generate_chapter: '生成本章',
  continue_next_chapter: '继续下一章',
  review_chapter: '审核章节',
  apply_memory_updates: '应用记忆更新',
  recover_blocked_run: '重置阻塞运行',
  generate_arc_plan: '生成章节计划',
}

const RESULT_MAP: Record<string, string> = {
  success: '成功',
  failed: '失败',
  skipped: '跳过',
  dry_run: '预览',
  running: '运行中',
}

function tStopReason(reason: string): string {
  return STOP_REASON_MAP[reason] || reason
}

function tActionKey(key: string): string {
  return ACTION_KEY_MAP[key] || key
}

function tResult(result: string): string {
  return RESULT_MAP[result] || result
}

function stepBorderColor(result: string): string {
  if (result === 'success') return '#10b981'
  if (result === 'failed') return '#ef4444'
  if (result === 'skipped') return '#94a3b8'
  if (result === 'running') return '#3b82f6'
  return '#f59e0b'
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ProjectOverviewModule({ project, stats, chapterNumber }: Props) {
  const navigate = useNavigate()

  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(null)
  const [productionNext, setProductionNext] = useState<ProductionNext | null>(null)
  const [loading, setLoading] = useState(true)
  const [filling, setFilling] = useState(false)
  const [fillResult, setFillResult] = useState<string>('')

  /* v5.5.7: Auto-run state */
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoResult, setAutoResult] = useState<AutoRunResponse | null>(null)
  const [autoError, setAutoError] = useState<{ code: string; message: string; details?: unknown } | null>(null)
  const [autoConfig, setAutoConfig] = useState({
    maxSteps: 5,
    chapterStart: 1,
    chapterEnd: 10,
    stopOnReview: true,
  })
  const autoConfigInitialized = useRef(false)

  /* v5.5.7: SSE stream state */
  const [streamSteps, setStreamSteps] = useState<AutoRunStep[]>([])
  const [streamStatus, setStreamStatus] = useState<'idle' | 'running' | 'completed' | 'stopped' | 'error'>('idle')
  const [streamError, setStreamError] = useState<{ code: string; message: string } | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  /* v5.5.8: Session control state */
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<AutoRunSession[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [sessionLoading, setSessionLoading] = useState(false)

  /* v5.5.9: Resilience state */
  const [disconnected, setDisconnected] = useState(false)
  const [recovering, setRecovering] = useState(false)

  /* Reset auto-run state when project changes (P2-1) */
  useEffect(() => {
    autoConfigInitialized.current = false
    setAutoResult(null)
    setAutoError(null)
    setStreamSteps([])
    setStreamStatus('idle')
    setStreamError(null)
    setDisconnected(false)
    setRecovering(false)
    setAutoConfig({ maxSteps: 5, chapterStart: 1, chapterEnd: 10, stopOnReview: true })
    setProductionNext(null) // Clear stale productionNext to prevent race condition
    setShowHistory(false)
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [project.project_id])

  /* Cleanup EventSource on unmount */
  useEffect(() => {
    return () => {
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

  const load = useCallback(async () => {
    setLoading(true)
    const chapterParam = chapterNumber && chapterNumber > 1 ? `?chapter=${chapterNumber}` : ''
    const [ctxRes, prodRes] = await Promise.all([
      get<ContextStatus>(`/projects/${project.project_id}/context-status${chapterParam}`),
      get<ProductionNext>(`/projects/${project.project_id}/production-next`),
    ])
    if (ctxRes.ok && ctxRes.data) setContextStatus(ctxRes.data)
    if (prodRes.ok && prodRes.data) setProductionNext(prodRes.data)
    setLoading(false)
  }, [project.project_id, chapterNumber])

  /* v5.5.9: Check for active session on mount/recovery */
  const checkActiveSession = useCallback(async () => {
    try {
      const res = await get<{ active: boolean; session?: AutoRunSession; steps?: AutoRunStep[] }>(
        `/projects/${project.project_id}/production/run-auto/active-session`
      )
      if (res.ok && res.data && res.data.active && res.data.session) {
        const s = res.data.session
        setActiveSessionId(s.id)
        // If session is paused or disconnected, show recovery UI
        if (s.status === 'paused' || s.status === 'running') {
          setStreamStatus(s.status === 'running' ? 'running' : 'stopped')
          setAutoRunning(s.status === 'running')
          if (res.data.steps) {
            setStreamSteps(
              res.data.steps.map((st) => ({
                step: st.step,
                action: st.action,
                label: st.label,
                target_chapter: st.target_chapter,
                result: st.result,
                warnings: st.warnings || [],
                error: st.error,
              }))
            )
          }
          if (s.last_event === 'paused' || s.stop_reason === 'client_disconnected') {
            setDisconnected(true)
            setStreamError({ code: 'DISCONNECTED', message: '连接已断开，可重新接入' })
          }
        }
      }
    } catch {
      // ignore
    }
  }, [project.project_id])

  useEffect(() => {
    load().then(() => checkActiveSession())
  }, [load, checkActiveSession])

  /* ---------------------------------------------------------------- */
  /*  Auto-fill (single entry)                                        */
  /* ---------------------------------------------------------------- */

  const handleAutoFill = async () => {
    setFilling(true)
    setFillResult('')
    try {
      const currentCh = productionNext?.current_chapter || 1
      const res = await post<{ filled: boolean; created: Record<string, number>; warnings: string[] }>(
        `/projects/${project.project_id}/production/auto-fill`,
        { scope: 'missing_context', chapter_start: currentCh, chapter_end: currentCh + 9, confirm: true }
      )
      if (res.ok && res.data) {
        const total = Object.values(res.data.created).reduce((a, b) => a + b, 0)
        setFillResult(`已自动补齐 ${total} 项资料`)
        load()
      } else {
        setFillResult(res.error?.message || '补齐失败')
      }
    } catch (err) {
      setFillResult(err instanceof Error ? err.message : '网络请求失败')
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
      setFilling(true)
      setFillResult('')
      try {
        const ch = productionNext.current_chapter
        const res = await post<{ workflow_status: string; message: string }>('/run/chapter', {
          project_id: project.project_id,
          chapter: ch,
        })
        if (res.ok && res.data) {
          setFillResult(res.data.message || `第 ${ch} 章生成已触发`)
          navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
        } else {
          setFillResult(res.error?.message || '生成触发失败')
        }
      } catch (err) {
        setFillResult(err instanceof Error ? err.message : '网络请求失败')
      } finally {
        setFilling(false)
      }
      return
    }

    if (action.key === 'continue_next_chapter') {
      setFilling(true)
      setFillResult('')
      try {
        const ch = action.target_chapter || productionNext.current_chapter + 1
        const res = await post<{ workflow_status: string; message: string }>('/run/chapter', {
          project_id: project.project_id,
          chapter: ch,
        })
        if (res.ok && res.data) {
          setFillResult(res.data.message || `第 ${ch} 章生成已触发`)
          navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
        } else {
          setFillResult(res.error?.message || '生成触发失败')
        }
      } catch (err) {
        setFillResult(err instanceof Error ? err.message : '网络请求失败')
      } finally {
        setFilling(false)
      }
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
      setFilling(true)
      setFillResult('')
      try {
        const resetPath = action.action_url.replace(/^\/api/, '')
        const res = await post<{ message: string }>(resetPath, {})
        if (res.ok && res.data) {
          setFillResult(res.data.message || `第 ${ch} 章已重置`)
          load()
          navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
        } else {
          setFillResult(res.error?.message || '重置失败')
        }
      } catch (err) {
        setFillResult(err instanceof Error ? err.message : '网络请求失败')
      } finally {
        setFilling(false)
      }
      return
    }

    if (action.key === 'generate_arc_plan') {
      setFilling(true)
      setFillResult('')
      try {
        const nextCh = productionNext.current_chapter + 1
        const res = await post<{ planned: boolean; created: Record<string, number> }>(
          `/projects/${project.project_id}/production/arc-plan`,
          { chapter_start: nextCh, chapter_end: nextCh + 9, confirm: true }
        )
        if (res.ok && res.data) {
          const total = Object.values(res.data.created).reduce((a, b) => a + b, 0)
          setFillResult(`已生成章节计划，新增 ${total} 项`)
          load()
        } else {
          setFillResult(res.error?.message || '计划生成失败')
        }
      } catch (err) {
        setFillResult(err instanceof Error ? err.message : '网络请求失败')
      } finally {
        setFilling(false)
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
  /*  Auto production runner (SSE stream) v5.5.8 with session         */
  /* ---------------------------------------------------------------- */

  const handleRunAutoStream = async (dryRun: boolean = false) => {
    // Cleanup any existing stream
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    // Fallback if EventSource not supported
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

    try {
      // v5.5.8: Create session first
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

      const es = new EventSource(stream_url)
      eventSourceRef.current = es

      es.addEventListener('auto_run_started', () => {
        // stream is running
      })

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
                ? {
                    ...s,
                    result: data.result!,
                    warnings: data.warnings || [],
                    error: data.error || undefined,
                  }
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
                ? {
                    ...s,
                    result: 'failed',
                    warnings: data.warnings || [],
                    error: data.error || undefined,
                  }
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
        if (!dryRun) {
          load()
        }
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
        if (!dryRun) {
          load()
        }
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
          setDisconnected(true)
          setStreamStatus('stopped')
          setStreamError({
            code: 'NETWORK_ERROR',
            message: 'SSE 连接失败或已断开，可重新接入',
          })
          setAutoRunning(false)
          es.close()
          eventSourceRef.current = null
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
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setStreamStatus('stopped')
    setAutoRunning(false)
    setStreamError({ code: 'STOPPED_BY_USER', message: '已停止监听' })
  }

  /* ---------------------------------------------------------------- */
  /*  Session control (v5.5.8)                                        */
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

  const handleCancelSession = async () => {
    if (!activeSessionId) return
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
        // Cooperative pause: server stops at next boundary and sends stopped event
      }
    } catch {
      // ignore
    }
  }

  const handleResumeSession = async () => {
    if (!activeSessionId) return
    setAutoRunning(true)
    setStreamError(null)
    setStreamStatus('running')
    setDisconnected(false)
    setRecovering(true)
    try {
      const res = await post<{ resumed: boolean; stream_url: string }>(
        `/projects/${project.project_id}/production/run-auto/sessions/${activeSessionId}/resume`,
        {}
      )
      if (!res.ok || !res.data?.resumed) {
        setAutoRunning(false)
        setRecovering(false)
        return
      }
      // Reconnect to stream URL returned by resume
      const es = new EventSource(res.data.stream_url)
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
        setRecovering(false)
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
        setRecovering(false)
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
          setDisconnected(true)
          setStreamStatus('stopped')
          setStreamError({ code: 'NETWORK_ERROR', message: 'SSE 连接失败或已断开，可重新接入' })
          setAutoRunning(false)
          es.close()
          eventSourceRef.current = null
        }
      }
    } catch {
      setAutoRunning(false)
      setRecovering(false)
    }
  }

  /* v5.5.9: Retry a failed step */
  const handleRetryStep = async (stepNumber: number) => {
    if (!activeSessionId) return
    try {
      const res = await post<{
        retried: boolean
        result: string
        error?: string
        warnings?: string[]
      }>(
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
  const completionRate = stats.total_chapters > 0 ? Math.round((published / stats.total_chapters) * 100) : 0
  const missingCount = productionNext?.missing.length || 0
  const healthReady = contextStatus?.ready ? '就绪' : missingCount > 0 ? '待补齐' : '检查中'

  /* ---------------------------------------------------------------- */
  /*  Render                                                          */
  /* ---------------------------------------------------------------- */

  return (
    <div className="project-module">
      {/* ============================================================== */}
      {/*  Production Command Center (v5.5.6)                            */}
      {/* ============================================================== */}
      <div
        style={{
          background: '#ffffff',
          border: '1px solid rgba(15, 118, 110, 0.14)',
          borderRadius: 8,
          marginBottom: 18,
          overflow: 'hidden',
          boxShadow: '0 18px 45px rgba(8, 17, 31, 0.12)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '18px 20px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.14)',
            background: 'linear-gradient(135deg, #08111f 0%, #16324f 58%, #0f766e 100%)',
            color: '#ffffff',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <Terminal size={20} style={{ color: '#5eead4', flexShrink: 0 }} />
            <div style={{ minWidth: 0 }}>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, whiteSpace: 'nowrap', letterSpacing: 0 }}>
                生产指挥台
              </h3>
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.72)', marginTop: 2 }}>
                自动生产 · 实时监控 · 断线恢复
              </div>
            </div>
            {loading && <Loader2 size={14} className="spin" style={{ color: 'rgba(255,255,255,0.72)' }} />}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <span
              style={{
                fontSize: 12,
                color: 'rgba(255,255,255,0.72)',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              第 {currentCh} 章
            </span>
            {productionNext?.next_action && (
              <span
                className="status-badge"
                style={{
                  background: nextActionKey === 'none' ? 'rgba(255,255,255,0.12)' : 'rgba(20,184,166,0.2)',
                  color: '#ffffff',
                  border: '1px solid rgba(255,255,255,0.18)',
                  fontSize: 11,
                }}
              >
                {tActionKey(nextActionKey)}
              </span>
            )}
          </div>
        </div>

        {/* Body */}
        <div style={{ padding: '18px 20px' }}>
          {loading ? (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>加载生产状态中…</div>
          ) : productionNext ? (
            <>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(min(160px, 100%), 1fr))',
                  gap: 10,
                  marginBottom: 16,
                }}
              >
                {[
                  { label: '工厂状态', value: healthReady, hint: missingCount ? `${missingCount} 个缺口` : '资料链路可用' },
                  { label: '当前章节', value: `第 ${currentCh} 章`, hint: tActionKey(nextActionKey) },
                  { label: '发布进度', value: `${completionRate}%`, hint: `${published}/${stats.total_chapters || 0} 章` },
                ].map((item) => (
                  <div
                    key={item.label}
                    style={{
                      padding: '12px 13px',
                      borderRadius: 8,
                      background: '#f8fbff',
                      border: '1px solid rgba(15, 118, 110, 0.12)',
                    }}
                  >
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{item.label}</div>
                    <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>
                      {item.value}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 5, overflowWrap: 'anywhere' }}>
                      {item.hint}
                    </div>
                  </div>
                ))}
              </div>

              {/* Next action description */}
              <div
                style={{
                  fontSize: 14,
                  color: 'var(--text-secondary)',
                  lineHeight: 1.5,
                  marginBottom: 14,
                  padding: '11px 13px',
                  borderRadius: 8,
                  background: '#f6f8fb',
                  border: '1px solid rgba(8, 17, 31, 0.06)',
                  overflowWrap: 'anywhere',
                  wordBreak: 'break-all',
                }}
              >
                {productionNext.next_action.description}
              </div>

              {/* Primary + secondary buttons */}
              <div
                style={{
                  display: 'flex',
                  gap: 10,
                  flexWrap: 'wrap',
                  marginBottom: 16,
                }}
              >
                <button
                  className="btn btn-primary"
                  onClick={handlePrimaryAction}
                  disabled={filling || autoRunning || nextActionKey === 'none'}
                  style={{ flex: '1 1 220px', minWidth: 0, minHeight: 42 }}
                >
                  {filling ? (
                    <>
                      <Loader2 size={14} className="spin" /> 处理中…
                    </>
                  ) : (
                    <>
                      <Zap size={14} />
                      {productionNext.next_action.label}
                    </>
                  )}
                </button>

                {!autoRunning && disconnected && (
                  <button
                    className="btn btn-secondary"
                    onClick={handleResumeSession}
                    disabled={filling || recovering}
                    style={{ flex: '1 1 150px', minWidth: 0 }}
                  >
                    <Play size={14} /> {recovering ? '恢复中…' : '重新接入'}
                  </button>
                )}

                {!autoRunning && streamStatus === 'stopped' && autoResult?.stop_reason === 'paused' && !disconnected && (
                  <button
                    className="btn btn-secondary"
                    onClick={handleResumeSession}
                    disabled={filling}
                    style={{ flex: '1 1 150px', minWidth: 0 }}
                  >
                    <Play size={14} /> 继续自动生产
                  </button>
                )}

                {!autoRunning && !(streamStatus === 'stopped' && autoResult?.stop_reason === 'paused') && !disconnected && (
                  <>
                    <button
                      className="btn btn-secondary"
                      onClick={() => handleRunAutoStream(true)}
                      disabled={filling}
                      style={{ flex: '1 1 150px', minWidth: 0, minHeight: 42 }}
                    >
                      <Sparkles size={14} /> 预览自动生产
                    </button>

                    <button
                      className="btn btn-secondary"
                      onClick={() => handleRunAutoStream(false)}
                      disabled={filling}
                      style={{ flex: '1 1 150px', minWidth: 0, minHeight: 42 }}
                    >
                      <Play size={14} /> 开始自动生产
                    </button>
                  </>
                )}

                {autoRunning && (
                  <>
                    <button
                      className="btn btn-secondary"
                      onClick={handlePauseSession}
                      style={{ flex: '1 1 120px', minWidth: 0 }}
                    >
                      <Square size={14} /> 暂停
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={handleCancelSession}
                      style={{ flex: '1 1 120px', minWidth: 0 }}
                    >
                      <XCircle size={14} /> 取消
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={handleStopListening}
                      style={{ flex: '1 1 120px', minWidth: 0 }}
                    >
                      <Square size={14} /> 停止监听
                    </button>
                  </>
                )}
              </div>

              {/* Inline fill result */}
              {fillResult && (
                <div
                  className={fillResult.includes('失败') ? 'alert alert-error' : 'alert alert-success'}
                  style={{ padding: '8px 12px', fontSize: 13, marginBottom: 12 }}
                >
                  {fillResult}
                </div>
              )}

              {/* Config row (compact) */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(min(170px, 100%), 1fr))',
                  gap: 16,
                  alignItems: 'stretch',
                  padding: '10px 12px',
                  background: '#f8fbff',
                  border: '1px solid rgba(15, 118, 110, 0.12)',
                  borderRadius: 8,
                  marginBottom: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flexWrap: 'wrap' }}>
                  <Settings size={13} style={{ color: 'var(--text-muted)' }} />
                  <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>最大步数</label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={autoConfig.maxSteps}
                    onChange={(e) =>
                      setAutoConfig((prev) => ({ ...prev, maxSteps: parseInt(e.target.value) || 5 }))
                    }
                    disabled={autoRunning || filling}
                    style={{
                      width: 52,
                      minHeight: 32,
                      padding: '4px 7px',
                      fontSize: 12,
                      borderRadius: 6,
                      border: '1px solid var(--border-color)',
                      background: 'var(--bg-primary)',
                    }}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flexWrap: 'wrap' }}>
                  <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>章节范围</label>
                  <input
                    type="number"
                    min={1}
                    value={autoConfig.chapterStart}
                    onChange={(e) =>
                      setAutoConfig((prev) => ({ ...prev, chapterStart: parseInt(e.target.value) || 1 }))
                    }
                    disabled={autoRunning || filling}
                    style={{
                      width: 46,
                      minHeight: 32,
                      padding: '4px 7px',
                      fontSize: 12,
                      borderRadius: 6,
                      border: '1px solid var(--border-color)',
                      background: 'var(--bg-primary)',
                    }}
                  />
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>-</span>
                  <input
                    type="number"
                    min={1}
                    value={autoConfig.chapterEnd}
                    onChange={(e) =>
                      setAutoConfig((prev) => ({ ...prev, chapterEnd: parseInt(e.target.value) || 10 }))
                    }
                    disabled={autoRunning || filling}
                    style={{
                      width: 46,
                      minHeight: 32,
                      padding: '4px 7px',
                      fontSize: 12,
                      borderRadius: 6,
                      border: '1px solid var(--border-color)',
                      background: 'var(--bg-primary)',
                    }}
                  />
                </div>

                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    fontSize: 12,
                    color: 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={autoConfig.stopOnReview}
                    onChange={(e) => setAutoConfig((prev) => ({ ...prev, stopOnReview: e.target.checked }))}
                    disabled={autoRunning || filling}
                  />
                  遇审核停止
                </label>
              </div>

              {/* Auto-run result */}
              {(autoResult || streamSteps.length > 0 || streamError) && (
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
                  {/* Status bar */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 8,
                      flexWrap: 'wrap',
                      marginBottom: 10,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {streamStatus === 'running' && <Loader2 size={14} className="spin" color="#3b82f6" />}
                      {autoResult?.status === 'completed' && <CheckCircle2 size={14} color="#10b981" />}
                      {autoResult?.status === 'failed' && <XCircle size={14} color="#ef4444" />}
                      {autoResult?.status === 'dry_run' && <Sparkles size={14} color="#06b6d4" />}
                      {autoResult?.status === 'stopped' && <AlertCircle size={14} color="#f59e0b" />}
                      {streamStatus === 'error' && <XCircle size={14} color="#ef4444" />}
                      {!streamStatus && autoResult && autoResult.status !== 'completed' && autoResult.status !== 'failed' && autoResult.status !== 'dry_run' && autoResult.status !== 'stopped' && (
                        <AlertCircle size={14} color="#f59e0b" />
                      )}
                      <span style={{ fontSize: 13, fontWeight: 500 }}>
                        {streamStatus === 'running'
                          ? '运行中…'
                          : streamStatus === 'error'
                          ? '流错误'
                          : autoResult?.status === 'completed'
                          ? '已完成'
                          : autoResult?.status === 'failed'
                          ? '失败'
                          : autoResult?.status === 'dry_run'
                          ? '预览结果'
                          : '已停止'}
                      </span>
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {streamError
                        ? `${streamError.code}: ${streamError.message}`
                        : `停止原因: ${tStopReason(autoResult?.stop_reason || '')}`}
                    </span>
                  </div>

                  {/* Steps timeline */}
                  {(streamSteps.length > 0 || (autoResult?.steps && autoResult.steps.length > 0)) && (
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 6,
                        maxHeight: 240,
                        overflowY: 'auto',
                      }}
                    >
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
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              gap: 8,
                              flexWrap: 'wrap',
                            }}
                          >
                            <div style={{ fontSize: 13, fontWeight: 500 }}>
                              步骤 {step.step}: {tActionKey(step.action)}
                              {step.target_chapter && (
                                <span style={{ color: 'var(--text-muted)', marginLeft: 6, fontWeight: 400 }}>
                                  第 {step.target_chapter} 章
                                </span>
                              )}
                            </div>
                            <span
                              className="status-badge"
                              style={{
                                fontSize: 11,
                                background:
                                  step.result === 'success'
                                    ? '#d1fae5'
                                    : step.result === 'failed'
                                    ? '#fee2e2'
                                    : step.result === 'skipped'
                                    ? '#f1f5f9'
                                    : step.result === 'running'
                                    ? '#dbeafe'
                                    : '#fef3c7',
                                color:
                                  step.result === 'success'
                                    ? '#065f46'
                                    : step.result === 'failed'
                                    ? '#991b1b'
                                    : step.result === 'skipped'
                                    ? '#64748b'
                                    : step.result === 'running'
                                    ? '#1e40af'
                                    : '#92400e',
                              }}
                            >
                              {tResult(step.result)}
                            </span>
                          </div>
                          {step.error && (
                            <div style={{ fontSize: 12, color: '#ef4444', marginTop: 4 }}>{step.error}</div>
                          )}
                          {step.warnings && step.warnings.length > 0 && (
                            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                              {step.warnings.join('; ')}
                            </div>
                          )}
                          {step.result === 'failed' && activeSessionId && (
                            <div style={{ marginTop: 6 }}>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleRetryStep(step.step)}
                                style={{ fontSize: 11 }}
                              >
                                <Wrench size={11} /> 重试此步骤
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
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 8,
                      flexWrap: 'wrap',
                      marginBottom: 10,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <XCircle size={14} color="#ef4444" />
                      <span style={{ fontSize: 13, fontWeight: 500 }}>运行失败</span>
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {autoError.code}: {autoError.message}
                    </span>
                  </div>

                  {autoError.code === 'AUTO_RUN_STEP_FAILED' && !!autoError.details && (
                    <div
                      className="alert alert-error"
                      style={{ padding: '8px 12px', fontSize: 12, marginBottom: 10 }}
                    >
                      <pre
                        style={{
                          margin: 0,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontFamily: 'inherit',
                        }}
                      >
                        {JSON.stringify(autoError.details as Record<string, unknown>, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* Session history (v5.5.8) */}
              <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12, marginTop: 12 }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    marginBottom: 10,
                  }}
                >
                  <span style={{ fontSize: 13, fontWeight: 500 }}>自动生产历史</span>
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
                    {sessions.map((s) => (
                      <div
                        key={s.id}
                        style={{
                          padding: '8px 10px',
                          background: 'var(--bg-tertiary)',
                          borderRadius: 6,
                          fontSize: 12,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <span style={{ fontWeight: 500 }}>
                            {s.chapter_start && s.chapter_end
                              ? `第 ${s.chapter_start}-${s.chapter_end} 章`
                              : '自动范围'}
                          </span>
                          <span
                            className="status-badge"
                            style={{
                              fontSize: 11,
                              background:
                                s.status === 'completed'
                                  ? '#d1fae5'
                                  : s.status === 'failed'
                                  ? '#fee2e2'
                                  : s.status === 'cancelled'
                                  ? '#f1f5f9'
                                  : s.status === 'paused'
                                  ? '#fef3c7'
                                  : '#dbeafe',
                              color:
                                s.status === 'completed'
                                  ? '#065f46'
                                  : s.status === 'failed'
                                  ? '#991b1b'
                                  : s.status === 'cancelled'
                                  ? '#64748b'
                                  : s.status === 'paused'
                                  ? '#92400e'
                                  : '#1e40af',
                            }}
                          >
                            {s.status}
                          </span>
                        </div>
                        <div style={{ color: 'var(--text-muted)', marginTop: 4 }}>
                          步数: {s.current_step} / {s.max_steps}
                          {s.stop_reason ? ` · ${tStopReason(s.stop_reason)}` : ''}
                          {s.last_event ? ` · 最近: ${s.last_event}` : ''}
                        </div>
                        <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>
                          {s.created_at}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>无法获取生产建议</div>
          )}
        </div>
      </div>

      {/* ============================================================== */}
      {/*  Secondary info (compact)                                      */}
      {/* ============================================================== */}

      {/* Progress + goals (2-col on desktop, stacked on mobile) */}
      <div
        className="data-grid"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(240px, 100%), 1fr))', marginBottom: 0 }}
      >
        <div className="data-card" style={{ padding: 12 }}>
          <div className="data-card-title" style={{ fontSize: 13, marginBottom: 4 }}>
            章节进度
          </div>
          <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 4 }}>
            {published}
            <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 400 }}>
              {' '}/ {stats.total_chapters}
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            已发布 {published} 章 · 已规划 {planned} 章 · 共 {stats.total_words.toLocaleString()} 字
          </div>
        </div>

        <div className="data-card" style={{ padding: 12 }}>
          <div className="data-card-title" style={{ fontSize: 13, marginBottom: 4 }}>
            创作目标
          </div>
          <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 4 }}>
            {project.total_chapters_planned}
            <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 400 }}> 章</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            目标 {project.target_words.toLocaleString()} 字
          </div>
        </div>
      </div>

      {/* Project description (compact) */}
      {project.description && (
        <div className="data-card" style={{ marginTop: 12, padding: 12 }}>
          <div className="data-card-title" style={{ fontSize: 13, marginBottom: 4 }}>
            项目简介
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {project.description}
          </div>
        </div>
      )}

      {/* Context readiness (compact) */}
      <div className="data-card" style={{ marginTop: 12, padding: 12 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            marginBottom: 8,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {contextStatus?.ready ? (
              <CheckCircle2 size={14} color="#10b981" />
            ) : (
              <AlertCircle size={14} color="#f59e0b" />
            )}
            <span style={{ fontSize: 13, fontWeight: 500 }}>上下文准备度</span>
          </div>
          {contextStatus && (
            <span
              className="status-badge"
              style={{
                fontSize: 11,
                background: contextStatus.ready ? '#d1fae5' : '#fef3c7',
                color: contextStatus.ready ? '#065f46' : '#92400e',
              }}
            >
              {contextStatus.score}%
            </span>
          )}
        </div>

        {loading ? (
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>检查中…</div>
        ) : contextStatus?.ready ? (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            项目资料已满足章节生成的最低要求。
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {(contextStatus?.actions || []).map((action) => (
                <Link
                  key={`${action.label}-${action.path}`}
                  className="btn btn-secondary btn-sm"
                  to={action.path}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  <FileText size={12} />
                  {action.label}
                </Link>
              ))}
              {(contextStatus?.missing || []).length > 0 && nextActionKey !== 'generate_missing_context' && (
                <button className="btn btn-secondary btn-sm" onClick={handleAutoFill} disabled={filling || autoRunning}>
                  <Sparkles size={12} /> 让 AI 补齐缺失资料
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Missing items (compact list) */}
      {productionNext && productionNext.missing.length > 0 && (
        <div className="data-card" style={{ marginTop: 12, padding: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <AlertCircle size={14} color="#ef4444" />
            <span style={{ fontSize: 13, fontWeight: 500 }}>资料缺口</span>
            <span
              className="status-badge"
              style={{ fontSize: 11, background: '#fee2e2', color: '#991b1b', marginLeft: 'auto' }}
            >
              {productionNext.missing.length} 项
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {productionNext.missing.map((item) => (
              <div
                key={item.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '6px 8px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: 6,
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span
                    className="status-badge"
                    style={{
                      background: item.severity === 'blocking' ? '#fee2e2' : '#fef3c7',
                      color: item.severity === 'blocking' ? '#991b1b' : '#92400e',
                      fontSize: 11,
                      flexShrink: 0,
                    }}
                  >
                    {item.severity === 'blocking' ? '阻塞' : '警告'}
                  </span>
                  <span style={{ fontSize: 13, overflowWrap: 'anywhere' }}>{item.label}</span>
                </div>
                <Link
                  className="btn btn-secondary btn-sm"
                  to={item.manual_url}
                  style={{ flexShrink: 0, fontSize: 11 }}
                >
                  <Wrench size={11} /> 手动编辑
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
