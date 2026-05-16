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

  const parseDraft = (): DraftData | null => {
    if (!genesis?.draft_json) return null
    try {
      return JSON.parse(genesis.draft_json)
    } catch {
      return null
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

  if (loading) return <div className="module-loading">加载中...</div>

  const draft = parseDraft()
  const canGenerate = !genesis || genesis.status === 'approved' || genesis.status === 'rejected' || genesis.status === 'failed'

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
          {draft && genesis.status === 'generated' && (
            <>
              <div className="genesis-draft">
                {draft.project_updates?.description && (
                  <div className="draft-section">
                    <h4>项目描述</h4>
                    <p>{draft.project_updates.description}</p>
                  </div>
                )}

                {draft.world_settings && draft.world_settings.length > 0 && (
                  <div className="draft-section">
                    <h4>世界观设定 ({draft.world_settings.length})</h4>
                    <ul>
                      {draft.world_settings.map((ws, i) => (
                        <li key={i}><strong>[{ws.category}] {ws.title}</strong>: {ws.content}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft.characters && draft.characters.length > 0 && (
                  <div className="draft-section">
                    <h4>角色 ({draft.characters.length})</h4>
                    <ul>
                      {draft.characters.map((c, i) => (
                        <li key={i}><strong>{c.name}</strong> ({c.role}): {c.description}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft.factions && draft.factions.length > 0 && (
                  <div className="draft-section">
                    <h4>势力 ({draft.factions.length})</h4>
                    <ul>
                      {draft.factions.map((f, i) => (
                        <li key={i}><strong>{f.name}</strong> ({f.type}): {f.description}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft.outlines && draft.outlines.length > 0 && (
                  <div className="draft-section">
                    <h4>大纲 ({draft.outlines.length})</h4>
                    <ul>
                      {draft.outlines.map((o, i) => (
                        <li key={i}><strong>第{o.chapters_range}章 {o.title}</strong>: {o.content}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft.plot_holes && draft.plot_holes.length > 0 && (
                  <div className="draft-section">
                    <h4>伏笔/悬念 ({draft.plot_holes.length})</h4>
                    <ul>
                      {draft.plot_holes.map((ph, i) => (
                        <li key={i}><strong>[{ph.type}] {ph.title}</strong>: {ph.description}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {draft.instructions && draft.instructions.length > 0 && (
                  <div className="draft-section">
                    <h4>章节指令 ({draft.instructions.length})</h4>
                    <ul>
                      {draft.instructions.map((inst, i) => (
                        <li key={i}><strong>第{inst.chapter_number}章</strong>: {inst.objective}</li>
                      ))}
                    </ul>
                  </div>
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
                    <button className="btn btn-primary" onClick={handleApprove} disabled={approving}>
                      {approving ? <><Loader2 size={14} className="spin" /> 应用中...</> : <><CheckCircle2 size={14} /> 批准并应用</>}
                    </button>
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
        .status-running { background: #dbeafe; color: #1d4ed8; }
        .status-pending { background: #fef3c7; color: #92400e; }
        .status-approved { background: #d1fae5; color: #065f46; }
        .status-rejected { background: #fee2e2; color: #991b1b; }
        .status-failed { background: #fee2e2; color: #991b1b; }
        .genesis-time {
          font-size: 12px;
          color: var(--text-muted, #9ca3af);
        }
        .genesis-error {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px;
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 6px;
          color: #991b1b;
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
          border-bottom: 1px solid var(--border-light, #f3f4f6);
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
          color: #991b1b;
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
          background: #f0fdf4;
          border: 1px solid #bbf7d0;
          border-radius: 8px;
          color: #065f46;
          font-size: 14px;
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
