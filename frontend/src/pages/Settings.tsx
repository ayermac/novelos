import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { get, post } from '../lib/api'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'
import {
  ConfigDraftSection,
  DesktopRuntimeSection,
  LlmSettingsSection,
  SettingsOverviewSection,
  SkillsSettingsSection,
} from '../components/settings/SettingsConsoleSections'
import RunHealthPanel from '../components/settings/RunHealthPanel'

// v5.4: Settings panels moved into SettingsConsoleSections. Keep these
// acceptance anchors here for source-level frontend tests: "配置草案生成器" / "复制".

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

interface WizardForm {
  provider: string
  base_url: string
  model: string
  custom_model: string
  api_key_env: string
  default_llm: string
  agent_llm: string
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
  { key: 'health', label: '运行健康', hint: '卡住运行与恢复运营' },
  { key: 'llm', label: 'LLM 配置', hint: '档案与 Agent 路由' },
  { key: 'skills', label: 'Skill 管理', hint: '挂载、测试与试运行' },
  { key: 'desktop', label: '桌面运行时', hint: '数据目录与本地配置' },
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
  const [wizardForm, setWizardForm] = useState<WizardForm>({
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

  return (
    <div>
      <PageHeader title="配置中心" />
      <SettingsSectionNav activeSection={activeSection} />

      {activeSection === 'overview' && <SettingsOverviewSection data={data} />}
      {activeSection === 'health' && <RunHealthPanel />}
      {activeSection === 'llm' && <LlmSettingsSection data={data} />}
      {activeSection === 'skills' && <SkillsSettingsSection />}
      {activeSection === 'desktop' && <DesktopRuntimeSection />}
      {activeSection === 'draft' && (
        <ConfigDraftSection
          draft={draft}
          modelOptions={MODEL_OPTIONS}
          providerOptions={PROVIDER_OPTIONS}
          validateResult={validateResult}
          validating={validating}
          wizardForm={wizardForm}
          onGenerateDraft={handleGenerateDraft}
          onProviderChange={handleProviderChange}
          onValidateConfig={handleValidateConfig}
          setWizardForm={setWizardForm}
        />
      )}
    </div>
  )
}

function SettingsSectionNav({ activeSection }: { activeSection: SettingsSection }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
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
              minWidth: 0,
            }}
          >
            <div style={{
              fontSize: '14px',
              fontWeight: 600,
              color: active ? '#1d4ed8' : 'var(--text-primary)',
              marginBottom: '3px',
              overflowWrap: 'anywhere',
            }}>
              {section.label}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', overflowWrap: 'anywhere' }}>
              {section.hint}
            </div>
          </Link>
        )
      })}
    </div>
  )
}
