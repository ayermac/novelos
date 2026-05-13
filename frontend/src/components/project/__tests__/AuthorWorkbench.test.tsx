import { beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AuthorWorkbench from '../AuthorWorkbench'

// Mock API
vi.mock('../../../lib/api', () => ({
  get: vi.fn().mockResolvedValue({ ok: true, data: null }),
  post: vi.fn().mockResolvedValue({ ok: true, data: null }),
}))

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  Link: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children: React.ReactNode }) => (
    <a {...props}>{children}</a>
  ),
  useNavigate: () => vi.fn(),
}))

const baseProps = {
  activeTab: 'content' as const,
  chapterDetail: null,
  chapterLoading: false,
  chapters: [
    { chapter_number: 1, status: 'published', word_count: 5000, title: '第一章' },
    { chapter_number: 2, status: 'reviewed', word_count: 4200, title: '第二章' },
    { chapter_number: 3, status: 'drafted', word_count: 3800, title: '第三章' },
    { chapter_number: 4, status: 'planned', word_count: 0, title: '第四章' },
  ],
  currentChapter: 3,
  currentChapterRecord: { chapter_number: 3, status: 'drafted', word_count: 3800, title: '第三章' },
  genError: '',
  genErrorDetails: null,
  isLaunching: false,
  isStub: true,
  isStreaming: false,
  isWorkflowRunning: false,
  llmMode: 'stub',
  projectId: 'test-proj',
  runDetail: null,
  runsForChapter: [],
  sseSteps: {},
  onGenerate: vi.fn(),
  onGenerateNext: vi.fn(),
  onMarkRunStuck: vi.fn(),
  onPublish: vi.fn(),
  onResetRunRecovery: vi.fn(),
  onGenerateChapter: vi.fn(),
  onGenerateNextFromChapter: vi.fn(),
  onPublishChapter: vi.fn(),
  onOpenChapterView: vi.fn(),
  isChapterWorkflowRunning: vi.fn().mockReturnValue(false),
  onSelectChapter: vi.fn(),
  onTabChange: vi.fn(),
  onViewContent: vi.fn(),
  onViewWorkflow: vi.fn(),
}

