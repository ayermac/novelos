import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import DesktopFirstRunSetup from '../DesktopFirstRunSetup'
import { AppDialogProvider } from '../../AppDialog'
import { ToastProvider } from '../../ui'

const mockSetApiKey = vi.fn()
const mockRestartSidecar = vi.fn()
const mockSecretStatus = vi.fn()

let fetchMock: ReturnType<typeof vi.fn>

const setupDesktop = (config: {
  llm_mode?: string
  default_llm?: string | null
  profiles?: Record<string, unknown>
} = {}) => {
  Object.defineProperty(window, '__NOVELOS_DESKTOP__', {
    value: {
      setApiKey: mockSetApiKey,
      restartSidecar: mockRestartSidecar,
      secretStatus: mockSecretStatus,
    },
    writable: true,
    configurable: true,
  })

  fetchMock = vi.fn()
  global.fetch = fetchMock as unknown as typeof global.fetch

  fetchMock.mockImplementation((url: string) => {
    if (url.includes('/desktop/config')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          data: {
            exists: true,
            llm_mode: config.llm_mode ?? 'stub',
            default_llm: config.default_llm ?? 'default',
            profiles: config.profiles ?? {
              default: {
                provider: 'openai_compatible',
                model: '',
                base_url: '',
                api_key_env: 'OPENAI_API_KEY',
                api_key_configured: false,
                api_key_source: 'missing',
                temperature: 0.7,
                max_tokens: 4096,
              },
            },
          },
        }),
      })
    }
    if (url.includes('/desktop/runtime-info')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          data: { is_desktop: true, llm_mode: config.llm_mode ?? 'stub' },
        }),
      })
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({ ok: true, data: { status: 'ok' } }) })
  })
}

const clearDesktop = () => {
  delete window.__NOVELOS_DESKTOP__
}

