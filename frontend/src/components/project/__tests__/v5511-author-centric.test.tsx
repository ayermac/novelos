import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ProjectSideNav from '../ProjectSideNav'
import ChapterWorkspace from '../ChapterWorkspace'

// Mock API module
vi.mock('../../../lib/api', () => ({
  get: vi.fn().mockResolvedValue({ ok: true, data: null }),
  post: vi.fn().mockResolvedValue({ ok: true, data: null }),
}))

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  Link: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children: React.ReactNode }) => <a {...props}>{children}</a>,
  useNavigate: () => vi.fn(),
}))

/* ------------------------------------------------------------------ */
/*  v5.5.11-A: Navigation labels and grouping                         */
/* ------------------------------------------------------------------ */

describe('v5.5.11-A: ProjectSideNav labels and grouping', () => {
  it('renders author task group label', () => {
    render(<ProjectSideNav activeModule="overview" onModuleChange={vi.fn()} />)
    expect(screen.getByText('作者任务')).toBeInTheDocument()
  })

  it('renders novel settings group label', () => {
    render(<ProjectSideNav activeModule="overview" onModuleChange={vi.fn()} />)
    expect(screen.getByText('小说设定')).toBeInTheDocument()
  })

  it('renders system status group label', () => {
    render(<ProjectSideNav activeModule="overview" onModuleChange={vi.fn()} />)
    expect(screen.getByText('系统状态')).toBeInTheDocument()
  })

  it('renders updated nav labels', () => {
    render(<ProjectSideNav activeModule="overview" onModuleChange={vi.fn()} />)
    expect(screen.getByText('审稿发布')).toBeInTheDocument()
    expect(screen.getByText('记忆收件箱')).toBeInTheDocument()
  })

  it('does not render old labels', () => {
    render(<ProjectSideNav activeModule="overview" onModuleChange={vi.fn()} />)
    expect(screen.queryByText('审核发布')).not.toBeInTheDocument()
    expect(screen.queryByText('记忆收纳')).not.toBeInTheDocument()
    expect(screen.queryByText('日常工作')).not.toBeInTheDocument()
    expect(screen.queryByText('小说资料')).not.toBeInTheDocument()
    expect(screen.queryByText('系统')).not.toBeInTheDocument()
  })

  it('system status group is collapsible', () => {
    render(<ProjectSideNav activeModule="overview" onModuleChange={vi.fn()} />)
    const systemLabel = screen.getByText('系统状态').closest('.project-side-nav-label')
    expect(systemLabel).toHaveClass('collapsible')
  })
})

/* ------------------------------------------------------------------ */
/*  v5.5.11-B: Tech words hidden from main UI                         */
/* ------------------------------------------------------------------ */

describe('v5.5.11-B: Tech words not visible in main overview UI', () => {
  const TECH_WORDS = ['SSE', 'EventSource', 'max_steps', 'dry-run', 'auto-run', 'session']

  it.each(TECH_WORDS)('"%s" should not appear in visible nav text', (word) => {
    render(<ProjectSideNav activeModule="overview" onModuleChange={vi.fn()} />)
    const navText = document.querySelector('.project-side-nav')?.textContent || ''
    expect(navText).not.toContain(word)
  })
})

/* ------------------------------------------------------------------ */
/*  v5.5.11-C: Workflow launch visibility                              */
/* ------------------------------------------------------------------ */

describe('v5.5.11-C: ChapterWorkspace launching state', () => {
  const baseProps = {
    activeTab: 'workflow' as const,
    chapterDetail: null,
    chapterLoading: false,
    chapters: [{ chapter_number: 1, status: 'planned', word_count: 0 }],
    currentChapter: 1,
    currentChapterRecord: null,
    genError: '',
    genErrorDetails: null,
    isStub: true,
    isStreaming: false,
    llmMode: 'stub' as const,
    nextChapterNumber: null,
    projectId: 'test-project',
    runDetail: null,
    runsForChapter: [],
    sseSteps: {},
    totalChapters: 10,
    onGenerate: vi.fn(),
    onGenerateNext: vi.fn(),
    onNavigateToRun: vi.fn(),
    onPublish: vi.fn(),
    onResetChapter: vi.fn(),
    onSelectChapter: vi.fn(),
    onTabChange: vi.fn(),
    onViewContent: vi.fn(),
    onViewWorkflow: vi.fn(),
  }

  const runningRunDetail = {
    run_id: 'run-1',
    project_id: 'test-project',
    chapter_number: 1,
    workflow_status: 'running',
    chapter_status: 'planned',
    current_node: 'editor',
    llm_mode: 'stub' as const,
    steps: [
      { key: 'screenwriter', label: '编剧', description: '规划章节场景和情节', status: 'completed' as const },
      { key: 'author', label: '执笔', description: '撰写章节正文', status: 'completed' as const },
      { key: 'polisher', label: '润色', description: '优化文字表达', status: 'completed' as const },
      { key: 'editor', label: '审核', description: '检查内容质量', status: 'running' as const },
      { key: 'publish', label: '发布', description: '发布章节内容', status: 'pending' as const },
    ],
  }

  it('shows launching indicator when isLaunching is true and not yet streaming', () => {
    render(<ChapterWorkspace {...baseProps} isLaunching={true} isStreaming={false} />)
    expect(screen.getByText('正在启动生成流程...')).toBeInTheDocument()
    expect(screen.getByText('准备章节数据和 AI 模型，即将开始')).toBeInTheDocument()
  })

  it('does not show launching indicator when isLaunching is false', () => {
    render(<ChapterWorkspace {...baseProps} isLaunching={false} isStreaming={false} />)
    expect(screen.queryByText('正在启动生成流程...')).not.toBeInTheDocument()
  })

  it('does not show launching indicator when streaming has started', () => {
    render(<ChapterWorkspace {...baseProps} isLaunching={true} isStreaming={true} />)
    expect(screen.queryByText('正在启动生成流程...')).not.toBeInTheDocument()
  })

  it('shows a clearer workflow status banner for running editor step', () => {
    render(<ChapterWorkspace {...baseProps} runDetail={runningRunDetail as never} isLaunching={false} isStreaming={false} />)
    expect(screen.getByText('工作流正在推进')).toBeInTheDocument()
    expect(screen.getByText('当前节点：审核')).toBeInTheDocument()
    expect(screen.getByText('运行中')).toBeInTheDocument()
    expect(screen.getByText('已规划', { selector: '.status-badge' })).toBeInTheDocument()
  })
})
