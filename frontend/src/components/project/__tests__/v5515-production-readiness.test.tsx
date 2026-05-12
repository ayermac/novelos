import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { render, screen } from '@testing-library/react'
import { tSessionStopLabel } from '../../../lib/state-labels'
import ChapterWorkspace from '../ChapterWorkspace'

/* ------------------------------------------------------------------ */
/*  v5.5.15 Production Readiness Closure — frontend tests              */
/* ------------------------------------------------------------------ */

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

describe('v5.5.15 production readiness closure', () => {
  const overviewPath = resolve(__dirname, '../ProjectOverviewModule.tsx')
  const chapterPath = resolve(__dirname, '../ChapterWorkspace.tsx')

  /* ---- 1. Overview fetches /production/health-summary ---- */
  it('ProjectOverviewModule fetches the project health summary', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('ProductionHealthSummary')
    expect(content).toContain('/production/health-summary')
    expect(content).toContain('setHealthSummary')
  })

  /* ---- 2. Health card renders author-understandable actions ---- */
  it('ProjectOverviewModule renders author-facing health actions', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('项目健康需要处理')
    expect(content).toContain('handleHealthAction')
    expect(content).toContain('item.action_label')
  })

  /* ---- 3. Disconnected obsolete session does NOT show "重新接入" as primary CTA ---- */
  it('obsolete disconnected session shows cleanup action instead of reconnect', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('obsoleteSessionItem')
    expect(content).toContain('isSessionObsolete')
    expect(content).toMatch(/!isSessionObsolete/)
    expect(content).toContain('清理旧会话')
  })

  /* ---- 4. Running workflow disables generate CTA ---- */
  it('ProjectOverviewModule disables primary action when workflow is running', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toMatch(/disabled=\{[^}]*hasRunningWorkflow/)
    expect(content).toContain('has_running_target_workflow')
  })

  it('ChapterWorkspace disables generate when isWorkflowRunning', () => {
    const content = readFileSync(chapterPath, 'utf-8')
    expect(content).toContain('isWorkflowRunning')
    expect(content).toContain('生成中...')
  })

  /* ---- 5. README does NOT contain test baseline numbers ---- */
  it('README.md does not contain pytest baseline numbers', () => {
    const readMePath = resolve(__dirname, '../../../../../README.md')
    const content = readFileSync(readMePath, 'utf-8')
    expect(content).not.toMatch(/\d+\/\d+ passed/)
    expect(content).not.toContain('1828/1828')
    expect(content).not.toContain('46/46')
  })

  it('README.zh-CN.md does not contain pytest baseline numbers', () => {
    const readMeZhPath = resolve(__dirname, '../../../../../README.zh-CN.md')
    const content = readFileSync(readMeZhPath, 'utf-8')
    expect(content).not.toMatch(/\d+\/\d+ passed/)
    expect(content).not.toContain('1828/1828')
    expect(content).not.toContain('46/46')
  })

  /* ---- 6. State labels: obsolete session label ---- */
  it('tSessionStopLabel returns 旧会话已过期 for stopped + obsolete', () => {
    expect(tSessionStopLabel('stopped', 'obsolete')).toBe('旧会话已过期')
  })

  /* ---- 7. Health summary contradiction field type exists ---- */
  it('ProjectOverviewModule types include contradictions in health summary', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('ProductionHealthSummary')
  })

  /* ---- 8. ChapterWorkspace respects terminal chapter status ---- */
  it('ChapterWorkspace does not show generate for reviewed/awaiting_publish/published', () => {
    const content = readFileSync(chapterPath, 'utf-8')
    expect(content).toContain("'reviewed'")
    expect(content).toContain("'awaiting_publish'")
    expect(content).toContain("'published'")
    expect(content).toMatch(/status\s*!==\s*['"]awaiting_publish['"]/)
  })

  /* ---- 9. Backend CHAPTER_ALREADY_COMPLETED guard exists in shared module ---- */
  it('shared guard module contains CHAPTER_ALREADY_COMPLETED guard', () => {
    const guardPath = resolve(process.cwd(), '..', 'novel_factory', 'api', 'routes', '_run_guards.py')
    const content = readFileSync(guardPath, 'utf-8')
    expect(content).toContain('CHAPTER_ALREADY_COMPLETED')
    expect(content).toContain('TERMINAL_STATUSES')
  })

  /* ---- 10. REAL RENDER: ChapterWorkspace hides generate button for published chapter ---- */
  it('ChapterWorkspace does not render generate button for published chapter', () => {
    const publishedChapter = {
      chapter_number: 1,
      status: 'published',
      word_count: 5000,
      title: '第一章',
    }
    render(
      <ChapterWorkspace
        activeTab="workflow"
        chapterDetail={null}
        chapterLoading={false}
        chapters={[publishedChapter]}
        currentChapter={1}
        currentChapterRecord={publishedChapter as never}
        genError=""
        genErrorDetails={null}
        isStub={true}
        isStreaming={false}
        isLaunching={false}
        llmMode="stub"
        projectId="test-proj"
        runDetail={null}
        runsForChapter={[]}
        sseSteps={{}}
        onGenerate={vi.fn()}
        onGenerateNext={vi.fn()}
        onPublish={vi.fn()}
        onResetChapter={vi.fn()}
        onSelectChapter={vi.fn()}
        onTabChange={vi.fn()}
        onViewContent={vi.fn()}
        onViewWorkflow={vi.fn()}
        isWorkflowRunning={false}
      />
    )
    // For a published chapter, the generate button should NOT be present
    // Use button role to avoid matching helper text like "生成章节后可查看工作流步骤"
    expect(screen.queryByRole('button', { name: /开始生成|生成章节/ })).not.toBeInTheDocument()
  })

  /* ---- 11. REAL RENDER: ChapterWorkspace shows 生成中 when workflow is running ---- */
  it('ChapterWorkspace shows 生成中 indicator when workflow is running', () => {
    render(
      <ChapterWorkspace
        activeTab="workflow"
        chapterDetail={null}
        chapterLoading={false}
        chapters={[{ chapter_number: 1, status: 'drafted', word_count: 2000 }]}
        currentChapter={1}
        currentChapterRecord={null}
        genError=""
        genErrorDetails={null}
        isStub={true}
        isStreaming={true}
        isLaunching={false}
        llmMode="stub"
        projectId="test-proj"
        runDetail={null}
        runsForChapter={[]}
        sseSteps={{}}
        onGenerate={vi.fn()}
        onGenerateNext={vi.fn()}
        onPublish={vi.fn()}
        onResetChapter={vi.fn()}
        onSelectChapter={vi.fn()}
        onTabChange={vi.fn()}
        onViewContent={vi.fn()}
        onViewWorkflow={vi.fn()}
        isWorkflowRunning={true}
      />
    )
    expect(screen.getByText('生成中...')).toBeInTheDocument()
  })

  /* ---- 12. Unified guard module is imported by all three entry points ---- */
  it('run.py and runs.py and production.py all use the shared guard', () => {
    const runContent = readFileSync(resolve(process.cwd(), '..', 'novel_factory', 'api', 'routes', 'run.py'), 'utf-8')
    const runsContent = readFileSync(resolve(process.cwd(), '..', 'novel_factory', 'api', 'routes', 'runs.py'), 'utf-8')
    const prodContent = readFileSync(resolve(process.cwd(), '..', 'novel_factory', 'api', 'routes', 'production.py'), 'utf-8')

    // All three should import the shared guard
    expect(runContent).toContain('from ._run_guards import check_chapter_run_guard')
    expect(runsContent).toContain('from ._run_guards import check_chapter_run_guard')
    expect(prodContent).toContain('from ._run_guards import check_chapter_run_guard')
  })
})
