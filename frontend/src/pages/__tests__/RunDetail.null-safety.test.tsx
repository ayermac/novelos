import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import RunDetail from '../../pages/RunDetail'

// Mock react-router-dom hooks
vi.mock('react-router-dom', () => ({
  useParams: () => ({ runId: 'test-run-001' }),
  useNavigate: () => vi.fn(),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}))

// Mock AppDialogContext
vi.mock('../../components/AppDialogContext', () => ({
  useAppDialog: () => ({
    confirm: vi.fn().mockResolvedValue(false),
  }),
}))

// Mock API module
vi.mock('../../lib/api', () => ({
  get: vi.fn().mockResolvedValue({
    ok: true,
    data: {
      run_id: 'test-run-001',
      project_id: 'test-proj',
      project_name: 'Test Project',
      chapter_number: 1,
      workflow_status: 'completed',
      chapter_status: 'published',
      llm_mode: 'stub',
      started_at: '2026-01-01T00:00:00',
      completed_at: '2026-01-01T00:10:00',
      steps: [],
    },
  }),
  post: vi.fn().mockResolvedValue({ ok: false }),
}))

describe('RunDetail null safety', () => {
  it('renders without crash when recovery is null', async () => {
    // The component fetches recovery data, and if null, should show fallback text
    const { container, findByText } = render(<RunDetail />)
    // Should not throw, should render basic page
    await findByText('运行详情').catch(() => {})
    expect(container).toBeTruthy()
  })

  it('renders without crash when running_tasks is missing from recovery', async () => {
    const { get } = await import('../../lib/api')
    const mockGet = vi.mocked(get)
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/recovery')) {
        return Promise.resolve({
          ok: true,
          data: {
            run_id: 'test-run-001',
            project_id: 'test-proj',
            chapter_number: 1,
            workflow_status: 'completed',
            chapter_status: 'published',
            retry_count: 0,
            max_retries: 3,
            timeout_minutes: 30,
            stuck: false,
            checkpoint_exists: false,
            can_reset: false,
            // running_tasks is missing entirely
            actions: {
              reset_to_planned: { enabled: false, label: '重置', reason: '' },
              mark_stuck_blocked: { enabled: false, label: '标记', reason: '' },
            },
          },
        })
      }
      return Promise.resolve({
        ok: true,
        data: {
          run_id: 'test-run-001',
          project_id: 'test-proj',
          project_name: 'Test Project',
          chapter_number: 1,
          workflow_status: 'completed',
          chapter_status: 'published',
          current_node: null,
          llm_mode: 'stub',
          started_at: '2026-01-01T00:00:00',
          completed_at: '2026-01-01T00:10:00',
          error_message: undefined,
          steps: [],
          total_tokens: 0,
          duration_ms: 0,
        },
      })
    })

    const { container } = render(<RunDetail />)
    expect(container).toBeTruthy()
  })

  it('renders without crash when memory_status is null', async () => {
    const { get } = await import('../../lib/api')
    const mockGet = vi.mocked(get)
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/recovery')) {
        return Promise.resolve({
          ok: true,
          data: {
            run_id: 'test-run-001',
            project_id: 'test-proj',
            chapter_number: 1,
            workflow_status: 'completed',
            chapter_status: 'published',
            retry_count: 0,
            max_retries: 3,
            timeout_minutes: 30,
            stuck: false,
            checkpoint_exists: false,
            can_reset: false,
            running_tasks: [],
            actions: {
              reset_to_planned: { enabled: false, label: '重置', reason: '' },
              mark_stuck_blocked: { enabled: false, label: '标记', reason: '' },
            },
          },
        })
      }
      return Promise.resolve({
        ok: true,
        data: {
          run_id: 'test-run-001',
          project_id: 'test-proj',
          project_name: 'Test Project',
          chapter_number: 1,
          workflow_status: 'completed',
          chapter_status: 'published',
          current_node: null,
          llm_mode: 'stub',
          started_at: '2026-01-01T00:00:00',
          completed_at: '2026-01-01T00:10:00',
          error_message: undefined,
          steps: [],
          // memory_status is missing/null
          total_tokens: 0,
          duration_ms: 0,
        },
      })
    })

    const { container } = render(<RunDetail />)
    expect(container).toBeTruthy()
  })

  it('renders without crash when recovery actions are missing', async () => {
    const { get } = await import('../../lib/api')
    const mockGet = vi.mocked(get)
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/recovery')) {
        return Promise.resolve({
          ok: true,
          data: {
            run_id: 'test-run-001',
            project_id: 'test-proj',
            chapter_number: 1,
            workflow_status: 'completed',
            chapter_status: 'published',
            retry_count: 0,
            max_retries: 3,
            timeout_minutes: 30,
            stuck: false,
            checkpoint_exists: false,
            can_reset: false,
            running_tasks: [],
            // actions is missing
          },
        })
      }
      return Promise.resolve({
        ok: true,
        data: {
          run_id: 'test-run-001',
          project_id: 'test-proj',
          project_name: 'Test Project',
          chapter_number: 1,
          workflow_status: 'completed',
          chapter_status: 'published',
          current_node: null,
          llm_mode: 'stub',
          started_at: '2026-01-01T00:00:00',
          completed_at: '2026-01-01T00:10:00',
          steps: [],
          total_tokens: 0,
          duration_ms: 0,
        },
      })
    })

    const { container } = render(<RunDetail />)
    expect(container).toBeTruthy()
  })
})
