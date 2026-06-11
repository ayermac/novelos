import { useState, useEffect, useCallback } from 'react'
import { get, post, put } from '../../lib/api'
import { Sparkles, CheckCircle2, XCircle, Loader2, FileText, Shield } from 'lucide-react'

interface LaunchProfile {
  target_reader?: string
  market_lane?: string
  genre_family?: string
  subgenre?: string
  title_promise?: string
  core_hook?: string
  primary_payoff_loop?: string
  secondary_payoff_loops?: string[]
  protagonist_growth_engine?: string
  commercial_comps?: string[]
  first_30_chapter_strategy?: string
  hard_do_not_drift_rules?: string[]
  [key: string]: unknown
}

interface GenreContract {
  genre_id?: string
  promise_statement?: string
  reader_expectations?: string[]
  must_have_beats?: string[]
  allowed_dark_lines?: string[]
  forbidden_drift?: string[]
  payoff_cadence?: Record<string, unknown>
  pressure_limits?: Record<string, unknown>
  upgrade_cadence?: Record<string, unknown>
  relationship_cadence?: Record<string, unknown>
  mystery_reveal_cadence?: Record<string, unknown>
  style_constraints?: string[]
  editor_weights?: Record<string, number>
  [key: string]: unknown
}

interface CoreLoopStep {
  id?: string
  label?: string
  description?: string
  payoff_type?: string
  required?: boolean
}

interface SupportingMechanism {
  id?: string
  label?: string
  description?: string
  allowed_role?: string
  must_serve_core_loop?: boolean
}

interface DriftRule {
  id?: string
  description?: string
  severity?: string
  window_chapters?: number
  threshold?: number
}

interface StoryContract {
  project_id?: string
  core_promise?: string
  core_loop?: CoreLoopStep[]
  supporting_mechanisms?: SupportingMechanism[]
  payoff_types?: string[]
  drift_rules?: DriftRule[]
  cadence?: Record<string, number>
  status?: string
  version?: string
  [key: string]: unknown
}

interface CreativeContractData {
  project_id: string
  launch_profile: LaunchProfile | null
  genre_contract: GenreContract | null
  story_contract: StoryContract | null
  is_approved: boolean
  is_ready_for_production: boolean
}

interface GenreProfilesResponse {
  profiles: string[]
  count: number
}

interface Props {
  projectId: string
}

