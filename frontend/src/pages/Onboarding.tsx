import { useState } from 'react'
import { Link } from 'react-router-dom'
import { post } from '../lib/api'
import PageHeader from '../components/PageHeader'

interface ProjectResult {
  project: {
    project_id: string
    name: string
  }
  chapters: Array<{ chapter_number: number }>
}

/** Generate a project ID from a Chinese/English name */
function generateProjectId(name: string): string {
  if (!name) return ''
  // Use pinyin-like approach: extract ASCII chars, or transliterate
  let id = name
    .toLowerCase()
    .replace(/[\u4e00-\u9fff]/g, '') // Remove CJK
    .replace(/[^a-z0-9_]/g, '_') // Replace non-alphanumeric with underscore
    .replace(/_+/g, '_') // Collapse multiple underscores
    .replace(/^_|_$/g, '') // Trim leading/trailing underscores
  // If all CJK (no ASCII), use a prefix + hash
  if (!id) {
    const hash = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
    id = `novel_${hash.toString(36)}`
  }
  return id
}

export default function Onboarding() {
  const [form, setForm] = useState({
    project_id: '',
    name: '',
    genre: 'urban',
    description: '',
    total_chapters_planned: 500,
    target_words: 1500000,
    style_template: 'default_web_serial',
    start_chapter: 1,
    initial_chapter_count: 10,
    // New fields for world/character/outline
    world_setting: '',
    main_character_name: '',
    main_character_role: 'protagonist',
    main_character_description: '',
    main_character_traits: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ProjectResult | null>(null)
  const [idManuallyEdited, setIdManuallyEdited] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const handleNameChange = (name: string) => {
    setForm((prev) => ({
      ...prev,
      name,
      // Auto-generate ID if user hasn't manually edited it
      project_id: idManuallyEdited ? prev.project_id : generateProjectId(name),
    }))
  }

  const handleIdChange = (id: string) => {
    setIdManuallyEdited(true)
    setForm((prev) => ({ ...prev, project_id: id }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const res = await post('/onboarding/projects', form)

    if (res.ok && res.data) {
      setResult(res.data as ProjectResult)
    } else {
      const msg = res.error?.message || '创建失败'
      // Translate known error codes
      if (msg.includes('已存在')) {
        setError(`项目 ID '${form.project_id}' 已被使用，请换一个项目 ID。`)
      } else {
        setError(msg)
      }
    }
    setLoading(false)
  }

  if (result) {
    return (
      <div>
        <PageHeader title="创建成功" />
        <div style={{
          background: 'var(--paper-surface)',
          borderRadius: 'var(--radius-xl)',
          boxShadow: 'var(--shadow-flat)',
          border: '1px solid rgba(30, 58, 95, 0.06)',
          padding: 'var(--space-10)',
          textAlign: 'center',
        }}>
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: 'var(--gradient-ink)',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '32px',
              margin: '0 auto var(--space-6)',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            ✓
          </div>
          <h3 style={{ marginBottom: 'var(--space-2)', fontSize: 'var(--text-xl)', fontWeight: 'var(--font-semibold)' }}>项目创建成功</h3>
          <p style={{ color: 'var(--text-charcoal)', marginBottom: 'var(--space-6)', fontSize: 'var(--text-base)' }}>
            「{result.project.name}」已创建，共规划 {result.chapters.length} 个初始章节。
          </p>
          <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'center' }}>
            <Link
              to={`/projects/${result.project.project_id}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                padding: 'var(--space-3) var(--space-5)',
                background: 'var(--gradient-ink)',
                color: 'white',
                borderRadius: 'var(--radius-md)',
                fontSize: 'var(--text-base)',
                fontWeight: 'var(--font-medium)',
                textDecoration: 'none',
                transition: 'all var(--duration-fast) var(--ease-out)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-1px)'
                e.currentTarget.style.boxShadow = 'var(--shadow-md)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = ''
                e.currentTarget.style.boxShadow = ''
              }}
            >
              进入项目工作台
            </Link>
            <Link
              to={`/projects/${result.project.project_id}?chapter=1`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                padding: 'var(--space-3) var(--space-5)',
                background: 'var(--paper-surface)',
                color: 'var(--text-ink)',
                border: '1px solid rgba(30, 58, 95, 0.12)',
                borderRadius: 'var(--radius-md)',
                fontSize: 'var(--text-base)',
                fontWeight: 'var(--font-medium)',
                textDecoration: 'none',
                transition: 'all var(--duration-fast) var(--ease-out)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--paper-hover)'
                e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.2)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'var(--paper-surface)'
                e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)'
              }}
            >
              进入工作台生成第一章
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <PageHeader title="创建新项目" backTo="/projects" backLabel="返回列表" />

      {error && (
        <div style={{
          marginBottom: 'var(--space-4)',
          padding: 'var(--space-4)',
          background: 'rgba(239, 68, 68, 0.08)',
          color: '#991b1b',
          borderRadius: 'var(--radius-md)',
          fontSize: 'var(--text-sm)',
        }}>
          {error}
        </div>
      )}

      <div style={{
        background: 'var(--paper-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-flat)',
        border: '1px solid rgba(30, 58, 95, 0.06)',
        overflow: 'hidden',
      }}>
        <div style={{ padding: 'var(--space-5)' }}>
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 'var(--space-6)' }}>
              <div style={{
                fontSize: 'var(--text-sm)',
                fontWeight: 'var(--font-semibold)',
                marginBottom: 'var(--space-4)',
                color: 'var(--ink-accent)',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
              }}>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  background: 'var(--gradient-ink)',
                  color: 'white',
                  fontSize: '12px',
                  fontWeight: 'var(--font-bold)',
                }}>1</span>
                基础信息
              </div>
              <div style={{ marginBottom: 'var(--space-4)' }}>
                <label style={{
                  display: 'block',
                  marginBottom: 'var(--space-2)',
                  fontWeight: 'var(--font-medium)',
                  color: 'var(--text-ink)',
                  fontSize: 'var(--text-sm)',
                }}>小说名称</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => handleNameChange(e.target.value)}
                  placeholder="例如：斗破苍穹"
                  required
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid rgba(30, 58, 95, 0.12)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--paper-surface)',
                    color: 'var(--text-ink)',
                    transition: 'border-color var(--duration-fast) var(--ease-out)',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                />
              </div>

              <div style={{ marginBottom: 'var(--space-4)' }}>
                <label style={{
                  display: 'block',
                  marginBottom: 'var(--space-2)',
                  fontWeight: 'var(--font-medium)',
                  color: 'var(--text-ink)',
                  fontSize: 'var(--text-sm)',
                }}>项目 ID</label>
                <input
                  type="text"
                  value={form.project_id}
                  onChange={(e) => handleIdChange(e.target.value)}
                  placeholder="根据名称自动生成，可手动修改"
                  required
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid rgba(30, 58, 95, 0.12)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--paper-surface)',
                    color: 'var(--text-ink)',
                    transition: 'border-color var(--duration-fast) var(--ease-out)',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                />
                <div style={{
                  marginTop: 'var(--space-1)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-gray)',
                }}>唯一标识符，只能包含字母、数字、下划线（根据名称自动生成）</div>
              </div>

              <div style={{ marginBottom: 'var(--space-4)' }}>
                <label style={{
                  display: 'block',
                  marginBottom: 'var(--space-2)',
                  fontWeight: 'var(--font-medium)',
                  color: 'var(--text-ink)',
                  fontSize: 'var(--text-sm)',
                }}>
                  类型 / 题材 <span style={{ color: 'var(--status-danger)' }}>*</span>
                </label>
                <select
                  value={form.genre}
                  onChange={(e) => setForm({ ...form, genre: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid rgba(30, 58, 95, 0.12)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--paper-surface)',
                    color: 'var(--text-ink)',
                    transition: 'border-color var(--duration-fast) var(--ease-out)',
                    cursor: 'pointer',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                >
                  <option value="urban">都市</option>
                  <option value="fantasy">奇幻</option>
                  <option value="sci-fi">科幻</option>
                  <option value="xianxia">仙侠</option>
                  <option value="romance">言情</option>
                  <option value="mystery">悬疑</option>
                </select>
              </div>

              <div style={{ marginBottom: 'var(--space-4)' }}>
                <label style={{
                  display: 'block',
                  marginBottom: 'var(--space-2)',
                  fontWeight: 'var(--font-medium)',
                  color: 'var(--text-ink)',
                  fontSize: 'var(--text-sm)',
                }}>简介</label>
                <textarea
                  rows={3}
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="简要描述故事背景和大纲"
                  style={{
                    width: '100%',
                    padding: 'var(--space-3)',
                    border: '1px solid rgba(30, 58, 95, 0.12)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--paper-surface)',
                    color: 'var(--text-ink)',
                    transition: 'border-color var(--duration-fast) var(--ease-out)',
                    resize: 'vertical',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                />
              </div>
            </div>

            <div style={{ marginBottom: 'var(--space-6)', paddingTop: 'var(--space-4)', borderTop: '1px solid rgba(30, 58, 95, 0.06)' }}>
              <div style={{
                fontSize: 'var(--text-sm)',
                fontWeight: 'var(--font-semibold)',
                marginBottom: 'var(--space-4)',
                color: 'var(--ink-accent)',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
              }}>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  background: 'var(--gradient-ink)',
                  color: 'white',
                  fontSize: '12px',
                  fontWeight: 'var(--font-bold)',
                }}>2</span>
                规模设置
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <label style={{
                    display: 'block',
                    marginBottom: 'var(--space-2)',
                    fontWeight: 'var(--font-medium)',
                    color: 'var(--text-ink)',
                    fontSize: 'var(--text-sm)',
                  }}>计划总章节数</label>
                  <input
                    type="number"
                    value={form.total_chapters_planned}
                    onChange={(e) =>
                      setForm({ ...form, total_chapters_planned: parseInt(e.target.value) })
                    }
                    min={1}
                    style={{
                      width: '100%',
                      padding: 'var(--space-3)',
                      border: '1px solid rgba(30, 58, 95, 0.12)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--text-base)',
                      background: 'var(--paper-surface)',
                      color: 'var(--text-ink)',
                      transition: 'border-color var(--duration-fast) var(--ease-out)',
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                  />
                </div>
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <label style={{
                    display: 'block',
                    marginBottom: 'var(--space-2)',
                    fontWeight: 'var(--font-medium)',
                    color: 'var(--text-ink)',
                    fontSize: 'var(--text-sm)',
                  }}>目标总字数</label>
                  <input
                    type="number"
                    value={form.target_words}
                    onChange={(e) =>
                      setForm({ ...form, target_words: parseInt(e.target.value) })
                    }
                    min={1}
                    style={{
                      width: '100%',
                      padding: 'var(--space-3)',
                      border: '1px solid rgba(30, 58, 95, 0.12)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--text-base)',
                      background: 'var(--paper-surface)',
                      color: 'var(--text-ink)',
                      transition: 'border-color var(--duration-fast) var(--ease-out)',
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                  />
                </div>
              </div>
            </div>

            <div style={{ marginBottom: 'var(--space-6)', paddingTop: 'var(--space-4)', borderTop: '1px solid rgba(30, 58, 95, 0.06)' }}>
              <div style={{
                fontSize: 'var(--text-sm)',
                fontWeight: 'var(--font-semibold)',
                marginBottom: 'var(--space-4)',
                color: 'var(--ink-accent)',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
              }}>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  background: 'var(--gradient-ink)',
                  color: 'white',
                  fontSize: '12px',
                  fontWeight: 'var(--font-bold)',
                }}>3</span>
                初始章节
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <label style={{
                    display: 'block',
                    marginBottom: 'var(--space-2)',
                    fontWeight: 'var(--font-medium)',
                    color: 'var(--text-ink)',
                    fontSize: 'var(--text-sm)',
                  }}>起始章节号</label>
                  <input
                    type="number"
                    value={form.start_chapter}
                    onChange={(e) =>
                      setForm({ ...form, start_chapter: parseInt(e.target.value) })
                    }
                    min={1}
                    style={{
                      width: '100%',
                      padding: 'var(--space-3)',
                      border: '1px solid rgba(30, 58, 95, 0.12)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--text-base)',
                      background: 'var(--paper-surface)',
                      color: 'var(--text-ink)',
                      transition: 'border-color var(--duration-fast) var(--ease-out)',
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                  />
                </div>
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <label style={{
                    display: 'block',
                    marginBottom: 'var(--space-2)',
                    fontWeight: 'var(--font-medium)',
                    color: 'var(--text-ink)',
                    fontSize: 'var(--text-sm)',
                  }}>初始章节数</label>
                  <input
                    type="number"
                    value={form.initial_chapter_count}
                    onChange={(e) =>
                      setForm({ ...form, initial_chapter_count: parseInt(e.target.value) })
                    }
                    min={1}
                    style={{
                      width: '100%',
                      padding: 'var(--space-3)',
                      border: '1px solid rgba(30, 58, 95, 0.12)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 'var(--text-base)',
                      background: 'var(--paper-surface)',
                      color: 'var(--text-ink)',
                      transition: 'border-color var(--duration-fast) var(--ease-out)',
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                  />
                  <div style={{
                    marginTop: 'var(--space-1)',
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-gray)',
                  }}>创建项目时预生成的章节数量</div>
                </div>
              </div>
            </div>

            <div style={{ marginBottom: 'var(--space-6)', paddingTop: 'var(--space-4)', borderTop: '1px solid rgba(30, 58, 95, 0.06)' }}>
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                style={{
                  width: '100%',
                  marginBottom: showAdvanced ? 'var(--space-4)' : 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 'var(--space-2)',
                  padding: 'var(--space-3)',
                  background: 'var(--paper-hover)',
                  border: '1px solid rgba(30, 58, 95, 0.12)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--text-sm)',
                  fontWeight: 'var(--font-medium)',
                  color: 'var(--text-charcoal)',
                  cursor: 'pointer',
                  transition: 'all var(--duration-fast) var(--ease-out)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--paper-elevated)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'var(--paper-hover)'
                }}
              >
                {showAdvanced ? '▼ 收起高级设置' : '▶ 展开高级设置（世界观与角色）'}
              </button>

              {showAdvanced && (
                <div style={{
                  border: '1px solid rgba(30, 58, 95, 0.08)',
                  borderRadius: 'var(--radius-lg)',
                  padding: 'var(--space-5)',
                  background: 'var(--paper-bg)',
                }}>
                  <div style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-gray)',
                    marginBottom: 'var(--space-4)',
                    padding: 'var(--space-3)',
                    background: 'var(--paper-surface)',
                    borderRadius: 'var(--radius-md)',
                  }}>
                    这些信息将帮助 AI 生成更符合你设想的小说内容。可以稍后在项目工作台补充。
                  </div>

                  <div style={{ marginBottom: 'var(--space-4)' }}>
                    <label style={{
                      display: 'block',
                      marginBottom: 'var(--space-2)',
                      fontWeight: 'var(--font-medium)',
                      color: 'var(--text-ink)',
                      fontSize: 'var(--text-sm)',
                    }}>世界观设定</label>
                    <textarea
                      rows={3}
                      value={form.world_setting}
                      onChange={(e) => setForm({ ...form, world_setting: e.target.value })}
                      placeholder="描述力量体系、社会结构等核心世界观...&#10;例如：斗气大陆以斗气为尊，修炼等级从斗之气到斗帝共十阶..."
                      style={{
                        width: '100%',
                        padding: 'var(--space-3)',
                        border: '1px solid rgba(30, 58, 95, 0.12)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: 'var(--text-base)',
                        background: 'var(--paper-surface)',
                        color: 'var(--text-ink)',
                        transition: 'border-color var(--duration-fast) var(--ease-out)',
                        resize: 'vertical',
                      }}
                      onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                      onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                    />
                  </div>

                  <div style={{
                    fontSize: 'var(--text-sm)',
                    fontWeight: 'var(--font-semibold)',
                    margin: 'var(--space-4) 0 var(--space-3)',
                    color: 'var(--text-charcoal)',
                  }}>
                    主角设定
                  </div>

                  <div style={{ marginBottom: 'var(--space-4)' }}>
                    <label style={{
                      display: 'block',
                      marginBottom: 'var(--space-2)',
                      fontWeight: 'var(--font-medium)',
                      color: 'var(--text-ink)',
                      fontSize: 'var(--text-sm)',
                    }}>主角名称</label>
                    <input
                      type="text"
                      value={form.main_character_name}
                      onChange={(e) => setForm({ ...form, main_character_name: e.target.value })}
                      placeholder="例如：萧炎"
                      style={{
                        width: '100%',
                        padding: 'var(--space-3)',
                        border: '1px solid rgba(30, 58, 95, 0.12)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: 'var(--text-base)',
                        background: 'var(--paper-surface)',
                        color: 'var(--text-ink)',
                        transition: 'border-color var(--duration-fast) var(--ease-out)',
                      }}
                      onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                      onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                    />
                  </div>

                  <div style={{ marginBottom: 'var(--space-4)' }}>
                    <label style={{
                      display: 'block',
                      marginBottom: 'var(--space-2)',
                      fontWeight: 'var(--font-medium)',
                      color: 'var(--text-ink)',
                      fontSize: 'var(--text-sm)',
                    }}>主角简介</label>
                    <textarea
                      rows={2}
                      value={form.main_character_description}
                      onChange={(e) => setForm({ ...form, main_character_description: e.target.value })}
                      placeholder="描述主角的背景、经历..."
                      style={{
                        width: '100%',
                        padding: 'var(--space-3)',
                        border: '1px solid rgba(30, 58, 95, 0.12)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: 'var(--text-base)',
                        background: 'var(--paper-surface)',
                        color: 'var(--text-ink)',
                        transition: 'border-color var(--duration-fast) var(--ease-out)',
                        resize: 'vertical',
                      }}
                      onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                      onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                    />
                  </div>

                  <div style={{ marginBottom: 'var(--space-4)' }}>
                    <label style={{
                      display: 'block',
                      marginBottom: 'var(--space-2)',
                      fontWeight: 'var(--font-medium)',
                      color: 'var(--text-ink)',
                      fontSize: 'var(--text-sm)',
                    }}>性格特征</label>
                    <input
                      type="text"
                      value={form.main_character_traits}
                      onChange={(e) => setForm({ ...form, main_character_traits: e.target.value })}
                      placeholder="用逗号分隔，例如：坚韧、重情义、不服输"
                      style={{
                        width: '100%',
                        padding: 'var(--space-3)',
                        border: '1px solid rgba(30, 58, 95, 0.12)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: 'var(--text-base)',
                        background: 'var(--paper-surface)',
                        color: 'var(--text-ink)',
                        transition: 'border-color var(--duration-fast) var(--ease-out)',
                      }}
                      onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--ink-accent)' }}
                      onBlur={(e) => { e.currentTarget.style.borderColor = 'rgba(30, 58, 95, 0.12)' }}
                    />
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-4)', paddingTop: 'var(--space-4)', borderTop: '1px solid rgba(30, 58, 95, 0.06)' }}>
              <button
                type="submit"
                disabled={loading}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 'var(--space-2)',
                  padding: 'var(--space-3) var(--space-6)',
                  background: loading ? 'var(--text-muted)' : 'var(--gradient-ink)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--text-base)',
                  fontWeight: 'var(--font-medium)',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  transition: 'all var(--duration-fast) var(--ease-out)',
                }}
                onMouseEnter={(e) => {
                  if (!loading) {
                    e.currentTarget.style.transform = 'translateY(-1px)'
                    e.currentTarget.style.boxShadow = 'var(--shadow-md)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = ''
                  e.currentTarget.style.boxShadow = ''
                }}
              >
                {loading ? '创建中...' : '创建项目'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
