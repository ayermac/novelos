import { useCallback, useEffect, useMemo, useState } from 'react'
import { Code2, RefreshCcw, Save, Trash2 } from 'lucide-react'
import { del, get, put } from '../../lib/api'

interface ProjectSkillOverridesResponse {
  project_id: string
  overrides: Record<string, unknown>
  skills_count: number
  agent_count: number
  has_overrides: boolean
  updated_at?: string
}

interface Props {
  projectId: string
}

const DEFAULT_EXAMPLE = {
  skills: {
    'style-bible-checker': {
      enabled: true,
      payload_defaults: {
        style_bible: {
          source: 'project',
        },
      },
      notes: 'Project-sensitive style gate',
    },
  },
  agent_skills: {
    editor: {
      before_review: ['style-bible-checker'],
    },
  },
}

export default function ProjectSkillOverridesModule({ projectId }: Props) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [summary, setSummary] = useState<ProjectSkillOverridesResponse | null>(null)
  const [draft, setDraft] = useState('')

  const prettyExample = useMemo(() => JSON.stringify(DEFAULT_EXAMPLE, null, 2), [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    const res = await get<ProjectSkillOverridesResponse>(`/projects/${projectId}/skill-overrides`)
    if (res.ok && res.data) {
      setSummary(res.data)
      setDraft(JSON.stringify(res.data.overrides || {}, null, 2))
    } else {
      setError(res.error?.message || '获取项目 Skill 覆盖失败')
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    setError('')

    let parsed: Record<string, unknown>
    try {
      parsed = draft.trim() ? JSON.parse(draft) : {}
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('覆盖内容必须是 JSON 对象')
      }
    } catch (err) {
      setSaving(false)
      setError(err instanceof Error ? err.message : '覆盖内容 JSON 解析失败')
      return
    }

    const res = await put<ProjectSkillOverridesResponse>(`/projects/${projectId}/skill-overrides`, {
      overrides: parsed,
    })
    setSaving(false)

    if (res.ok && res.data) {
      setSummary(res.data)
      setDraft(JSON.stringify(res.data.overrides || {}, null, 2))
      setMessage('项目 Skill 覆盖已保存')
    } else {
      setError(res.error?.message || '保存项目 Skill 覆盖失败')
    }
  }

  const handleClear = async () => {
    setSaving(true)
    setMessage('')
    setError('')

    const res = await del<ProjectSkillOverridesResponse>(`/projects/${projectId}/skill-overrides`, {})
    setSaving(false)

    if (res.ok && res.data) {
      setSummary(res.data)
      setDraft(JSON.stringify(res.data.overrides || {}, null, 2))
      setMessage('项目 Skill 覆盖已清空')
    } else {
      setError(res.error?.message || '清空项目 Skill 覆盖失败')
    }
  }

  if (loading) {
    return <div className="module-loading">加载中...</div>
  }

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Code2 size={18} /> 项目级 Skill 覆盖</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary btn-sm" onClick={load} disabled={saving}>
            <RefreshCcw size={14} />
            重新加载
          </button>
          <button className="btn btn-secondary btn-sm" onClick={handleClear} disabled={saving}>
            <Trash2 size={14} />
            清空
          </button>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            <Save size={14} />
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {message && (
        <div className="data-card" style={{ marginBottom: 16 }}>
          <div className="data-card-content">{message}</div>
        </div>
      )}

      {error && (
        <div className="data-card" style={{ marginBottom: 16, borderColor: 'var(--danger)' }}>
          <div className="data-card-content" style={{ color: 'var(--danger)' }}>{error}</div>
        </div>
      )}

      <div className="data-card" style={{ marginBottom: 16 }}>
        <div className="data-card-content" style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>覆盖技能数</div>
              <div style={{ fontWeight: 600 }}>{summary?.skills_count ?? 0}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>覆盖 Agent 数</div>
              <div style={{ fontWeight: 600 }}>{summary?.agent_count ?? 0}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>更新时间</div>
              <div style={{ fontWeight: 600 }}>{summary?.updated_at || '未保存'}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>状态</div>
              <div style={{ fontWeight: 600, color: summary?.has_overrides ? 'var(--success)' : 'var(--text-secondary)' }}>
                {summary?.has_overrides ? '已配置' : '继承全局'}
              </div>
            </div>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            这里保存的是“项目覆盖层”，不会改写全局 <code>skills.yaml</code>。可用来覆盖某个 Skill 的启用策略、挂载方案和参数默认值。
          </div>
        </div>
      </div>

      <div className="data-card" style={{ marginBottom: 16 }}>
        <div className="data-card-content" style={{ display: 'grid', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>覆盖 JSON</div>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={18}
              style={{ width: '100%', fontFamily: 'monospace' }}
              placeholder={prettyExample}
            />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
            <div>建议结构：</div>
            <code style={{ display: 'block', whiteSpace: 'pre-wrap', marginTop: 8 }}>{prettyExample}</code>
            <div style={{ marginTop: 8 }}>
              <strong>skills</strong> 下写单个 Skill 的覆盖：
              <code>enabled</code>、<code>payload_defaults</code>、<code>notes</code>。
            </div>
            <div>
              <strong>agent_skills</strong> 下写项目级挂载方案：
              <code>agent / stage / skill_ids</code>。
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