export default function CreativeContractsModule({ projectId }: Props) {
  const [contracts, setContracts] = useState<CreativeContractData | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [approving, setApproving] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [showGenerateForm, setShowGenerateForm] = useState(false)
  const [userIdea, setUserIdea] = useState('')
  const [genreProfileId, setGenreProfileId] = useState('generic')
  const [availableProfiles, setAvailableProfiles] = useState<string[]>([])
  const [editingStory, setEditingStory] = useState(false)
  const [savingStory, setSavingStory] = useState(false)
  const [storyDraft, setStoryDraft] = useState<StoryContract | null>(null)

  const loadContracts = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true)
    setErrorMsg('')
    try {
      const res = await get<CreativeContractData>(`/projects/${projectId}/creative-contracts`)
      if (res.ok && res.data) {
        setContracts(res.data)
        setStoryDraft(res.data.story_contract ? { ...res.data.story_contract } : null)
      } else {
        setContracts(null)
        setStoryDraft(null)
        if (res.error?.details?.domain_status !== 'not_found') {
          setErrorMsg(res.error?.message || '加载创作合同失败')
        }
      }
    } catch {
      setErrorMsg('加载创作合同失败')
    }
    setLoading(false)
  }, [projectId])

  const loadGenreProfiles = useCallback(async () => {
    try {
      const res = await get<GenreProfilesResponse>('/genre-profiles')
      if (res.ok && res.data) {
        setAvailableProfiles(res.data.profiles)
      }
    } catch {
      // Silently fail, fallback to generic
    }
  }, [])

  useEffect(() => {
    loadContracts()
    loadGenreProfiles()
  }, [loadContracts, loadGenreProfiles])

  const handleGenerate = async () => {
    if (!userIdea.trim()) {
      setErrorMsg('请输入你的创意/想法')
      return
    }
    setGenerating(true)
    setErrorMsg('')
    setSuccessMsg('')
    try {
      const res = await post(`/projects/${projectId}/creative-contracts/generate`, {
        project_id: projectId,
        user_idea: userIdea.trim(),
        genre_profile_id: genreProfileId,
      })
      if (res.ok) {
        setSuccessMsg('创作合同生成成功')
        setShowGenerateForm(false)
        setUserIdea('')
        await loadContracts(false)
      } else {
        setErrorMsg(res.error?.message || '生成创作合同失败')
      }
    } catch {
      setErrorMsg('生成创作合同失败')
    }
    setGenerating(false)
  }

  const handleApprove = async () => {
    setApproving(true)
    setErrorMsg('')
    setSuccessMsg('')
    try {
      const res = await post(`/projects/${projectId}/creative-contracts/approve`, {
        project_id: projectId,
      })
      if (res.ok) {
        setSuccessMsg('创作合同审批成功，项目已准备就绪')
        await loadContracts(false)
      } else {
        setErrorMsg(res.error?.message || '审批创作合同失败')
      }
    } catch {
      setErrorMsg('审批创作合同失败')
    }
    setApproving(false)
  }

  const serializeCoreLoop = (steps?: CoreLoopStep[]): string => (
    steps && steps.length > 0
      ? steps.map((step, index) => `${step.id || `step_${index + 1}`} | ${step.label || ''} | ${step.description || ''}`).join('\n')
      : ''
  )

  const parseCoreLoop = (text: string): CoreLoopStep[] => (
    text.split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const parts = line.split('|').map((part) => part.trim())
        if (parts.length >= 2) {
          return {
            id: parts[0] || `step_${index + 1}`,
            label: parts[1] || parts[0] || `步骤${index + 1}`,
            description: parts.slice(2).join(' | '),
            required: true,
          }
        }
        return {
          id: `step_${index + 1}`,
          label: line,
          description: '',
          required: true,
        }
      })
  )

  const serializeMechanisms = (items?: SupportingMechanism[]): string => (
    items && items.length > 0
      ? items.map((item, index) => `${item.id || `mech_${index + 1}`} | ${item.label || ''} | ${item.allowed_role || 'pressure'} | ${item.description || ''}`).join('\n')
      : ''
  )

  const parseMechanisms = (text: string): SupportingMechanism[] => (
    text.split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const parts = line.split('|').map((part) => part.trim())
        if (parts.length >= 2) {
          return {
            id: parts[0] || `mech_${index + 1}`,
            label: parts[1] || parts[0] || `机制${index + 1}`,
            allowed_role: parts[2] || 'pressure',
            description: parts.slice(3).join(' | '),
            must_serve_core_loop: true,
          }
        }
        return {
          id: `mech_${index + 1}`,
          label: line,
          allowed_role: 'pressure',
          description: '',
          must_serve_core_loop: true,
        }
      })
  )

  const serializeRules = (rules?: DriftRule[]): string => (
    rules && rules.length > 0
      ? rules.map((rule, index) => `${rule.id || `rule_${index + 1}`} | ${rule.description || ''} | ${rule.severity || 'warning'} | ${rule.window_chapters || 1} | ${rule.threshold || 1}`).join('\n')
      : ''
  )

  const parseRules = (text: string): DriftRule[] => (
    text.split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const parts = line.split('|').map((part) => part.trim())
        return {
          id: parts[0] || `rule_${index + 1}`,
          description: parts[1] || parts[0] || `规则${index + 1}`,
          severity: parts[2] || 'warning',
          window_chapters: Number(parts[3] || 1),
          threshold: Number(parts[4] || 1),
        }
      })
  )

  const serializeStringList = (items?: string[]): string => items?.join('\n') || ''

  const parseStringList = (text: string): string[] => (
    text.split('\n').map((line) => line.trim()).filter(Boolean)
  )

  const serializeCadence = (cadence?: Record<string, number>): string => (
    cadence
      ? Object.entries(cadence).map(([key, value]) => `${key}=${value}`).join('\n')
      : ''
  )

  const parseCadence = (text: string): Record<string, number> => {
    const result: Record<string, number> = {}
    text.split('\n').forEach((line) => {
      const [key, value] = line.split('=').map((part) => part.trim())
      if (key) result[key] = Number(value || 1)
    })
    return result
  }

  const handleSaveStoryContract = async () => {
    if (!storyDraft) return
    setSavingStory(true)
    setErrorMsg('')
    setSuccessMsg('')
    try {
      const res = await put<{ story_contract: StoryContract }>(
        `/projects/${projectId}/creative-contracts/story-contract`,
        { story_contract: storyDraft },
      )
      if (res.ok) {
        setSuccessMsg('故事合同已保存')
        setEditingStory(false)
        await loadContracts(false)
      } else {
        setErrorMsg(res.error?.message || '保存故事合同失败')
      }
    } catch {
      setErrorMsg('保存故事合同失败')
    }
    setSavingStory(false)
  }

  const formatValue = (value: unknown): string => {
    if (value === null || value === undefined) return '未设置'
    if (Array.isArray(value)) {
      return value.length > 0 ? value.join('、') : '未设置'
    }
    if (typeof value === 'object') {
      return JSON.stringify(value, null, 2)
    }
    return String(value)
  }

  if (loading) {
    return <div className="module-loading">加载中...</div>
  }

  const hasContracts = contracts && (contracts.launch_profile || contracts.genre_contract || contracts.story_contract)
  const isApproved = contracts?.is_approved ?? false
  const isReady = contracts?.is_ready_for_production ?? false

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><FileText size={18} /> 创作合同</h3>
        {!hasContracts && !showGenerateForm && (
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setShowGenerateForm(true)}
          >
            <Sparkles size={14} /> 生成合同
          </button>
        )}
        {hasContracts && !isApproved && (
          <button
            className="btn btn-primary btn-sm"
            onClick={handleApprove}
            disabled={approving}
          >
            {approving ? (
              <><Loader2 size={14} className="spin" /> 审批中...</>
            ) : (
              <><CheckCircle2 size={14} /> 审批合同</>
            )}
          </button>
        )}
      </div>

      {/* Messages */}
      {errorMsg && (
        <div className="contract-message error">
          <XCircle size={16} /> {errorMsg}
        </div>
      )}
      {successMsg && (
        <div className="contract-message success">
          <CheckCircle2 size={16} /> {successMsg}
        </div>
      )}

      {/* Status indicator */}
      {hasContracts && (
        <div className={`contract-status ${isReady ? 'ready' : 'not-ready'}`}>
          <Shield size={16} />
          <span>
            {isReady
              ? '项目已准备就绪，可以开始章节生产'
              : isApproved
                ? '合同已审批，但项目尚未完全准备就绪'
                : '合同未审批，请审批后开始章节生产'
            }
          </span>
        </div>
      )}

      {/* Generate form */}
      {showGenerateForm && (
        <div className="contract-generate-form">
          <h4>生成创作合同</h4>
          <p className="form-description">
            创作合同定义了项目的类型承诺、读者期望和创作边界。合同将指导整个创作过程。
          </p>
          
          <div className="form-group">
            <label htmlFor="genre-profile">类型配置</label>
            <select
              id="genre-profile"
              value={genreProfileId}
              onChange={(e) => setGenreProfileId(e.target.value)}
            >
              <option value="generic">通用（默认）</option>
              {availableProfiles.map((profile) => (
                <option key={profile} value={profile}>
                  {profile.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
            <small>选择最接近你作品类型的配置</small>
          </div>

          <div className="form-group">
            <label htmlFor="user-idea">你的创意/想法 *</label>
            <textarea
              id="user-idea"
              value={userIdea}
              onChange={(e) => setUserIdea(e.target.value)}
              placeholder="描述你的故事创意、核心冲突、主角设定等..."
              rows={4}
            />
            <small>提供详细的创意描述有助于生成更准确的合同</small>
          </div>

          <div className="form-actions">
            <button
              className="btn btn-secondary"
              onClick={() => {
                setShowGenerateForm(false)
                setUserIdea('')
                setErrorMsg('')
              }}
            >
              取消
            </button>
            <button
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={generating || !userIdea.trim()}
            >
              {generating ? (
                <><Loader2 size={14} className="spin" /> 生成中...</>
              ) : (
                <><Sparkles size={14} /> 生成合同</>
              )}
            </button>
          </div>
        </div>
      )}

      {/* No contracts state */}
      {!hasContracts && !showGenerateForm && (
        <div className="data-empty">
          <div className="data-empty-icon"><FileText size={32} /></div>
          <div className="data-empty-title">尚未生成创作合同</div>
          <div className="data-empty-desc">
            创作合同定义了项目的类型承诺、读者期望和创作边界。
            <br />
            生成合同后，系统将根据合同指导整个创作过程。
          </div>
          <button
            className="btn btn-primary"
            onClick={() => setShowGenerateForm(true)}
            style={{ marginTop: 12 }}
          >
            <Sparkles size={14} /> 生成创作合同
          </button>
        </div>
      )}

      {/* Contract details */}
      {hasContracts && (
        <div className="contract-details">
          {/* Story Contract */}
          {contracts.story_contract && (
            <div className="contract-section story-contract-section">
              <div className="contract-section-header">
                <h4>故事合同 (Story Contract)</h4>
                {!editingStory ? (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setStoryDraft(contracts.story_contract ? { ...contracts.story_contract } : null)
                      setEditingStory(true)
                    }}
                  >
                    编辑故事合同
                  </button>
                ) : (
                  <div className="contract-actions-inline">
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        setStoryDraft(contracts.story_contract ? { ...contracts.story_contract } : null)
                        setEditingStory(false)
                      }}
                    >
                      取消
                    </button>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={handleSaveStoryContract}
                      disabled={savingStory || !storyDraft}
                    >
                      {savingStory ? <><Loader2 size={14} className="spin" /> 保存中...</> : '保存故事合同'}
                    </button>
                  </div>
                )}
              </div>

              {!editingStory && (
                <div className="contract-grid">
                  <div className="contract-item">
                    <span className="contract-label">状态</span>
                    <span className="contract-value">{formatValue(contracts.story_contract.status)}</span>
                  </div>
                  <div className="contract-item">
                    <span className="contract-label">版本</span>
                    <span className="contract-value">{formatValue(contracts.story_contract.version)}</span>
                  </div>
                  <div className="contract-item full-width">
                    <span className="contract-label">核心承诺</span>
                    <span className="contract-value">{formatValue(contracts.story_contract.core_promise)}</span>
                  </div>
                  <div className="contract-item full-width">
                    <span className="contract-label">核心循环</span>
                    <span className="contract-value">
                      {contracts.story_contract.core_loop?.map((step) => step.label || step.id).join(' → ') || '未设置'}
                    </span>
                  </div>
                  <div className="contract-item full-width">
                    <span className="contract-label">辅助机制</span>
                    <span className="contract-value">
                      {contracts.story_contract.supporting_mechanisms?.map((item) => item.label || item.id).join('、') || '未设置'}
                    </span>
                  </div>
                  <div className="contract-item full-width">
                    <span className="contract-label">漂移规则</span>
                    <span className="contract-value">
                      {contracts.story_contract.drift_rules?.map((rule) => rule.description || rule.id).join('；') || '未设置'}
                    </span>
                  </div>
                </div>
              )}

              {editingStory && storyDraft && (
                <div className="story-contract-editor">
                  <div className="form-group">
                    <label>状态</label>
                    <select
                      value={storyDraft.status || 'draft'}
                      onChange={(e) => setStoryDraft({ ...storyDraft, status: e.target.value })}
                    >
                      <option value="draft">草稿：只提示，不阻断</option>
                      <option value="needs_review">待确认：需要人工确认</option>
                      <option value="active">已启用：可参与阻断</option>
                      <option value="confirmed">已确认：可参与阻断</option>
                    </select>
                    <small>只有 active/confirmed 状态下，blocking 级漂移规则才会进入阻断。</small>
                  </div>

                  <div className="form-group">
                    <label>核心承诺</label>
                    <textarea
                      value={storyDraft.core_promise || ''}
                      onChange={(e) => setStoryDraft({ ...storyDraft, core_promise: e.target.value })}
                      rows={3}
                      placeholder="例如：主角通过核心机制获得可见收益，并用收益完成权力兑现。"
                    />
                  </div>

                  <div className="form-group">
                    <label>核心循环</label>
                    <textarea
                      value={serializeCoreLoop(storyDraft.core_loop)}
                      onChange={(e) => setStoryDraft({ ...storyDraft, core_loop: parseCoreLoop(e.target.value) })}
                      rows={6}
                      placeholder={'每行一个步骤：id | 名称 | 描述\ntrigger | 触发核心机会 | 到达或激活核心机会'}
                    />
                    <small>每行格式：id | 名称 | 描述。用于约束每章必须推进什么。</small>
                  </div>

                  <div className="form-group">
                    <label>辅助机制</label>
                    <textarea
                      value={serializeMechanisms(storyDraft.supporting_mechanisms)}
                      onChange={(e) => setStoryDraft({ ...storyDraft, supporting_mechanisms: parseMechanisms(e.target.value) })}
                      rows={4}
                      placeholder={'每行一个机制：id | 名称 | 角色 | 描述\ncountdown | 倒计时 | pressure | 只作为压力来源'}
                    />
                    <small>辅助机制可以制造压力，但不能长期替代核心循环。</small>
                  </div>

                  <div className="form-group">
                    <label>回报类型</label>
                    <textarea
                      value={serializeStringList(storyDraft.payoff_types)}
                      onChange={(e) => setStoryDraft({ ...storyDraft, payoff_types: parseStringList(e.target.value) })}
                      rows={3}
                      placeholder={'每行一个回报类型\nreward\npublic_reversal\nrelationship_shift'}
                    />
                  </div>

                  <div className="form-group">
                    <label>漂移规则</label>
                    <textarea
                      value={serializeRules(storyDraft.drift_rules)}
                      onChange={(e) => setStoryDraft({ ...storyDraft, drift_rules: parseRules(e.target.value) })}
                      rows={5}
                      placeholder={'每行一条规则：id | 描述 | warning/blocking | 窗口章数 | 阈值\npayoff_within_window | 连续2章内必须有核心兑现 | warning | 2 | 1'}
                    />
                  </div>

                  <div className="form-group">
                    <label>节奏阈值</label>
                    <textarea
                      value={serializeCadence(storyDraft.cadence)}
                      onChange={(e) => setStoryDraft({ ...storyDraft, cadence: parseCadence(e.target.value) })}
                      rows={3}
                      placeholder={'每行一个键值：key=value\nminor_payoff=1\nvisible_upgrade=3'}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Launch Profile */}
          {contracts.launch_profile && (
            <div className="contract-section">
              <h4>启动配置 (Launch Profile)</h4>
              <div className="contract-grid">
                <div className="contract-item">
                  <span className="contract-label">目标读者</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.target_reader)}</span>
                </div>
                <div className="contract-item">
                  <span className="contract-label">市场赛道</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.market_lane)}</span>
                </div>
                <div className="contract-item">
                  <span className="contract-label">类型家族</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.genre_family)}</span>
                </div>
                <div className="contract-item">
                  <span className="contract-label">子类型</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.subgenre)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">标题承诺</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.title_promise)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">核心钩子</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.core_hook)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">主要回报循环</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.primary_payoff_loop)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">次要回报循环</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.secondary_payoff_loops)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">主角成长引擎</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.protagonist_growth_engine)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">商业对标作品</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.commercial_comps)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">前30章策略</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.first_30_chapter_strategy)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">不可偏离规则</span>
                  <span className="contract-value">{formatValue(contracts.launch_profile.hard_do_not_drift_rules)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Genre Contract */}
          {contracts.genre_contract && (
            <div className="contract-section">
              <h4>类型合同 (Genre Contract)</h4>
              <div className="contract-grid">
                <div className="contract-item">
                  <span className="contract-label">类型ID</span>
                  <span className="contract-value">{formatValue(contracts.genre_contract.genre_id)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">承诺声明</span>
                  <span className="contract-value">{formatValue(contracts.genre_contract.promise_statement)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">读者期望</span>
                  <span className="contract-value">{formatValue(contracts.genre_contract.reader_expectations)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">必须包含的节拍</span>
                  <span className="contract-value">{formatValue(contracts.genre_contract.must_have_beats)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">允许的黑暗元素</span>
                  <span className="contract-value">{formatValue(contracts.genre_contract.allowed_dark_lines)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">禁止的偏离</span>
                  <span className="contract-value">{formatValue(contracts.genre_contract.forbidden_drift)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">风格约束</span>
                  <span className="contract-value">{formatValue(contracts.genre_contract.style_constraints)}</span>
                </div>
                <div className="contract-item full-width">
                  <span className="contract-label">编辑权重</span>
                  <span className="contract-value">
                    {contracts.genre_contract.editor_weights
                      ? Object.entries(contracts.genre_contract.editor_weights)
                          .map(([key, value]) => `${key}: ${value}`)
                          .join(', ')
                      : '未设置'
                    }
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Approval status */}
          <div className="contract-approval-status">
            <div className={`approval-badge ${isApproved ? 'approved' : 'pending'}`}>
              {isApproved ? (
                <><CheckCircle2 size={16} /> 已审批</>
              ) : (
                <><XCircle size={16} /> 待审批</>
              )}
            </div>
            {!isApproved && (
              <p className="approval-note">
                审批合同后，系统将根据合同约束指导整个创作过程。
                未审批的合同不会影响章节生成，但不会提供类型约束保护。
              </p>
            )}
          </div>
        </div>
      )}

      <style>{`
        .contract-message {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px;
          border-radius: 6px;
          font-size: 13px;
          margin-bottom: 16px;
        }
        .contract-message.error {
          background: color-mix(in srgb, var(--danger) 12%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--danger) 28%, transparent);
          color: var(--danger);
        }
        .contract-message.success {
          background: color-mix(in srgb, var(--success) 12%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--success) 28%, transparent);
          color: var(--success);
        }
        .contract-status {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px;
          border-radius: 6px;
          font-size: 13px;
          margin-bottom: 16px;
        }
        .contract-status.ready {
          background: color-mix(in srgb, var(--success) 12%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--success) 28%, transparent);
          color: var(--success);
        }
        .contract-status.not-ready {
          background: color-mix(in srgb, var(--warning) 12%, var(--bg-primary));
          border: 1px solid color-mix(in srgb, var(--warning) 28%, transparent);
          color: var(--warning);
        }
        .contract-generate-form {
          background: var(--bg-secondary, #f9fafb);
          border: 1px solid var(--border, #e5e7eb);
          border-radius: 8px;
          padding: 20px;
          margin-bottom: 16px;
        }
        .contract-generate-form h4 {
          margin: 0 0 12px;
          font-size: 16px;
          font-weight: 600;
        }
        .form-description {
          font-size: 13px;
          color: var(--text-secondary);
          margin-bottom: 16px;
          line-height: 1.5;
        }
        .form-group {
          margin-bottom: 16px;
        }
        .form-group label {
          display: block;
          font-size: 13px;
          font-weight: 500;
          margin-bottom: 6px;
          color: var(--text-secondary);
        }
        .form-group select,
        .form-group textarea {
          width: 100%;
          padding: 8px 10px;
          border: 1px solid var(--border-color);
          border-radius: 6px;
          font-size: 14px;
          background: var(--bg-primary);
          color: var(--text-primary);
          box-sizing: border-box;
        }
        .form-group select:focus,
        .form-group textarea:focus {
          outline: none;
          border-color: rgba(118, 26, 52, 0.42);
          box-shadow: 0 0 0 3px rgba(118,26,52,0.08);
        }
        .form-group small {
          display: block;
          margin-top: 4px;
          font-size: 12px;
          color: var(--text-muted);
        }
        .form-actions {
          display: flex;
          gap: 8px;
          justify-content: flex-end;
          margin-top: 16px;
        }
        .contract-details {
          background: var(--bg-primary, #fff);
          border: 1px solid var(--border, #e5e7eb);
          border-radius: 8px;
          padding: 16px;
          margin-bottom: 16px;
        }
        .contract-section {
          margin-bottom: 24px;
        }
        .contract-section:last-child {
          margin-bottom: 0;
        }
        .contract-section h4 {
          font-size: 15px;
          font-weight: 600;
          margin: 0 0 12px;
          color: var(--text-primary);
          padding-bottom: 8px;
          border-bottom: 1px solid var(--border-color);
        }
        .contract-section-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;
          padding-bottom: 8px;
          border-bottom: 1px solid var(--border-color);
        }
        .contract-section-header h4 {
          margin: 0;
          padding-bottom: 0;
          border-bottom: 0;
        }
        .contract-actions-inline {
          display: flex;
          gap: 8px;
          align-items: center;
        }
        .story-contract-section {
          border: 1px solid color-mix(in srgb, var(--primary) 18%, var(--border-color));
          border-radius: 8px;
          padding: 14px;
          background: color-mix(in srgb, var(--primary) 4%, var(--bg-primary));
        }
        .story-contract-editor {
          display: grid;
          gap: 12px;
        }
        .contract-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }
        .contract-item {
          padding: 10px;
          background: var(--bg-secondary, #f9fafb);
          border-radius: 6px;
          border: 1px solid var(--border-color);
        }
        .contract-item.full-width {
          grid-column: 1 / -1;
        }
        .contract-label {
          display: block;
          font-size: 12px;
          font-weight: 500;
          color: var(--text-muted);
          margin-bottom: 4px;
        }
        .contract-value {
          display: block;
          font-size: 13px;
          color: var(--text-primary);
          line-height: 1.5;
          word-break: break-word;
        }
        .contract-approval-status {
          margin-top: 20px;
          padding-top: 16px;
          border-top: 1px solid var(--border-color);
        }
        .approval-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 12px;
          border-radius: 16px;
          font-size: 13px;
          font-weight: 500;
          margin-bottom: 8px;
        }
        .approval-badge.approved {
          background: color-mix(in srgb, var(--success) 16%, transparent);
          color: var(--success);
        }
        .approval-badge.pending {
          background: color-mix(in srgb, var(--warning) 16%, transparent);
          color: var(--warning);
        }
        .approval-note {
          font-size: 13px;
          color: var(--text-secondary);
          margin: 0;
          line-height: 1.5;
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
