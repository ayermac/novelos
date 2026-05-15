import { useEffect, useState, useCallback, useRef } from 'react'
import {
  DESKTOP_PROVIDER_PRESETS,
  getPresetById,
} from '../../lib/desktopProviderPresets'
import { get, post, put } from '../../lib/api'
import { useAppDialog } from '../AppDialogContext'
import { FormField, Select, TextInput, NumberInput } from '../ui'
import { ChevronDown, ChevronUp, Wifi, WifiOff, RefreshCw, Zap, AlertTriangle } from 'lucide-react'

type SetupStep =
  | 'checking'
  | 'prompt'
  | 'editing'
  | 'saving_config'
  | 'saving_key'
  | 'testing'
  | 'restart_required'
  | 'restarting'
  | 'ready'
  | 'error'

interface SetupForm {
  providerPreset: string
  baseUrl: string
  model: string
  apiKeyEnv: string
  apiKey: string
  llmMode: 'stub' | 'real'
  temperature: number
  timeout: number
}

interface DesktopConfig {
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
}

interface TestResult {
  ok: boolean
  mode: string
  provider: string
  base_url: string
  model: string
  latency_ms?: number
  message: string
  error_code?: string
  suggestion?: string
}

function getInitialForm(config: DesktopConfig | null): SetupForm {
  const defaultProfileName = config?.default_llm || Object.keys(config?.profiles || {})[0] || 'default'
  const profile = config?.profiles?.[defaultProfileName]
  const preset = DESKTOP_PROVIDER_PRESETS.find(
    (p) => p.baseUrl === (profile?.base_url || '') && p.apiKeyEnv === (profile?.api_key_env || '')
  )
  return {
    providerPreset: preset?.id || 'custom',
    baseUrl: profile?.base_url || '',
    model: profile?.model || '',
    apiKeyEnv: profile?.api_key_env || 'OPENAI_API_KEY',
    apiKey: '',
    llmMode: (config?.llm_mode as 'stub' | 'real') || 'stub',
    temperature: profile?.temperature ?? 0.7,
    timeout: 60,
  }
}

function needsSetup(config: DesktopConfig | null): boolean {
  if (!config) return true
  if (config.llm_mode !== 'real') return true
  const defaultProfileName = config.default_llm || Object.keys(config.profiles || {})[0] || 'default'
  const profile = config.profiles?.[defaultProfileName]
  if (!profile) return true
  if (!profile.api_key_configured) return true
  if (!profile.base_url) return true
  if (!profile.model) return true
  return false
}

