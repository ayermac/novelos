import { useEffect, useState } from 'react'
import { get, post } from '../lib/api'

interface SettingsData {
  llm_mode: string
  llm_profiles: Array<{
    name: string
    provider: string
    model: string
    has_key: boolean
  }>
  default_llm: string | null
}

export default function Settings() {
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState<string | null>(null)

  useEffect(() => {
    get<SettingsData>('/settings').then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      }
      setLoading(false)
    })
  }, [])

  const handleGenerateDraft = async () => {
    const res = await post('/config/plan', {
      provider: 'openai',
      model: 'gpt-4',
      api_key_env: 'OPENAI_API_KEY',
      default_llm: 'default',
    })

    if (res.ok && res.data) {
      setDraft((res.data as { draft: string }).draft)
    }
  }

  if (loading) {
    return <div>加载中...</div>
  }

  if (!data) {
    return <div>加载失败</div>
  }

  return (
    <div>
      <h2 style={{ marginBottom: '24px' }}>配置中心</h2>

      {/* LLM Mode */}
      <div className="card mb-4">
        <div className="card-header">
          <h3>运行模式</h3>
        </div>
        <div className="card-body">
          <span className={`status-badge status-${data.llm_mode}`}>
            {data.llm_mode === 'real' ? '真实 LLM' : '演示模式'}
          </span>
        </div>
      </div>

      {/* LLM Profiles */}
      <div className="card mb-4">
        <div className="card-header">
          <h3>LLM 档案</h3>
          <span className="text-secondary">默认: {data.default_llm || '未设置'}</span>
        </div>
        <div className="card-body">
          {data.llm_profiles.length > 0 ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>提供商</th>
                  <th>模型</th>
                  <th>API Key</th>
                </tr>
              </thead>
              <tbody>
                {data.llm_profiles.map((profile) => (
                  <tr key={profile.name}>
                    <td>{profile.name}</td>
                    <td>{profile.provider}</td>
                    <td>{profile.model}</td>
                    <td>
                      {profile.has_key ? (
                        <span className="text-success">已配置</span>
                      ) : (
                        <span className="text-danger">未配置</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <div className="empty-title">暂无 LLM 档案</div>
              <div className="empty-hint">使用配置向导创建档案</div>
            </div>
          )}
        </div>
      </div>

      {/* Config Wizard */}
      <div className="card">
        <div className="card-header">
          <h3>配置向导</h3>
          <span className="text-secondary">生成配置草案</span>
        </div>
        <div className="card-body">
          <button onClick={handleGenerateDraft} className="btn btn-primary">
            生成配置草案
          </button>

          {draft && (
            <div style={{ marginTop: '16px' }}>
              <h4 style={{ marginBottom: '8px' }}>配置草案预览</h4>
              <pre
                style={{
                  background: '#1f2937',
                  color: '#f9fafb',
                  padding: '16px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  overflow: 'auto',
                }}
              >
                {draft}
              </pre>
              <button
                onClick={() => navigator.clipboard.writeText(draft)}
                className="btn btn-secondary"
                style={{ marginTop: '8px' }}
              >
                复制草案
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
