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

  /* v5.5.6: Auto-run state */
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

  /* Only initialise range once so user edits are not overwritten */
  useEffect(() => {
    if (productionNext && !autoConfigInitialized.current) {
      autoConfigInitialized.current = true
      const current = productionNext.current_chapter || 1
      setAutoConfig((prev) => ({ ...prev, chapterStart: current, chapterEnd: current + 9 }))
    }
  }, [productionNext])

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

  useEffect(() => {
    load()
  }, [load])

  /* ---------------------------------------------------------------- */
  /*  Auto-fill (single entry)                                        */
  /* ---------------------------------------------------------------- */

  const handleAutoFill = async () => {
    setFilling(true)
    setFillResult('')
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
    setFilling(false)
  }

  /* ---------------------------------------------------------------- */
  /*  Execute single next step (primary action)                       */
  /* ---------------------------------------------------------------- */

  const handlePrimaryAction = async () => {
    if (!productionNext) return
    const action = productionNext.next_action

    if (action.key === 'generate_genesis' || action.key === 'review_genesis') {
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
      const ch = productionNext.current_chapter
      const res = await post<{ workflow_status: string; message: string }>('/run/chapter', {
        project_id: project.project_id,
        chapter: ch,
      })
      setFilling(false)
      if (res.ok && res.data) {
        setFillResult(res.data.message || `第 ${ch} 章生成已触发`)
      } else {
        setFillResult(res.error?.message || '生成触发失败')
      }
      navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
      return
    }

    if (action.key === 'continue_next_chapter') {
      setFilling(true)
      setFillResult('')
      const ch = action.target_chapter || productionNext.current_chapter + 1
      const res = await post<{ workflow_status: string; message: string }>('/run/chapter', {
        project_id: project.project_id,
        chapter: ch,
      })
      setFilling(false)
      if (res.ok && res.data) {
        setFillResult(res.data.message || `第 ${ch} 章生成已触发`)
      } else {
        setFillResult(res.error?.message || '生成触发失败')
      }
      navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
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
      const resetPath = action.action_url.replace(/^\/api/, '')
      const res = await post<{ message: string }>(resetPath, {})
      setFilling(false)
      if (res.ok && res.data) {
        setFillResult(res.data.message || `第 ${ch} 章已重置`)
        load()
      } else {
        setFillResult(res.error?.message || '重置失败')
      }
      navigate(`/projects/${project.project_id}?module=chapters&chapter=${ch}`)
      return
    }

    if (action.key === 'generate_arc_plan') {
      setFilling(true)
      setFillResult('')
      const nextCh = productionNext.current_chapter + 1
      const res = await post<{ planned: boolean; created: Record<string, number> }>(
        `/projects/${project.project_id}/production/arc-plan`,
        { chapter_start: nextCh, chapter_end: nextCh + 9, confirm: true }
      )
      setFilling(false)
      if (res.ok && res.data) {
        const total = Object.values(res.data.created).reduce((a, b) => a + b, 0)
        setFillResult(`已生成章节计划，新增 ${total} 项`)
        load()
      } else {
        setFillResult(res.error?.message || '计划生成失败')
      }
      return
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Auto production runner                                          */
  /* ---------------------------------------------------------------- */

  const handleRunAuto = async (dryRun: boolean = false) => {
    setAutoRunning(true)
    setAutoResult(null)
    setAutoError(null)

    const res = await post<AutoRunResponse>(`/projects/${project.project_id}/production/run-auto`, {
      max_steps: autoConfig.maxSteps,
      chapter_start: autoConfig.chapterStart,
      chapter_end: autoConfig.chapterEnd,
      stop_on_review: autoConfig.stopOnReview,
      dry_run: dryRun,
      confirm: true,
    })

    setAutoRunning(false)
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
  }

  /* ---------------------------------------------------------------- */
  /*  Derived values                                                  */
  /* ---------------------------------------------------------------- */

  const published = stats.status_counts?.published || 0
  const planned = stats.status_counts?.planned || 0
  const nextActionKey = productionNext?.next_action?.key || 'none'
  const currentCh = productionNext?.current_chapter || 1

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
          background: 'var(--bg-primary)',
          border: '1px solid var(--border-color)',
          borderRadius: 8,
          marginBottom: 20,
          overflow: 'hidden',
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
            background: 'var(--bg-secondary)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <Terminal size={18} style={{ color: 'var(--primary)', flexShrink: 0 }} />
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, whiteSpace: 'nowrap' }}>生产指挥台</h3>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 4 }}>下一步生产动作</span>
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
            {productionNext?.next_action && (
              <span
                className="status-badge"
                style={{
                  background: nextActionKey === 'none' ? '#f1f5f9' : '#dbeafe',
                  color: nextActionKey === 'none' ? '#64748b' : '#1d4ed8',
                  fontSize: 11,
                }}
              >
                {tActionKey(nextActionKey)}
              </span>
            )}
          </div>
        </div>

        {/* Body */}
        <div style={{ padding: '16px 18px' }}>
          {loading ? (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>加载生产状态中…</div>
          ) : productionNext ? (
            <>
              {/* Next action description */}
              <div
                style={{
                  fontSize: 14,
                  color: 'var(--text-secondary)',
                  lineHeight: 1.5,
                  marginBottom: 14,
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
                  style={{ flex: '1 1 140px', minWidth: 120 }}
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

                <button
                  className="btn btn-secondary"
                  onClick={() => handleRunAuto(true)}
                  disabled={autoRunning || filling}
                  style={{ flex: '0 1 auto' }}
                >
                  {autoRunning ? (
                    <>
                      <Loader2 size={14} className="spin" /> 预览中…
                    </>
                  ) : (
                    <>
                      <Sparkles size={14} /> 预览自动生产
                    </>
                  )}
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={() => handleRunAuto(false)}
                  disabled={autoRunning || filling}
                  style={{ flex: '0 1 auto' }}
                >
                  {autoRunning ? (
                    <>
                      <Loader2 size={14} className="spin" /> 运行中…
                    </>
                  ) : (
                    <>
                      <Play size={14} /> 开始自动生产
                    </>
                  )}
                </button>
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
                  display: 'flex',
                  gap: 16,
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  padding: '10px 12px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: 6,
                  marginBottom: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
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
                      padding: '3px 6px',
                      fontSize: 12,
                      borderRadius: 4,
                      border: '1px solid var(--border-color)',
                      background: 'var(--bg-primary)',
                    }}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
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
                      padding: '3px 6px',
                      fontSize: 12,
                      borderRadius: 4,
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
                      padding: '3px 6px',
                      fontSize: 12,
                      borderRadius: 4,
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
              {autoResult && (
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
                      {autoResult.status === 'completed' && <CheckCircle2 size={14} color="#10b981" />}
                      {autoResult.status === 'failed' && <XCircle size={14} color="#ef4444" />}
                      {autoResult.status === 'dry_run' && <Sparkles size={14} color="#06b6d4" />}
                      {autoResult.status === 'stopped' && <AlertCircle size={14} color="#f59e0b" />}
                      {autoResult.status !== 'completed' && autoResult.status !== 'failed' && autoResult.status !== 'dry_run' && autoResult.status !== 'stopped' && (
                        <AlertCircle size={14} color="#f59e0b" />
                      )}
                      <span style={{ fontSize: 13, fontWeight: 500 }}>
                        {autoResult.status === 'completed'
                          ? '已完成'
                          : autoResult.status === 'failed'
                          ? '失败'
                          : autoResult.status === 'dry_run'
                          ? '预览结果'
                          : '已停止'}
                      </span>
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      停止原因: {tStopReason(autoResult.stop_reason)}
                    </span>
                  </div>

                  {/* Steps timeline */}
                  {autoResult.steps.length > 0 && (
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 6,
                        maxHeight: 240,
                        overflowY: 'auto',
                      }}
                    >
                      {autoResult.steps.map((step, idx) => (
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
                                    : '#fef3c7',
                                color:
                                  step.result === 'success'
                                    ? '#065f46'
                                    : step.result === 'failed'
                                    ? '#991b1b'
                                    : step.result === 'skipped'
                                    ? '#64748b'
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
                        </div>
                      ))}
                    </div>
                  )}

                  {autoResult.chapters_touched.length > 0 && (
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
              {(contextStatus?.missing || []).length > 0 && (
                <button className="btn btn-primary btn-sm" onClick={handleAutoFill} disabled={filling || autoRunning}>
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

          <div style={{ marginTop: 10 }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleAutoFill}
              disabled={filling || autoRunning}
              style={{ fontSize: 12 }}
            >
              <Sparkles size={12} /> AI 补齐全部缺失资料
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
