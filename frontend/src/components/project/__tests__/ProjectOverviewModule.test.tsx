import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ProjectOverviewModule from '../ProjectOverviewModule'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('../../../lib/api', () => ({
  get: (...args: unknown[]) => mockGet(...args),
  post: (...args: unknown[]) => mockPost(...args),
  apiUrl: (path: string) => `http://localhost:8765${path}`,
  getApiBase: () => 'http://localhost:8765',
}))

vi.mock('react-router-dom', () => ({
  Link: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children: React.ReactNode }) => (
    <a {...props}>{children}</a>
  ),
  useNavigate: () => vi.fn(),
}))

const baseProject = {
  project_id: 'test-proj',
  name: '测试小说',
  genre: '玄幻',
  description: '这是一个测试项目',
  total_chapters_planned: 100,
  target_words: 300000,
}

const baseStats = {
  total_chapters: 10,
  total_words: 50000,
  status_counts: { published: 2, planned: 8 },
}

function mockLoadData(overrides?: {
  contextStatus?: object
  productionNext?: object
  healthSummary?: object
  activeSession?: object
}) {
  mockGet.mockImplementation((path: string) => {
    if (path.includes('/context-status')) {
      return Promise.resolve({
        ok: true,
        data: overrides?.contextStatus ?? {
          ready: false,
          score: 40,
          missing: ['world_settings', 'characters'],
          actions: [{ label: '编辑世界观', path: '?module=world-settings' }],
        },
      })
    }
    if (path.includes('/production-next')) {
      return Promise.resolve({
        ok: true,
        data: overrides?.productionNext ?? {
          project_id: 'test-proj',
          current_chapter: 3,
          next_action: {
            key: 'generate_missing_context',
            label: '补齐缺失资料',
            description: '项目资料不完整，需要先生成世界观和角色设定。',
            primary: true,
            action_url: '',
            method: 'POST',
            requires_confirmation: false,
          },
          health: {
            has_project: true,
            has_genesis: true,
            has_approved_genesis: true,
            has_world_settings: false,
            has_characters: false,
            has_outlines: false,
            has_instructions_for_current_chapter: false,
            has_pending_memory_updates: false,
            has_blocking_chapter: false,
            has_stuck_run: false,
            has_running_chapter_workflow: false,
          },
          missing: [
            { key: 'world_settings', label: '缺少世界观设定', severity: 'blocking', manual_url: '?module=world-settings', ai_action: { key: 'generate_world', label: 'AI 生成' } },
            { key: 'characters', label: '缺少主角设定', severity: 'blocking', manual_url: '?module=characters', ai_action: { key: 'generate_characters', label: 'AI 生成' } },
          ],
          actions: [],
        },
      })
    }
    if (path.includes('/health-summary')) {
      return Promise.resolve({
        ok: true,
        data: overrides?.healthSummary ?? {
          project_id: 'test-proj',
          status: 'ok',
          summary: { blocking: 0, attention: 0, warning: 0, stale_runs: 0, pending_memory_items: 0, obsolete_sessions: 0 },
          items: [],
        },
      })
    }
    if (path.includes('/active-session')) {
      return Promise.resolve({
        ok: true,
        data: overrides?.activeSession ?? { active: false },
      })
    }
    return Promise.resolve({ ok: true, data: null })
  })
}