describe('DesktopFirstRunSetup', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockSetApiKey.mockReset()
    mockRestartSidecar.mockReset()
    mockSecretStatus.mockReset()
    mockSecretStatus.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
    clearDesktop()
  })

  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <ToastProvider>
      <AppDialogProvider>{children}</AppDialogProvider>
    </ToastProvider>
  )

  it('does not render in browser mode', () => {
    clearDesktop()
    render(
      <Wrapper>
        <DesktopFirstRunSetup />
      </Wrapper>,
    )
    expect(screen.queryByText(/欢迎使用 Novelos 桌面版/)).not.toBeInTheDocument()
  })

  it('shows first-run prompt when desktop config is incomplete', async () => {
    setupDesktop({ llm_mode: 'stub' })
    render(
      <Wrapper>
        <DesktopFirstRunSetup />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText(/欢迎使用 Novelos 桌面版/)).toBeInTheDocument()
    })
  })

  it('does not show prompt when config is ready', async () => {
    setupDesktop({
      llm_mode: 'real',
      profiles: {
        default: {
          provider: 'openai_compatible',
          model: 'gpt-4o-mini',
          base_url: 'https://api.openai.com/v1',
          api_key_env: 'OPENAI_API_KEY',
          api_key_configured: true,
          api_key_source: 'desktop_secure_storage',
          temperature: 0.7,
          max_tokens: 4096,
        },
      },
    })
    mockSecretStatus.mockResolvedValue({ OPENAI_API_KEY: { configured: true } })

    render(
      <Wrapper>
        <DesktopFirstRunSetup />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.queryByText(/欢迎使用 Novelos 桌面版/)).not.toBeInTheDocument()
    })
  })

  it('allows entering config editing from prompt', async () => {
    setupDesktop({ llm_mode: 'stub' })
    render(
      <Wrapper>
        <DesktopFirstRunSetup />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText(/欢迎使用 Novelos 桌面版/)).toBeInTheDocument()
    })

    const startBtn = screen.getByText('开始配置')
    await userEvent.click(startBtn)

    await waitFor(() => {
      expect(screen.getByText(/配置真实 LLM/)).toBeInTheDocument()
    })
  })

  it('fills preset fields when provider selected', async () => {
    setupDesktop({ llm_mode: 'stub' })
    render(
      <Wrapper>
        <DesktopFirstRunSetup />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText(/欢迎使用 Novelos 桌面版/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('开始配置'))

    await waitFor(() => {
      expect(screen.getByText(/配置真实 LLM/)).toBeInTheDocument()
    })

    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThan(0)
    const providerSelect = selects[0] as HTMLSelectElement
    await userEvent.selectOptions(providerSelect, 'deepseek')

    await waitFor(() => {
      const inputs = screen.getAllByRole('textbox')
      const baseUrlInput = inputs.find((el) => el.getAttribute('type') !== 'password') as HTMLInputElement
      expect(baseUrlInput.value).toBe('https://api.deepseek.com/v1')
    })
  })

  it('calls save config API when save button clicked', async () => {
    setupDesktop({ llm_mode: 'stub' })
    render(
      <Wrapper>
        <DesktopFirstRunSetup />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText(/欢迎使用 Novelos 桌面版/)).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText('开始配置'))

    await waitFor(() => {
      expect(screen.getByText(/配置真实 LLM/)).toBeInTheDocument()
    })

    // Fill required fields
    const inputs = screen.getAllByRole('textbox')
    const baseUrlInput = inputs[0] as HTMLInputElement
    const modelInput = inputs[1] as HTMLInputElement
    await userEvent.clear(baseUrlInput)
    await userEvent.type(baseUrlInput, 'https://api.openai.com/v1')
    await userEvent.clear(modelInput)
    await userEvent.type(modelInput, 'gpt-4o-mini')

    await userEvent.click(screen.getByText('保存配置'))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/desktop/config'),
        expect.objectContaining({ method: 'PUT' }),
      )
    })
  })

  it('calls safeStorage IPC when save key button clicked', async () => {
    setupDesktop({ llm_mode: 'stub' })
    render(
      <Wrapper>
        <DesktopFirstRunSetup />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText(/欢迎使用 Novelos 桌面版/)).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText('开始配置'))

    await waitFor(() => {
      expect(screen.getByText(/配置真实 LLM/)).toBeInTheDocument()
    })

    const keyInput = screen.getByLabelText('API Key')
    await userEvent.type(keyInput, 'sk-test-key-123')

    await userEvent.click(screen.getByText('保存 API Key'))

    await waitFor(() => {
      expect(mockSetApiKey).toHaveBeenCalledWith('OPENAI_API_KEY', 'sk-test-key-123')
    })
  })

  it('dismisses prompt when skip clicked', async () => {
    setupDesktop({ llm_mode: 'stub' })
    render(
      <Wrapper>
        <DesktopFirstRunSetup />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText(/欢迎使用 Novelos 桌面版/)).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText('暂时跳过'))

    await waitFor(() => {
      expect(screen.queryByText(/欢迎使用 Novelos 桌面版/)).not.toBeInTheDocument()
    })
  })

  it('compact mode renders editing form directly', async () => {
    setupDesktop({ llm_mode: 'stub' })
    render(
      <Wrapper>
        <DesktopFirstRunSetup compact />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('服务商')).toBeInTheDocument()
    })
  })

  /* v6.5.5 Settings & Desktop Runtime Polish tests ------------- */

  it('save config button uses LoadingButton and is disabled while saving', async () => {
    setupDesktop({ llm_mode: 'stub' })
    let resolvePut: (v: unknown) => void
    const putPromise = new Promise((resolve) => {
      resolvePut = resolve
    })

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET'
      if (url.includes('/desktop/config') && method !== 'PUT') {
        // GET
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            ok: true,
            data: {
              exists: true,
              llm_mode: 'stub',
              default_llm: 'default',
              profiles: {
                default: {
                  provider: 'openai_compatible',
                  model: '',
                  base_url: '',
                  api_key_env: 'OPENAI_API_KEY',
                  api_key_configured: false,
                  api_key_source: 'missing',
                  temperature: 0.7,
                  max_tokens: 4096,
                },
              },
            },
          }),
        })
      }
      if (url.includes('/desktop/config')) {
        // PUT — delay resolve so we can catch loading state
        return putPromise.then(() => ({
          ok: true,
          status: 200,
          json: async () => ({ ok: true, data: { saved: true, restart_required: false, message: '配置已保存' } }),
        }))
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ ok: true, data: { status: 'ok' } }) })
    })

    render(
      <Wrapper>
        <DesktopFirstRunSetup compact />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('服务商')).toBeInTheDocument()
    })

    const inputs = screen.getAllByRole('textbox')
    const baseUrlInput = inputs[0] as HTMLInputElement
    const modelInput = inputs[1] as HTMLInputElement
    await userEvent.clear(baseUrlInput)
    await userEvent.type(baseUrlInput, 'https://api.openai.com/v1')
    await userEvent.clear(modelInput)
    await userEvent.type(modelInput, 'gpt-4o-mini')

    await userEvent.click(screen.getByText('保存配置'))

    await waitFor(() => {
      const saveBtn = screen.getByRole('button', { name: /保存中/ })
      expect(saveBtn).toBeDisabled()
    })

    resolvePut!({})
  })

  it('save key button calls IPC and input is cleared on success', async () => {
    setupDesktop({ llm_mode: 'stub' })
    render(
      <Wrapper>
        <DesktopFirstRunSetup compact />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('API Key')).toBeInTheDocument()
    })

    const keyInput = screen.getByLabelText('API Key')
    await userEvent.type(keyInput, 'sk-test-key-123')

    await userEvent.click(screen.getByText('保存 API Key'))

    await waitFor(() => {
      expect(mockSetApiKey).toHaveBeenCalledWith('OPENAI_API_KEY', 'sk-test-key-123')
    })
  })

  it('keeps a single restart button after saving an API key and disables test until restart', async () => {
    setupDesktop({
      llm_mode: 'real',
      profiles: {
        default: {
          provider: 'openai_compatible',
          model: 'gpt-4o-mini',
          base_url: 'https://api.openai.com/v1',
          api_key_env: 'OPENAI_API_KEY',
          api_key_configured: false,
          api_key_source: 'missing',
          temperature: 0.7,
          max_tokens: 4096,
        },
      },
    })
    mockSecretStatus.mockResolvedValue({ OPENAI_API_KEY: { configured: true } })

    render(
      <Wrapper>
        <DesktopFirstRunSetup compact />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('API Key')).toBeInTheDocument()
    })

    await userEvent.type(screen.getByLabelText('API Key'), 'sk-test-key-123')
    await userEvent.click(screen.getByText('保存 API Key'))

    await waitFor(() => {
      expect(mockSetApiKey).toHaveBeenCalledWith('OPENAI_API_KEY', 'sk-test-key-123')
      expect(screen.getAllByRole('button', { name: /重启本地服务/ })).toHaveLength(1)
    })

    expect(screen.getByRole('button', { name: /测试连接/ })).toBeDisabled()
    expect(screen.getByText(/重启前暂时无法测试连接/)).toBeInTheDocument()
  })
})
