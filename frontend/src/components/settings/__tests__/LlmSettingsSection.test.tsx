import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppDialogProvider } from '../../AppDialog'
import { ToastProvider } from '../../ui'
import { LlmSettingsSection } from '../SettingsConsoleSections'
import { get, post, put } from '../../../lib/api'

vi.mock('../../../lib/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))

const settingsData = {
  llm_mode: 'stub',
  config_path: '/tmp/local.yaml',
  db_path: '/tmp/novelos.db',
  llm_profiles: [],
  agent_routes: [],
  default_llm: 'default',
  diagnostics: {
    llm_mode: 'stub',
    has_profiles: true,
    has_default_llm: true,
  },
  generation_stats: {
    test_result: 'pending' as const,
    success_rate: 0,
    avg_duration_seconds: 0,
    total_runs: 0,
    last_run_at: null,
  },
}

const desktopConfig = {
  exists: true,
  llm_mode: 'stub',
  configured_llm_mode: 'stub',
  runtime_llm_mode: 'stub',
  default_llm: 'default',
  profiles: {
    default: {
      provider: 'openai_compatible',
      model: 'gpt-4o-mini',
      base_url: 'https://api.openai.com/v1',
      api_key_env: 'OPENAI_API_KEY',
      api_key_configured: true,
      api_key_source: 'desktop_secure_storage',
      temperature: 0.7,
      timeout: 180,
      max_tokens: 4096,
    },
    author: {
      provider: 'openai_compatible',
      model: 'kimi-k2',
      base_url: 'https://api.moonshot.cn/v1',
      api_key_env: 'MOONSHOT_API_KEY',
      api_key_configured: false,
      api_key_source: 'missing',
      temperature: 0.8,
      timeout: 300,
      max_tokens: 4096,
    },
    memory_curator_fast: {
      provider: 'openai_compatible',
      model: 'gpt-4o-mini',
      base_url: 'https://api.openai.com/v1',
      api_key_env: 'OPENAI_API_KEY',
      api_key_configured: true,
      api_key_source: 'desktop_secure_storage',
      temperature: 0.7,
      timeout: 90,
      max_tokens: 2048,
    },
    openrouter: {
      provider: 'openai_compatible',
      model: 'openrouter/auto',
      base_url: 'https://openrouter.ai/api/v1',
      api_key_env: 'OPENROUTER_API_KEY',
      api_key_configured: true,
      api_key_source: 'environment',
      temperature: 0.7,
      timeout: 180,
      max_tokens: 4096,
    },
  },
  agent_llm: {
    genesis: 'default',
    planner: 'default',
    screenwriter: 'default',
    author: 'author',
    polisher: 'default',
    editor: 'default',
    memory_curator: 'default',
  },
  agent_llm_fallback: {
    memory_curator: 'memory_curator_fast',
  },
}

function setupDesktop() {
  Object.defineProperty(window, '__NOVELOS_DESKTOP__', {
    value: {
      secretStatus: vi.fn().mockResolvedValue({
        OPENAI_API_KEY: { configured: true, storage: 'electron_safe_storage' },
        FREEMODEL_API_KEY: { configured: true, storage: 'electron_safe_storage' },
        MOONSHOT_API_KEY: { configured: false, storage: 'missing' },
      }),
      setApiKey: vi.fn().mockResolvedValue(undefined),
      deleteApiKey: vi.fn().mockResolvedValue(undefined),
      restartSidecar: vi.fn().mockResolvedValue({ success: true, apiBaseUrl: 'http://127.0.0.1:8765/api' }),
    },
    writable: true,
    configurable: true,
  })
  vi.mocked(get).mockResolvedValue({ ok: true, data: desktopConfig })
}

function renderSection() {
  return render(
    <ToastProvider>
      <AppDialogProvider>
        <LlmSettingsSection data={settingsData} />
      </AppDialogProvider>
    </ToastProvider>,
  )
}

describe('LlmSettingsSection', () => {
  beforeEach(() => {
    vi.mocked(get).mockReset()
    vi.mocked(put).mockReset()
    vi.mocked(post).mockReset()
    delete window.__NOVELOS_DESKTOP__
  })

  it('renders template cards and agent template selectors', async () => {
    setupDesktop()

    renderSection()

    expect(await screen.findByText('模型配置')).toBeInTheDocument()
    expect(screen.getByLabelText('default 模板名称')).toHaveValue('default')
    expect(screen.getByLabelText('author 模板名称')).toHaveValue('author')
    expect(screen.getByText('Agent 使用哪个模板')).toBeInTheDocument()
    expect(screen.getByLabelText('author LLM 模板')).toHaveValue('author')
    expect(screen.getByLabelText('memory_curator 备用 LLM 模板')).toHaveValue('memory_curator_fast')
  })

  it('saves llm profiles and agent routes instead of raw route text', async () => {
    setupDesktop()
    vi.mocked(put).mockResolvedValue({ ok: true, data: { saved: true, restart_required: true } })

    renderSection()

    await screen.findByText('模型配置')
    await userEvent.selectOptions(screen.getByLabelText('editor LLM 模板'), 'author')
    await userEvent.click(screen.getByRole('button', { name: '保存模型配置' }))

    await waitFor(() => {
      expect(put).toHaveBeenCalledWith('/desktop/config', expect.objectContaining({
        llm_mode: 'real',
        default_llm: 'default',
        llm_profiles: expect.objectContaining({
          default: expect.objectContaining({ model: 'gpt-4o-mini' }),
          author: expect.objectContaining({ model: 'kimi-k2' }),
        }),
        agent_llm: expect.objectContaining({
          author: 'author',
          editor: 'author',
        }),
        agent_llm_fallback: expect.objectContaining({
          memory_curator: 'memory_curator_fast',
        }),
      }))
    })
  })

  it('saves template timeout settings without template max token settings', async () => {
    setupDesktop()
    vi.mocked(put).mockResolvedValue({ ok: true, data: { saved: true, restart_required: true } })

    renderSection()

    await screen.findByText('模型配置')
    expect(screen.queryByLabelText('author max_tokens')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('author request_timeout_seconds'), {
      target: { value: '360' },
    })
    await userEvent.click(screen.getByRole('button', { name: '保存模型配置' }))

    await waitFor(() => {
      expect(put).toHaveBeenCalled()
    })
    const payload = vi.mocked(put).mock.calls[0][1] as { llm_profiles: Record<string, Record<string, unknown>> }
    expect(payload.llm_profiles.author.request_timeout_seconds).toBe(360)
    expect(payload.llm_profiles.author).not.toHaveProperty('max_tokens')
  })

  it('saves api keys in a separate key storage section', async () => {
    setupDesktop()

    renderSection()

    await screen.findByText('模型配置')
    expect(screen.getByText('API Key 安全存储')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('输入 MOONSHOT_API_KEY 的 Key')).not.toBeInTheDocument()

    const keyInput = screen.getByLabelText('MOONSHOT_API_KEY API Key')
    fireEvent.change(keyInput, { target: { value: 'sk-moonshot-test' } })
    await userEvent.click(screen.getByRole('button', { name: '保存 MOONSHOT_API_KEY' }))

    await waitFor(() => {
      expect(window.__NOVELOS_DESKTOP__?.setApiKey).toHaveBeenCalledWith('MOONSHOT_API_KEY', 'sk-moonshot-test')
      expect(screen.getAllByText(/重启本地服务后可测试连接/).length).toBeGreaterThan(0)
    })
    expect(screen.getByRole('button', { name: /重启本地服务/ })).toBeInTheDocument()
  })

  it('explains api key sources and only enables deletion for locally stored keys', async () => {
    setupDesktop()

    renderSection()

    await screen.findByText('模型配置')

    expect(screen.getByText('OPENAI_API_KEY 已保存到本机安全存储')).toBeInTheDocument()
    expect(screen.getByText('OPENROUTER_API_KEY 来自系统环境变量，不能在这里删除')).toBeInTheDocument()
    expect(screen.queryByLabelText('DEEPSEEK_API_KEY API Key')).not.toBeInTheDocument()

    expect(screen.getByRole('button', { name: '删除 OPENAI_API_KEY' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '删除 OPENROUTER_API_KEY' })).toBeDisabled()
  })

  it('uses selected api key env names when saving templates', async () => {
    setupDesktop()
    vi.mocked(put).mockResolvedValue({ ok: true, data: { saved: true, restart_required: true } })

    renderSection()

    await screen.findByText('模型配置')
    await userEvent.selectOptions(screen.getByLabelText('author API Key 环境变量名'), 'OPENAI_API_KEY')
    await userEvent.click(screen.getByRole('button', { name: '保存模型配置' }))

    await waitFor(() => {
      expect(put).toHaveBeenCalledWith('/desktop/config', expect.objectContaining({
        llm_profiles: expect.objectContaining({
          author: expect.objectContaining({
            api_key_env: 'OPENAI_API_KEY',
          }),
        }),
      }))
    })
  })

  it('keeps template name input focused while typing', async () => {
    setupDesktop()

    renderSection()

    await screen.findByText('模型配置')
    const nameInput = screen.getByLabelText('default 模板名称')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'gpt55')

    expect(nameInput).toHaveValue('gpt55')
    expect(nameInput).toHaveFocus()
  })

  it('shows readonly snapshot in browser mode', () => {
    renderSection()

    expect(screen.getByText('当前为浏览器模式')).toBeInTheDocument()
    expect(screen.getByText(/模板、API Key 安全存储和重启服务需要在桌面客户端中使用/)).toBeInTheDocument()
  })
})
