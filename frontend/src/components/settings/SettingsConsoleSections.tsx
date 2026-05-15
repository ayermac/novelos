import type { Dispatch, ReactNode, SetStateAction } from 'react'
import React, { useEffect, useState } from 'react'
import EmptyState from '../EmptyState'
import SkillVisibilityPanel from './SkillVisibilityPanel'
import { tLlmMode } from '../../lib/i18n'
import { DataTable, FormField, NumberInput, Select, TextInput } from '../ui'
import { get, post, put } from '../../lib/api'
import { useAppDialog } from '../AppDialogContext'

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

interface ValidateResult {
  valid: boolean
  message: string
  error_code?: string
}

interface Option {
  value: string
  label: string
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
  return (
    <>
      <SectionCard title="LLM 档案" subtitle={`默认: ${data.default_llm || '未设置'}`}>
        <div style={{ padding: 'var(--space-5)' }}>
          {data.llm_profiles.length > 0 ? (
            <DataTable
              compact
              data={data.llm_profiles}
              getRowKey={(profile) => profile.name}
              columns={[
                { key: 'name', header: '名称', render: (profile) => profile.name },
                { key: 'provider', header: '提供商', render: (profile) => profile.provider },
                { key: 'model', header: '模型', render: (profile) => profile.model },
                {
                  key: 'apiKey',
                  header: 'API Key',
                  render: (profile) => (
                    <>
                      {profile.has_key ? <span className="text-success">已配置</span> : <span className="text-danger">未配置</span>}
                      {profile.api_key_env && <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>变量: {profile.api_key_env}</div>}
                      {profile.api_key_source && <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>来源: {profile.api_key_source}</div>}
                    </>
                  ),
                },
                {
                  key: 'baseUrl',
                  header: 'Base URL',
                  render: (profile) => (
                    <>
                      {profile.has_base_url ? <span className="text-success">已配置</span> : <span className="text-danger">未配置</span>}
                      {profile.resolved_base_url && (
                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)', maxWidth: 260, wordBreak: 'break-all' }}>
                          {profile.resolved_base_url}
                        </div>
                      )}
                      {profile.base_url_source && <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>来源: {profile.base_url_source}</div>}
                    </>
                  ),
                },
                {
                  key: 'params',
                  header: '参数',
                  render: (profile) => (
                    <>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>temperature: {profile.temperature ?? '-'}</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>max_tokens: {profile.max_tokens ?? '-'}</div>
                    </>
                  ),
                },
              ]}
            />
          ) : (
            <EmptyState
              title="暂无 LLM 档案"
              hint="使用配置草案生成器创建档案，或手动编辑配置文件。"
            />
          )}
        </div>
      </SectionCard>

      {data.agent_routes.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
          <div className="card-header">
            <h3>Agent 路由</h3>
          </div>
          <div className="card-body">
            <DataTable
              compact
              data={data.agent_routes}
              getRowKey={(route) => route.agent}
              columns={[
                { key: 'agent', header: 'Agent', render: (route) => route.agent },
                { key: 'route', header: 'LLM Profile', render: (route) => route.route },
              ]}
            />
          </div>
        </div>
      )}
    </>
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
  const dialog = useAppDialog()

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
        await dialog.alert({ title: '重启成功', message: '本地服务已重启。', tone: 'success' })
      } else {
        await dialog.alert({ title: '重启失败', message: '本地服务未能成功重启，请检查日志。', tone: 'danger' })
      }
    } catch (err) {
      await dialog.alert({ title: '重启失败', message: `错误: ${(err as Error).message}`, tone: 'danger' })
    }
    setRestarting(false)
    load()
  }

  if (loading) {
    return (
      <SectionCard title="桌面运行时">
        <div style={{ padding: 'var(--space-5)', color: 'var(--text-secondary)' }}>加载中...</div>
      </SectionCard>
    )
  }

  return (
    <>
      <SectionCard
        title="桌面运行时"
        subtitle={isDesktop ? 'Electron 桌面模式' : '浏览器模式'}
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
              <button className="btn btn-warning" onClick={handleRestart} disabled={restarting}>
                {restarting ? '重启中...' : '重启本地服务'}
              </button>
            </div>
          )}

          {!isDesktop && (
            <div style={{ padding: '12px', background: 'var(--bg-secondary)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              浏览器模式下无法打开本地目录。如需完整桌面功能，请使用 Novelos 桌面应用。
            </div>
          )}
        </div>
      </SectionCard>

      <DesktopConfigSection />
    </>
  )
}

