import { useEffect, useState } from 'react'
import { get, post } from '../lib/api'
import { tLlmMode } from '../lib/i18n'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface LlmProfile {
  name: string
  provider: string
  model: string
  has_key: boolean
  has_base_url: boolean
  api_key_env: string | null
  base_url_env: string | null
}

interface AgentRoute {
  agent: string
  route: string
}

interface Diagnostics {
  llm_mode: string
  has_profiles: boolean
  has_default_llm: boolean
}

interface SettingsData {
  llm_mode: string
  llm_profiles: LlmProfile[]
  agent_routes: AgentRoute[]
  default_llm: string | null
  diagnostics: Diagnostics
}

export default function Settings() {
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError('')
    get<SettingsData>('/settings').then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取配置信息失败')
      }
      setLoading(false)
    })
  }

  useEffect(() => {
    load()
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
    } else {
      setError(res.error?.message || '生成配置草案失败')
    }
  }

  if (loading) {
    return <div>加载中...</div>
  }

  if (error && !data) {
    return (
      <ErrorState
        title="加载失败"
        message={error}
        onRetry={load}
      />
    )
  }

  if (!data) {
    return (
      <ErrorState
        title="加载失败"
        message="无法获取配置数据"
        onRetry={load}
      />
    )
  }

  const isStub = data.llm_mode === 'stub'

  return (
    <div>
      <PageHeader title="配置中心" />

      {/* Diagnostics Banner */}
      {isStub && (
        <div className="alert alert-warn" style={{ marginBottom: '16px' }}>
          <strong>当前为演示模式</strong>
          <div style={{ marginTop: '4px', fontSize: '14px' }}>
            未配置真实 LLM，所有生成操作使用占位符返回。如需真实生成，请配置 LLM Profile 并使用 --llm-mode real 启动。
          </div>
        </div>
      )}

      {/* LLM Mode */}
      <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <div className="card-header">
          <h3>运行模式</h3>
        </div>
        <div className="card-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
            <StatusBadge status={data.llm_mode} />
            <span style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
              {isStub ? '演示模式 — 返回占位内容，不调用真实 LLM' : '真实 LLM — 将调用外部 API 生成内容'}
            </span>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            启动命令示例：
            <code style={{ display: 'block', marginTop: '8px', padding: '12px', background: '#1f2937', color: '#f9fafb', borderRadius: '6px', fontSize: '12px', overflow: 'auto' }}>
              novelos api --llm-mode real --config config/local.yaml
            </code>
          </div>
        </div>
      </div>

      {/* Diagnostics */}
      <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <div className="card-header">
          <h3>配置诊断</h3>
        </div>
        <div className="card-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>LLM 档案</div>
              <div style={{ fontWeight: 600, color: data.diagnostics.has_profiles ? 'var(--success)' : 'var(--danger)' }}>
                {data.diagnostics.has_profiles ? '已配置' : '未配置'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>默认 LLM</div>
              <div style={{ fontWeight: 600, color: data.diagnostics.has_default_llm ? 'var(--success)' : 'var(--danger)' }}>
                {data.diagnostics.has_default_llm ? '已设置' : '未设置'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>运行模式</div>
              <div style={{ fontWeight: 600 }}>{tLlmMode(data.diagnostics.llm_mode)}</div>
            </div>
          </div>
          {!data.diagnostics.has_profiles && (
            <div style={{ marginTop: '16px', padding: '12px', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              提示：暂无 LLM 档案。使用下方「配置向导」生成草案，保存到 config/local.yaml 后重启服务即可启用真实 LLM。
            </div>
          )}
        </div>
      </div>

      {/* LLM Profiles */}
      <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <div className="card-header">
          <h3>LLM 档案</h3>
          <span className="text-secondary">默认: {data.default_llm || '未设置'}</span>
        </div>
        <div className="card-body">
          {data.llm_profiles.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>提供商</th>
                    <th>模型</th>
                    <th>API Key</th>
                    <th>Base URL</th>
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
                        {profile.api_key_env && (
                          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                            变量: {profile.api_key_env}
                          </div>
                        )}
                      </td>
                      <td>
                        {profile.has_base_url ? (
                          <span className="text-success">已配置</span>
                        ) : (
                          <span className="text-danger">未配置</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="暂无 LLM 档案"
              hint="使用配置向导生成档案草案，或手动编辑配置文件。"
            />
          )}
        </div>
      </div>

      {/* Agent Routes */}
      {data.agent_routes.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
          <div className="card-header">
            <h3>Agent 路由</h3>
          </div>
          <div className="card-body">
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>LLM Profile</th>
                  </tr>
                </thead>
                <tbody>
                  {data.agent_routes.map((route) => (
                    <tr key={route.agent}>
                      <td>{route.agent}</td>
                      <td>{route.route}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Config Wizard */}
      <div className="card">
        <div className="card-header">
          <h3>配置向导</h3>
          <span className="text-secondary">生成配置草案（仅预览，不写入文件）</span>
        </div>
        <div className="card-body">
          <div style={{ marginBottom: '16px', fontSize: '14px', color: 'var(--text-secondary)' }}>
            向导会生成一份 YAML 配置草案。你需要：
            <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
              <li>将草案保存到 <code>config/local.yaml</code></li>
              <li>设置环境变量 <code>export OPENAI_API_KEY=your-key</code></li>
              <li>使用 <code>novelos api --config config/local.yaml --llm-mode real</code> 启动</li>
            </ol>
          </div>
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
