import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import DesktopRuntimeBanner from '../DesktopRuntimeBanner'
import { AppDialogProvider } from '../AppDialog'

const mockRestartSidecar = vi.fn()
const mockOpenLogsDir = vi.fn()
const mockExportDiagnostics = vi.fn()
let runtimeStatusCallback: ((status: unknown) => void) | null = null

const setupDesktop = () => {
  Object.defineProperty(window, '__NOVELOS_DESKTOP__', {
    value: {
      restartSidecar: mockRestartSidecar,
      openLogsDir: mockOpenLogsDir,
      exportDiagnostics: mockExportDiagnostics,
      onRuntimeStatus: (cb: (status: unknown) => void) => {
        runtimeStatusCallback = cb
        return () => { runtimeStatusCallback = null }
      },
    },
    writable: true,
    configurable: true,
  })
}

const clearDesktop = () => {
  delete window.__NOVELOS_DESKTOP__
}

describe('DesktopRuntimeBanner', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockRestartSidecar.mockReset()
    mockOpenLogsDir.mockReset()
    mockExportDiagnostics.mockReset()
    runtimeStatusCallback = null
    global.fetch = vi.fn()
  })

  afterEach(() => {
    vi.useRealTimers()
    clearDesktop()
  })

  it('does not render in browser mode', () => {
    clearDesktop()
    const { container } = render(
      <AppDialogProvider>
        <DesktopRuntimeBanner />
      </AppDialogProvider>,
    )
    expect(container.firstChild).toBeNull()
  })

  it('shows banner after health fails twice', async () => {
    setupDesktop()
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ ok: false }) })

    render(
      <AppDialogProvider>
        <DesktopRuntimeBanner />
      </AppDialogProvider>,
    )

    expect(screen.queryByText(/本地后端服务连接中断/)).not.toBeInTheDocument()

    // first ping
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(1)
    })
    vi.advanceTimersByTime(8000)

    // second ping
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(2)
    })
    vi.advanceTimersByTime(8000)

    await waitFor(() => {
      expect(screen.getByText(/本地后端服务连接中断/)).toBeInTheDocument()
    })
  })

  it('hides banner when health recovers', async () => {
    setupDesktop()
    let callCount = 0
    global.fetch = vi.fn().mockImplementation(() => {
      callCount++
      if (callCount <= 2) {
        return Promise.resolve({ ok: false, status: 503, json: async () => ({ ok: false }) })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ ok: true, data: { status: 'ok' } }) })
    })

    render(
      <AppDialogProvider>
        <DesktopRuntimeBanner />
      </AppDialogProvider>,
    )

    // trigger failures
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1))
    vi.advanceTimersByTime(8000)
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2))

    await waitFor(() => {
      expect(screen.getByText(/本地后端服务连接中断/)).toBeInTheDocument()
    })

    vi.advanceTimersByTime(8000)
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(3))

    await waitFor(() => {
      expect(screen.queryByText(/本地后端服务连接中断/)).not.toBeInTheDocument()
    })
  })

  it('calls restartSidecar via dialog confirmation', async () => {
    setupDesktop()
    mockRestartSidecar.mockResolvedValue({ success: true })
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ ok: false }) })

    render(
      <AppDialogProvider>
        <DesktopRuntimeBanner />
      </AppDialogProvider>,
    )

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1))
    vi.advanceTimersByTime(8000)
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2))

    await waitFor(() => {
      expect(screen.getByText(/本地后端服务连接中断/)).toBeInTheDocument()
    })

    const restartBtn = screen.getByText('重启本地服务')
    await userEvent.click(restartBtn)

    // Dialog should appear
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    const confirmBtn = screen.getAllByRole('button', { name: /重启/i })[1]
    await userEvent.click(confirmBtn)

    await waitFor(() => {
      expect(mockRestartSidecar).toHaveBeenCalledTimes(1)
    })

    await waitFor(() => {
      expect(screen.queryByText(/本地后端服务连接中断/)).not.toBeInTheDocument()
    })
  })

  it('shows banner when runtime status signals failure', async () => {
    setupDesktop()
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true, data: { status: 'ok' } }) })

    render(
      <AppDialogProvider>
        <DesktopRuntimeBanner />
      </AppDialogProvider>,
    )

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1))
    expect(screen.queryByText(/本地后端服务连接中断/)).not.toBeInTheDocument()

    if (runtimeStatusCallback) {
      act(() => {
        runtimeStatusCallback!({ status: 'failed', lastError: { reason: 'crash' } })
      })
    }

    await waitFor(() => {
      expect(screen.getByText(/本地后端服务连接中断/)).toBeInTheDocument()
    })
  })

  it('exports diagnostics from the failure banner', async () => {
    setupDesktop()
    mockExportDiagnostics.mockResolvedValue({
      success: true,
      path: '/tmp/novelos-diagnostics.json',
      message: '诊断包已导出',
    })
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ ok: false }) })

    render(
      <AppDialogProvider>
        <DesktopRuntimeBanner />
      </AppDialogProvider>,
    )

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1))
    vi.advanceTimersByTime(8000)
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2))

    await waitFor(() => {
      expect(screen.getByText(/本地后端服务连接中断/)).toBeInTheDocument()
    })

    await userEvent.click(screen.getByText('导出诊断包'))

    await waitFor(() => {
      expect(mockExportDiagnostics).toHaveBeenCalledTimes(1)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/novelos-diagnostics\.json/)).toBeInTheDocument()
    })
  })
})
