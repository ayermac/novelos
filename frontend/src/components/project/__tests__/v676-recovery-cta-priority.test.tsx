import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import AuthorWritingSurface from '../AuthorWritingSurface'
import AuthorAgentPanel from '../AuthorAgentPanel'
import type { WorkflowTimelineData } from '../../../lib/api'

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  Link: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children: React.ReactNode }) => (
    <a {...props}>{children}</a>
  ),
  useNavigate: () => vi.fn(),
}))

function makeTimeline(overrides: Partial<WorkflowTimelineData>): WorkflowTimelineData {
  return {
    project_id: 'test-proj',
    chapter_number: 5,
    run_id: 'run-123',
    run_status: null,
    chapter_status: null,
    current_node: null,
    started_at: null,
    elapsed_minutes: null,
    is_stale: false,
    recovery: {
      recommended_action: null,
      reason: null,
      safe_actions: [],
    },
    nodes: [],
    ...overrides,
  }
}

const baseProps = {
  activeTab: 'workflow' as const,
  chapterDetail: null,
  chapterLoading: false,
  currentChapter: 5,
  currentChapterRecord: { chapter_number: 5, status: 'awaiting_publish', word_count: 3000, title: '第五章' },
  genError: '',
  genErrorDetails: null,
  isLaunching: false,
  isStub: true,
  isStreaming: false,
  isWorkflowRunning: false,
  isProjectWorkflowRunning: false,
  runningWorkflowChapter: null,
  llmMode: 'real',
  projectId: 'test-proj',
  runDetail: null,
  runsForChapter: [],
  sseSteps: {},
  onGenerate: vi.fn(),
  onGenerateNext: vi.fn(),
  onMarkRunStuck: vi.fn(),
  onPublish: vi.fn(),
  onResetRunRecovery: vi.fn(),
  onRetryRunNode: vi.fn(),
  onTabChange: vi.fn(),
  onViewContent: vi.fn(),
  onViewWorkflow: vi.fn(),
}

describe('v6.7.6 Recovery CTA Priority', () => {
  it('shows recovery panel with reset for blocked run + awaiting_publish', () => {
    const timeline = makeTimeline({
      run_status: 'blocked',
      chapter_status: 'awaiting_publish',
      recovery: {
        recommended_action: 'reset_chapter',
        reason: '工作流被阻塞，可清除阻塞并重置。',
        safe_actions: [
          { key: 'view_artifacts', label: '查看产物', safe: true },
          { key: 'view_content', label: '查看正文', safe: true },
          { key: 'reset_chapter', label: '清除阻塞并重置', safe: true, note: '保留当前正文和版本，回到 planned，完整重跑' },
        ],
      },
    })

    render(<AuthorWritingSurface {...baseProps} timeline={timeline} />)

    // Should show the reset button
    expect(screen.getByText('清除阻塞并重置')).toBeInTheDocument()
    // Should NOT show publish button
    expect(screen.queryByText('确认发布')).not.toBeInTheDocument()
  })

  it('shows recovery panel with reset for failed run + awaiting_publish', () => {
    const timeline = makeTimeline({
      run_status: 'failed',
      chapter_status: 'awaiting_publish',
      recovery: {
        recommended_action: 'reset_chapter',
        reason: '工作流运行失败，可清除阻塞并重置。',
        safe_actions: [
          { key: 'view_artifacts', label: '查看产物', safe: true },
          { key: 'view_content', label: '查看正文', safe: true },
          { key: 'reset_chapter', label: '清除阻塞并重置', safe: true },
        ],
      },
    })

    render(<AuthorWritingSurface {...baseProps} timeline={timeline} />)

    expect(screen.getByText('清除阻塞并重置')).toBeInTheDocument()
    expect(screen.queryByText('确认发布')).not.toBeInTheDocument()
  })

  it('shows recovery panel with mark_stuck for stale running + awaiting_publish', () => {
    const timeline = makeTimeline({
      run_status: 'running',
      chapter_status: 'awaiting_publish',
      is_stale: true,
      recovery: {
        recommended_action: 'mark_stuck',
        reason: '工作流运行超时，需要人工干预。',
        safe_actions: [
          { key: 'view_content', label: '查看正文', safe: true },
          { key: 'mark_stuck', label: '标记卡住', safe: true },
        ],
      },
    })

    render(<AuthorWritingSurface {...baseProps} timeline={timeline} />)

    expect(screen.getByText('标记卡住')).toBeInTheDocument()
    expect(screen.queryByText('确认发布')).not.toBeInTheDocument()
  })

  it('shows publish button for healthy completed run + awaiting_publish', () => {
    const timeline = makeTimeline({
      run_status: 'completed',
      chapter_status: 'awaiting_publish',
      recovery: {
        recommended_action: 'publish',
        reason: null,
        safe_actions: [
          { key: 'view_content', label: '查看正文', safe: true },
          { key: 'publish', label: '确认发布', safe: true },
        ],
      },
    })

    render(<AuthorWritingSurface {...baseProps} timeline={timeline} />)

    expect(screen.getByText('确认发布')).toBeInTheDocument()
  })

  // v6.7.6 round 2: Header publish CTA must respect recovery
  it('hides header publish button for blocked run + reviewed', () => {
    const timeline = makeTimeline({
      run_status: 'blocked',
      chapter_status: 'reviewed',
      recovery: {
        recommended_action: 'reset_chapter',
        reason: '工作流被阻塞。',
        safe_actions: [
          { key: 'reset_chapter', label: '清除阻塞并重置', safe: true },
        ],
      },
    })

    render(
      <AuthorWritingSurface
        {...baseProps}
        activeTab="content"
        currentChapterRecord={{ status: 'reviewed', word_count: 3000, title: '第五章' }}
        timeline={timeline}
      />,
    )

    // Header publish button should be hidden
    expect(screen.queryByText('确认发布')).not.toBeInTheDocument()
  })

  it('hides header publish button for stale running + reviewed', () => {
    const timeline = makeTimeline({
      run_status: 'running',
      chapter_status: 'reviewed',
      is_stale: true,
      elapsed_minutes: 120,
      recovery: {
        recommended_action: 'mark_stuck',
        reason: '运行超时。',
        safe_actions: [
          { key: 'mark_stuck', label: '标记卡住', safe: true },
        ],
      },
    })

    render(
      <AuthorWritingSurface
        {...baseProps}
        activeTab="content"
        currentChapterRecord={{ status: 'reviewed', word_count: 3000, title: '第五章' }}
        timeline={timeline}
      />,
    )

    expect(screen.queryByText('确认发布')).not.toBeInTheDocument()
  })
})

