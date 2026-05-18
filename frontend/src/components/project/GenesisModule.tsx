import { useState, useEffect, useCallback } from 'react'
import { get, post } from '../../lib/api'
import { Sparkles, CheckCircle2, XCircle, Loader2, RotateCcw } from 'lucide-react'
import { FormField, NumberInput, TextArea, TextInput } from '../ui'

interface GenesisRun {
  id: string
  project_id: string
  status: string
  input_json: string
  draft_json: string | null
  error_message: string | null
  created_at: string
  updated_at: string
  quality_report?: QualityReport
}

interface QualityIssue {
  code: string
  severity: 'blocker' | 'warning' | 'advisory'
  message: string
  section: string
  item_ref?: string
  suggestion?: string
}

interface QualityReport {
  passed: boolean
  score: number
  quality_status: 'pass' | 'warning' | 'blocked' | 'scaffold_fallback'
  issues: QualityIssue[]
  metrics: Record<string, number>
}

interface DraftData {
  project_updates?: { description?: string }
  world_settings?: Array<{ title: string; category: string; content: string }>
  characters?: Array<{ name: string; role: string; description: string; traits: string }>
  factions?: Array<{ name: string; type: string; description: string }>
  outlines?: Array<{ chapters_range: string; title: string; content: string }>
  plot_holes?: Array<{ code: string; type: string; title: string; description: string }>
  instructions?: Array<{ chapter_number: number; objective: string; key_events: string }>
}

interface DraftPreview {
  draft: DraftData | null
  rawText: string
  invalid: boolean
  empty: boolean
  incomplete: boolean
  missingRequiredSections: string[]
}

type DraftArrayItem<K extends keyof DraftData> = NonNullable<DraftData[K]> extends Array<infer T> ? T : never

const REQUIRED_DRAFT_LABELS = ['项目简介', '世界观设定', '角色', '势力/组织', '大纲', '伏笔/悬念', '章节指令']

const REQUIRED_DRAFT_SECTIONS: Array<[keyof DraftData, string]> = [
  ['world_settings', '世界观设定'],
  ['characters', '角色'],
  ['factions', '势力/组织'],
  ['outlines', '大纲'],
  ['plot_holes', '伏笔/悬念'],
  ['instructions', '章节指令'],
]

const normalizeDraftValue = (value: unknown): DraftData | null => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as DraftData
  }
  if (!Array.isArray(value)) return null

  const draft: DraftData = {}
  value.forEach((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return
    const record = item as Record<string, unknown>
    if ('title' in record && 'category' in record && 'content' in record) {
      draft.world_settings = [...(draft.world_settings || []), item as DraftArrayItem<'world_settings'>]
    } else if ('chapter_number' in record) {
      draft.instructions = [...(draft.instructions || []), item as DraftArrayItem<'instructions'>]
    } else if ('chapters_range' in record || ('level' in record && 'sequence' in record && 'content' in record)) {
      draft.outlines = [...(draft.outlines || []), item as DraftArrayItem<'outlines'>]
    } else if ('code' in record) {
      draft.plot_holes = [...(draft.plot_holes || []), item as DraftArrayItem<'plot_holes'>]
    } else if ('relationship_with_protagonist' in record || ('name' in record && 'type' in record)) {
      draft.factions = [...(draft.factions || []), item as DraftArrayItem<'factions'>]
    } else if ('name' in record) {
      draft.characters = [...(draft.characters || []), item as DraftArrayItem<'characters'>]
    }
  })

  return Object.keys(draft).length > 0 ? draft : null
}

interface Props {
  projectId: string
  project?: {
    name?: string
    genre?: string
    description?: string
    target_words?: number
    total_chapters_planned?: number
  }
}

