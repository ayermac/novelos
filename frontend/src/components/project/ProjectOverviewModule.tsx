import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, BookOpen, CheckCircle2, FileText, Sparkles, Wrench, ArrowRight, Loader2, Play, Settings } from 'lucide-react'
import { get, post } from '../../lib/api'

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

interface Props {
  project: ProjectSummary
  stats: WorkspaceStats
  chapterNumber?: number
}

export default function ProjectOverviewModule({ project, stats, chapterNumber }: Props) {
  const navigate = useNavigate()
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(null)
  const [productionNext, setProductionNext] = useState<ProductionNext | null>(null)
  const [loading, setLoading] = useState(true)
  const [filling, setFilling] = useState(false)
  const [fillResult, setFillResult] = useState<string>('')
  
  // v5.5.5: Auto production state
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoResult, setAutoResult] = useState<{
    status: string
    steps: Array<{
      step: number
      action: string
      label: string
      target_chapter?: number
      result: string
      warnings?: string[]
      error?: string
    }>
    stop_reason: string
    chapters_touched: number[]
  } | null>(null)
  const [autoConfig, setAutoConfig] = useState({
    maxSteps: 5,
    chapterStart: 1,
    chapterEnd: 10,
    stopOnReview: true,
  })

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

  useEffect(() => { load() }, [load])

  const handleAutoFill = async () => {
    setFilling(true)
    setFillResult('')
    const currentCh = productionNext?.current_chapter || 1
    const res = await post<{ filled: boolean; created: Record<string, number>; warnings: string[] }>(
      `/projects/${project.project_id}/production/auto-fill`,
      { scope: 'missing_context', chapter_start: currentCh, chapter_end: currentCh + 9, confirm: true }
    )
    if (res.ok && res.data) {
      const created = res.data.created
      const total = Object.values(created).reduce((a, b) => a + b, 0)
      setFillResult(`已自动补齐 ${total} 项资料`)
      load()
    } else {
      setFillResult(res.error?.message || '补齐失败')
    }
    setFilling(false)
  }

  const handlePrimaryAction = async () => {
    if (!productionNext) return
    const action = productionNext.next_action
    if (action.key === 'generate_genesis') {
      navigate(`/projects/${project.project_id}?module=genesis`)
      return
    }
    if (action.key === 'review_genesis') {
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
      const res = await post<{ workflow_status: string; message: string }>(
        '/run/chapter',
        { project_id: project.project_id, chapter: ch }
      )
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
      const res = await post<{ workflow_status: string; message: string }>(
        '/run/chapter',
        { project_id: project.project_id, chapter: ch }
      )
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
      if (res.ok && res.data) {
        const created = res.data.created
        const total = Object.values(created).reduce((a, b) => a + b, 0)
        setFillResult(`已生成章节计划，新增 ${total} 项`)
        load()
      } else {
        setFillResult(res.error?.message || '计划生成失败')
      }
      setFilling(false)
      return
    }
  }

  // v5.5.5: Auto production runner
  const handleRunAuto = async (dryRun: boolean = false) => {
    setAutoRunning(true)
    setAutoResult(null)
    
    const res = await post<{
      status: string
      steps: Array<{
        step: number
        action: string
        label: string
        target_chapter?: number
        result: string
        warnings?: string[]
        error?: string
      }>
      stop_reason: string
      chapters_touched: number[]
    }>(
      `/projects/${project.project_id}/production/run-auto`,
      {
        max_steps: autoConfig.maxSteps,
        chapter_start: autoConfig.chapterStart,
        chapter_end: autoConfig.chapterEnd,
        stop_on_review: autoConfig.stopOnReview,
        dry_run: dryRun,
        confirm: true,
      }
    )
    
    setAutoRunning(false)
    if (res.ok && res.data) {
      setAutoResult(res.data)
      if (!dryRun && res.data.status !== 'failed') {
        load() // Refresh production-next
      }
    } else {
      setAutoResult({
        status: 'failed',
        steps: [],
        stop_reason: res.error?.message || '运行失败',
        chapters_touched: [],
      })
    }
  }

  const published = stats.status_counts?.published || 0
  const planned = stats.status_counts?.planned || 0

  const actionColor = (key: string) => {
    if (key === 'generate_genesis' || key === 'generate_missing_context' || key === 'generate_arc_plan') return 'btn-primary'
    if (key === 'recover_blocked_run') return 'btn-danger'
    if (key === 'review_chapter' || key === 'review_genesis') return 'btn-secondary'
    return 'btn-primary'
  }

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><BookOpen size={18} /> 项目总览</h3>
      </div>

      {/* Production Next Panel */}
      <div className="data-card" style={{ marginBottom: 16, borderLeft: '4px solid var(--primary)' }}>
        <div className="data-card-header">
          <Sparkles size={18} style={{ color: 'var(--primary)' }} />
          <div className="data-card-title" style={{ marginBottom: 0 }}>下一步生产动作</div>
        </div>

        {loading ? (
          <div className="data-card-content">检查中...</div>
        ) : productionNext ? (
          <>
            <div className="data-card-content" style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)' }}>
              {productionNext.next_action.label}
            </div>
            <div className="data-card-content">
              {productionNext.next_action.description}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <button
                className={`btn ${actionColor(productionNext.next_action.key)}`}
                onClick={handlePrimaryAction}
                disabled={filling || productionNext.next_action.key === 'none'}
              >
                {filling ? <><Loader2 size={14} className="spin" /> 处理中...</> : <><ArrowRight size={14} /> {productionNext.next_action.label}</>}
              </button>
              {productionNext.next_action.key !== 'generate_genesis' && !productionNext.health.has_approved_genesis && (
                <Link className="btn btn-secondary btn-sm" to={`/projects/${project.project_id}?module=genesis`}>
                  去创世
                </Link>
              )}
            </div>
            {fillResult && (
              <div style={{ marginTop: 10, fontSize: 13, color: fillResult.includes('失败') ? '#dc2626' : '#16a34a' }}>
                {fillResult}
              </div>
            )}
          </>
        ) : (
          <div className="data-card-content">无法获取生产建议</div>
        )}
      </div>

      <div className="data-grid">
        <div className="data-card">
          <div className="data-card-title">项目简介</div>
          <div className="data-card-content">
            {project.description || '尚未填写项目简介。'}
          </div>
          {!project.description && (
            <Link className="btn btn-secondary btn-sm" to={`/projects/${project.project_id}?module=settings`}>
              填写简介
            </Link>
          )}
        </div>

        <div className="data-card">
          <div className="data-card-title">章节进度</div>
          <div className="data-card-content">
            已发布 {published} 章，已规划 {planned} 章，共 {stats.total_chapters} 个章节槽位。
          </div>
          <div className="data-card-traits">当前字数：{stats.total_words.toLocaleString()}</div>
        </div>

        <div className="data-card">
          <div className="data-card-title">创作目标</div>
          <div className="data-card-content">
            预计 {project.total_chapters_planned} 章，目标 {project.target_words.toLocaleString()} 字。
          </div>
        </div>
      </div>

      {/* Health / Missing Items */}
      {productionNext && productionNext.missing.length > 0 && (
        <div className="data-card" style={{ marginTop: 16 }}>
          <div className="data-card-header">
            <AlertCircle size={18} style={{ color: '#dc2626' }} />
            <div className="data-card-title" style={{ marginBottom: 0 }}>资料缺口</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {productionNext.missing.map((item) => (
              <div key={item.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '8px 10px', background: 'var(--bg-tertiary)', borderRadius: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="status-badge" style={{ background: item.severity === 'blocking' ? '#fee2e2' : '#fef3c7', color: item.severity === 'blocking' ? '#991b1b' : '#92400e' }}>
                    {item.severity === 'blocking' ? '阻塞' : '警告'}
                  </span>
                  <span style={{ fontSize: 14 }}>{item.label}</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <Link className="btn btn-secondary btn-sm" to={item.manual_url}>
                    <Wrench size={12} /> 手动编辑
                  </Link>
                  <button className="btn btn-primary btn-sm" onClick={handleAutoFill} disabled={filling}>
                    <Sparkles size={12} /> {item.ai_action.label}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Context Readiness (legacy) */}
      <div className="data-card" style={{ marginTop: 16 }}>
        <div className="data-card-header">
          {contextStatus?.ready ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <div className="data-card-title" style={{ marginBottom: 0 }}>上下文准备度</div>
          {contextStatus && <span className="data-card-badge">{contextStatus.score}%</span>}
        </div>

        {loading ? (
          <div className="data-card-content">检查中...</div>
        ) : contextStatus?.ready ? (
          <div className="data-card-content">项目资料已满足章节生成的最低要求。</div>
        ) : (
          <>
            <div className="data-card-content">
              生成前还需要补齐这些资料：
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, maxWidth: '100%', overflow: 'hidden' }}>
              {(contextStatus?.actions || []).map((action) => (
                <Link key={`${action.label}-${action.path}`} className="btn btn-secondary btn-sm" to={action.path} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <FileText size={14} />
                  {action.label}
                </Link>
              ))}
              {(contextStatus?.missing || []).length > 0 && (
                <button className="btn btn-primary btn-sm" onClick={handleAutoFill} disabled={filling}>
                  <Sparkles size={14} /> 让 AI 补齐缺失资料
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {/* v5.5.5: Auto Production Console */}
      <div className="data-card" style={{ marginTop: 16, borderLeft: '4px solid #8b5cf6' }}>
        <div className="data-card-header">
          <Play size={18} style={{ color: '#8b5cf6' }} />
          <div className="data-card-title" style={{ marginBottom: 0 }}>自动生产控制台</div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Config */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Settings size={14} />
              <label style={{ fontSize: 13 }}>最大步数:</label>
              <input
                type="number"
                min="1"
                max="50"
                value={autoConfig.maxSteps}
                onChange={(e) => setAutoConfig({ ...autoConfig, maxSteps: parseInt(e.target.value) || 5 })}
                style={{ width: 60, padding: '4px 8px', borderRadius: 4, border: '1px solid var(--border)' }}
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <label style={{ fontSize: 13 }}>章节范围:</label>
              <input
                type="number"
                min="1"
                value={autoConfig.chapterStart}
                onChange={(e) => setAutoConfig({ ...autoConfig, chapterStart: parseInt(e.target.value) || 1 })}
                style={{ width: 50, padding: '4px 8px', borderRadius: 4, border: '1px solid var(--border)' }}
              />
              <span style={{ fontSize: 13 }}>-</span>
              <input
                type="number"
                min="1"
                value={autoConfig.chapterEnd}
                onChange={(e) => setAutoConfig({ ...autoConfig, chapterEnd: parseInt(e.target.value) || 10 })}
                style={{ width: 50, padding: '4px 8px', borderRadius: 4, border: '1px solid var(--border)' }}
              />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
              <input
                type="checkbox"
                checked={autoConfig.stopOnReview}
                onChange={(e) => setAutoConfig({ ...autoConfig, stopOnReview: e.target.checked })}
              />
              遇审核停止
            </label>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn-secondary"
              onClick={() => handleRunAuto(true)}
              disabled={autoRunning}
            >
              {autoRunning ? <><Loader2 size={14} className="spin" /> 预览中...</> : '预览步骤'}
            </button>
            <button
              className="btn btn-primary"
              onClick={() => handleRunAuto(false)}
              disabled={autoRunning}
            >
              {autoRunning ? <><Loader2 size={14} className="spin" /> 运行中...</> : <><Play size={14} /> 开始自动生产</>}
            </button>
          </div>

          {/* Result */}
          {autoResult && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 13, marginBottom: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>
                  状态: <strong style={{ color: autoResult.status === 'completed' ? '#16a34a' : autoResult.status === 'failed' ? '#dc2626' : '#f59e0b' }}>
                    {autoResult.status === 'completed' ? '已完成' : autoResult.status === 'failed' ? '失败' : autoResult.status === 'dry_run' ? '预览' : '已停止'}
                  </strong>
                </span>
                <span style={{ color: 'var(--text-secondary)' }}>
                  停止原因: {autoResult.stop_reason}
                </span>
              </div>

              {/* Steps Timeline */}
              {autoResult.steps.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
                  {autoResult.steps.map((step, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '8px 10px',
                        background: 'var(--bg-tertiary)',
                        borderRadius: 6,
                        borderLeft: `3px solid ${step.result === 'success' ? '#16a34a' : step.result === 'failed' ? '#dc2626' : '#f59e0b'}`,
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 500 }}>
                        步骤 {step.step}: {step.label}
                        {step.target_chapter && <span style={{ color: 'var(--text-secondary)', marginLeft: 6 }}>第 {step.target_chapter} 章</span>}
                      </div>
                      {step.error && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>{step.error}</div>}
                      {step.warnings && step.warnings.length > 0 && (
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                          {step.warnings.join('; ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {autoResult.chapters_touched.length > 0 && (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 8 }}>
                  涉及章节: {autoResult.chapters_touched.join(', ')}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
