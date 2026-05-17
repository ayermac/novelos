import { beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import AuthorWorkbench from '../AuthorWorkbench'
import { get } from '../../../lib/api'

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
  onResetRunRecoveryForChapter: vi.fn(),
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
    vi.mocked(get).mockResolvedValue({ ok: true, data: null })
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
    expect(screen.getByText('本章还没有正文内容')).toBeInTheDocument()
    expect(screen.getByText('编剧将规划章节场景和情节')).toBeInTheDocument()
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

  it('blocking chapter menu shows reset recovery and not generate', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        chapters={[
          ...baseProps.chapters,
          { chapter_number: 5, status: 'blocking', word_count: 3800, title: '第五章' },
        ]}
        currentChapter={5}
        currentChapterRecord={{ chapter_number: 5, status: 'blocking', word_count: 3800, title: '第五章' }}
      />
    )
    fireEvent.click(screen.getByLabelText('第 5 章操作'))
    expect(screen.getByRole('menuitem', { name: /清除阻塞并重置/ })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /生成本章/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /继续生成/ })).not.toBeInTheDocument()
  })

  it('revision chapter menu shows reset recovery and continue generate', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        chapters={[
          ...baseProps.chapters,
          { chapter_number: 5, status: 'revision', word_count: 3800, title: '第五章' },
        ]}
        currentChapter={5}
        currentChapterRecord={{ chapter_number: 5, status: 'revision', word_count: 3800, title: '第五章' }}
      />
    )
    fireEvent.click(screen.getByLabelText('第 5 章操作'))
    expect(screen.getByRole('menuitem', { name: /清除阻塞并重置/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /继续生成/ })).toBeInTheDocument()
  })

  it('menu reset recovery targets the clicked chapter', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        chapters={[
          ...baseProps.chapters,
          { chapter_number: 5, status: 'blocking', word_count: 3800, title: '第五章' },
        ]}
        currentChapter={5}
        currentChapterRecord={{ chapter_number: 5, status: 'blocking', word_count: 3800, title: '第五章' }}
      />
    )
    fireEvent.click(screen.getByLabelText('第 5 章操作'))
    fireEvent.click(screen.getByRole('menuitem', { name: /清除阻塞并重置/ }))
    expect(baseProps.onResetRunRecoveryForChapter).toHaveBeenCalledWith(5)
    expect(baseProps.onResetRunRecovery).not.toHaveBeenCalled()
  })

  it('warns contradictory state when terminal chapter has running workflow', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        currentChapter={1}
        currentChapterRecord={baseProps.chapters[0]}
        runDetail={{
          run_id: 'run-contra',
          project_id: 'test-proj',
          chapter_number: 1,
          workflow_status: 'running',
          chapter_status: 'published',
          current_node: 'author',
          llm_mode: 'real',
          started_at: new Date().toISOString(),
          steps: [],
        }}
        runsForChapter={[{
          run_id: 'run-contra',
          chapter_number: 1,
          status: 'running',
          created_at: new Date().toISOString(),
        }]}
        isWorkflowRunning
      />
    )
    expect(screen.getByText('状态矛盾：终态章节仍有运行中工作流')).toBeInTheDocument()
    expect(screen.getByText(/本章状态已经是 已发布/)).toBeInTheDocument()
  })

  it('contradictory state takes priority over stale running', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        currentChapter={1}
        currentChapterRecord={baseProps.chapters[0]}
        runDetail={{
          run_id: 'run-contra-stale',
          project_id: 'test-proj',
          chapter_number: 1,
          workflow_status: 'running',
          chapter_status: 'published',
          current_node: 'author',
          llm_mode: 'real',
          started_at: '2000-01-01 00:00:00',
          steps: [],
        }}
        runsForChapter={[{
          run_id: 'run-contra-stale',
          chapter_number: 1,
          status: 'running',
          created_at: '2000-01-01T00:00:00',
        }]}
        isWorkflowRunning
      />
    )
    expect(screen.getByText('状态矛盾：终态章节仍有运行中工作流')).toBeInTheDocument()
    expect(screen.queryByText('工作流疑似卡住')).not.toBeInTheDocument()
    expect(screen.getAllByText(/已运行约/).length).toBeGreaterThan(0)
  })

  it('agent panel publish button shows pending spinner', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        currentChapter={2}
        currentChapterRecord={baseProps.chapters[1]}
        llmMode="real"
        publishPending
      />
    )
    const publishBtn = screen.getAllByRole('button', { name: /发布中/ }).find((b) =>
      b.closest('[aria-label="AI 助手面板"]')
    )
    expect(publishBtn).toBeDefined()
    expect(publishBtn).toBeDisabled()
  })

  it('agent panel recovery buttons show pending spinner', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        currentChapterRecord={{ chapter_number: 3, status: 'blocking', word_count: 3800, title: '第三章' }}
        runDetail={{
          run_id: 'run-block',
          project_id: 'test-proj',
          chapter_number: 3,
          workflow_status: 'blocked',
          chapter_status: 'blocking',
          current_node: 'human_review',
          llm_mode: 'real',
          started_at: '2026-05-13 10:00:00',
          steps: [{
            key: 'editor',
            label: '审核',
            description: '需要人工处理',
            status: 'blocked',
          }],
        }}
        runsForChapter={[{
          run_id: 'run-block',
          chapter_number: 3,
          status: 'blocked',
          created_at: '2026-05-13T10:00:00',
        }]}
        resetRecoveryPending
      />
    )
    const panel = screen.getByLabelText('AI 助手面板')
    const resetBtn = screen.getAllByRole('button', { name: /处理中/ }).find((b) =>
      panel.contains(b)
    )
    expect(resetBtn).toBeDefined()
    expect(resetBtn).toBeDisabled()
  })

  /* v5.8 Workflow Observability tests ----------------------------------- */

  it('renders timeline nodes with chinese labels from timeline data', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        timeline={{
          project_id: 'test-proj',
          chapter_number: 3,
          run_id: 'run-tl',
          run_status: 'completed',
          current_node: 'author',
          started_at: '2026-05-13T10:00:00',
          elapsed_minutes: 12,
          is_stale: false,
          recovery: { recommended_action: null, reason: null, safe_actions: [] },
          nodes: [
            {
              node_name: 'screenwriter',
              label: '编剧',
              node_group: 'creative_agent',
              node_type: 'creative_agent',
              status: 'completed',
              started_at: '2026-05-13T10:00:00',
              completed_at: '2026-05-13T10:05:00',
              duration_ms: 300000,
              messages: ['已生成章节场景规划'],
              artifacts: [{ type: 'scene_plan', label: '章节场景规划', artifact_id: 'art-1' }],
            },
            {
              node_name: 'author',
              label: '执笔',
              node_group: 'creative_agent',
              node_type: 'creative_agent',
              status: 'completed',
              started_at: '2026-05-13T10:05:00',
              completed_at: '2026-05-13T10:10:00',
              duration_ms: 300000,
              messages: ['已生成章节初稿'],
              artifacts: [],
            },
          ],
        }}
      />
    )
    expect(screen.getByText('编剧')).toBeInTheDocument()
    expect(screen.getAllByText('执笔').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('已生成章节场景规划').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryAllByText(/章节场景规划/).length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('scene_plan')).not.toBeInTheDocument()
  })

  it('workflow tab renders canonical LangGraph labels and groups from timeline', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        timeline={{
          project_id: 'test-proj',
          chapter_number: 3,
          run_id: 'run-canon',
          run_status: 'running',
          current_node: 'memory_curator',
          started_at: '2026-05-13T10:00:00',
          elapsed_minutes: 4,
          is_stale: false,
          recovery: { recommended_action: null, reason: null, safe_actions: [] },
          checkpoint: {
            checkpoint_exists: false,
            checkpoint_node: null,
            current_node: null,
            checkpoint_summary: null,
            state_keys: [],
            recovery_available: false,
          },
          nodes: [
            { node_name: 'health_check', label: '预检', node_group: 'system', node_type: 'system', status: 'completed', started_at: null, completed_at: null, duration_ms: null, messages: [], artifacts: [] },
            { node_name: 'screenwriter', label: '编剧', node_group: 'creative_agent', node_type: 'creative_agent', status: 'completed', started_at: null, completed_at: null, duration_ms: null, messages: [], artifacts: [] },
            { node_name: 'memory_curator', label: '记忆整理', node_group: 'support_agent', node_type: 'support_agent', status: 'running', started_at: null, completed_at: null, duration_ms: null, messages: ['开始记忆整理'], artifacts: [] },
            { node_name: 'awaiting_publish', label: '等待发布', node_group: 'terminal', node_type: 'terminal', status: 'pending', started_at: null, completed_at: null, duration_ms: null, messages: [], artifacts: [] },
            { node_name: 'archive', label: '归档', node_group: 'terminal', node_type: 'terminal', status: 'pending', started_at: null, completed_at: null, duration_ms: null, messages: [], artifacts: [] },
            { node_name: 'revision_router', label: '返修路由', node_group: 'router', node_type: 'router', status: 'pending', started_at: null, completed_at: null, duration_ms: null, messages: [], artifacts: [] },
            { node_name: 'human_review', label: '人工审核', node_group: 'terminal', node_type: 'terminal', status: 'pending', started_at: null, completed_at: null, duration_ms: null, messages: [], artifacts: [] },
          ],
        }}
      />
    )

    expect(screen.getByText('系统节点')).toBeInTheDocument()
    expect(screen.getByText('创作 Agent')).toBeInTheDocument()
    expect(screen.getByText('支撑 Agent')).toBeInTheDocument()
    expect(screen.getByText('终态/人工节点')).toBeInTheDocument()
    expect(screen.getAllByText('记忆整理').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('等待发布')).toBeInTheDocument()
    expect(screen.getByText('归档')).toBeInTheDocument()
    expect(screen.getByText('返修路由')).toBeInTheDocument()
    expect(screen.getByText('人工审核')).toBeInTheDocument()
  })

  it('checkpoint panel renders available and unavailable states', () => {
    const timelineBase = {
      project_id: 'test-proj',
      chapter_number: 3,
      run_id: 'run-checkpoint',
      run_status: 'running',
      current_node: 'author',
      started_at: '2026-05-13T10:00:00',
      elapsed_minutes: 1,
      is_stale: false,
      recovery: { recommended_action: null, reason: null, safe_actions: [] },
      nodes: [],
    }

    const { rerender } = render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        timeline={{
          ...timelineBase,
          checkpoint: {
            checkpoint_exists: true,
            checkpoint_node: 'author',
            current_node: 'author',
            checkpoint_summary: 'node=author, status=drafted',
            state_keys: ['chapter_status', 'current_node'],
            recovery_available: true,
          },
        }}
      />
    )

    expect(screen.getByText('Checkpoint')).toBeInTheDocument()
    expect(screen.getByText('存在')).toBeInTheDocument()
    expect(screen.getByText('可从 checkpoint 恢复')).toBeInTheDocument()
    expect(screen.getByText(/state keys：chapter_status、current_node/)).toBeInTheDocument()

    rerender(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        timeline={{
          ...timelineBase,
          checkpoint: {
            checkpoint_exists: false,
            checkpoint_node: null,
            current_node: null,
            checkpoint_summary: null,
            state_keys: [],
            recovery_available: false,
          },
        }}
      />
    )

    expect(screen.getByText('不可用')).toBeInTheDocument()
    expect(screen.getByText('无 checkpoint 恢复')).toBeInTheDocument()
  })

  it('legacy runDetail fallback is clearly labeled', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        runDetail={{
          run_id: 'run-legacy',
          project_id: 'test-proj',
          chapter_number: 3,
          workflow_status: 'completed',
          chapter_status: 'reviewed',
          current_node: 'editor',
          llm_mode: 'stub',
          started_at: '2026-05-13T10:00:00',
          steps: [{ key: 'editor', label: '审核', description: '完成', status: 'completed' }],
        }}
      />
    )

    expect(screen.getByText(/Legacy fallback/)).toBeInTheDocument()
    expect(screen.getByText(/可能缺少 memory_curator、awaiting_publish、archive/)).toBeInTheDocument()
  })

  it('running workflow fallback uses canonical nodes beyond the old five steps', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        isStreaming
        sseSteps={{
          author: {
            status: 'running',
            started_at: '2026-05-13T10:00:00',
            logs: [{ id: 'log-1', timestamp: '2026-05-13T10:00:00', level: 'info', message: '开始执笔撰写' }],
          },
        }}
      />
    )

    expect(screen.getByText('实时事件备用视图')).toBeInTheDocument()
    expect(screen.getByText('预检')).toBeInTheDocument()
    expect(screen.getByText('任务识别')).toBeInTheDocument()
    expect(screen.getByText('记忆整理')).toBeInTheDocument()
    expect(screen.getByText('等待发布')).toBeInTheDocument()
    expect(screen.getByText('归档')).toBeInTheDocument()
  })

  it('shows running node loading animation in timeline', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        timeline={{
          project_id: 'test-proj',
          chapter_number: 3,
          run_id: 'run-run',
          run_status: 'running',
          current_node: 'polisher',
          started_at: '2026-05-13T10:00:00',
          elapsed_minutes: 5,
          is_stale: false,
          recovery: { recommended_action: null, reason: null, safe_actions: [] },
          nodes: [
            {
              node_name: 'screenwriter',
              label: '编剧',
              status: 'completed',
              started_at: '2026-05-13T10:00:00',
              completed_at: '2026-05-13T10:02:00',
              duration_ms: 120000,
              messages: ['已生成章节场景规划'],
              artifacts: [],
            },
            {
              node_name: 'polisher',
              label: '润色',
              status: 'running',
              started_at: '2026-05-13T10:02:00',
              completed_at: null,
              duration_ms: null,
              messages: ['开始润色'],
              artifacts: [],
            },
          ],
        }}
      />
    )
    // Running node should have loading indicator (pulse animation class)
    const runningStep = screen.getAllByText('润色')
      .map((node) => node.closest('.step-item'))
      .find(Boolean)
    expect(runningStep).toHaveClass('step-running')
  })

  it('shows stale run recovery suggestions in timeline', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        timeline={{
          project_id: 'test-proj',
          chapter_number: 3,
          run_id: 'run-stale-tl',
          run_status: 'running',
          current_node: 'author',
          started_at: '2026-05-13T10:00:00',
          elapsed_minutes: 35,
          is_stale: true,
          recovery: {
            recommended_action: 'mark_stuck',
            reason: '运行已超过 30 分钟仍处于 running',
            safe_actions: [
              { key: 'mark_stuck', label: '标记为阻塞', safe: true },
              { key: 'reset_chapter', label: '清除阻塞并重置', safe: true, note: '保留当前正文和版本' },
            ],
          },
          nodes: [
            {
              node_name: 'author',
              label: '执笔',
              status: 'running',
              started_at: '2026-05-13T10:00:00',
              completed_at: null,
              duration_ms: null,
              messages: ['开始执笔撰写'],
              artifacts: [],
            },
          ],
        }}
      />
    )
    expect(screen.getByText('工作流疑似卡住')).toBeInTheDocument()
    expect(screen.getByText(/恢复建议/)).toBeInTheDocument()
    expect(screen.getAllByText('标记为阻塞').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('清除阻塞并重置').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/保留当前正文和版本/)).toBeInTheDocument()
  })

  it('shows targeted retry action for blocked author node', () => {
    const onRetryRunNode = vi.fn()
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        onRetryRunNode={onRetryRunNode}
        timeline={{
          project_id: 'test-proj',
          chapter_number: 3,
          run_id: 'run-author-blocked',
          run_status: 'blocked',
          current_node: 'author',
          started_at: '2026-05-13T10:00:00',
          elapsed_minutes: 5,
          is_stale: false,
          recovery: {
            recommended_action: 'retry_node',
            reason: '章节处于阻塞/返修状态，可保留已有产物并重试执笔。',
            safe_actions: [
              { key: 'retry_node', label: '重试执笔', safe: true, note: '恢复到 scripted，跳过已完成上游节点' },
              { key: 'reset_chapter', label: '清除阻塞并重置', safe: true, note: '回到 planned，完整重跑' },
            ],
          },
          nodes: [
            {
              node_name: 'author',
              label: '执笔',
              status: 'blocked',
              started_at: '2026-05-13T10:00:00',
              completed_at: null,
              duration_ms: null,
              messages: ['执笔撰写失败：LLM 响应超时'],
              artifacts: [],
            },
          ],
        }}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '重试执笔' }))
    expect(onRetryRunNode).toHaveBeenCalledWith('run-author-blocked')
    expect(screen.getByText(/跳过已完成上游节点/)).toBeInTheDocument()
  })

  it('shows inline error when timeline refresh fails', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        timelineError="获取工作流时间线失败"
      />
    )
    expect(screen.getByText(/刷新失败：获取工作流时间线失败/)).toBeInTheDocument()
  })

  it('does not show generate button for terminal chapter with timeline', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        currentChapter={1}
        currentChapterRecord={baseProps.chapters[0]}
        timeline={{
          project_id: 'test-proj',
          chapter_number: 1,
          run_id: 'run-pub',
          run_status: 'completed',
          current_node: 'publish',
          started_at: '2026-05-13T10:00:00',
          elapsed_minutes: null,
          is_stale: false,
          recovery: { recommended_action: null, reason: null, safe_actions: [] },
          nodes: [],
        }}
      />
    )
    expect(screen.queryByRole('button', { name: /生成本章/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /继续生成/ })).not.toBeInTheDocument()
  })

  /* v6.5.3 Chapter Writing Surface Polish tests ----------------------- */

  it('shows skeleton stack while chapter content is loading', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        chapterLoading
      />
    )
    const skeletonStack = document.querySelector('.ui-skeleton-stack')
    expect(skeletonStack).toBeInTheDocument()
  })

  it('places quality diagnosis before the chapter editor for quick access', async () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        chapterDetail={{
          project_id: 'test-proj',
          project_name: '测试项目',
          chapter_number: 3,
          title: '第三章',
          content: '正文内容',
          word_count: 3800,
          status: 'drafted',
          quality_score: null,
          created_at: '2026-05-16 10:00:00',
          updated_at: '2026-05-16 10:00:00',
        }}
      />
    )

    const diagnosis = screen.getByLabelText('质量诊断')
    await waitFor(() => expect(document.querySelector('.chapter-editor-surface')).toBeInTheDocument())
    const editor = document.querySelector('.chapter-editor-surface')
    expect(editor).toBeInTheDocument()
    expect(diagnosis.compareDocumentPosition(editor!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('keeps the header quality score stable when diagnosis opens', async () => {
    vi.mocked(get).mockImplementation(async (path: string) => {
      if (path.includes('/quality-diagnosis')) {
        return {
          ok: true,
          data: {
            overall_score: 69.2,
            dimensions: { death_penalty: 100, narrative_quality: 58 },
            findings: [],
            metrics: {
              word_count: 3992,
              paragraph_count: 129,
              sentence_count: 187,
              avg_sentence_length: 19.6,
              dialogue_ratio: 0,
              dialogue_count: 0,
            },
          },
        }
      }
      return { ok: true, data: null }
    })

    render(
      <AuthorWorkbench
        {...baseProps}
        currentChapterRecord={{ chapter_number: 3, status: 'drafted', word_count: 3800, title: '第三章', quality_score: 83 }}
        chapterDetail={{
          project_id: 'test-proj',
          project_name: '测试项目',
          chapter_number: 3,
          title: '第三章',
          content: '正文内容',
          word_count: 3800,
          status: 'drafted',
          quality_score: 83,
          created_at: '2026-05-16 10:00:00',
          updated_at: '2026-05-16 10:00:00',
        }}
      />
    )

    const strip = document.querySelector('.author-readiness-strip')
    expect(strip?.textContent).toContain('83')

    const diagnosis = screen.getByLabelText('质量诊断')
    fireEvent.click(within(diagnosis).getByRole('button'))

    await waitFor(() => expect(within(diagnosis).getByText('69.2')).toBeInTheDocument())
    expect(strip?.textContent).toContain('质量')
    expect(strip?.textContent).toContain('83')
    expect(strip?.textContent).not.toContain('诊断分')
  })

  it('empty state shows actionable next steps for ungenerated chapter', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        currentChapter={4}
        currentChapterRecord={baseProps.chapters[3]}
      />
    )
    expect(screen.getByText('本章还没有正文内容')).toBeInTheDocument()
    expect(screen.getByText('编剧将规划章节场景和情节')).toBeInTheDocument()
    expect(screen.getByText('执笔将撰写章节正文')).toBeInTheDocument()
    expect(screen.getByText('润色、审核后生成最终版本')).toBeInTheDocument()
    const surface = screen.getByLabelText('写作区')
    const generateBtn = screen.getAllByRole('button', { name: /生成本章/ }).find((b) => surface.contains(b))
    expect(generateBtn).toBeDefined()
  })

  it('planned chapter with preserved content asks for explicit overwrite instead of normal generate', () => {
    const onConfirmRegenerate = vi.fn()
    const preserved = { chapter_number: 4, status: 'planned', word_count: 900, title: '第四章' }

    render(
      <AuthorWorkbench
        {...baseProps}
        activeTab="workflow"
        chapters={[...baseProps.chapters.slice(0, 3), preserved]}
        currentChapter={4}
        currentChapterRecord={preserved}
        chapterDetail={{
          project_id: 'test-proj',
          project_name: '测试项目',
          chapter_number: 4,
          title: '第四章',
          content: '这是一段恢复后保留的正文。',
          word_count: 900,
          status: 'planned',
          quality_score: null,
          created_at: '2026-05-16 10:00:00',
          updated_at: '2026-05-16 10:00:00',
        }}
        onConfirmRegenerate={onConfirmRegenerate}
      />
    )

    expect(screen.getAllByRole('button', { name: /覆盖重生成/ }).length).toBeGreaterThanOrEqual(2)
    expect(screen.queryAllByRole('button', { name: /^生成本章$/ })).toHaveLength(0)

    fireEvent.click(screen.getAllByRole('button', { name: /覆盖重生成/ })[0])
    expect(onConfirmRegenerate).toHaveBeenCalled()
  })

  it('existing-content guard error shows review and confirm actions', () => {
    const onConfirmRegenerate = vi.fn()
    const onRefreshContent = vi.fn()

    render(
      <AuthorWorkbench
        {...baseProps}
        genError="第 2 章已有正文内容，不能按空白 planned 章节直接生成。"
        genErrorDetails={{
          hint: 'review_existing_content',
          word_count: 1200,
          chapter_status: 'planned',
        }}
        onConfirmRegenerate={onConfirmRegenerate}
        onRefreshContent={onRefreshContent}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /查看已有正文/ }))
    expect(onRefreshContent).toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /确认覆盖并重新生成/ }))
    expect(onConfirmRegenerate).toHaveBeenCalled()
  })

  it('chapter menu does not offer direct generate for planned chapter with preserved content', () => {
    const preserved = { chapter_number: 4, status: 'planned', word_count: 900, title: '第四章' }
    render(
      <AuthorWorkbench
        {...baseProps}
        chapters={[...baseProps.chapters.slice(0, 3), preserved]}
        currentChapter={4}
        currentChapterRecord={preserved}
      />
    )

    fireEvent.click(screen.getByLabelText('第 4 章操作'))
    expect(screen.getByRole('menuitem', { name: /查看正文后确认覆盖/ })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /生成本章/ })).not.toBeInTheDocument()
  })

  it('generate button shows loading state via LoadingButton when workflow is running', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        isWorkflowRunning
        currentChapter={4}
        currentChapterRecord={baseProps.chapters[3]}
      />
    )
    const generateBtn = screen.getAllByRole('button', { name: /生成中/ }).find((b) =>
      b.closest('[aria-label="写作区"]')
    )
    expect(generateBtn).toBeDefined()
    expect(generateBtn).toBeDisabled()
  })

  /* v6.5.4 Agent Process Narrative tests ----------------------------- */

  it('shows node-specific narrative in agent panel when workflow is running', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        isWorkflowRunning
        runDetail={{
          run_id: 'run-1',
          project_id: 'test-proj',
          chapter_number: 3,
          workflow_status: 'running',
          chapter_status: 'drafted',
          current_node: 'author',
          llm_mode: 'stub',
          started_at: new Date().toISOString(),
          steps: [],
        }}
      />
    )
    const panel = screen.getByLabelText('AI 助手面板')
    expect(within(panel).getByText('正在撰写章节正文...')).toBeInTheDocument()
    expect(within(panel).getByText('AI 正在根据场景规划撰写章节正文。')).toBeInTheDocument()
  })

  it('shows planner narrative when planner node is running', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        isWorkflowRunning
        runDetail={{
          run_id: 'run-2',
          project_id: 'test-proj',
          chapter_number: 3,
          workflow_status: 'running',
          chapter_status: 'planned',
          current_node: 'planner',
          llm_mode: 'stub',
          started_at: new Date().toISOString(),
          steps: [],
        }}
      />
    )
    const panel = screen.getByLabelText('AI 助手面板')
    expect(within(panel).getByText('正在规划章节结构...')).toBeInTheDocument()
    expect(within(panel).getByText('AI 正在分析章节目标、角色关系和伏笔，规划本章结构。')).toBeInTheDocument()
  })

  it('shows streaming step narrative in agent panel', () => {
    render(
      <AuthorWorkbench
        {...baseProps}
        isStreaming
        sseSteps={{
          polisher: {
            status: 'running',
            started_at: '2026-05-13T10:00:00Z',
            logs: [],
          },
        }}
      />
    )
    const panel = screen.getByLabelText('AI 助手面板')
    expect(within(panel).getByText('正在润色文字表达...')).toBeInTheDocument()
  })
})