export default function GenesisModule({ projectId, project }: Props) {
  const [genesis, setGenesis] = useState<GenesisRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [approving, setApproving] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [showRejectConfirm, setShowRejectConfirm] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [formErrors, setFormErrors] = useState<Record<string, string>>({})
  const [form, setForm] = useState({
    title: '',
    genre: '',
    premise: '',
    target_chapters: 10,
    target_words: 30000,
    target_audience: '',
    style_preference: '',
    constraints: '',
  })
  const [showForm, setShowForm] = useState(false)
  const projectTitle = (project?.name || form.title).trim()
  const projectGenre = (project?.genre || form.genre).trim()

  const loadGenesis = useCallback(async () => {
    setLoading(true)
    const res = await get(`/projects/${projectId}/genesis/latest`)
    if (res.ok && res.data) {
      setGenesis(res.data as GenesisRun)
    } else {
      setGenesis(null)
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => { loadGenesis() }, [loadGenesis])

  useEffect(() => {
    if (!project) return
    setForm((prev) => ({
      ...prev,
      title: project.name || prev.title,
      genre: project.genre || prev.genre,
      premise: prev.premise || project.description || '',
    }))
  }, [project?.name, project?.genre, project?.description]) // eslint-disable-line react-hooks/exhaustive-deps

  const validateForm = () => {
    const errors: Record<string, string> = {}
    if (!projectTitle) errors.title = '项目标题缺失，请先在项目设置中补齐'
    if (!projectGenre) errors.genre = '作品类型缺失，请先在项目设置中补齐'
    // v6.3: premise is now optional — AI can generate it from title + genre + description
    if (!Number.isFinite(form.target_chapters) || form.target_chapters < 1) errors.target_chapters = '首批规划章数必须大于 0'
    if (!Number.isFinite(form.target_words) || form.target_words < 1) errors.target_words = '首批规划字数必须大于 0'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleGenerate = async () => {
    if (!validateForm()) {
      setErrorMsg('请先补齐创世设定的必要信息')
      return
    }
    setGenerating(true)
    setErrorMsg('')
    const res = await post('/genesis/generate', {
      ...form,
      title: projectTitle,
      genre: projectGenre,
      premise: form.premise.trim(),
      project_id: projectId,
    })
    if (res.ok) {
      setGenesis(res.data as GenesisRun)
      setShowForm(false)
    } else {
      setErrorMsg(res.error?.message || '生成失败')
    }
    setGenerating(false)
  }

  const handleApprove = async () => {
    if (!genesis) return
    setApproving(true)
    setErrorMsg('')
    const res = await post('/genesis/approve', { project_id: projectId, genesis_id: genesis.id })
    if (res.ok) {
      loadGenesis()
    } else {
      setErrorMsg(res.error?.message || '批准失败')
    }
    setApproving(false)
  }

  const handleReject = async () => {
    if (!genesis) return
    setRejecting(true)
    setErrorMsg('')
    const res = await post('/genesis/reject', { project_id: projectId, genesis_id: genesis.id })
    if (res.ok) {
      setShowRejectConfirm(false)
      loadGenesis()
    } else {
      setErrorMsg(res.error?.message || '拒绝失败')
    }
    setRejecting(false)
  }

  const parseDraft = (): DraftPreview => {
    if (!genesis?.draft_json) {
      return {
        draft: null,
        rawText: '',
        invalid: true,
        empty: true,
        incomplete: true,
        missingRequiredSections: REQUIRED_DRAFT_LABELS,
      }
    }

    let value: unknown = genesis.draft_json
    for (let i = 0; i < 2; i += 1) {
      if (typeof value !== 'string') break
      try {
        value = JSON.parse(value)
      } catch {
        return {
          draft: null,
          rawText: genesis.draft_json,
          invalid: true,
          empty: true,
          incomplete: true,
          missingRequiredSections: REQUIRED_DRAFT_LABELS,
        }
      }
    }

    const draft = normalizeDraftValue(value)
    if (!draft) {
      return {
        draft: null,
        rawText: typeof value === 'string' ? value : genesis.draft_json,
        invalid: true,
        empty: true,
        incomplete: true,
        missingRequiredSections: REQUIRED_DRAFT_LABELS,
      }
    }

    const missingRequiredSections = [
      ...(!draft.project_updates?.description?.trim() ? ['项目简介'] : []),
      ...REQUIRED_DRAFT_SECTIONS
      .filter(([key]) => {
        const section = draft[key]
        return !Array.isArray(section) || section.length === 0
      })
      .map(([, label]) => label),
    ]
    const empty = !(
      draft.project_updates?.description ||
      draft.world_settings?.length ||
      draft.characters?.length ||
      draft.factions?.length ||
      draft.outlines?.length ||
      draft.plot_holes?.length ||
      draft.instructions?.length
    )
    return {
      draft,
      rawText: JSON.stringify(draft, null, 2),
      invalid: false,
      empty,
      incomplete: missingRequiredSections.length > 0,
      missingRequiredSections,
    }
  }

  const statusLabel = (status: string) => {
    switch (status) {
      case 'running': return '生成中...'
      case 'generated': return '待审批'
      case 'approved': return '已批准'
      case 'rejected': return '已拒绝'
      case 'failed': return '生成失败'
      default: return status
    }
  }

  const statusClass = (status: string) => {
    switch (status) {
      case 'running': return 'status-running'
      case 'generated': return 'status-pending'
      case 'approved': return 'status-approved'
      case 'rejected': return 'status-rejected'
      case 'failed': return 'status-failed'
      default: return ''
    }
  }

  const qualityStatusLabel = (status: string) => {
    switch (status) {
      case 'pass': return '质量通过'
      case 'warning': return '质量警告'
      case 'blocked': return '质量阻塞'
      case 'scaffold_fallback': return '兜底模板'
      default: return status
    }
  }

  const qualityStatusClass = (status: string) => {
    switch (status) {
      case 'pass': return 'quality-pass'
      case 'warning': return 'quality-warning'
      case 'blocked': return 'quality-blocked'
      case 'scaffold_fallback': return 'quality-scaffold'
      default: return ''
    }
  }

  if (loading) return <div className="module-loading">加载中...</div>

  const draftPreview = parseDraft()
  const draft = draftPreview.draft
  const canGenerate = !genesis || genesis.status === 'approved' || genesis.status === 'rejected' || genesis.status === 'failed'

  // v6.6.3: Check quality gate
  const qualityBlocked = genesis?.quality_report && !genesis.quality_report.passed
  const isScaffold = genesis?.quality_report?.quality_status === 'scaffold_fallback'

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Sparkles size={18} /> 项目初始化（创世）</h3>
        {canGenerate && (
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setShowForm(!showForm)}
          >
            <RotateCcw size={14} /> 重新生成
          </button>
        )}
      </div>

      {/* Generate form */}
      {showForm && (
        <div className="genesis-form">
          <div className="genesis-scope-note">
            创世会生成整本书底盘设定；这里设置的是首批展开到章节指令的范围，不代表整本书总章数。
          </div>
          <div className="genesis-project-context">
            <div className="context-intro">
              <span className="context-label">已继承项目基础信息</span>
              <strong>创建小说时填写的标题、类型和全书规模会直接用于创世</strong>
            </div>
            <div>
              <span className="context-label">项目标题</span>
              <strong>{projectTitle || '未填写'}</strong>
            </div>
            <div>
              <span className="context-label">作品类型</span>
              <strong>{projectGenre || '未填写'}</strong>
            </div>
            {project?.total_chapters_planned || project?.target_words ? (
              <div>
                <span className="context-label">全书规模</span>
                <strong>
                  {project.total_chapters_planned ? `${project.total_chapters_planned} 章` : '章数未设'}
                  {project.target_words ? ` / 约 ${project.target_words.toLocaleString('zh-CN')} 字` : ''}
                </strong>
              </div>
            ) : null}
          </div>
          {(formErrors.title || formErrors.genre) && (
            <div className="genesis-error">
              <XCircle size={16} /> {formErrors.title || formErrors.genre}
            </div>
          )}
          <div className="form-grid">
            <FormField label="创意/前提" helper="可留空，AI 会根据书名和类型自动推断故事前提" error={formErrors.premise} className="form-full">
              <TextArea
                value={form.premise}
                onChange={(e) => {
                  setForm({ ...form, premise: e.target.value })
                  if (formErrors.premise) setFormErrors({ ...formErrors, premise: '' })
                }}
                placeholder="描述你的故事核心创意（可选，留空让 AI 自动推断）..."
                rows={3}
              />
            </FormField>
            <FormField
              label="首批规划章数"
              helper="用于生成前 N 章章节指令，后续可继续通过章节批次规划扩展。"
              required
              error={formErrors.target_chapters}
            >
              <NumberInput
                value={form.target_chapters}
                min={1}
                onChange={(e) => {
                  setForm({ ...form, target_chapters: Number(e.target.value) })
                  if (formErrors.target_chapters) setFormErrors({ ...formErrors, target_chapters: '' })
                }}
              />
            </FormField>
            <FormField
              label="首批规划字数"
              helper="用于估算首批章节的单章字数，不是全书总字数。"
              required
              error={formErrors.target_words}
            >
              <NumberInput
                value={form.target_words}
                min={1}
                onChange={(e) => {
                  setForm({ ...form, target_words: Number(e.target.value) })
                  if (formErrors.target_words) setFormErrors({ ...formErrors, target_words: '' })
                }}
              />
            </FormField>
            <FormField label="目标读者">
              <TextInput
                value={form.target_audience}
                onChange={(e) => setForm({ ...form, target_audience: e.target.value })}
                placeholder="男频、女频、全年龄..."
              />
            </FormField>
            <FormField label="风格偏好">
              <TextInput
                value={form.style_preference}
                onChange={(e) => setForm({ ...form, style_preference: e.target.value })}
                placeholder="轻松、严肃、热血..."
              />
            </FormField>
          </div>
          {errorMsg && (
            <div className="genesis-error" style={{ marginTop: 12 }}>
              <XCircle size={16} /> {errorMsg}
            </div>
          )}
          <div className="form-actions">
            <button className="btn btn-secondary" onClick={() => { setShowForm(false); setErrorMsg(''); setFormErrors({}) }}>取消</button>
            <button className="btn btn-primary" onClick={handleGenerate} disabled={generating}>
              {generating ? <><Loader2 size={14} className="spin" /> 生成中...</> : <><Sparkles size={14} /> 生成创世设定</>}
            </button>
          </div>
        </div>
      )}

      {/* No genesis yet */}
      {!genesis && !showForm && (
        <div className="data-empty">
          <div className="data-empty-icon"><Sparkles size={32} /></div>
          <div className="data-empty-title">项目初始化</div>
          <div className="data-empty-desc">创世只需一次，生成整本书的底盘设定（世界观、角色、大纲等）。<br />表单里的章数只决定首批展开范围，后续章节通过「章节批次规划」延续。</div>
          <button className="btn btn-primary" onClick={() => setShowForm(true)} style={{ marginTop: 12 }}>
            <Sparkles size={14} /> 生成项目设定
          </button>
        </div>
      )}

      {/* Genesis status */}
      {genesis && (
        <div className="genesis-result">
          <div className="genesis-status-bar">
            <span className={`genesis-status ${statusClass(genesis.status)}`}>
              {statusLabel(genesis.status)}
            </span>
            <span className="genesis-time">{new Date(genesis.created_at).toLocaleString('zh-CN')}</span>
          </div>

          {/* Error */}
          {genesis.status === 'failed' && genesis.error_message && (
            <div className="genesis-error">
              <XCircle size={16} /> {genesis.error_message}
            </div>
          )}

          {/* Running */}
          {genesis.status === 'running' && (
            <div className="genesis-running">
              <Loader2 size={20} className="spin" /> AI 正在生成项目设定，请稍候...
            </div>
          )}

          {/* Draft preview */}
          {genesis.status === 'generated' && (
            <>
              {/* v6.6.3: Quality report */}
              {genesis.quality_report && (
                <div className={`genesis-quality-report ${qualityStatusClass(genesis.quality_report.quality_status)}`}>
                  <div className="quality-header">
                    <span className="quality-status">{qualityStatusLabel(genesis.quality_report.quality_status)}</span>
                    <span className="quality-score">评分: {genesis.quality_report.score.toFixed(0)}</span>
                  </div>
                  {genesis.quality_report.quality_status === 'scaffold_fallback' && (
                    <div className="quality-scaffold-warning">
                      当前草案包含兜底模板内容，不建议批准。请重新生成或人工补全。
                    </div>
                  )}
                  {genesis.quality_report.issues.length > 0 && (
                    <div className="quality-issues">
                      {genesis.quality_report.issues.map((issue, i) => (
                        <div key={i} className={`quality-issue issue-${issue.severity}`}>
                          <span className="issue-severity">
                            {issue.severity === 'blocker' ? '阻塞' : issue.severity === 'warning' ? '警告' : '建议'}
                          </span>
                          <span className="issue-message">{issue.message}</span>
                          {issue.suggestion && <span className="issue-suggestion">{issue.suggestion}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="genesis-draft">
                {draftPreview.invalid && (
                  <div className="draft-empty draft-invalid">
                    <XCircle size={16} />
                    <div>
                      <strong>创世草案格式异常，无法应用</strong>
                      <p>请拒绝当前草案后重新生成。系统不会把异常草案写入正式设定。</p>
                    </div>
                  </div>
                )}

                {!draftPreview.invalid && draftPreview.empty && (
                  <div className="draft-empty">
                    <Sparkles size={16} />
                    <div>
                      <strong>创世草案没有可应用内容</strong>
                      <p>请拒绝当前草案后重新生成，或补充项目标题、类型和创意后再次生成。</p>
                    </div>
                  </div>
                )}

                {!draftPreview.invalid && !draftPreview.empty && draftPreview.incomplete && (
                  <div className="draft-empty draft-invalid">
                    <XCircle size={16} />
                    <div>
                      <strong>创世草案不完整，不能应用</strong>
                      <p>缺少：{draftPreview.missingRequiredSections.join('、')}。请拒绝当前草案后重新生成。</p>
                    </div>
                  </div>
                )}

                {draft?.project_updates?.description && (
                  <div className="draft-section">
                    <h4>项目描述</h4>
                    <p>{draft.project_updates.description}</p>
                  </div>
                )}

                {draft?.world_settings && draft.world_settings.length > 0 && (
                  <div className="draft-section">
                    <h4>世界观设定 ({draft.world_settings.length})</h4>
                    <ul>
                      {draft.world_settings.map((ws, i) => (
                        <li key={i}><strong>[{ws.category}] {ws.title}</strong>: {ws.content}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft?.characters && draft.characters.length > 0 && (
                  <div className="draft-section">
                    <h4>角色 ({draft.characters.length})</h4>
                    <ul>
                      {draft.characters.map((c, i) => (
                        <li key={i}><strong>{c.name}</strong> ({c.role}): {c.description}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft?.factions && draft.factions.length > 0 && (
                  <div className="draft-section">
                    <h4>势力 ({draft.factions.length})</h4>
                    <ul>
                      {draft.factions.map((f, i) => (
                        <li key={i}><strong>{f.name}</strong> ({f.type}): {f.description}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft?.outlines && draft.outlines.length > 0 && (
                  <div className="draft-section">
                    <h4>大纲 ({draft.outlines.length})</h4>
                    <ul>
                      {draft.outlines.map((o, i) => (
                        <li key={i}><strong>第{o.chapters_range}章 {o.title}</strong>: {o.content}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft?.plot_holes && draft.plot_holes.length > 0 && (
                  <div className="draft-section">
                    <h4>伏笔/悬念 ({draft.plot_holes.length})</h4>
                    <ul>
                      {draft.plot_holes.map((ph, i) => (
                        <li key={i}><strong>[{ph.type}] {ph.title}</strong>: {ph.description}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft?.instructions && draft.instructions.length > 0 && (
                  <div className="draft-section">
                    <h4>章节指令 ({draft.instructions.length})</h4>
                    <ul>
                      {draft.instructions.map((inst, i) => (
                        <li key={i}><strong>第{inst.chapter_number}章</strong>: {inst.objective}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {(draftPreview.invalid || draftPreview.empty) && draftPreview.rawText && (
                  <details className="draft-raw">
                    <summary>查看原始草案</summary>
                    <pre>{draftPreview.rawText}</pre>
                  </details>
                )}
              </div>

              <div className="genesis-actions">
                {errorMsg && (
                  <div className="genesis-action-error"><XCircle size={14} /> {errorMsg}</div>
                )}
                {showRejectConfirm ? (
                  <div className="genesis-reject-confirm">
                    <span>确定拒绝此创世草案？</span>
                    <button className="btn btn-secondary btn-sm" onClick={() => setShowRejectConfirm(false)}>取消</button>
                    <button className="btn btn-danger btn-sm" onClick={handleReject} disabled={rejecting}>
                      {rejecting ? <><Loader2 size={14} className="spin" /> 处理中...</> : '确认拒绝'}
                    </button>
                  </div>
                ) : (
                  <>
                    <button className="btn btn-danger" onClick={() => setShowRejectConfirm(true)}>
                      <XCircle size={14} /> 拒绝
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={handleApprove}
                      disabled={approving || draftPreview.invalid || draftPreview.empty || draftPreview.incomplete || qualityBlocked}
                      title={qualityBlocked ? '质量门未通过，无法批准' : ''}
                    >
                      {approving ? <><Loader2 size={14} className="spin" /> 应用中...</> : <><CheckCircle2 size={14} /> 批准并应用</>}
                    </button>
                    {qualityBlocked && !isScaffold && (
                      <span className="quality-block-hint">草案存在质量问题，请重新生成</span>
                    )}
                    {isScaffold && (
                      <span className="quality-block-hint">兜底模板不建议直接批准</span>
                    )}
                  </>
                )}
              </div>
            </>
          )}

          {/* Approved */}
          {genesis.status === 'approved' && (
            <div className="genesis-approved">
              <CheckCircle2 size={20} /> 项目设定已批准并应用到正式表。
              {canGenerate && (
                <button className="btn btn-secondary btn-sm" onClick={() => setShowForm(true)} style={{ marginLeft: 12 }}>
                  重新生成
                </button>
              )}
            </div>
          )}
        </div>
      )}

      <style>{`
        .genesis-form {
          background: var(--bg-secondary, #f9fafb);
          border: 1px solid var(--border, #e5e7eb);
          border-radius: 8px;
          padding: 20px;
          margin-bottom: 16px;
        }
        .genesis-scope-note {
          margin-bottom: 14px;
          padding: 10px 12px;
          border: 1px solid var(--border, #e5e7eb);
          border-radius: 6px;
          background: var(--bg-primary, #fff);
          color: var(--text-secondary, #4b5563);
          font-size: 13px;
          line-height: 1.6;
        }
        .genesis-project-context {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
          margin-bottom: 14px;
        }
        .genesis-project-context > div {
          min-width: 0;
          padding: 10px 12px;
          border: 1px solid var(--border, #e5e7eb);
          border-radius: 6px;
          background: var(--bg-primary, #fff);
        }
        .context-label {
          display: block;
          margin-bottom: 4px;
          color: var(--text-muted, #6b7280);
          font-size: 12px;
        }
        .genesis-project-context .context-intro {
          grid-column: 1 / -1;
        }
        .genesis-project-context strong {
          display: block;
          overflow: hidden;
          color: var(--text-primary, #111827);
          font-size: 14px;
          font-weight: 600;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .form-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }
        .form-grid .form-full {
          grid-column: 1 / -1;
        }
        @media (max-width: 900px) {
          .genesis-project-context {
            grid-template-columns: 1fr;
          }
        }
        .form-actions {
          display: flex;
          gap: 8px;
          justify-content: flex-end;
          margin-top: 16px;
        }
        .genesis-status-bar {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 16px;
        }
        .genesis-status {
          display: inline-flex;
          align-items: center;
          padding: 4px 10px;
          border-radius: 12px;
          font-size: 12px;
          font-weight: 500;
        }
        .status-running { background: var(--accent-soft); color: var(--primary); }
        .status-pending { background: color-mix(in srgb, var(--warning) 16%, transparent); color: var(--warning); }
        .status-approved { background: color-mix(in srgb, var(--success) 16%, transparent); color: var(--success); }
        .status-rejected { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
        .status-failed { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
        .genesis-time {
          font-size: 12px;
          color: var(--text-muted, #9ca3af);
        }
        .genesis-error {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px;
          background: color-mix(in srgb, var(--danger) 12%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--danger) 28%, transparent);
          border-radius: 6px;
          color: var(--danger);
          font-size: 13px;
          margin-bottom: 16px;
        }
        .genesis-running {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 20px;
          justify-content: center;
          color: var(--text-secondary, #6b7280);
          font-size: 14px;
        }
        .genesis-draft {
          background: var(--bg-primary, #fff);
          border: 1px solid var(--border, #e5e7eb);
          border-radius: 8px;
          padding: 16px;
          margin-bottom: 16px;
          max-height: 500px;
          overflow-y: auto;
        }
        .draft-empty {
          display: flex;
          gap: 10px;
          align-items: flex-start;
          padding: 14px;
          border: 1px solid color-mix(in srgb, var(--warning) 30%, transparent);
          border-radius: 6px;
          background: color-mix(in srgb, var(--warning) 10%, var(--bg-primary));
          color: var(--text-secondary);
          font-size: 13px;
          line-height: 1.6;
        }
        .draft-empty strong {
          display: block;
          color: var(--text-primary);
          font-size: 14px;
          margin-bottom: 2px;
        }
        .draft-empty p {
          margin: 0;
        }
        .draft-invalid {
          border-color: color-mix(in srgb, var(--danger) 30%, transparent);
          background: color-mix(in srgb, var(--danger) 10%, var(--bg-primary));
        }
        .draft-raw {
          margin-top: 12px;
          font-size: 12px;
          color: var(--text-muted);
        }
        .draft-raw summary {
          cursor: pointer;
        }
        .draft-raw pre {
          margin: 8px 0 0;
          max-height: 220px;
          overflow: auto;
          white-space: pre-wrap;
          word-break: break-word;
          color: var(--text-secondary);
        }
        .draft-section {
          margin-bottom: 16px;
        }
        .draft-section:last-child {
          margin-bottom: 0;
        }
        .draft-section h4 {
          font-size: 14px;
          font-weight: 600;
          margin: 0 0 8px;
          color: var(--text-primary, #111827);
        }
        .draft-section p {
          font-size: 13px;
          line-height: 1.6;
          color: var(--text-secondary, #374151);
          margin: 0;
        }
        .draft-section ul {
          list-style: none;
          padding: 0;
          margin: 0;
        }
        .draft-section li {
          font-size: 13px;
          line-height: 1.5;
          padding: 6px 0;
          border-bottom: 1px solid var(--border-color);
          color: var(--text-secondary, #374151);
        }
        .draft-section li:last-child {
          border-bottom: none;
        }
        .genesis-actions {
          display: flex;
          gap: 8px;
          justify-content: flex-end;
          align-items: center;
          flex-wrap: wrap;
        }
        .genesis-action-error {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-right: auto;
          font-size: 13px;
          color: var(--danger);
        }
        .genesis-reject-confirm {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          color: var(--text-secondary, #6b7280);
        }
        .genesis-approved {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 16px;
          background: color-mix(in srgb, var(--success) 12%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--success) 28%, transparent);
          border-radius: 8px;
          color: var(--success);
          font-size: 14px;
        }
        .genesis-quality-report {
          padding: 14px;
          border-radius: 8px;
          margin-bottom: 16px;
          font-size: 13px;
        }
        .quality-pass {
          background: color-mix(in srgb, var(--success) 10%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--success) 24%, transparent);
        }
        .quality-warning {
          background: color-mix(in srgb, var(--warning) 10%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--warning) 24%, transparent);
        }
        .quality-blocked, .quality-scaffold {
          background: color-mix(in srgb, var(--danger) 10%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--danger) 24%, transparent);
        }
        .quality-header {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 10px;
        }
        .quality-status {
          font-weight: 600;
          font-size: 14px;
        }
        .quality-pass .quality-status { color: var(--success); }
        .quality-warning .quality-status { color: var(--warning); }
        .quality-blocked .quality-status, .quality-scaffold .quality-status { color: var(--danger); }
        .quality-score {
          color: var(--text-muted);
          font-size: 12px;
        }
        .quality-scaffold-warning {
          padding: 10px;
          background: color-mix(in srgb, var(--danger) 8%, transparent);
          border-radius: 4px;
          color: var(--danger);
          margin-bottom: 10px;
          line-height: 1.5;
        }
        .quality-issues {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .quality-issue {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          align-items: baseline;
          padding: 8px;
          background: color-mix(in srgb, var(--bg-primary) 50%, transparent);
          border-radius: 4px;
        }
        .issue-severity {
          font-weight: 600;
          font-size: 11px;
          padding: 2px 6px;
          border-radius: 3px;
          text-transform: uppercase;
        }
        .issue-blocker .issue-severity {
          background: color-mix(in srgb, var(--danger) 20%, transparent);
          color: var(--danger);
        }
        .issue-warning .issue-severity {
          background: color-mix(in srgb, var(--warning) 20%, transparent);
          color: var(--warning);
        }
        .issue-advisory .issue-severity {
          background: color-mix(in srgb, var(--text-muted) 20%, transparent);
          color: var(--text-muted);
        }
        .issue-message {
          flex: 1;
          min-width: 200px;
          color: var(--text-primary);
        }
        .issue-suggestion {
          width: 100%;
          margin-top: 4px;
          font-size: 12px;
          color: var(--text-muted);
          font-style: italic;
        }
        .quality-block-hint {
          font-size: 12px;
          color: var(--danger);
          margin-left: 8px;
        }
        .spin {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
