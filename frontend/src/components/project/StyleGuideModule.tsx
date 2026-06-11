import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { get, post } from '../../lib/api'
import { Palette, Plus, Pencil, ExternalLink } from 'lucide-react'

interface StyleBible {
  project_id: string
  project_name: string
  status: string
  version: number | string
  updated_at: string
}

interface StyleConsoleData {
  style_bibles: StyleBible[]
  style_gate_configs: { project_id: string; project_name: string; enabled: boolean; threshold: number }[]
  style_samples: { project_id: string; sample_id: string; source: string; word_count: number }[]
  health: { total_projects: number; projects_with_bible: number; gate_configs: number }
}

interface Props {
  projectId: string
}

function getStyleStatusLabel(status: string): string {
  if (status === 'active') return '已启用'
  if (status === 'draft') return '草稿'
  if (status === 'needs_review') return '待确认'
  return '已建立'
}

export default function StyleGuideModule({ projectId }: Props) {
  const [bible, setBible] = useState<StyleBible | null>(null)
  const [loading, setLoading] = useState(true)
  const [initLoading, setInitLoading] = useState(false)
  const [error, setError] = useState('')
  const [initSuccess, setInitSuccess] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    const res = await get<StyleConsoleData>('/style/console')
    if (res.ok && res.data) {
      const found = res.data.style_bibles.find((b) => b.project_id === projectId)
      setBible(found || null)
    } else {
      setError(res.error?.message || '获取风格指南失败')
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleInit = async () => {
    setInitLoading(true)
    setError('')
    setInitSuccess(false)
    const res = await post('/style/init', { project_id: projectId })
    if (res.ok) {
      setInitSuccess(true)
      load()
    } else {
      setError(res.error?.message || '初始化风格指南失败')
    }
    setInitLoading(false)
  }

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Palette size={18} /> 风格指南</h3>
        <Link
          to="/style"
          style={{ fontSize: 13, color: 'var(--primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}
        >
          全局风格管理 <ExternalLink size={14} />
        </Link>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}
      {initSuccess && (
        <div className="alert alert-success" style={{ marginBottom: 12 }}>
          风格指南初始化成功！您可以继续完善风格设置，或直接进入编辑。
        </div>
      )}

      {bible ? (
        <div className="data-card" style={{ maxWidth: 600 }}>
          <div className="data-card-header">
            <span className="data-card-category">风格指南</span>
            <span className="data-card-badge">v{bible.version}</span>
          </div>
          <div className="data-card-title">状态: {getStyleStatusLabel(bible.status)}</div>
          <div className="data-card-content">更新于: {bible.updated_at || '未知'}</div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <Link to={`/style?project_id=${projectId}`} className="btn btn-secondary btn-sm" style={{ textDecoration: 'none' }}>
              <Pencil size={14} /> 编辑
            </Link>
          </div>
        </div>
      ) : (
        <div className="data-empty">
          <div className="data-empty-icon"><Palette size={32} /></div>
          <div className="data-empty-title">暂无风格指南</div>
          <div className="data-empty-desc">风格指南定义写作风格、用词偏好和叙事视角，帮助 AI 保持文风一致</div>
          <button
            className="btn btn-primary"
            onClick={handleInit}
            disabled={initLoading}
            style={{ marginTop: 12 }}
          >
            <Plus size={14} /> {initLoading ? '初始化中...' : '初始化风格指南'}
          </button>
        </div>
      )}
    </div>
  )
}