describe('AuthorWorkbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    baseProps.isChapterWorkflowRunning.mockReturnValue(false)
  })

  it('renders three zones: chapter rail, writing surface, agent panel', () => {
    render(<AuthorWorkbench {...baseProps} />)
    expect(screen.getByLabelText('章节导航')).toBeInTheDocument()
    expect(screen.getByLabelText('写作区')).toBeInTheDocument()
    expect(screen.getByLabelText('AI 助手面板')).toBeInTheDocument()
  })

  it('highlights current chapter in rail', () => {
    render(<AuthorWorkbench {...baseProps} />)
    const items = screen.getAllByRole('button')
    const current = items.find((b) => b.classList.contains('active'))
    expect(current).toBeDefined()
    expect(current?.textContent).toContain('第三章')
  })

  it('shows chapter progress in rail', () => {
    render(<AuthorWorkbench {...baseProps} />)
    expect(screen.getByText('1/4')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
  })

  it('shows generate button for drafted chapter', () => {
    render(<AuthorWorkbench {...baseProps} />)
    expect(screen.getAllByRole('button', { name: /生成本章/ }).length).toBeGreaterThan(0)
  })

  it('does not show generate button for published chapter', () => {
    render(<AuthorWorkbench {...baseProps} currentChapter={1} currentChapterRecord={baseProps.chapters[0]} />)
    expect(screen.queryAllByRole('button', { name: /生成本章/ })).toHaveLength(0)
  })

  it('does not show generate button for reviewed chapter in real mode', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        currentChapter={2}
        currentChapterRecord={baseProps.chapters[1]}
        llmMode="real"
      />
    )
    expect(screen.queryAllByRole('button', { name: /生成本章/ })).toHaveLength(0)
  })

  it('shows publish button for reviewed + real mode', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        currentChapter={2}
        currentChapterRecord={baseProps.chapters[1]}
        llmMode="real"
      />
    )
    expect(screen.getAllByRole('button', { name: /确认发布/ }).length).toBeGreaterThan(0)
  })

  it('shows generate-next button for published chapter', () => {
    render(<AuthorWorkbench {...baseProps} currentChapter={1} currentChapterRecord={baseProps.chapters[0]} />)
    expect(screen.getAllByRole('button', { name: /生成下一章/ }).length).toBeGreaterThan(0)
  })

  it('disables generate when workflow is running', () => {
    render(<AuthorWorkbench {...baseProps} isWorkflowRunning />)
    for (const btn of screen.getAllByRole('button', { name: /生成中/ })) {
      expect(btn).toBeDisabled()
    }
  })

  it('shows content tab by default', () => {
    render(<AuthorWorkbench {...baseProps} />)
    const contentTab = screen.getByRole('button', { name: '正文' })
    expect(contentTab.classList.contains('active')).toBe(true)
  })

  it('renders empty state for planned chapter without content', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        currentChapter={4}
        currentChapterRecord={baseProps.chapters[3]}
      />
    )
    expect(screen.getByText('本章尚未生成')).toBeInTheDocument()
  })

  it('renders workflow timeline steps on workflow tab', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        runDetail={{
          run_id: 'run-1',
          project_id: 'test-proj',
          chapter_number: 3,
          workflow_status: 'completed',
          chapter_status: 'drafted',
          current_node: 'author',
          llm_mode: 'stub',
          steps: [
            {
              key: 'screenwriter',
              label: '编剧',
              description: '完成分场',
              status: 'completed',
            },
            {
              key: 'author',
              label: '执笔',
              description: '完成正文',
              status: 'completed',
            },
          ],
        }}
        runsForChapter={[{
          run_id: 'run-1',
          chapter_number: 3,
          status: 'completed',
          created_at: '2026-05-13T10:00:00',
        }]}
      />
    )
    expect(screen.getByText('编剧')).toBeInTheDocument()
    expect(screen.getByText('完成分场')).toBeInTheDocument()
    expect(screen.getByText('执笔')).toBeInTheDocument()
    expect(screen.getByText('完成正文')).toBeInTheDocument()
  })

  it('renders node logs while workflow is streaming', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        isStreaming
        sseSteps={{
          polisher: {
            status: 'running',
            started_at: '2026-05-13T10:00:00Z',
            logs: [
              {
                id: 'log-1',
                timestamp: '2026-05-13T10:00:00Z',
                level: 'info',
                message: '润色节点已开始处理。',
              },
            ],
          },
        }}
      />
    )

    expect(screen.getByText('工作流运行中')).toBeInTheDocument()
    expect(screen.getByText('节点日志')).toBeInTheDocument()
    expect(screen.getByText('润色节点已开始处理。')).toBeInTheDocument()
  })

  it('content tab shows loading state without workflow steps while streaming', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="content"
        isStreaming
        sseSteps={{
          polisher: {
            status: 'running',
            started_at: '2026-05-13T10:00:00Z',
            logs: [
              {
                id: 'log-1',
                timestamp: '2026-05-13T10:00:00Z',
                level: 'info',
                message: '润色节点已开始处理。',
              },
            ],
          },
        }}
      />
    )

    expect(screen.getByText('正文生成中')).toBeInTheDocument()
    expect(screen.queryByText('工作流运行中')).not.toBeInTheDocument()
    expect(screen.queryByText('润色节点已开始处理。')).not.toBeInTheDocument()
  })

  it('shows readable process draft labels instead of raw artifact keys', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="artifacts"
        runDetail={{
          run_id: 'run-artifacts',
          project_id: 'test-proj',
          chapter_number: 3,
          workflow_status: 'completed',
          chapter_status: 'polished',
          current_node: 'editor',
          llm_mode: 'real',
          steps: [
            {
              key: 'screenwriter',
              label: '编剧',
              description: '完成分场',
              status: 'completed',
              artifacts: {
                summary: 'scene_plan (screenwriter), scene_plan (screenwriter), scene_plan (screenwriter)',
                artifact_count: 3,
              },
            },
            {
              key: 'author',
              label: '执笔',
              description: '完成正文',
              status: 'completed',
              artifacts: {
                summary: 'draft (author), draft (author)',
                artifact_count: 2,
              },
            },
          ],
        }}
      />
    )

    expect(screen.getByRole('button', { name: '过程稿' })).toBeInTheDocument()
    expect(screen.getByText('分场大纲')).toBeInTheDocument()
    expect(screen.getByText('正文初稿')).toBeInTheDocument()
    expect(screen.getByText('已生成：分场规划 · 编剧（3 条记录）')).toBeInTheDocument()
    expect(screen.getByText('已生成：正文初稿 · 执笔（2 条记录）')).toBeInTheDocument()
    expect(screen.queryByText(/scene_plan/)).not.toBeInTheDocument()
    expect(screen.queryByText(/draft \(author\)/)).not.toBeInTheDocument()
  })

  it('labels long-running workflow as possibly stuck', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        runDetail={{
          run_id: 'run-stale',
          project_id: 'test-proj',
          chapter_number: 3,
          workflow_status: 'running',
          chapter_status: 'polished',
          current_node: 'polisher',
          llm_mode: 'real',
          started_at: '2000-01-01 00:00:00',
          steps: [
            {
              key: 'polisher',
              label: '润色',
              description: '优化文字表达',
              status: 'running',
            },
          ],
        }}
        runsForChapter={[{
          run_id: 'run-stale',
          chapter_number: 3,
          status: 'running',
          created_at: '2000-01-01 00:00:00',
        }]}
        isWorkflowRunning
      />
    )
    expect(screen.getByText('工作流疑似卡住')).toBeInTheDocument()
    expect(screen.getAllByText(/超过卡住阈值 30 分钟/).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /标记为阻塞/ }).length).toBeGreaterThan(0)
    expect(screen.getByText('打开恢复详情')).toBeInTheDocument()
  })

  it('shows reset recovery action for blocking chapter workflow', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        currentChapterRecord={{ chapter_number: 3, status: 'blocking', word_count: 3800, title: '第三章' }}
        runDetail={{
          run_id: 'run-blocked',
          project_id: 'test-proj',
          chapter_number: 3,
          workflow_status: 'blocked',
          chapter_status: 'blocking',
          current_node: 'human_review',
          llm_mode: 'real',
          started_at: '2026-05-13 10:00:00',
          steps: [
            {
              key: 'editor',
              label: '审核',
              description: '需要人工处理',
              status: 'blocked',
            },
          ],
        }}
        runsForChapter={[{
          run_id: 'run-blocked',
          chapter_number: 3,
          status: 'blocked',
          created_at: '2026-05-13T10:00:00',
        }]}
      />
    )
    expect(screen.getAllByRole('button', { name: /清除阻塞并重置/ }).length).toBeGreaterThan(0)
  })

  /* Chapter menu tests ------------------------------------------------ */

  it('renders chapter menu buttons with aria-label', () => {
    render(<AuthorWorkbench {...baseProps} />)
    expect(screen.getByLabelText('第 4 章操作')).toBeInTheDocument()
    expect(screen.getByLabelText('第 1 章操作')).toBeInTheDocument()
  })

  it('clicking menu button does not trigger onSelectChapter', () => {
    render(<AuthorWorkbench {...baseProps} />)
    const menuBtn = screen.getByLabelText('第 4 章操作')
    fireEvent.click(menuBtn)
    expect(baseProps.onSelectChapter).not.toHaveBeenCalled()
  })

  it('published chapter menu shows generate-next and not generate', () => {
    render(<AuthorWorkbench {...baseProps} currentChapter={1} currentChapterRecord={baseProps.chapters[0]} />)
    fireEvent.click(screen.getByLabelText('第 1 章操作'))
    expect(screen.getByRole('menuitem', { name: /生成下一章/ })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /生成本章/ })).not.toBeInTheDocument()
  })

  it('reviewed + real mode menu shows confirm publish', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        currentChapter={2}
        currentChapterRecord={baseProps.chapters[1]}
        llmMode="real"
      />
    )
    fireEvent.click(screen.getByLabelText('第 2 章操作'))
    expect(screen.getByRole('menuitem', { name: /确认发布/ })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /生成本章/ })).not.toBeInTheDocument()
  })

  it('running workflow disables generate action in menu', () => {
    baseProps.isChapterWorkflowRunning.mockImplementation((chapterNumber: number) => chapterNumber === 3)
    render(<AuthorWorkbench {...baseProps} isWorkflowRunning />)
    fireEvent.click(screen.getByLabelText('第 3 章操作'))
    expect(screen.getByText(/已有运行中工作流/)).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /生成本章/ })).not.toBeInTheDocument()
  })

  it('menu view workflow triggers onTabChange', () => {
    render(<AuthorWorkbench {...baseProps} />)
    fireEvent.click(screen.getByLabelText('第 4 章操作'))
    fireEvent.click(screen.getByRole('menuitem', { name: /查看工作流/ }))
    expect(baseProps.onOpenChapterView).toHaveBeenCalledWith(4, 'workflow')
  })

  it('menu generate targets the clicked inactive chapter', () => {
    render(<AuthorWorkbench {...baseProps} />)
    fireEvent.click(screen.getByLabelText('第 4 章操作'))
    fireEvent.click(screen.getByRole('menuitem', { name: /生成本章/ }))
    expect(baseProps.onGenerateChapter).toHaveBeenCalledWith(4)
    expect(baseProps.onGenerate).not.toHaveBeenCalled()
  })

  it('menu publish targets the clicked reviewed chapter', () => {
    render(<AuthorWorkbench {...baseProps} llmMode="real" />)
    fireEvent.click(screen.getByLabelText('第 2 章操作'))
    fireEvent.click(screen.getByRole('menuitem', { name: /确认发布/ }))
    expect(baseProps.onPublishChapter).toHaveBeenCalledWith(2)
    expect(baseProps.onPublish).not.toHaveBeenCalled()
  })

  it('menu generate-next targets the clicked published chapter', () => {
    render(<AuthorWorkbench {...baseProps} />)
    fireEvent.click(screen.getByLabelText('第 1 章操作'))
    fireEvent.click(screen.getByRole('menuitem', { name: /生成下一章/ }))
    expect(baseProps.onGenerateNextFromChapter).toHaveBeenCalledWith(1)
    expect(baseProps.onGenerateNext).not.toHaveBeenCalled()
  })

  it('running workflow state is evaluated per chapter in menu', () => {
    baseProps.isChapterWorkflowRunning.mockImplementation((chapterNumber: number) => chapterNumber === 4)
    render(<AuthorWorkbench {...baseProps} />)
    fireEvent.click(screen.getByLabelText('第 4 章操作'))
    expect(screen.getByText(/已有运行中工作流/)).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /生成本章/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('第 4 章操作'))
    fireEvent.click(screen.getByLabelText('第 3 章操作'))
    expect(screen.queryByText(/已有运行中工作流/)).not.toBeInTheDocument()
  })

  it('terminal chapters do not show generate chapter in menu', () => {
    // reviewed (stub) is terminal for generate
    render(<AuthorWorkbench {...baseProps} currentChapter={2} currentChapterRecord={baseProps.chapters[1]} />)
    fireEvent.click(screen.getByLabelText('第 2 章操作'))
    expect(screen.queryByRole('menuitem', { name: /生成本章/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /继续生成/ })).not.toBeInTheDocument()

    // awaiting_publish
    render(
      <AuthorWorkbench
        {...baseProps}
        chapters={[
          ...baseProps.chapters,
          { chapter_number: 5, status: 'awaiting_publish', word_count: 4000, title: '第五章' },
        ]}
        currentChapter={5}
        currentChapterRecord={{ chapter_number: 5, status: 'awaiting_publish', word_count: 4000, title: '第五章' }}
      />
    )
    fireEvent.click(screen.getByLabelText('第 5 章操作'))
    expect(screen.queryByRole('menuitem', { name: /生成本章/ })).not.toBeInTheDocument()
  })
})