describe('ProjectOverviewModule v6.5.2', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('renders skeleton stack while loading', () => {
    mockGet.mockImplementation(() => new Promise(() => {}))
    const { container } = render(
      <ProjectOverviewModule project={baseProject} stats={baseStats} />
    )
    expect(container.querySelector('.ui-skeleton-stack')).toBeInTheDocument()
  })

  it('renders next action task card with responsibility badge and LoadingButton', async () => {
    mockLoadData()
    render(<ProjectOverviewModule project={baseProject} stats={baseStats} />)

    await waitFor(() => {
      expect(screen.getByText('项目资料不完整，需要先生成世界观和角色设定。')).toBeInTheDocument()
    })

    expect(screen.getByText('AI 可自动处理')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /补齐缺失资料/i })).toBeInTheDocument()
  })

  it('renders context missing checklist with severity dots', async () => {
    mockLoadData()
    render(<ProjectOverviewModule project={baseProject} stats={baseStats} />)

    await waitFor(() => {
      expect(screen.getByText('资料缺口')).toBeInTheDocument()
    })

    expect(screen.getByText('缺少世界观设定')).toBeInTheDocument()
    expect(screen.getByText('缺少主角设定')).toBeInTheDocument()
    expect(screen.getByText('2 项')).toBeInTheDocument()
  })

  it('shows inline message on primary action success when action is generate_missing_context', async () => {
    mockLoadData()
    mockPost.mockResolvedValue({
      ok: true,
      data: { filled: true, created: { world_settings: 1, characters: 2 }, warnings: [] },
    })

    render(<ProjectOverviewModule project={baseProject} stats={baseStats} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /补齐缺失资料/i })).toBeInTheDocument()
    })

    const primaryButton = screen.getByRole('button', { name: /补齐缺失资料/i })
    fireEvent.click(primaryButton)

    await waitFor(() => {
      expect(screen.getByText('已自动补齐 3 项资料')).toBeInTheDocument()
    })
  })

  it('shows inline message on primary action failure', async () => {
    mockLoadData()
    mockPost.mockResolvedValue({
      ok: false,
      error: { code: 'FILL_FAILED', message: '资料补齐失败：LLM 未响应' },
    })

    render(<ProjectOverviewModule project={baseProject} stats={baseStats} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /补齐缺失资料/i })).toBeInTheDocument()
    })

    const primaryButton = screen.getByRole('button', { name: /补齐缺失资料/i })
    fireEvent.click(primaryButton)

    await waitFor(() => {
      expect(screen.getByText('资料补齐失败：LLM 未响应')).toBeInTheDocument()
    })
  })

  it('renders ready context state when score is 100', async () => {
    mockLoadData({
      contextStatus: { ready: true, score: 100, missing: [], actions: [] },
      productionNext: {
        project_id: 'test-proj',
        current_chapter: 3,
        next_action: {
          key: 'generate_chapter',
          label: '生成章节',
          description: '资料已就绪，可以开始生成第 3 章。',
          primary: true,
          action_url: '',
          method: 'POST',
          requires_confirmation: false,
        },
        health: {
          has_project: true,
          has_genesis: true,
          has_approved_genesis: true,
          has_world_settings: true,
          has_characters: true,
          has_outlines: true,
          has_instructions_for_current_chapter: true,
          has_pending_memory_updates: false,
          has_blocking_chapter: false,
          has_stuck_run: false,
          has_running_chapter_workflow: false,
        },
        missing: [],
        actions: [],
      },
    })

    render(<ProjectOverviewModule project={baseProject} stats={baseStats} />)

    await waitFor(() => {
      expect(screen.getByText('项目资料已满足章节生成的最低要求。')).toBeInTheDocument()
    })

    expect(screen.queryByText('资料缺口')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /生成章节/i })).toBeInTheDocument()
  })

  it('shows workflow still running when auto-run listener disconnected but target workflow is active', async () => {
    mockLoadData({
      contextStatus: { ready: true, score: 100, missing: [], actions: [] },
      productionNext: {
        project_id: 'test-proj',
        current_chapter: 15,
        next_action: {
          key: 'view_running_workflow',
          label: '查看第 16 章运行进度',
          description: '第 16 章已有工作流正在运行，当前节点：author。请先查看进度，不要重复启动生成。',
          primary: true,
          action_url: '/projects/test-proj?module=chapters&chapter=16&view=workflow',
          method: 'GET',
          requires_confirmation: false,
          target_chapter: 16,
        },
        health: {
          has_project: true,
          has_genesis: true,
          has_approved_genesis: true,
          has_world_settings: true,
          has_characters: true,
          has_outlines: true,
          has_instructions_for_current_chapter: true,
          has_pending_memory_updates: false,
          has_blocking_chapter: false,
          has_stuck_run: false,
          has_running_chapter_workflow: false,
          has_running_target_workflow: true,
          target_chapter: 16,
          target_workflow_current_node: 'author',
        },
        missing: [],
        actions: [],
      },
      activeSession: {
        active: true,
        session: {
          id: 'session-1',
          project_id: 'test-proj',
          status: 'paused',
          stop_reason: 'client_disconnected',
          current_step: 1,
          chapter_start: 15,
          chapter_end: 24,
          max_steps: 5,
          dry_run: 0,
          last_event: 'client_disconnected',
          created_at: '2026-05-24 18:00:00',
          updated_at: '2026-05-24 18:01:00',
        },
        steps: [
          {
            step: 1,
            action: 'continue_next_chapter',
            label: '继续下一章',
            target_chapter: 16,
            result: 'running',
            warnings: [],
          },
        ],
      },
    })

    render(<ProjectOverviewModule project={baseProject} stats={baseStats} />)

    await waitFor(() => {
      expect(screen.getByText('工作流运行中')).toBeInTheDocument()
    })

    expect(screen.getAllByText('后台执行中：执笔').length).toBeGreaterThan(0)
    expect(screen.queryByText(/监听连接断开/)).not.toBeInTheDocument()
    expect(screen.queryByText('已暂停')).not.toBeInTheDocument()
    expect(screen.queryByText(/查看第 16 章实时进度/)).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /查看第 16 章运行进度/ })).toHaveLength(1)
  })
})