export default function DesktopFirstRunSetup({
  compact = false,
  onDismiss,
  onReady,
}: {
  compact?: boolean
  onDismiss?: () => void
  onReady?: () => void
}) {
  const isDesktop = typeof window !== 'undefined' && !!window.__NOVELOS_DESKTOP__
  const dialog = useAppDialog()
  const [step, setStep] = useState<SetupStep>(compact ? 'editing' : 'checking')
  const [config, setConfig] = useState<DesktopConfig | null>(null)
  const [form, setForm] = useState<SetupForm>(getInitialForm(null))
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [secretStatuses, setSecretStatuses] = useState<Record<string, { configured: boolean }>>({})
  const dismissedRef = useRef(false)

  const loadConfig = useCallback(async () => {
    const res = await get<DesktopConfig>('/desktop/config')
    if (res.ok && res.data) {
      setConfig(res.data)
      return res.data
    }
    return null
  }, [])

  const loadSecrets = useCallback(async () => {
    if (!window.__NOVELOS_DESKTOP__?.secretStatus) return
    try {
      const statuses = await window.__NOVELOS_DESKTOP__.secretStatus()
      setSecretStatuses(statuses)
    } catch {
      setSecretStatuses({})
    }
  }, [])

  useEffect(() => {
    if (!isDesktop || compact) return
    let mounted = true
    ;(async () => {
      const cfg = await loadConfig()
      await loadSecrets()
      if (!mounted) return
      if (cfg && needsSetup(cfg) && !dismissedRef.current) {
        setStep('prompt')
      } else {
        setStep('ready')
      }
    })()
    return () => {
      mounted = false
    }
  }, [isDesktop, compact, loadConfig, loadSecrets])

  useEffect(() => {
    if (config && step === 'checking') {
      setForm(getInitialForm(config))
    }
  }, [config, step])

  useEffect(() => {
    if (compact && config) {
      setForm(getInitialForm(config))
    }
  }, [compact, config])

  const applyPreset = (presetId: string) => {
    const preset = getPresetById(presetId)
    if (!preset) return
    setForm((prev) => ({
      ...prev,
      providerPreset: presetId,
      baseUrl: preset.baseUrl,
      model: preset.model,
      apiKeyEnv: preset.apiKeyEnv,
    }))
  }

  const handleSaveConfig = async () => {
    setStep('saving_config')
    setErrorMessage('')
    const res = await put('/desktop/config', {
      llm_mode: form.llmMode,
      base_url: form.baseUrl,
      model: form.model,
      temperature: form.temperature,
      timeout: form.timeout,
      api_key_env: form.apiKeyEnv,
    })
    if (res.ok && res.data) {
      const data = res.data as { saved: boolean; restart_required?: boolean; message?: string }
      await loadConfig()
      if (data.restart_required) {
        setStep('restart_required')
      } else {
        setStep('editing')
      }
    } else {
      setErrorMessage(res.error?.message || '保存配置失败')
      setStep('error')
    }
  }

  const handleSaveKey = async () => {
    if (!form.apiKey.trim()) return
    setStep('saving_key')
    setErrorMessage('')
    try {
      await window.__NOVELOS_DESKTOP__?.setApiKey?.(form.apiKeyEnv, form.apiKey.trim())
      setForm((prev) => ({ ...prev, apiKey: '' }))
      await loadSecrets()
      await loadConfig()
      setStep('editing')
    } catch (err) {
      setErrorMessage(`保存 API Key 失败: ${(err as Error).message}`)
      setStep('error')
    }
  }

  const handleTest = async () => {
    setStep('testing')
    setTestResult(null)
    setErrorMessage('')
    const res = await post<TestResult>('/desktop/test-llm', {
      provider: 'openai_compatible',
      base_url: form.baseUrl,
      model: form.model,
      api_key_env: form.apiKeyEnv,
    })
    if (res.ok && res.data) {
      setTestResult(res.data)
      if (res.data.ok) {
        setStep('ready')
      } else {
        setStep('editing')
      }
    } else {
      setTestResult({
        ok: false,
        mode: 'unknown',
        provider: '',
        base_url: form.baseUrl,
        model: form.model,
        message: res.error?.message || '测试请求失败',
        error_code: 'REQUEST_FAILED',
        suggestion: '请检查网络连接和配置参数。',
      })
      setStep('editing')
    }
  }

  const handleRestart = async () => {
    const ok = await dialog.confirm({
      title: '重启本地服务',
      message: '确定要重启本地后端服务吗？进行中的请求可能会中断。',
      tone: 'warning',
      confirmLabel: '重启',
    })
    if (!ok) return
    setStep('restarting')
    setErrorMessage('')
    try {
      const res = await window.__NOVELOS_DESKTOP__?.restartSidecar?.()
      if (res?.success) {
        await loadConfig()
        await loadSecrets()
        setStep('ready')
        onReady?.()
      } else {
        setErrorMessage('本地服务未能成功重启，请检查日志。')
        setStep('error')
      }
    } catch (err) {
      setErrorMessage(`重启失败: ${(err as Error).message}`)
      setStep('error')
    }
  }

  const handleContinueDemo = async () => {
    if (!compact) {
      dismissedRef.current = true
    }
    setStep('ready')
    onDismiss?.()
  }

  const handleDismissPrompt = () => {
    dismissedRef.current = true
    setStep('ready')
    onDismiss?.()
  }

  const canTest =
    form.llmMode === 'real' &&
    form.baseUrl.trim() &&
    form.model.trim() &&
    form.apiKeyEnv.trim() &&
    !!secretStatuses[form.apiKeyEnv]?.configured

  const preset = getPresetById(form.providerPreset)

  if (!isDesktop) return null

  // ── Compact mode (embedded in Settings) ─────────────────────────
  if (compact) {
    return (
      <div>
        {renderFormBody()}
      </div>
    )
  }

  // ── Checking state (full-screen modal preparation) ──────────────
  if (step === 'checking') {
    return null
  }

  // ── Ready state (nothing to show) ───────────────────────────────
  if (step === 'ready') {
    return null
  }

  // ── Prompt state (initial banner/modal) ─────────────────────────
  if (step === 'prompt') {
    return (
      <div className="desktop-first-run-overlay">
        <div className="desktop-first-run-modal">
          <div className="desktop-first-run-header">
            <Zap size={28} style={{ color: '#761a34' }} />
            <h2>欢迎使用 Novelos 桌面版</h2>
            <p>让我们花一分钟配置真实 LLM，即可开始创作。</p>
          </div>
          <div className="desktop-first-run-body">
            <div className="setup-summary">
              <div className="setup-summary-item">
                <span className="setup-summary-dot" style={{ background: config?.llm_mode === 'real' ? '#1d7b46' : '#b46b18' }} />
                <span>当前模式: {config?.llm_mode === 'real' ? '真实 LLM' : '演示模式'}</span>
              </div>
              <div className="setup-summary-item">
                <span className="setup-summary-dot" style={{ background: Object.values(config?.profiles || {}).some((p) => p.api_key_configured) ? '#1d7b46' : '#ef4444' }} />
                <span>API Key: {Object.values(config?.profiles || {}).some((p) => p.api_key_configured) ? '已配置' : '未配置'}</span>
              </div>
              <div className="setup-summary-item">
                <span className="setup-summary-dot" style={{ background: config?.default_llm ? '#1d7b46' : '#ef4444' }} />
                <span>默认模型: {config?.default_llm || '未设置'}</span>
              </div>
            </div>
          </div>
          <div className="desktop-first-run-actions">
            <button className="btn btn-primary" onClick={() => setStep('editing')}>
              开始配置
            </button>
            <button className="btn btn-secondary" onClick={handleDismissPrompt}>
              暂时跳过
            </button>
          </div>
        </div>
        <style>{`
          .desktop-first-run-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.45);
            backdrop-filter: blur(4px);
            z-index: 400;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
          }
          .desktop-first-run-modal {
            background: #fff;
            border-radius: 12px;
            max-width: 520px;
            width: 100%;
            box-shadow: 0 24px 48px rgba(0,0,0,0.18);
            overflow: hidden;
          }
          .desktop-first-run-header {
            padding: 28px 28px 16px;
            text-align: center;
          }
          .desktop-first-run-header h2 {
            margin: 12px 0 6px;
            font-size: 20px;
            font-weight: 600;
            color: #191715;
          }
          .desktop-first-run-header p {
            margin: 0;
            font-size: 14px;
            color: #6f6862;
          }
          .desktop-first-run-body {
            padding: 0 28px 20px;
          }
          .setup-summary {
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding: 16px;
            background: #f7f4ef;
            border-radius: 8px;
          }
          .setup-summary-item {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 14px;
            color: #554f49;
          }
          .setup-summary-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
          }
          .desktop-first-run-actions {
            display: flex;
            gap: 12px;
            padding: 16px 28px 28px;
            justify-content: center;
          }
        `}</style>
      </div>
    )
  }

  // ── Editing / saving / testing / restart / error states ─────────
  return (
    <div className="desktop-first-run-overlay">
      <div className="desktop-first-run-modal desktop-first-run-config-modal">
        <div className="desktop-first-run-header desktop-first-run-config-header">
          <div>
            <h2>配置真实 LLM</h2>
            <p>选择服务商并填写参数，配置将保存到本地安全存储。</p>
          </div>
          <button className="desktop-first-run-skip" type="button" onClick={handleContinueDemo}>
            暂时跳过
          </button>
        </div>
        <div className="desktop-first-run-body desktop-first-run-config-body">
          {renderFormBody()}
        </div>
        <div className="desktop-first-run-actions desktop-first-run-footer">
          {step !== 'restarting' && step !== 'saving_config' && step !== 'saving_key' && (
            <>
              <button className="btn btn-secondary" onClick={handleContinueDemo}>
                继续使用演示模式
              </button>
              {step === 'restart_required' && (
                <button className="btn btn-warning" onClick={handleRestart}>
                  <RefreshCw size={14} style={{ marginRight: 4 }} />
                  重启本地服务
                </button>
              )}
            </>
          )}
        </div>
      </div>
      <style>{`
        .desktop-first-run-overlay {
          position: fixed;
          inset: 0;
          background: rgba(15, 17, 20, 0.54);
          backdrop-filter: blur(5px);
          z-index: 400;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 32px;
          overflow-y: auto;
        }
        .desktop-first-run-modal {
          background: #fff;
          border-radius: 12px;
          width: 100%;
          box-shadow: 0 24px 48px rgba(0,0,0,0.18);
          overflow: hidden;
        }
        .desktop-first-run-config-modal {
          display: flex;
          max-width: min(780px, calc(100vw - 64px));
          max-height: min(760px, calc(100vh - 64px));
          flex-direction: column;
        }
        .desktop-first-run-config-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 24px;
          padding: 24px 28px 16px;
          border-bottom: 1px solid var(--border-color);
          text-align: left;
        }
        .desktop-first-run-config-header h2 {
          margin: 0 0 6px;
          font-size: 22px;
          font-weight: 700;
          line-height: 1.2;
          color: var(--text-primary);
          letter-spacing: 0;
        }
        .desktop-first-run-config-header p {
          margin: 0;
          color: var(--text-secondary);
          font-size: 14px;
          line-height: 1.45;
        }
        .desktop-first-run-skip {
          flex: 0 0 auto;
          min-height: 36px;
          padding: 7px 12px;
          border: 1px solid var(--border-color);
          border-radius: 7px;
          background: var(--bg-primary);
          color: var(--text-secondary);
          font: inherit;
          font-size: 13px;
          font-weight: 650;
          cursor: pointer;
        }
        .desktop-first-run-skip:hover {
          border-color: rgba(118, 26, 52, 0.28);
          color: var(--text-primary);
        }
        .desktop-first-run-config-body {
          min-height: 0;
          overflow-y: auto;
          padding: 18px 28px;
        }
        .desktop-first-run-footer {
          justify-content: flex-end;
          padding: 14px 28px 18px;
          border-top: 1px solid var(--border-color);
          background: rgba(250, 249, 247, 0.96);
        }
        @media (max-width: 720px) {
          .desktop-first-run-overlay {
            align-items: stretch;
            padding: 16px;
          }
          .desktop-first-run-config-modal {
            max-width: 100%;
            max-height: calc(100vh - 32px);
          }
          .desktop-first-run-config-header,
          .desktop-first-run-config-body,
          .desktop-first-run-footer {
            padding-left: 18px;
            padding-right: 18px;
          }
          .desktop-first-run-config-header {
            flex-direction: column;
            gap: 12px;
          }
        }
      `}</style>
    </div>
  )

  function renderFormBody() {
    const isBusy = step === 'saving_config' || step === 'saving_key' || step === 'testing' || step === 'restarting'

    return (
      <div className="desktop-first-run-form">
        {/* Mode indicator */}
        <div
          className={`desktop-first-run-mode ${form.llmMode === 'real' ? 'is-real' : 'is-stub'}`}
        >
          {form.llmMode === 'real' ? <Wifi size={16} /> : <WifiOff size={16} />}
          <span>当前模式: <strong>{form.llmMode === 'real' ? '真实 LLM' : '演示模式'}</strong></span>
        </div>

        {/* Provider preset */}
        <FormField label="服务商" helper={preset?.helperText}>
          <Select
            value={form.providerPreset}
            onChange={(e) => applyPreset(e.target.value)}
            disabled={isBusy}
          >
            {DESKTOP_PROVIDER_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </Select>
        </FormField>

        {/* Base URL */}
        <FormField label="Base URL">
          <TextInput
            value={form.baseUrl}
            onChange={(e) => setForm((prev) => ({ ...prev, baseUrl: e.target.value }))}
            placeholder="https://api.example.com/v1"
            disabled={isBusy}
          />
        </FormField>

        {/* Model */}
        <FormField label="模型 ID">
          <TextInput
            value={form.model}
            onChange={(e) => setForm((prev) => ({ ...prev, model: e.target.value }))}
            placeholder="gpt-4o-mini"
            disabled={isBusy}
          />
        </FormField>

        {/* API Key Env */}
        <FormField label="API Key 环境变量名">
          <TextInput
            value={form.apiKeyEnv}
            onChange={(e) => setForm((prev) => ({ ...prev, apiKeyEnv: e.target.value }))}
            placeholder="OPENAI_API_KEY"
            disabled={isBusy}
          />
        </FormField>

        {/* API Key input */}
        <FormField
          label="API Key"
          helper={secretStatuses[form.apiKeyEnv]?.configured ? `${form.apiKeyEnv} 已保存到本机安全存储` : undefined}
        >
          <TextInput
            type="password"
            value={form.apiKey}
            onChange={(e) => setForm((prev) => ({ ...prev, apiKey: e.target.value }))}
            placeholder="输入 API Key（仅保存到本机安全存储）"
            disabled={isBusy}
          />
        </FormField>

        {/* Advanced toggle */}
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '13px',
            color: '#554f49',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
            width: 'fit-content',
          }}
        >
          {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          高级设置
        </button>

        {showAdvanced && (
          <div className="desktop-first-run-advanced">
            <FormField label="Temperature">
              <NumberInput
                min="0"
                max="2"
                step="0.1"
                value={form.temperature}
                onChange={(e) => setForm((prev) => ({ ...prev, temperature: parseFloat(e.target.value) }))}
                disabled={isBusy}
              />
            </FormField>
            <FormField label="Timeout (秒)">
              <NumberInput
                min="1"
                max="300"
                step="1"
                value={form.timeout}
                onChange={(e) => setForm((prev) => ({ ...prev, timeout: parseInt(e.target.value, 10) }))}
                disabled={isBusy}
              />
            </FormField>
          </div>
        )}

        {/* Action buttons */}
        <div className="desktop-first-run-primary-actions">
          <button
            className="btn btn-primary"
            onClick={handleSaveConfig}
            disabled={isBusy || !form.baseUrl.trim() || !form.model.trim()}
          >
            {step === 'saving_config' ? '保存中...' : '保存配置'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleSaveKey}
            disabled={isBusy || !form.apiKey.trim()}
          >
            {step === 'saving_key' ? '保存中...' : '保存 API Key'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleTest}
            disabled={isBusy || !canTest}
          >
            {step === 'testing' ? '测试中...' : '测试连接'}
          </button>
          {(step === 'restart_required' || step === 'restarting') && (
            <button className="btn btn-warning" onClick={handleRestart} disabled={isBusy}>
              <RefreshCw size={14} style={{ marginRight: 4 }} />
              {step === 'restarting' ? '重启中...' : '重启本地服务'}
            </button>
          )}
        </div>

        {/* Restart required notice */}
        {step === 'restart_required' && (
          <div style={{
            padding: '12px',
            borderRadius: '6px',
            background: '#fef3c7',
            color: '#92400e',
            fontSize: '13px',
          }}>
            <AlertTriangle size={16} style={{ marginRight: 6, verticalAlign: 'middle' }} />
            <strong>配置已更改，需要重启本地服务才能生效。</strong>
            <div style={{ marginTop: 4 }}>点击「重启本地服务」按钮，或稍后手动重启。</div>
          </div>
        )}

        {/* Error / test result */}
        {errorMessage && (
          <div style={{
            padding: '12px',
            borderRadius: '6px',
            background: '#fef2f2',
            color: '#991b1b',
            fontSize: '13px',
          }}>
            <strong>错误</strong>
            <div style={{ marginTop: 4 }}>{errorMessage}</div>
          </div>
        )}

        {testResult && (
          <div style={{
            padding: '12px',
            borderRadius: '6px',
            background: testResult.ok ? '#dcfce7' : '#fef2f2',
            color: testResult.ok ? '#166534' : '#991b1b',
            fontSize: '13px',
          }}>
            <strong>{testResult.ok ? '✓ 连接成功' : `✗ ${testResult.error_code || '连接失败'}`}</strong>
            <div style={{ marginTop: 4 }}>{testResult.message}</div>
            {testResult.latency_ms !== undefined && (
              <div style={{ marginTop: 4, fontSize: '12px' }}>延迟: {testResult.latency_ms}ms</div>
            )}
            {testResult.suggestion && (
              <div style={{ marginTop: 4, fontSize: '12px' }}>建议: {testResult.suggestion}</div>
            )}
          </div>
        )}
        <style>{`
          .desktop-first-run-form {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 16px 18px;
          }
          .desktop-first-run-mode,
          .desktop-first-run-primary-actions,
          .desktop-first-run-advanced,
          .desktop-first-run-form > button,
          .desktop-first-run-form > div[style*="fef3c7"],
          .desktop-first-run-form > div[style*="fef2f2"],
          .desktop-first-run-form > div[style*="dcfce7"] {
            grid-column: 1 / -1;
          }
          .desktop-first-run-mode {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
          }
          .desktop-first-run-mode.is-real {
            background: #dcfce7;
            color: #166534;
          }
          .desktop-first-run-mode.is-stub {
            background: #fef3c7;
            color: #92400e;
          }
          .desktop-first-run-advanced {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 16px 18px;
            padding: 14px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: var(--bg-secondary);
          }
          .desktop-first-run-primary-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            padding-top: 4px;
          }
          .desktop-first-run-primary-actions .btn,
          .desktop-first-run-footer .btn {
            white-space: nowrap;
          }
          @media (max-width: 720px) {
            .desktop-first-run-form,
            .desktop-first-run-advanced {
              grid-template-columns: 1fr;
            }
          }
        `}</style>
      </div>
    )
  }
}
