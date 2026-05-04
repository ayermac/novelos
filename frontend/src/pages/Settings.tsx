import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { get, post } from '../lib/api'
import { tLlmMode } from '../lib/i18n'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'
import SkillVisibilityPanel from '../components/settings/SkillVisibilityPanel'

interface LlmProfile {
  name: string
  provider: string
  model: string
  has_key: boolean
  has_base_url: boolean
  api_key_env: string | null
  base_url_env: string | null
  resolved_base_url?: string | null
  base_url_source?: string
  api_key_source?: string
  temperature?: number
  max_tokens?: number
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

interface GenerationStats {
  test_result: 'pending' | 'success' | 'failed'
  success_rate: number
  avg_duration_seconds: number
  total_runs: number
  last_run_at: string | null
}

interface SettingsData {
  llm_mode: string
  config_path?: string | null
  db_path?: string | null
  llm_profiles: LlmProfile[]
  agent_routes: AgentRoute[]
  default_llm: string | null
  diagnostics: Diagnostics
  generation_stats: GenerationStats
}

const PROVIDER_OPTIONS = [
  { value: 'openai_compatible', label: 'OpenAI 兼容' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'deepseek', label: 'DeepSeek' },
]

const MODEL_OPTIONS = [
  { value: 'gpt-4', label: 'GPT-4' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
  { value: 'claude-3-5-sonnet', label: 'Claude 3.5 Sonnet' },
  { value: 'deepseek-chat', label: 'DeepSeek Chat' },
  { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner' },
  { value: 'custom', label: '自定义模型' },
]

const SETTINGS_SECTIONS = [
  { key: 'overview', label: '概览诊断', hint: '运行模式与生成健康度' },
  { key: 'llm', label: 'LLM 配置', hint: '档案与 Agent 路由' },
  { key: 'skills', label: 'Skill 管理', hint: '挂载、测试与试运行' },
  { key: 'draft', label: '配置草案', hint: '生成本地配置草案' },
] as const

type SettingsSection = typeof SETTINGS_SECTIONS[number]['key']

export default function Settings() {
  const [searchParams] = useSearchParams()
  const [data, setData] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState<string | null>(null)
  const [validating, setValidating] = useState(false)
  const [validateResult, setValidateResult] = useState<{
    valid: boolean
    message: string
    error_code?: string
  } | null>(null)
  const [wizardForm, setWizardForm] = useState({
    provider: 'openai_compatible',
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-4',
    custom_model: '',
    api_key_env: 'OPENAI_API_KEY',
    default_llm: 'default',
    agent_llm: '',
  })

  const effectiveModel = wizardForm.model === 'custom'
    ? wizardForm.custom_model.trim()
    : wizardForm.model
  const requestedSection = searchParams.get('section') as SettingsSection | null
  const activeSection: SettingsSection = SETTINGS_SECTIONS.some((section) => section.key === requestedSection)
    ? requestedSection!
    : 'overview'

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
    if (!effectiveModel) {
      setError('请填写自定义模型名')
      return
    }

    const res = await post('/config/plan', {
      ...wizardForm,
      model: effectiveModel,
    })

    if (res.ok && res.data) {
      setDraft((res.data as { draft: string }).draft)
    } else {
      setError(res.error?.message || '生成配置草案失败')
    }
  }

  const handleValidateConfig = async () => {
    setValidating(true)
    setValidateResult(null)

    const res = await post('/settings/validate', {
      provider: wizardForm.provider,
      base_url: wizardForm.base_url,
      model: effectiveModel || wizardForm.model,
      api_key_env: wizardForm.api_key_env,
    })

    setValidating(false)

    if (res.ok && res.data) {
      const data = res.data as { valid: boolean; message: string; error_code?: string }
      setValidateResult(data)
    } else {
      setValidateResult({
        valid: false,
        message: res.error?.message || '验证请求失败',
      })
    }
  }

  // Update base_url when provider changes
  const handleProviderChange = (provider: string) => {
    const urlMap: Record<string, string> = {
      openai_compatible: 'https://api.openai.com/v1',
      openai: 'https://api.openai.com/v1',
      anthropic: 'https://api.anthropic.com/v1',
      deepseek: 'https://api.deepseek.com/v1',
    }
    const envMap: Record<string, string> = {
      openai_compatible: 'OPENAI_API_KEY',
      openai: 'OPENAI_API_KEY',
      anthropic: 'ANTHROPIC_API_KEY',
      deepseek: 'DEEPSEEK_API_KEY',
    }
    setWizardForm({
      ...wizardForm,
      provider,
      base_url: urlMap[provider] || wizardForm.base_url,
      api_key_env: envMap[provider] || wizardForm.api_key_env,
    })
  }

  if (loading) {
    return (
      <div>
        <PageHeader title="配置中心" />
        <div style={{
          background: 'var(--paper-surface)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-flat)',
          border: '1px solid rgba(30, 58, 95, 0.06)',
          padding: 'var(--space-10)',
          textAlign: 'center',
          color: 'var(--text-charcoal)',
        }}>
          <div style={{
            width: '32px',
            height: '32px',
            border: '2px solid var(--paper-elevated)',
            borderTopColor: 'var(--ink-accent)',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto var(--space-3)',
          }} />
          加载中...
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    )
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
  const generationStatusLabel = data.generation_stats.test_result === 'success'
    ? '健康'
    : data.generation_stats.test_result === 'failed'
      ? '异常'
      : data.generation_stats.total_runs > 0
        ? '有记录'
        : '无记录'

  return (
    <div>
      <PageHeader title="配置中心" />

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '10px',
        marginBottom: 'var(--space-6)',
      }}>
        {SETTINGS_SECTIONS.map((section) => {
          const active = section.key === activeSection
          return (
            <Link
              key={section.key}
              to={`/settings?section=${section.key}`}
              style={{
                display: 'block',
                padding: '12px 14px',
                borderRadius: 'var(--radius-md)',
                border: active ? '1px solid rgba(37, 99, 235, 0.45)' : '1px solid rgba(30, 58, 95, 0.08)',
                background: active ? 'rgba(59, 130, 246, 0.08)' : 'var(--paper-surface)',
                boxShadow: 'var(--shadow-flat)',
                textDecoration: 'none',
              }}
            >
              <div style={{
                fontSize: '14px',
                fontWeight: 600,
                color: active ? '#1d4ed8' : 'var(--text-primary)',
                marginBottom: '3px',
              }}>
                {section.label}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {section.hint}
              </div>
            </Link>
          )
        })}
      </div>

      {activeSection === 'overview' && (
        <>
      {/* 能力诊断 - 合并运行模式 + 配置诊断 */}
      <div style={{
        background: 'var(--paper-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-flat)',
        border: '1px solid rgba(30, 58, 95, 0.06)',
        overflow: 'hidden',
        marginBottom: 'var(--space-6)',
      }}>
        <div style={{
          padding: 'var(--space-4) var(--space-5)',
          borderBottom: '1px solid rgba(30, 58, 95, 0.04)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <h3 style={{
            fontFamily: 'var(--font-brand)',
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--font-semibold)',
            margin: 0,
          }}>能力诊断</h3>
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 'var(--space-1)',
            padding: 'var(--space-1) var(--space-3)',
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--font-medium)',
            borderRadius: 'var(--radius-full)',
            background: isStub ? 'rgba(245, 158, 11, 0.1)' : 'rgba(16, 185, 129, 0.1)',
            color: isStub ? '#92400e' : '#065f46',
          }}>
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: isStub ? 'var(--status-warning)' : 'var(--status-success)',
            }} />
            {tLlmMode(data.llm_mode)}
          </span>
        </div>
        <div style={{ padding: 'var(--space-5)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '16px' }}>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>运行模式</div>
              <div style={{ fontWeight: 600, color: isStub ? 'var(--warning)' : 'var(--success)' }}>
                {isStub ? '演示模式' : '真实模式'}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {isStub ? '返回占位内容' : '调用外部 API'}
              </div>
            </div>
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
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>配置文件</div>
              <div style={{ fontWeight: 600 }}>
                {data.config_path || '未指定'}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                当前 API 进程实际加载
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>数据库</div>
              <div style={{ fontWeight: 600 }}>
                {data.db_path || '-'}
              </div>
            </div>
          </div>
          {isStub && (
            <div style={{ padding: '12px', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              <strong>当前为演示模式</strong>
              <div style={{ marginTop: '4px' }}>
                未配置真实 LLM，所有生成操作使用占位符返回。如需真实生成，请使用下方配置草案生成器配置 LLM 并以 --llm-mode real 启动。
              </div>
            </div>
          )}
          {!data.diagnostics.has_profiles && !isStub && (
            <div style={{ padding: '12px', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              提示：暂无 LLM 档案。使用下方「配置草案生成器」生成草案，保存到 config/local.yaml 后重启服务即可启用真实 LLM。
            </div>
          )}
          {!isStub && data.diagnostics.has_profiles && (
            <div style={{ padding: '12px', background: '#dbeafe', borderRadius: '6px', fontSize: '13px', color: '#1e40af' }}>
              <strong>真实模式提醒</strong>
              <div style={{ marginTop: '4px' }}>
                真实模式下每次生成会调用 LLM API，请关注用量和成本。建议在批量生成前先小规模测试。
              </div>
            </div>
          )}
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '12px' }}>
            启动命令：<code style={{ padding: '2px 6px', background: '#1f2937', color: '#f9fafb', borderRadius: '4px', fontSize: '11px' }}>
              novelos api --llm-mode real --config config/local.yaml
            </code>
          </div>
        </div>
      </div>

      {/* Generation Capability Diagnostics */}
      <div style={{
        background: 'var(--paper-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-flat)',
        border: '1px solid rgba(30, 58, 95, 0.06)',
        overflow: 'hidden',
        marginBottom: 'var(--space-6)',
      }}>
        <div style={{
          padding: 'var(--space-4) var(--space-5)',
          borderBottom: '1px solid rgba(30, 58, 95, 0.04)',
        }}>
          <h3 style={{
            fontFamily: 'var(--font-brand)',
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--font-semibold)',
            margin: 0,
          }}>生成记录健康度</h3>
        </div>
        <div style={{ padding: 'var(--space-5)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>最近生成状态</div>
              <div style={{ fontWeight: 600, color: data.generation_stats.test_result === 'success' ? 'var(--success)' : data.generation_stats.test_result === 'failed' ? 'var(--danger)' : 'var(--warning)' }}>
                {generationStatusLabel}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>成功率 (近 30 次)</div>
              <div style={{ fontWeight: 600 }}>{data.generation_stats.success_rate}%</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>平均生成时长</div>
              <div style={{ fontWeight: 600 }}>
                {data.generation_stats.avg_duration_seconds > 0
                  ? `${Math.floor(data.generation_stats.avg_duration_seconds / 60)}分${Math.round(data.generation_stats.avg_duration_seconds % 60)}秒`
                  : '-'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>总运行次数</div>
              <div style={{ fontWeight: 600 }}>{data.generation_stats.total_runs}</div>
            </div>
          </div>
          {data.generation_stats.test_result === 'pending' && !isStub && (
            <div style={{ marginTop: '16px', padding: '12px', background: '#fef3c7', borderRadius: '6px', fontSize: '13px', color: '#92400e' }}>
              尚无生成记录。运行一次章节生成后，此处将显示健康度统计。
            </div>
          )}
          {isStub && (
            <div style={{ marginTop: '16px', padding: '12px', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              演示模式下的生成记录统计。切换到真实模式后将显示实际 LLM 调用情况。
            </div>
          )}
        </div>
      </div>
        </>
      )}

      {activeSection === 'llm' && (
        <>
      {/* LLM Profiles */}
      <div style={{
        background: 'var(--paper-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-flat)',
        border: '1px solid rgba(30, 58, 95, 0.06)',
        overflow: 'hidden',
        marginBottom: 'var(--space-6)',
      }}>
        <div style={{
          padding: 'var(--space-4) var(--space-5)',
          borderBottom: '1px solid rgba(30, 58, 95, 0.04)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <h3 style={{
            fontFamily: 'var(--font-brand)',
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--font-semibold)',
            margin: 0,
          }}>LLM 档案</h3>
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-charcoal)' }}>
            默认: {data.default_llm || '未设置'}
          </span>
        </div>
        <div style={{ padding: 'var(--space-5)' }}>
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
                    <th>参数</th>
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
                        {profile.api_key_source && (
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            来源: {profile.api_key_source}
                          </div>
                        )}
                      </td>
                      <td>
                        {profile.has_base_url ? (
                          <span className="text-success">已配置</span>
                        ) : (
                          <span className="text-danger">未配置</span>
                        )}
                        {profile.resolved_base_url && (
                          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', maxWidth: 260, wordBreak: 'break-all' }}>
                            {profile.resolved_base_url}
                          </div>
                        )}
                        {profile.base_url_source && (
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            来源: {profile.base_url_source}
                          </div>
                        )}
                      </td>
                      <td>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          temperature: {profile.temperature ?? '-'}
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          max_tokens: {profile.max_tokens ?? '-'}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="暂无 LLM 档案"
              hint="使用配置草案生成器创建档案，或手动编辑配置文件。"
            />
          )}
        </div>
      </div>
        </>
      )}

      {activeSection === 'skills' && (
        <>
      {/* Skill Visibility */}
      <div style={{
        background: 'var(--paper-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-flat)',
        border: '1px solid rgba(30, 58, 95, 0.06)',
        overflow: 'hidden',
        marginBottom: 'var(--space-6)',
      }}>
        <div style={{
          padding: 'var(--space-4) var(--space-5)',
          borderBottom: '1px solid rgba(30, 58, 95, 0.04)',
        }}>
          <h3 style={{
            fontFamily: 'var(--font-brand)',
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--font-semibold)',
            margin: 0,
          }}>Skill 管理</h3>
        </div>
        <SkillVisibilityPanel />
      </div>
        </>
      )}

      {/* Agent Routes */}
      {activeSection === 'llm' && data.agent_routes.length > 0 && (
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

      {activeSection === 'draft' && (
        <>
      {/* Config Draft Generator */}
      <div style={{
        background: 'var(--paper-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-flat)',
        border: '1px solid rgba(30, 58, 95, 0.06)',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: 'var(--space-4) var(--space-5)',
          borderBottom: '1px solid rgba(30, 58, 95, 0.04)',
        }}>
          <h3 style={{
            fontFamily: 'var(--font-brand)',
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--font-semibold)',
            margin: 0,
            marginBottom: 'var(--space-1)',
          }}>配置草案生成器</h3>
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-charcoal)' }}>
            填写表单生成 YAML 草案（仅预览，不写入文件）
          </span>
        </div>
        <div style={{ padding: 'var(--space-5)' }}>
          <div style={{ marginBottom: '16px', fontSize: '14px', color: 'var(--text-secondary)' }}>
            根据表单生成配置草案，你需要：
            <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
              <li>将草案保存到 <code>config/local.yaml</code></li>
              <li>设置环境变量（如 <code>export OPENAI_API_KEY=your-key</code>）</li>
              <li>使用 <code>novelos api --config config/local.yaml --llm-mode real</code> 启动</li>
            </ol>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
            <div className="form-group">
              <label>提供商 (Provider)</label>
              <select
                className="form-control"
                value={wizardForm.provider}
                onChange={(e) => handleProviderChange(e.target.value)}
              >
                {PROVIDER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>模型</label>
              <select
                className="form-control"
                value={wizardForm.model}
                onChange={(e) => setWizardForm({ ...wizardForm, model: e.target.value })}
              >
                {MODEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              {wizardForm.model === 'custom' && (
                <>
                  <input
                    type="text"
                    className="form-control"
                    value={wizardForm.custom_model}
                    onChange={(e) => setWizardForm({ ...wizardForm, custom_model: e.target.value })}
                    placeholder="例如：Kimi-K2-Turbo"
                    style={{ marginTop: '8px' }}
                  />
                  <div className="hint">填写服务商实际支持的模型 ID，会写入配置草案的 model 字段</div>
                </>
              )}
            </div>
            <div className="form-group">
              <label>Base URL</label>
              <input
                type="text"
                className="form-control"
                value={wizardForm.base_url}
                onChange={(e) => setWizardForm({ ...wizardForm, base_url: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>API Key 环境变量名</label>
              <input
                type="text"
                className="form-control"
                value={wizardForm.api_key_env}
                onChange={(e) => setWizardForm({ ...wizardForm, api_key_env: e.target.value })}
              />
              <div className="hint">仅填写环境变量名，不要输入真实的 Key</div>
            </div>
            <div className="form-group">
              <label>Profile 名称</label>
              <input
                type="text"
                className="form-control"
                value={wizardForm.default_llm}
                onChange={(e) => setWizardForm({ ...wizardForm, default_llm: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Agent 路由（可选）</label>
              <input
                type="text"
                className="form-control"
                value={wizardForm.agent_llm}
                onChange={(e) => setWizardForm({ ...wizardForm, agent_llm: e.target.value })}
                placeholder="author=default,editor=default"
              />
              <div className="hint">格式: agent名=profile名，逗号分隔</div>
            </div>
          </div>

          <button onClick={handleGenerateDraft} className="btn btn-primary">
            生成配置草案
          </button>
          <button
            onClick={handleValidateConfig}
            className="btn btn-secondary"
            style={{ marginLeft: '8px' }}
            disabled={validating}
          >
            {validating ? '验证中...' : '验证配置'}
          </button>

          {validateResult && (
            <div
              style={{
                marginTop: '16px',
                padding: '12px',
                borderRadius: '6px',
                background: validateResult.valid ? '#dcfce7' : '#fef2f2',
                color: validateResult.valid ? '#166534' : '#991b1b',
              }}
            >
              <strong>{validateResult.valid ? '✓ 验证成功' : `✗ ${validateResult.error_code || '验证失败'}`}</strong>
              <div style={{ marginTop: '4px', fontSize: '13px' }}>{validateResult.message}</div>
            </div>
          )}

          {draft && (
            <div style={{ marginTop: '16px' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '8px',
              }}>
                <h4 style={{ margin: 0 }}>配置草案预览</h4>
                <span style={{
                  fontSize: '12px',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  background: '#fef3c7',
                  color: '#92400e',
                  fontWeight: 500,
                }}>
                  未应用
                </span>
              </div>
              <div style={{
                padding: '10px 12px',
                background: '#fffbeb',
                borderRadius: '6px',
                fontSize: '13px',
                color: '#92400e',
                marginBottom: '12px',
                border: '1px solid #fcd34d',
              }}>
                <strong>此草案尚未写入配置文件。</strong>
                <div style={{ marginTop: '4px' }}>
                  如需生效，请将草案保存到 <code>config/local.yaml</code>，然后重启 API 服务。
                </div>
              </div>
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
        </>
      )}
    </div>
  )
}