// ── v6.7.6 round 2: AuthorAgentPanel publish CTA ──────────────────

const agentBaseProps = {
  currentChapter: 5,
  currentChapterRecord: { status: 'awaiting_publish', word_count: 3000, title: '第五章' },
  llmMode: 'real',
  runDetail: null,
  runsForChapter: [],
  isStreaming: false,
  sseSteps: {},
  genError: '',
  onGenerate: vi.fn(),
  onViewContent: vi.fn(),
  onViewWorkflow: vi.fn(),
}

describe('v6.7.6 AuthorAgentPanel Recovery CTA Priority', () => {
  it('hides publish card for blocked run + awaiting_publish', () => {
    const timeline = makeTimeline({
      run_status: 'blocked',
      chapter_status: 'awaiting_publish',
      recovery: {
        recommended_action: 'reset_chapter',
        reason: '工作流被阻塞。',
        safe_actions: [],
      },
    })

    render(<AuthorAgentPanel {...agentBaseProps} timeline={timeline} />)

    // Should show recovery message, not publish
    expect(screen.queryByText('确认发布')).not.toBeInTheDocument()
    expect(screen.getByText('需要先恢复运行')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /打开工作流恢复/ })).toBeInTheDocument()
  })

  it('hides publish card for failed run + reviewed', () => {
    const timeline = makeTimeline({
      run_status: 'failed',
      chapter_status: 'reviewed',
      recovery: {
        recommended_action: 'reset_chapter',
        reason: '工作流运行失败。',
        safe_actions: [],
      },
    })

    render(
      <AuthorAgentPanel
        {...agentBaseProps}
        currentChapterRecord={{ status: 'reviewed', word_count: 3000, title: '第五章' }}
        timeline={timeline}
        onPublish={vi.fn()}
      />,
    )

    expect(screen.queryByText('确认发布')).not.toBeInTheDocument()
    expect(screen.getByText('需要先恢复运行')).toBeInTheDocument()
  })

  it('shows publish card for healthy completed run + reviewed', () => {
    const timeline = makeTimeline({
      run_status: 'completed',
      chapter_status: 'reviewed',
      recovery: {
        recommended_action: 'publish',
        reason: null,
        safe_actions: [],
      },
    })

    render(
      <AuthorAgentPanel
        {...agentBaseProps}
        currentChapterRecord={{ status: 'reviewed', word_count: 3000, title: '第五章' }}
        timeline={timeline}
        onPublish={vi.fn()}
      />,
    )

    expect(screen.getByText('确认发布')).toBeInTheDocument()
  })
})
