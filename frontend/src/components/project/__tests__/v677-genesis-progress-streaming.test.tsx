import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import GenesisModule from '../GenesisModule'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('../../../lib/api', () => ({
  get: (...args: unknown[]) => mockGet(...args),
  post: (...args: unknown[]) => mockPost(...args),
  apiUrl: (path: string) => `/api${path.startsWith('/') ? path : `/${path}`}`,
}))

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  listeners: Record<string, Array<(event: MessageEvent) => void>> = {}
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners[type] = [...(this.listeners[type] || []), listener]
  }

  close() {
    this.closed = true
  }

  emit(type: string, data: Record<string, unknown>) {
    const event = { data: JSON.stringify(data) } as MessageEvent
    ;(this.listeners[type] || []).forEach((listener) => listener(event))
  }
}

const project = {
  name: '潮汐档案',
  genre: '科幻悬疑',
  description: '近未来海洋城邦中的失联案。',
  total_chapters_planned: 30,
  target_words: 90000,
}

describe('v6.7.7 Genesis progress streaming', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    mockGet.mockResolvedValue({ ok: true, data: null })
  })

  it('shows running progress immediately after async start and normalizes /api stream URLs', async () => {
    mockPost.mockResolvedValue({
      ok: true,
      data: {
        run_id: 'genesis-run-1',
        stream_url: '/api/projects/proj-1/genesis/generate/stream/genesis-run-1',
        status: 'running',
      },
    })

    render(<GenesisModule projectId="proj-1" project={project} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /生成项目设定/ })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /生成项目设定/ }))
    fireEvent.click(screen.getByRole('button', { name: /生成创世设定/ }))

    await waitFor(() => {
      expect(screen.getByText('生成中...')).toBeInTheDocument()
    })

    expect(screen.getAllByText('正在生成基础设定').length).toBeGreaterThan(0)
    await waitFor(() => {
      expect(MockEventSource.instances).toHaveLength(1)
    })
    expect(MockEventSource.instances[0].url).toBe('/api/projects/proj-1/genesis/generate/stream/genesis-run-1')

    act(() => {
      MockEventSource.instances[0].emit('segment_started', {
        run_id: 'genesis-run-1',
        segment: 'foundation',
        label: '正在生成基础设定',
      })
    })

    await waitFor(() => {
      expect(screen.getAllByText('正在生成基础设定').length).toBeGreaterThan(0)
    })
  })

  it('reconnects progress stream for a running genesis loaded from latest endpoint', async () => {
    mockGet.mockResolvedValue({
      ok: true,
      data: {
        id: 'loaded-run-1',
        project_id: 'proj-1',
        status: 'running',
        input_json: '',
        draft_json: null,
        error_message: null,
        created_at: '2026-05-28T00:46:03',
        updated_at: '2026-05-28T00:46:03',
      },
    })

    render(<GenesisModule projectId="proj-1" project={project} />)

    await waitFor(() => {
      expect(screen.getByText('生成中...')).toBeInTheDocument()
    })

    expect(screen.getAllByText('正在生成基础设定').length).toBeGreaterThan(0)
    await waitFor(() => {
      expect(MockEventSource.instances).toHaveLength(1)
    })
    expect(MockEventSource.instances[0].url).toBe('/api/projects/proj-1/genesis/generate/stream/loaded-run-1')
  })

  it('marks prior phases complete when a later phase event arrives after reconnect', async () => {
    mockGet.mockResolvedValue({
      ok: true,
      data: {
        id: 'loaded-run-2',
        project_id: 'proj-1',
        status: 'running',
        input_json: '',
        draft_json: null,
        error_message: null,
        created_at: '2026-05-28T00:55:19',
        updated_at: '2026-05-28T00:55:19',
      },
    })

    const { container } = render(<GenesisModule projectId="proj-1" project={project} />)

    await waitFor(() => {
      expect(MockEventSource.instances).toHaveLength(1)
    })

    act(() => {
      MockEventSource.instances[0].emit('chapter_start', {
        run_id: 'loaded-run-2',
        chapter_start: 1,
        chapter_end: 5,
        label: '正在生成章节指令 1-5',
      })
    })

    await waitFor(() => {
      expect(screen.getAllByText('正在生成章节指令 1-5').length).toBeGreaterThan(0)
    })

    expect(container.querySelectorAll('.genesis-progress-step.step-completed')).toHaveLength(3)
    expect(container.querySelector('.genesis-progress-step.step-running')?.textContent).toContain('正在生成章节指令 1-5')
  })
})