function DesktopApiKeyCard({
  apiKeyEnv,
  apiKeySource,
  localSecretConfigured,
  onRefresh,
}: {
  apiKeyEnv: string
  apiKeySource: string
  localSecretConfigured: boolean
  onRefresh: () => void
}) {
  const dialog = useAppDialog()
  const [inputValue, setInputValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  const statusLabel = localSecretConfigured
    ? apiKeySource === 'desktop_secure_storage'
      ? '已安全保存'
      : '已安全保存（重启后生效）'
    : apiKeySource === 'desktop_secure_storage'
      ? '当前会话已注入（本机存储已删除，重启后失效）'
      : apiKeySource === 'environment'
        ? '来自环境变量'
        : '未配置'

  const statusColor =
    localSecretConfigured || apiKeySource === 'desktop_secure_storage'
      ? 'var(--success)'
      : apiKeySource === 'environment'
        ? '#1d4ed8'
        : 'var(--danger)'
  const canDeleteLocalSecret = localSecretConfigured || apiKeySource === 'desktop_secure_storage'

  const handleSave = async () => {
    if (!inputValue.trim()) return
    setSaving(true)
    setMessage('')
    try {
      await window.__NOVELOS_DESKTOP__?.setApiKey?.(apiKeyEnv, inputValue.trim())
      setInputValue('')
      setMessage('已保存，重启客户端后生效')
      onRefresh()
    } catch (err) {
      setMessage(`保存失败: ${(err as Error).message}`)
    }
    setSaving(false)
  }

  const handleDelete = async () => {
    const ok = await dialog.confirm({
      title: '删除本地保存的 API Key',
      message: `确定要删除 ${apiKeyEnv} 的本地安全存储吗？此操作不可恢复。`,
      tone: 'danger',
      confirmLabel: '删除',
    })
    if (!ok) return
    setSaving(true)
    setMessage('')
    try {
      await window.__NOVELOS_DESKTOP__?.deleteApiKey?.(apiKeyEnv)
      setMessage('已删除，重启客户端后生效')
      onRefresh()
    } catch (err) {
      setMessage(`删除失败: ${(err as Error).message}`)
    }
    setSaving(false)
  }

  return (
    <div style={{ marginTop: '16px', padding: '16px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
      <div style={{ marginBottom: '12px' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '4px' }}>API Key 安全存储</div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          环境变量: <code>{apiKeyEnv}</code>
        </div>
        <div style={{ fontSize: '12px', color: statusColor, fontWeight: 600, marginTop: '4px' }}>
          状态: {statusLabel}
        </div>
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
        <TextInput
          type="password"
          placeholder="输入 API Key"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          disabled={saving}
          style={{ minWidth: '240px', flex: 1 }}
        />
        <button className="btn btn-primary" onClick={handleSave} disabled={saving || !inputValue.trim()}>
          保存到本机安全存储
        </button>
        <button className="btn btn-danger" onClick={handleDelete} disabled={saving || !canDeleteLocalSecret}>
          删除本机保存的 Key
        </button>
      </div>

      {message && (
        <div style={{
          marginTop: '10px',
          padding: '8px 12px',
          borderRadius: '6px',
          fontSize: '12px',
          background: message.includes('失败') ? '#fef2f2' : '#dcfce7',
          color: message.includes('失败') ? '#991b1b' : '#166534',
        }}>
          {message}
        </div>
      )}
    </div>
  )
}

function DesktopConfigSection() {
  const isDesktop = typeof window !== 'undefined' && !!window.__NOVELOS_DESKTOP__
  const [config, setConfig] = useState<{
    exists: boolean
    llm_mode: string
    default_llm: string | null
    profiles: Record<string, {
      provider: string
      model: string
      base_url: string
      api_key_env: string
      api_key_configured: boolean
      api_key_source: string
      temperature: number
      max_tokens: number
    }>
  } | null>(null)
  const [secretStatuses, setSecretStatuses] = useState<Record<string, { configured: boolean; storage: string }>>({})
  const [draft, setDraft] = useState({
    llm_mode: 'stub',
    model: '',
    base_url: '',
    temperature: 0.7,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ valid: boolean; message: string; error_code?: string } | null>(null)

  const load = React.useCallback(async () => {
    if (!isDesktop) {
      setLoading(false)
      return
    }
    setLoading(true)
    const res = await get<typeof config>('/desktop/config')
    if (res.ok && res.data) {
      setConfig(res.data)
      const defaultProfileName = res.data.default_llm || Object.keys(res.data.profiles || {})[0] || 'default'
      const profile = res.data.profiles?.[defaultProfileName]
      setDraft({
        llm_mode: res.data.llm_mode || 'stub',
        model: profile?.model || '',
        base_url: profile?.base_url || '',
        temperature: profile?.temperature ?? 0.7,
      })
    } else {
      setMessage(res.error?.message || '桌面配置不可用')
    }
    try {
      const statuses = await window.__NOVELOS_DESKTOP__?.secretStatus?.()
      if (statuses) {
        setSecretStatuses(statuses)
      }
    } catch {
      setSecretStatuses({})
    }
    setLoading(false)
  }, [isDesktop])

  useEffect(() => {
    load()
  }, [load])

  const handleSave = async () => {
    if (!isDesktop) return
    setSaving(true)
    setMessage('')
    const res = await put('/desktop/config', draft)
    setSaving(false)
    if (res.ok) {
      setMessage('已保存')
      await load()
    } else {
      setMessage(res.error?.message || '保存失败')
    }
  }

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      if (draft.llm_mode === 'stub') {
        setTestResult({ valid: false, message: '当前为演示模式 (stub)。请切换为真实模式 (real) 并保存，然后重启客户端后测试。', error_code: 'STUB_MODE' })
        setTesting(false)
        return
      }
      const profileKey = config?.default_llm || Object.keys(config?.profiles || {})[0] || 'default'
      const profile = config?.profiles?.[profileKey]
      if (!profile) {
        setTestResult({ valid: false, message: '未找到 LLM 配置档案。', error_code: 'NO_PROFILE' })
        setTesting(false)
        return
      }
      if (!profile.api_key_configured) {
        setTestResult({ valid: false, message: `API Key 未配置 (${profile.api_key_env})。请先保存 API Key 并重启客户端。`, error_code: 'MISSING_API_KEY' })
        setTesting(false)
        return
      }
      const res = await post('/settings/validate', {
        provider: profile.provider || 'openai_compatible',
        base_url: draft.base_url || profile.base_url,
        model: draft.model || profile.model,
        api_key_env: profile.api_key_env,
      })
      if (res.ok && res.data) {
        const data = res.data as { valid: boolean; message: string; error_code?: string }
        setTestResult(data)
      } else {
        setTestResult({ valid: false, message: res.error?.message || '测试请求失败', error_code: 'REQUEST_FAILED' })
      }
    } catch (err) {
      setTestResult({ valid: false, message: `测试异常: ${(err as Error).message}`, error_code: 'EXCEPTION' })
    }
    setTesting(false)
  }

  if (loading) {
    return (
      <SectionCard title="桌面配置">
        <div style={{ padding: 'var(--space-5)', color: 'var(--text-secondary)' }}>加载中...</div>
      </SectionCard>
    )
  }

  if (!isDesktop) {
    return (
      <SectionCard title="桌面配置" subtitle="仅桌面应用可用">
        <div style={{ padding: 'var(--space-5)', color: 'var(--text-secondary)' }}>
          浏览器模式下不会读取或修改本地桌面配置。请在 Novelos 桌面应用中使用此功能。
        </div>
      </SectionCard>
    )
  }

  const defaultProfileName = config?.default_llm || Object.keys(config?.profiles || {})[0] || 'default'
  const profile = config?.profiles?.[defaultProfileName]
  const apiKeyEnv = profile?.api_key_env || 'OPENAI_API_KEY'
  const localSecretConfigured = !!secretStatuses[apiKeyEnv]?.configured

  return (
    <SectionCard title="桌面配置" subtitle="安全字段编辑（不包含 API Key）">
      <div style={{ padding: 'var(--space-5)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px', marginBottom: '16px' }}>
          <FormField label="LLM 模式">
            <Select
              value={draft.llm_mode}
              onChange={(e) => setDraft((prev) => ({ ...prev, llm_mode: e.target.value }))}
              disabled={saving}
            >
              <option value="stub">演示模式 (stub)</option>
              <option value="real">真实模式 (real)</option>
            </Select>
          </FormField>
          {profile && (
            <>
              <FormField label="模型">
                <TextInput
                  value={draft.model}
                  onChange={(e) => setDraft((prev) => ({ ...prev, model: e.target.value }))}
                  disabled={saving}
                />
              </FormField>
              <FormField label="Base URL">
                <TextInput
                  value={draft.base_url}
                  onChange={(e) => setDraft((prev) => ({ ...prev, base_url: e.target.value }))}
                  disabled={saving}
                />
              </FormField>
              <FormField label="Temperature">
                <NumberInput
                  min="0"
                  max="2"
                  step="0.1"
                  value={draft.temperature}
                  onChange={(e) => setDraft((prev) => ({ ...prev, temperature: parseFloat(e.target.value) }))}
                  disabled={saving}
                />
              </FormField>
            </>
          )}
        </div>

        {message && (
          <div style={{
            marginTop: '8px',
            padding: '10px 12px',
            borderRadius: '6px',
            fontSize: '13px',
            background: message === '已保存' ? '#dcfce7' : '#fef2f2',
            color: message === '已保存' ? '#166534' : '#991b1b',
          }}>
            {message}
          </div>
        )}

        <div style={{ marginTop: '12px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving || !profile}>
            {saving ? '保存中...' : '保存配置'}
          </button>
          <button className="btn btn-secondary" onClick={handleTestConnection} disabled={testing || !profile}>
            {testing ? '测试中...' : '测试 LLM 连接'}
          </button>
        </div>

        {testResult && (
          <div style={{
            marginTop: '12px',
            padding: '10px 12px',
            borderRadius: '6px',
            fontSize: '13px',
            background: testResult.valid ? '#dcfce7' : '#fef2f2',
            color: testResult.valid ? '#166534' : '#991b1b',
          }}>
            <strong>{testResult.valid ? '✓ 测试成功' : `✗ ${testResult.error_code || '测试失败'}`}</strong>
            <div style={{ marginTop: '4px' }}>{testResult.message}</div>
          </div>
        )}

        {profile && (
          <DesktopApiKeyCard
            apiKeyEnv={apiKeyEnv}
            apiKeySource={profile.api_key_source}
            localSecretConfigured={localSecretConfigured}
            onRefresh={load}
          />
        )}
      </div>
    </SectionCard>
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

        <button onClick={onGenerateDraft} className="btn btn-primary">
          生成配置草案
        </button>
        <button
          onClick={onValidateConfig}
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
    </SectionCard>
  )
}
