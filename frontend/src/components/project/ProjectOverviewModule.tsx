import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, BookOpen, CheckCircle2, FileText, Sparkles, Wrench, ArrowRight, Loader2 } from 'lucide-react'
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
      const res = await post<{ message: string }>(action.action_url, {})
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
    </div>
  )
}
