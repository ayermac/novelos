import type { Dispatch, ReactNode, SetStateAction } from 'react'
import React, { useEffect, useState } from 'react'
import EmptyState from '../EmptyState'
import SkillVisibilityPanel from './SkillVisibilityPanel'
import { tLlmMode } from '../../lib/i18n'
import { FormField, Select, TextInput, NumberInput, LoadingButton, InlineMessage, SkeletonStack, useToast } from '../ui'
import { get, post, put } from '../../lib/api'
import { useAppDialog } from '../AppDialogContext'
import { CheckCircle2, KeyRound, Plus, RefreshCw, Router, Server, Trash2, Wifi } from 'lucide-react'
import './SettingsConsoleSections.css'

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

interface DesktopProfile {
  provider: string
  model: string
  base_url: string
  api_key_env: string
  api_key_configured: boolean
  api_key_source: string
  temperature?: number
  timeout?: number
  request_timeout_seconds?: number
}

interface DesktopConfig {
  exists: boolean
  llm_mode: string
  configured_llm_mode?: string
  runtime_llm_mode?: string
  default_llm: string | null
  profiles: Record<string, DesktopProfile>
  agent_llm?: Record<string, string>
  agent_llm_fallback?: Record<string, string>
}

interface LlmTemplateForm {
  id: string
  name: string
  provider: string
  base_url: string
  model: string
  api_key_env: string
  temperature: number
  request_timeout_seconds: number
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

interface ValidateResult {
  valid: boolean
  message: string
  error_code?: string
}

interface Option {
  value: string
  label: string
}

type ApiKeySecretStatus = {
  configured: boolean
  storage?: string
}

type ApiKeySource = 'desktop_secure_storage' | 'environment' | 'missing'

const AGENT_OPTIONS = [
  { id: 'genesis', label: '创世设定', hint: '项目底盘、世界观、角色原型' },
  { id: 'planner', label: '章节规划', hint: '章节目标、关键事件、铺垫' },
  { id: 'screenwriter', label: '分场编剧', hint: '场景节拍和行动结构' },
  { id: 'author', label: '执笔撰写', hint: '长文本正文生成，建议使用最强写作模型' },
  { id: 'polisher', label: '润色修订', hint: '对白、节奏、去 AI 味' },
  { id: 'editor', label: '质量审核', hint: '评分、问题定位、发布建议' },
  { id: 'memory_curator', label: '记忆整理', hint: '事实、伏笔、连续性沉淀' },
] as const

const TEMPLATE_PROVIDER_OPTIONS = [
  { value: 'openai_compatible', label: 'OpenAI 兼容接口' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'anthropic', label: 'Anthropic' },
]

const PROVIDER_PRESETS: Record<string, Pick<LlmTemplateForm, 'provider' | 'base_url' | 'model' | 'api_key_env'>> = {
  default: {
    provider: 'openai_compatible',
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
    api_key_env: 'OPENAI_API_KEY',
  },
  author: {
    provider: 'openai_compatible',
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-4o',
    api_key_env: 'OPENAI_API_KEY',
  },
}

const COMMON_API_KEY_ENVS = [
  'OPENAI_API_KEY',
  'FREEMODEL_API_KEY',
] as const

let templateIdCounter = 0

function createTemplateId(seed = 'template'): string {
  templateIdCounter += 1
  const safeSeed = seed.replace(/[^A-Za-z0-9_-]/g, '') || 'template'
  return `${safeSeed}-${templateIdCounter}`
}

function normalizePositiveInt(value: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback
  return Math.max(1, Math.round(value))
}

function isLocalSecureSecret(status?: ApiKeySecretStatus): boolean {
  if (!status?.configured) return false
  return !status.storage || ['desktop_secure_storage', 'electron_safe_storage'].includes(status.storage)
}

function getApiKeySourceForEnv(
  envName: string,
  desktopConfig: DesktopConfig | null,
  secretStatuses: Record<string, ApiKeySecretStatus>,
): ApiKeySource {
  if (isLocalSecureSecret(secretStatuses[envName])) {
    return 'desktop_secure_storage'
  }

  const profileSources = Object.values(desktopConfig?.profiles || {})
    .filter((profile) => profile.api_key_env === envName)
    .map((profile) => profile.api_key_source)

  if (profileSources.includes('environment')) {
    return 'environment'
  }
  return 'missing'
}

function SectionCard({ title, subtitle, action, children }: {
  title: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
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
        <div>
          <h3 style={{
            fontFamily: 'var(--font-brand)',
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--font-semibold)',
            margin: 0,
            marginBottom: subtitle ? 'var(--space-1)' : 0,
          }}>{title}</h3>
          {subtitle && (
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-charcoal)' }}>
              {subtitle}
            </span>
          )}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

export function SettingsOverviewSection({ data }: { data: SettingsData }) {
  const isStub = data.llm_mode === 'stub'
  const generationStatusLabel = data.generation_stats.test_result === 'success'
    ? '健康'
    : data.generation_stats.test_result === 'failed'
      ? '异常'
      : data.generation_stats.total_runs > 0
        ? '有记录'
        : '无记录'

  return (
    <>
      <SectionCard
        title="能力诊断"
        action={
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
        }
      >
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
              <div style={{ fontWeight: 600 }}>{data.config_path || '未指定'}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                当前 API 进程实际加载
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>数据库</div>
              <div style={{ fontWeight: 600 }}>{data.db_path || '-'}</div>
            </div>
          </div>
          {isStub && (
            <div style={{ padding: '12px', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              <strong>当前为演示模式</strong>
              <div style={{ marginTop: '4px' }}>
                未配置真实 LLM，所有生成操作使用占位符返回。如需真实生成，请使用配置草案生成器配置 LLM 并以 --llm-mode real 启动。
              </div>
            </div>
          )}
          {!data.diagnostics.has_profiles && !isStub && (
            <div style={{ padding: '12px', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              提示：暂无 LLM 档案。使用「配置草案生成器」生成草案，保存到 config/local.yaml 后重启服务即可启用真实 LLM。
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
      </SectionCard>

      <SectionCard title="生成记录健康度">
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
      </SectionCard>
    </>
  )
}

export function LlmSettingsSection({ data }: { data: SettingsData }) {
  const isDesktop = typeof window !== 'undefined' && !!window.__NOVELOS_DESKTOP__
  const dialog = useAppDialog()
  const { showToast } = useToast()
  const [desktopConfig, setDesktopConfig] = useState<DesktopConfig | null>(null)
  const [secretStatuses, setSecretStatuses] = useState<Record<string, ApiKeySecretStatus>>({})
  const [loading, setLoading] = useState(isDesktop)
  const [saving, setSaving] = useState(false)
  const [savingKeyFor, setSavingKeyFor] = useState<string | null>(null)
  const [testingProfile, setTestingProfile] = useState<string | null>(null)
  const [restarting, setRestarting] = useState(false)
  const [restartRequired, setRestartRequired] = useState(false)
  const [inlineMsg, setInlineMsg] = useState<{ variant: 'success' | 'warning' | 'danger'; text: string } | null>(null)
  const [templates, setTemplates] = useState<LlmTemplateForm[]>([])
  const [defaultTemplate, setDefaultTemplate] = useState(data.default_llm || 'default')
  const [agentRoutes, setAgentRoutes] = useState<Record<string, string>>({})
  const [agentFallbackRoutes, setAgentFallbackRoutes] = useState<Record<string, string>>({})
  const [apiKeyDrafts, setApiKeyDrafts] = useState<Record<string, string>>({})
  const [customApiKeyEnvs, setCustomApiKeyEnvs] = useState<string[]>([])
  const [newApiKeyEnv, setNewApiKeyEnv] = useState('')

  const loadDesktopConfig = React.useCallback(async () => {
    if (!isDesktop) {
      setLoading(false)
      return
    }
    setLoading(true)
    const res = await get<DesktopConfig>('/desktop/config')
    if (res.ok && res.data) {
      const cfg = res.data
      setDesktopConfig(cfg)
      const profiles = Object.entries(cfg.profiles || {})
      const nextTemplates = profiles.length > 0
        ? profiles.map(([name, profile]) => ({
            id: createTemplateId(name),
            name,
            provider: profile.provider || 'openai_compatible',
            base_url: profile.base_url || '',
            model: profile.model || '',
            api_key_env: profile.api_key_env || 'OPENAI_API_KEY',
            temperature: profile.temperature ?? 0.7,
            request_timeout_seconds: profile.request_timeout_seconds ?? profile.timeout ?? 60,
          }))
        : [{
            id: createTemplateId('default'),
            name: 'default',
            ...PROVIDER_PRESETS.default,
            temperature: 0.7,
            request_timeout_seconds: 300,
          }]
      const defaultName = cfg.default_llm || nextTemplates[0]?.name || 'default'
      setTemplates(nextTemplates)
      setDefaultTemplate(defaultName)
      setAgentRoutes(Object.fromEntries(AGENT_OPTIONS.map((agent) => [
        agent.id,
        cfg.agent_llm?.[agent.id] || defaultName,
      ])))
      setAgentFallbackRoutes(Object.fromEntries(AGENT_OPTIONS.map((agent) => [
        agent.id,
        cfg.agent_llm_fallback?.[agent.id] || '',
      ])))
    } else {
      setInlineMsg({ variant: 'danger', text: res.error?.message || '读取桌面 LLM 配置失败' })
    }
    try {
      const statuses = await window.__NOVELOS_DESKTOP__?.secretStatus?.()
      setSecretStatuses(statuses || {})
    } catch {
      setSecretStatuses({})
    }
    setLoading(false)
  }, [isDesktop])

  useEffect(() => {
    loadDesktopConfig()
  }, [loadDesktopConfig])

  const updateTemplate = (id: string, patch: Partial<LlmTemplateForm>) => {
    setTemplates((prev) => prev.map((template) => (
      template.id === id ? { ...template, ...patch } : template
    )))
  }

  const renameTemplate = (id: string, oldName: string, nextName: string) => {
    updateTemplate(id, { name: nextName })
    if (defaultTemplate === oldName) {
      setDefaultTemplate(nextName)
    }
    setAgentRoutes((prev) => Object.fromEntries(
      Object.entries(prev).map(([agent, route]) => [agent, route === oldName ? nextName : route]),
    ))
    setAgentFallbackRoutes((prev) => Object.fromEntries(
      Object.entries(prev).map(([agent, route]) => [agent, route === oldName ? nextName : route]),
    ))
  }

  const addTemplate = () => {
    const baseName = templates.some((template) => template.name === 'author') ? 'profile' : 'author'
    let name = baseName
    let suffix = 2
    while (templates.some((template) => template.name === name)) {
      name = `${baseName}${suffix}`
      suffix += 1
    }
    setTemplates((prev) => [
      ...prev,
      {
        id: createTemplateId(name),
        name,
        ...(PROVIDER_PRESETS[name] || PROVIDER_PRESETS.default),
        temperature: 0.7,
        request_timeout_seconds: name === 'author' ? 300 : 180,
      },
    ])
  }

  const removeTemplate = async (name: string) => {
    if (templates.length <= 1) return
    const ok = await dialog.confirm({
      title: '删除 LLM 模板',
      message: `确定删除模板 ${name}？使用它的 Agent 会切回 ${defaultTemplate}。`,
      tone: 'danger',
      confirmLabel: '删除',
    })
    if (!ok) return
    const fallback = name === defaultTemplate
      ? templates.find((template) => template.name !== name)?.name || 'default'
      : defaultTemplate
    setTemplates((prev) => prev.filter((template) => template.name !== name))
    setDefaultTemplate(fallback)
    setAgentRoutes((prev) => Object.fromEntries(
      Object.entries(prev).map(([agent, route]) => [agent, route === name ? fallback : route]),
    ))
    setAgentFallbackRoutes((prev) => Object.fromEntries(
      Object.entries(prev).map(([agent, route]) => [agent, route === name ? '' : route]),
    ))
  }

  const handleSaveConfig = async () => {
    const normalizedNames = templates.map((template) => template.name.trim()).filter(Boolean)
    if (new Set(normalizedNames).size !== normalizedNames.length) {
      setInlineMsg({ variant: 'danger', text: '模板名称不能重复或为空' })
      return
    }
    const profiles = Object.fromEntries(templates.map((template) => [
      template.name.trim(),
      {
        provider: template.provider,
        model: template.model.trim(),
        base_url: template.base_url.trim(),
        api_key_env: template.api_key_env.trim(),
        temperature: template.temperature,
        request_timeout_seconds: normalizePositiveInt(Number(template.request_timeout_seconds), 300),
      },
    ]))
    setSaving(true)
    setInlineMsg(null)
    const fallbackRoutesToSave: Record<string, string> = {}
    Object.entries(agentFallbackRoutes).forEach(([agent, profile]) => {
      if (profile && profile !== '') {
        fallbackRoutesToSave[agent] = profile
      }
    })

    const res = await put('/desktop/config', {
      llm_mode: 'real',
      default_llm: defaultTemplate,
      llm_profiles: profiles,
      agent_llm: agentRoutes,
      agent_llm_fallback: fallbackRoutesToSave,
    })
    setSaving(false)
    if (res.ok && res.data) {
      const payload = res.data as { restart_required?: boolean; message?: string }
      await loadDesktopConfig()
      setRestartRequired(Boolean(payload.restart_required) || desktopConfig?.runtime_llm_mode !== 'real')
      setInlineMsg({ variant: 'success', text: 'LLM 模板和 Agent 路由已保存，重启本地服务后生效。' })
      showToast({ tone: 'success', title: 'LLM 配置已保存', message: '模板和 Agent 路由已写入本地配置。' })
    } else {
      const msg = res.error?.message || '保存 LLM 配置失败'
      setInlineMsg({ variant: 'danger', text: msg })
      showToast({ tone: 'danger', title: '保存失败', message: msg })
    }
  }

  const handleSaveKey = async (envName: string) => {
    const value = apiKeyDrafts[envName]?.trim()
    if (!value) return
    setSavingKeyFor(envName)
    setInlineMsg(null)
    try {
      await window.__NOVELOS_DESKTOP__?.setApiKey?.(envName, value)
      setApiKeyDrafts((prev) => ({ ...prev, [envName]: '' }))
      const statuses = await window.__NOVELOS_DESKTOP__?.secretStatus?.()
      setSecretStatuses(statuses || {})
      setRestartRequired(true)
      const msg = `${envName} 的 API Key 已保存到本机安全存储，重启本地服务后可测试连接。`
      setInlineMsg({ variant: 'success', text: msg })
      showToast({ tone: 'success', title: 'API Key 已保存', message: msg })
    } catch (err) {
      const msg = `保存 API Key 失败: ${(err as Error).message}`
      setInlineMsg({ variant: 'danger', text: msg })
      showToast({ tone: 'danger', title: '保存失败', message: msg })
    }
    setSavingKeyFor(null)
  }

  const handleDeleteKey = async (envName: string) => {
    const ok = await dialog.confirm({
      title: '删除本机 API Key',
      message: `确定删除 ${envName} 的本机安全存储？使用它的模板重启后将无法调用真实 LLM。`,
      tone: 'danger',
      confirmLabel: '删除',
    })
    if (!ok) return
    setSavingKeyFor(envName)
    setInlineMsg(null)
    try {
      await window.__NOVELOS_DESKTOP__?.deleteApiKey?.(envName)
      const statuses = await window.__NOVELOS_DESKTOP__?.secretStatus?.()
      setSecretStatuses(statuses || {})
      setRestartRequired(true)
      const msg = `${envName} 的 API Key 已删除，重启本地服务后生效。`
      setInlineMsg({ variant: 'success', text: msg })
      showToast({ tone: 'success', title: 'API Key 已删除', message: msg })
    } catch (err) {
      const msg = `删除 API Key 失败: ${(err as Error).message}`
      setInlineMsg({ variant: 'danger', text: msg })
      showToast({ tone: 'danger', title: '删除失败', message: msg })
    }
    setSavingKeyFor(null)
  }

  const handleAddApiKeyEnv = () => {
    const envName = newApiKeyEnv.trim().toUpperCase()
    if (!envName) return
    if (!/^[A-Z0-9_]+$/.test(envName) || !envName.endsWith("_API_KEY")) {
      setInlineMsg({ variant: 'danger', text: 'API Key 环境变量名必须为大写字母、数字或下划线，并以 _API_KEY 结尾' })
      return
    }
    setCustomApiKeyEnvs((prev) => prev.includes(envName) ? prev : [...prev, envName])
    setNewApiKeyEnv('')
  }

  const handleTest = async (template: LlmTemplateForm) => {
    setTestingProfile(template.name)
    setInlineMsg(null)
    const res = await post<{
      ok: boolean
      message: string
      error_code?: string
      latency_ms?: number
      suggestion?: string
    }>('/desktop/test-llm', {
      provider: template.provider,
      base_url: template.base_url,
      model: template.model,
      api_key_env: template.api_key_env,
    })
    setTestingProfile(null)
    if (res.ok && res.data) {
      if (res.data.ok) {
        const msg = `${template.name} 连接成功${res.data.latency_ms ? `，延迟 ${res.data.latency_ms}ms` : ''}`
        setInlineMsg({ variant: 'success', text: msg })
        showToast({ tone: 'success', title: '连接成功', message: msg })
      } else {
        const msg = `${res.data.error_code || '连接失败'}：${res.data.message}${res.data.suggestion ? `。${res.data.suggestion}` : ''}`
        setInlineMsg({ variant: 'danger', text: msg })
        showToast({ tone: 'danger', title: '连接未通过', message: res.data.message })
      }
    } else {
      const msg = res.error?.message || '测试连接失败'
      setInlineMsg({ variant: 'danger', text: msg })
      showToast({ tone: 'danger', title: '测试失败', message: msg })
    }
  }

  const handleRestart = async () => {
    const ok = await dialog.confirm({
      title: '重启本地服务',
      message: '重启后会加载最新 LLM 模板、Agent 路由和安全存储中的 API Key。进行中的请求会中断。',
      tone: 'warning',
      confirmLabel: '重启',
    })
    if (!ok) return
    setRestarting(true)
    try {
      const res = await window.__NOVELOS_DESKTOP__?.restartSidecar?.()
      if (res?.success) {
        setRestartRequired(false)
        await loadDesktopConfig()
        setInlineMsg({ variant: 'success', text: '本地服务已重启，真实 LLM 配置已加载。' })
        showToast({ tone: 'success', title: '重启成功', message: '可以开始测试连接或生成章节。' })
      } else {
        const msg = '本地服务未能成功重启，请检查日志。'
        setInlineMsg({ variant: 'danger', text: msg })
        showToast({ tone: 'danger', title: '重启失败', message: msg })
      }
    } catch (err) {
      const msg = `重启失败: ${(err as Error).message}`
      setInlineMsg({ variant: 'danger', text: msg })
      showToast({ tone: 'danger', title: '重启失败', message: msg })
    }
    setRestarting(false)
  }

  if (!isDesktop) {
    return (
      <>
        <SectionCard title="模型配置" subtitle="当前为浏览器模式">
          <div style={{ padding: 'var(--space-5)' }}>
            <InlineMessage variant="warning">
              浏览器模式只能查看当前 API 进程配置；模板、API Key 安全存储和重启服务需要在桌面客户端中使用。
            </InlineMessage>
          </div>
        </SectionCard>
        <ReadonlyLlmSnapshot data={data} />
      </>
    )
  }

  if (loading) {
    return (
      <SectionCard title="模型配置">
        <div style={{ padding: 'var(--space-5)' }}>
          <SkeletonStack rows={5} />
        </div>
      </SectionCard>
    )
  }

  const runtimeMode = desktopConfig?.runtime_llm_mode || desktopConfig?.llm_mode || data.llm_mode
  const configuredMode = desktopConfig?.configured_llm_mode || desktopConfig?.llm_mode || runtimeMode
  const profileNames = templates.map((template) => template.name)
  const apiKeyEnvOptions = Array.from(new Set([
    ...COMMON_API_KEY_ENVS,
    ...Object.entries(secretStatuses)
      .filter(([, status]) => status.configured)
      .map(([envName]) => envName),
    ...customApiKeyEnvs,
    ...templates.map((template) => template.api_key_env).filter(Boolean),
  ]))

  return (
    <>
      <SectionCard
        title="模型配置"
        subtitle="用模板管理 API、API Key 和模型；每个 Agent 选择一个模板，不选则使用 default"
        action={
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 10px',
            borderRadius: 'var(--radius-full)',
            background: runtimeMode === 'real' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.13)',
            color: runtimeMode === 'real' ? 'var(--success)' : 'var(--warning)',
            fontSize: '12px',
            fontWeight: 700,
          }}>
            <Wifi size={14} />
            运行中：{runtimeMode === 'real' ? '真实 LLM' : '演示模式'}
            {configuredMode !== runtimeMode ? '（待重启）' : ''}
          </span>
        }
      >
        <div style={{ padding: 'var(--space-5)' }}>
          {inlineMsg && (
            <div style={{ marginBottom: 16 }}>
              <InlineMessage variant={inlineMsg.variant}>{inlineMsg.text}</InlineMessage>
            </div>
          )}

          <div style={{
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-primary)',
            padding: 16,
            marginBottom: 18,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12 }}>
              <div>
                <h4 style={{ margin: 0, fontSize: 16 }}>API Key 安全存储</h4>
                <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 3 }}>
                  API Key 按环境变量名单独保存；模板只选择要引用的环境变量名。
                </div>
              </div>
            </div>
            <div className="settings-api-key-grid">
              <div className="settings-api-key-header" aria-hidden="true">
                <span>环境变量名</span>
                <span>API Key</span>
                <span>保存</span>
                <span>删除</span>
              </div>
              {apiKeyEnvOptions.map((envName) => {
                const apiKeySource = getApiKeySourceForEnv(envName, desktopConfig, secretStatuses)
                const canDelete = apiKeySource === 'desktop_secure_storage'
                const statusText = apiKeySource === 'desktop_secure_storage'
                  ? `${envName} 已保存到本机安全存储`
                  : apiKeySource === 'environment'
                    ? `${envName} 来自系统环境变量，不能在这里删除`
                    : `${envName} 尚未保存`
                const deleteTitle = canDelete
                  ? `删除 ${envName} 的本机安全存储`
                  : apiKeySource === 'environment'
                    ? `${envName} 来自系统环境变量，请在系统环境中删除或修改`
                    : `${envName} 尚未保存本机 API Key`
                return (
                  <div
                    key={envName}
                    className="settings-api-key-row"
                  >
                    <FormField label="环境变量名">
                      <TextInput value={envName} readOnly />
                    </FormField>
                    <FormField
                      label="API Key"
                      helper={statusText}
                    >
                      <TextInput
                        aria-label={`${envName} API Key`}
                        type="password"
                        value={apiKeyDrafts[envName] || ''}
                        onChange={(e) => setApiKeyDrafts((prev) => ({ ...prev, [envName]: e.target.value }))}
                        placeholder="输入 API Key"
                      />
                    </FormField>
                    <div className="settings-api-key-action">
                      <LoadingButton
                        className="btn btn-secondary"
                        variant="secondary"
                        aria-label={`保存 ${envName}`}
                        loading={savingKeyFor === envName}
                        loadingText="保存中..."
                        onClick={() => handleSaveKey(envName)}
                        disabled={!apiKeyDrafts[envName]?.trim()}
                      >
                        <KeyRound size={14} />
                        保存 Key
                      </LoadingButton>
                    </div>
                    <div className="settings-api-key-action">
                      <LoadingButton
                        className="btn btn-secondary"
                        variant="secondary"
                        aria-label={`删除 ${envName}`}
                        title={deleteTitle}
                        loading={savingKeyFor === envName}
                        loadingText="删除中..."
                        onClick={() => handleDeleteKey(envName)}
                        disabled={!canDelete}
                      >
                        删除
                      </LoadingButton>
                    </div>
                  </div>
                )
              })}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'minmax(180px, 0.35fr) auto',
                  gap: 10,
                  alignItems: 'end',
                  paddingTop: 2,
                }}
              >
                <FormField label="新增环境变量名">
                  <TextInput
                    value={newApiKeyEnv}
                    onChange={(e) => setNewApiKeyEnv(e.target.value.toUpperCase())}
                    placeholder="CUSTOM_API_KEY"
                  />
                </FormField>
                <button className="btn btn-secondary" type="button" onClick={handleAddApiKeyEnv}>
                  添加 Key 名称
                </button>
              </div>
            </div>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.2fr) minmax(280px, 0.8fr)',
            gap: 18,
            alignItems: 'start',
          }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: 16 }}>LLM 模板</h4>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 3 }}>
                    每个模板包含一套 Base URL、API Key 环境变量和模型 ID。
                  </div>
                </div>
                <LoadingButton className="btn btn-secondary" variant="secondary" loading={false} onClick={addTemplate}>
                  <Plus size={14} style={{ marginRight: 4 }} />
                  新建模板
                </LoadingButton>
              </div>

              <div style={{ display: 'grid', gap: 14 }}>
                {templates.map((template) => {
                  const isDefault = template.name === defaultTemplate
                  const secretConfigured = Boolean(secretStatuses[template.api_key_env]?.configured)
                  const persistedProfile = desktopConfig?.profiles?.[template.name]
                  const activeKey = secretConfigured || persistedProfile?.api_key_configured
                  const canTest = runtimeMode === 'real' && !restartRequired && activeKey
                  return (
                    <div
                      key={template.id}
                      style={{
                        border: isDefault ? '1px solid rgba(118, 26, 52, 0.36)' : '1px solid var(--border-color)',
                        borderRadius: 'var(--radius-md)',
                        padding: 16,
                        background: isDefault ? 'rgba(118, 26, 52, 0.035)' : 'var(--bg-primary)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 14 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <Server size={18} style={{ color: 'var(--ink-accent)' }} />
                          <TextInput
                            aria-label={`${template.name} 模板名称`}
                            value={template.name}
                            onChange={(e) => renameTemplate(template.id, template.name, e.target.value)}
                            style={{ width: 150, fontWeight: 700 }}
                          />
                          {isDefault && (
                            <span style={{
                              borderRadius: 'var(--radius-full)',
                              padding: '3px 8px',
                              background: 'rgba(118, 26, 52, 0.11)',
                              color: 'var(--ink-accent)',
                              fontSize: 12,
                              fontWeight: 700,
                            }}>
                              default
                            </span>
                          )}
                          {activeKey && (
                            <span style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 4,
                              color: 'var(--success)',
                              fontSize: 12,
                              fontWeight: 700,
                            }}>
                              <CheckCircle2 size={13} />
                              Key 已保存
                            </span>
                          )}
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                          {!isDefault && (
                            <LoadingButton className="btn btn-secondary" variant="secondary" loading={false} onClick={() => setDefaultTemplate(template.name)}>
                              设为默认
                            </LoadingButton>
                          )}
                          <button
                            className="btn btn-secondary"
                            type="button"
                            onClick={() => removeTemplate(template.name)}
                            disabled={templates.length <= 1}
                            aria-label={`删除 ${template.name} 模板`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
                        <FormField label="服务商">
                          <Select value={template.provider} onChange={(e) => updateTemplate(template.id, { provider: e.target.value })}>
                            {TEMPLATE_PROVIDER_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </Select>
                        </FormField>
                        <FormField label="模型 ID">
                          <TextInput
                            value={template.model}
                            onChange={(e) => updateTemplate(template.id, { model: e.target.value })}
                            placeholder="gpt-4o-mini / kimi-k2 / deepseek-chat"
                          />
                        </FormField>
                        <FormField label="Base URL">
                          <TextInput
                            value={template.base_url}
                            onChange={(e) => updateTemplate(template.id, { base_url: e.target.value })}
                            placeholder="https://api.example.com/v1"
                          />
                        </FormField>
                        <FormField label="API Key 环境变量名">
                          <Select
                            aria-label={`${template.name} API Key 环境变量名`}
                            value={template.api_key_env}
                            onChange={(e) => updateTemplate(template.id, { api_key_env: e.target.value })}
                          >
                            {apiKeyEnvOptions.map((envName) => (
                              <option key={envName} value={envName}>{envName}</option>
                            ))}
                          </Select>
                        </FormField>
                        <FormField label="request_timeout_seconds">
                          <NumberInput
                            aria-label={`${template.name} request_timeout_seconds`}
                            min="1"
                            step="1"
                            value={template.request_timeout_seconds}
                            onChange={(e) => updateTemplate(template.id, {
                              request_timeout_seconds: normalizePositiveInt(Number(e.target.value), template.request_timeout_seconds),
                            })}
                          />
                        </FormField>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                        <LoadingButton
                          className="btn btn-secondary"
                          variant="secondary"
                          loading={testingProfile === template.name}
                          loadingText="测试中..."
                          onClick={() => handleTest(template)}
                          disabled={!canTest}
                        >
                          测试连接
                        </LoadingButton>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div style={{
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-primary)',
              padding: 16,
              position: 'sticky',
              top: 12,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Router size={18} style={{ color: 'var(--ink-accent)' }} />
                <div>
                  <h4 style={{ margin: 0, fontSize: 16 }}>Agent 使用哪个模板</h4>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 2 }}>
                    默认都走 default，需要时给 author/editor 单独分配。
                  </div>
                </div>
              </div>
              <div style={{ display: 'grid', gap: 10 }}>
                {AGENT_OPTIONS.map((agent) => (
                  <div
                    key={agent.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'minmax(0, 1fr) 150px',
                      gap: 10,
                      alignItems: 'center',
                      padding: '10px 0',
                      borderBottom: '1px solid var(--border-color)',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700 }}>{agent.label}</div>
                      <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 2 }}>{agent.hint}</div>
                    </div>
                    <Select
                      aria-label={`${agent.id} LLM 模板`}
                      value={agentRoutes[agent.id] || defaultTemplate}
                      onChange={(e) => setAgentRoutes((prev) => ({ ...prev, [agent.id]: e.target.value }))}
                    >
                      {profileNames.map((name) => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </Select>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border-color)' }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
                  备用模板（仅记忆整理）
                </div>
                {AGENT_OPTIONS.filter((a) => a.id === 'memory_curator').map((agent) => (
                  <div
                    key={`${agent.id}-fallback`}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'minmax(0, 1fr) 150px',
                      gap: 10,
                      alignItems: 'center',
                      padding: '8px 0',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700 }}>记忆整理备用模板</div>
                      <div style={{ color: 'var(--text-secondary)', fontSize: 11, marginTop: 2 }}>
                        主模型超时后自动切换
                      </div>
                    </div>
                    <Select
                      aria-label={`${agent.id} 备用 LLM 模板`}
                      value={agentFallbackRoutes[agent.id] || ''}
                      onChange={(e) => setAgentFallbackRoutes((prev) => ({ ...prev, [agent.id]: e.target.value }))}
                    >
                      <option value=''>不启用</option>
                      {profileNames.map((name) => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </Select>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
            <LoadingButton className="btn btn-primary" variant="primary" loading={saving} loadingText="保存中..." onClick={handleSaveConfig}>
              保存模型配置
            </LoadingButton>
            {(restartRequired || runtimeMode !== 'real' || configuredMode !== runtimeMode) && (
              <LoadingButton className="btn btn-warning" variant="warning" loading={restarting} loadingText="重启中..." onClick={handleRestart}>
                <RefreshCw size={14} style={{ marginRight: 4 }} />
                重启本地服务
              </LoadingButton>
            )}
            <button className="btn btn-secondary" type="button" onClick={loadDesktopConfig}>
              刷新状态
            </button>
          </div>

          {(restartRequired || runtimeMode !== 'real' || configuredMode !== runtimeMode) && (
            <div style={{ marginTop: 14 }}>
              <InlineMessage variant="warning">
                配置或 API Key 已更新，但当前后端仍未加载最新环境。请重启本地服务后再测试连接或生成章节。
              </InlineMessage>
            </div>
          )}
        </div>
      </SectionCard>
    </>
  )
}

function ReadonlyLlmSnapshot({ data }: { data: SettingsData }) {
  return (
    <SectionCard title="当前 API 进程配置" subtitle={`默认: ${data.default_llm || '未设置'}`}>
      <div style={{ padding: 'var(--space-5)' }}>
        {data.llm_profiles.length > 0 ? (
          <div style={{ display: 'grid', gap: 10 }}>
            {data.llm_profiles.map((profile) => (
              <div
                key={profile.name}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '160px minmax(0, 1fr) 120px',
                  gap: 12,
                  padding: 12,
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <strong>{profile.name}</strong>
                <span style={{ color: 'var(--text-secondary)', wordBreak: 'break-all' }}>{profile.resolved_base_url || '-'}</span>
                <span>{profile.model}</span>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="暂无 LLM 档案" hint="请在桌面客户端中创建 LLM 模板。" />
        )}
      </div>
    </SectionCard>
  )
}

export function SkillsSettingsSection() {
  return (
    <SectionCard title="Skill 管理">
      <SkillVisibilityPanel />
    </SectionCard>
  )
}

export function DesktopRuntimeSection() {
  const [info, setInfo] = useState<{
    is_desktop: boolean
    app_data_dir: string
    data_dir: string
    db_path: string
    config_path: string
    config_dir: string
    logs_dir: string
    backups_dir: string
    llm_mode: string
    config_exists: boolean
    db_exists: boolean
    platform: string
    version: string
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [healthOk, setHealthOk] = useState(false)
  const [runtimeStatus, setRuntimeStatus] = useState<{
    status: string
    pid: number | null
    apiBaseUrl: string
    port: number
    lastError: {
      exitCode: number | null
      signal: string | null
      timestamp: string
      reason: string
    } | null
    stdoutLogPath: string
    stderrLogPath: string
  } | null>(null)
  const [restarting, setRestarting] = useState(false)
  const [exportingDiagnostics, setExportingDiagnostics] = useState(false)
  const dialog = useAppDialog()
  const { showToast } = useToast()

  const load = React.useCallback(async () => {
    setLoading(true)
    const [runtimeRes, healthRes] = await Promise.all([
      get<typeof info>('/desktop/runtime-info'),
      get('/health'),
    ])
    if (runtimeRes.ok && runtimeRes.data) {
      setInfo(runtimeRes.data)
    }
    setHealthOk(healthRes.ok && (healthRes.data as { status?: string } | undefined)?.status === 'ok')
    if (window.__NOVELOS_DESKTOP__?.runtimeStatus) {
      try {
        const r = await window.__NOVELOS_DESKTOP__.runtimeStatus()
        setRuntimeStatus(r as typeof runtimeStatus)
      } catch {
        // ignore
      }
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const unsub = window.__NOVELOS_DESKTOP__?.onRuntimeStatus?.((s) => {
      setRuntimeStatus(s as typeof runtimeStatus)
      if (s.status === 'healthy') {
        setHealthOk(true)
      } else if (s.status === 'failed' || s.status === 'exited') {
        setHealthOk(false)
      }
    })
    return () => {
      unsub?.()
    }
  }, [])

  const isDesktop = typeof window !== 'undefined' && !!window.__NOVELOS_DESKTOP__

  const openDataDir = () => window.__NOVELOS_DESKTOP__?.openDataDir?.()
  const openConfigDir = () => window.__NOVELOS_DESKTOP__?.openConfigDir?.()
  const openLogsDir = () => window.__NOVELOS_DESKTOP__?.openLogsDir?.()

  const handleRestart = async () => {
    const ok = await dialog.confirm({
      title: '重启本地服务',
      message: '确定要重启本地后端服务吗？进行中的请求可能会中断。',
      tone: 'warning',
      confirmLabel: '重启',
    })
    if (!ok) return
    setRestarting(true)
    try {
      const res = await window.__NOVELOS_DESKTOP__?.restartSidecar?.()
      if (res?.success) {
        setHealthOk(true)
        showToast({ tone: 'success', title: '重启成功', message: '本地服务已重启。' })
      } else {
        showToast({ tone: 'danger', title: '重启失败', message: '本地服务未能成功重启，请检查日志。' })
      }
    } catch (err) {
      showToast({ tone: 'danger', title: '重启失败', message: `错误: ${(err as Error).message}` })
    }
    setRestarting(false)
    load()
  }

  const handleExportDiagnostics = async () => {
    setExportingDiagnostics(true)
    try {
      const res = await window.__NOVELOS_DESKTOP__?.exportDiagnostics?.()
      if (res?.success) {
        showToast({ tone: 'success', title: '诊断包已导出', message: `脱敏诊断包已保存到 ${res.path}` })
      } else {
        showToast({ tone: 'danger', title: '导出失败', message: res?.message || '未能生成诊断包，请检查日志目录权限。' })
      }
    } catch (err) {
      showToast({ tone: 'danger', title: '导出失败', message: `错误: ${(err as Error).message}` })
    }
    setExportingDiagnostics(false)
  }

  if (loading) {
    return (
      <SectionCard title="本地服务">
        <div style={{ padding: 'var(--space-5)' }}>
          <SkeletonStack rows={4} />
        </div>
      </SectionCard>
    )
  }

  return (
    <>
      <SectionCard
        title="本地服务"
        subtitle={isDesktop ? '桌面端 sidecar、数据目录与日志' : '浏览器模式'}
        action={
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 'var(--space-1)',
            padding: 'var(--space-1) var(--space-3)',
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--font-medium)',
            borderRadius: 'var(--radius-full)',
            background: healthOk ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
            color: healthOk ? '#065f46' : '#991b1b',
          }}>
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: healthOk ? 'var(--status-success)' : 'var(--status-danger)',
            }} />
            {healthOk ? '后端正常' : '后端异常'}
          </span>
        }
      >
        <div style={{ padding: 'var(--space-5)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px', marginBottom: '16px' }}>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>运行模式</div>
              <div style={{ fontWeight: 600 }}>{isDesktop ? '桌面应用' : '浏览器'}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>平台</div>
              <div style={{ fontWeight: 600 }}>{info?.platform || '-'}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>LLM 模式</div>
              <div style={{ fontWeight: 600 }}>{tLlmMode(info?.llm_mode || 'stub')}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>版本</div>
              <div style={{ fontWeight: 600 }}>{info?.version || '-'}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>配置文件</div>
              <div style={{ fontWeight: 600 }}>{info?.config_exists ? '存在' : '未创建'}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px', wordBreak: 'break-all' }}>{info?.config_path || '-'}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>数据库</div>
              <div style={{ fontWeight: 600 }}>{info?.db_exists ? '存在' : '未创建'}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px', wordBreak: 'break-all' }}>{info?.db_path || '-'}</div>
            </div>
            {isDesktop && runtimeStatus && (
              <>
                <div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Sidecar 状态</div>
                  <div style={{ fontWeight: 600, color: runtimeStatus.status === 'healthy' ? 'var(--success)' : 'var(--danger)' }}>
                    {runtimeStatus.status === 'healthy' ? '运行中' : runtimeStatus.status === 'starting' ? '启动中' : runtimeStatus.status === 'stopping' ? '停止中' : '已停止'}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>API 地址</div>
                  <div style={{ fontWeight: 600, fontSize: '12px', wordBreak: 'break-all' }}>{runtimeStatus.apiBaseUrl || '-'}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Sidecar PID</div>
                  <div style={{ fontWeight: 600 }}>{runtimeStatus.pid ?? '-'}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>日志路径</div>
                  <div style={{ fontWeight: 600, fontSize: '11px', wordBreak: 'break-all' }}>{runtimeStatus.stderrLogPath || '-'}</div>
                </div>
              </>
            )}
          </div>

          {isDesktop && runtimeStatus?.lastError && (
            <div style={{ marginBottom: '16px', padding: '12px', background: '#fef2f2', borderRadius: '6px', fontSize: '13px', color: '#991b1b' }}>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>最近错误</div>
              <div>{runtimeStatus.lastError.reason}</div>
              <div style={{ fontSize: '11px', color: '#b91c1c', marginTop: '4px' }}>
                时间: {new Date(runtimeStatus.lastError.timestamp).toLocaleString()}
                {runtimeStatus.lastError.exitCode !== null && ` · 退出码: ${runtimeStatus.lastError.exitCode}`}
                {runtimeStatus.lastError.signal && ` · 信号: ${runtimeStatus.lastError.signal}`}
              </div>
            </div>
          )}

          {isDesktop && (
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" onClick={openDataDir} disabled={!window.__NOVELOS_DESKTOP__?.openDataDir}>
                打开数据目录
              </button>
              <button className="btn btn-secondary" onClick={openConfigDir} disabled={!window.__NOVELOS_DESKTOP__?.openConfigDir}>
                打开配置目录
              </button>
              <button className="btn btn-secondary" onClick={openLogsDir} disabled={!window.__NOVELOS_DESKTOP__?.openLogsDir}>
                打开日志目录
              </button>
              <button className="btn btn-secondary" onClick={load}>
                刷新
              </button>
              <LoadingButton
                className="btn btn-warning"
                variant="warning"
                loading={restarting}
                loadingText="重启中..."
                onClick={handleRestart}
              >
                重启本地服务
              </LoadingButton>
              <LoadingButton
                className="btn btn-primary"
                variant="primary"
                loading={exportingDiagnostics}
                loadingText="导出中..."
                onClick={handleExportDiagnostics}
                disabled={!window.__NOVELOS_DESKTOP__?.exportDiagnostics}
              >
                导出诊断包
              </LoadingButton>
            </div>
          )}

          {!isDesktop && (
            <div style={{ padding: '12px', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              浏览器模式下无法打开本地目录。如需完整桌面功能，请使用 Novelos 桌面应用。
            </div>
          )}
        </div>
      </SectionCard>

    </>
  )
}

export function ConfigDraftSection({
  draft,
  modelOptions,
  providerOptions,
  validateResult,
  validating,
  wizardForm,
  onGenerateDraft,
  onProviderChange,
  onValidateConfig,
  setWizardForm,
}: {
  draft: string | null
  modelOptions: Option[]
  providerOptions: Option[]
  validateResult: ValidateResult | null
  validating: boolean
  wizardForm: WizardForm
  onGenerateDraft: () => void
  onProviderChange: (provider: string) => void
  onValidateConfig: () => void
  setWizardForm: Dispatch<SetStateAction<WizardForm>>
}) {
  const { showToast } = useToast()

  const handleCopyDraft = () => {
    if (!draft) return
    navigator.clipboard.writeText(draft)
    showToast({ tone: 'success', title: '已复制', message: '配置草案已复制到剪贴板' })
  }

  return (
    <SectionCard title="配置草案生成器" subtitle="填写表单生成 YAML 草案（仅预览，不写入文件）">
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
          <FormField label="提供商 (Provider)">
            <Select
              value={wizardForm.provider}
              onChange={(e) => onProviderChange(e.target.value)}
            >
              {providerOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </Select>
          </FormField>
          <FormField label="模型" helper={wizardForm.model === 'custom' ? '填写服务商实际支持的模型 ID，会写入配置草案的 model 字段' : undefined}>
            <Select
              value={wizardForm.model}
              onChange={(e) => setWizardForm({ ...wizardForm, model: e.target.value })}
            >
              {modelOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </Select>
            {wizardForm.model === 'custom' && (
              <TextInput
                  value={wizardForm.custom_model}
                  onChange={(e) => setWizardForm({ ...wizardForm, custom_model: e.target.value })}
                  placeholder="例如：Kimi-K2-Turbo"
                  style={{ marginTop: '8px' }}
                />
            )}
          </FormField>
          <FormField label="Base URL">
            <TextInput
              value={wizardForm.base_url}
              onChange={(e) => setWizardForm({ ...wizardForm, base_url: e.target.value })}
            />
          </FormField>
          <FormField label="API Key 环境变量名" helper="仅填写环境变量名，不要输入真实的 Key">
            <TextInput
              value={wizardForm.api_key_env}
              onChange={(e) => setWizardForm({ ...wizardForm, api_key_env: e.target.value })}
            />
          </FormField>
          <FormField label="Profile 名称">
            <TextInput
              value={wizardForm.default_llm}
              onChange={(e) => setWizardForm({ ...wizardForm, default_llm: e.target.value })}
            />
          </FormField>
          <FormField label="Agent 路由（可选）" helper="格式: agent名=profile名，逗号分隔">
            <TextInput
              value={wizardForm.agent_llm}
              onChange={(e) => setWizardForm({ ...wizardForm, agent_llm: e.target.value })}
              placeholder="author=default,editor=default"
            />
          </FormField>
        </div>

        <LoadingButton
          className="btn btn-primary"
          variant="primary"
          loading={false}
          onClick={onGenerateDraft}
        >
          生成配置草案
        </LoadingButton>
        <LoadingButton
          className="btn btn-secondary"
          variant="secondary"
          loading={validating}
          loadingText="验证中..."
          onClick={onValidateConfig}
          style={{ marginLeft: '8px' }}
        >
          验证配置
        </LoadingButton>

        {validateResult && (
          <div style={{ marginTop: 16 }}>
            <InlineMessage variant={validateResult.valid ? 'success' : 'danger'}>
              <strong>{validateResult.valid ? '✓ 验证成功' : `✗ ${validateResult.error_code || '验证失败'}`}</strong>
              <div style={{ marginTop: '4px', fontSize: '13px' }}>{validateResult.message}</div>
            </InlineMessage>
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
            <LoadingButton
              className="btn btn-secondary"
              variant="secondary"
              loading={false}
              onClick={handleCopyDraft}
            >
              复制草案
            </LoadingButton>
          </div>
        )}
      </div>
    </SectionCard>
  )
}
