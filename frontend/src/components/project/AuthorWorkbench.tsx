import './AuthorWorkbench.css'
import AuthorChapterRail from './AuthorChapterRail'
import AuthorWritingSurface, { SurfaceTabKey } from './AuthorWritingSurface'
import AuthorAgentPanel from './AuthorAgentPanel'
import { StepStatus } from '../../hooks/useSSEStream'

export type { SurfaceTabKey }

interface Chapter {
  chapter_number: number
  status: string
  word_count: number
  quality_score?: number
  title?: string
}

interface ChapterDetail {
  project_id: string
  project_name: string
  chapter_number: number
  title: string
  status: string
  word_count: number
  quality_score: number | null
  content: string
  created_at: string
  updated_at: string
}

interface Run {
  run_id: string
  chapter_number: number
  status: string
  created_at: string
  error_message?: string
}

interface Step {
  key: string
  label: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  error_message?: string
  artifacts?: {
    summary: string
    output_preview?: string
    [key: string]: unknown
  } | null
}

interface RunDetailData {
  run_id: string
  project_id: string
  chapter_number: number
  workflow_status: string
  chapter_status: string
  current_node?: string | null
  llm_mode: string
  started_at?: string
  completed_at?: string
  steps: Step[]
  error_message?: string | null
  total_tokens?: number | null
  duration_ms?: number | null
}

interface AuthorWorkbenchProps {
  activeTab: SurfaceTabKey
  chapterDetail: ChapterDetail | null
  chapterLoading: boolean
  chapters: Chapter[]
  currentChapter: number
  currentChapterRecord: Chapter | null
  genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  isLaunching: boolean
  isStub: boolean
  isStreaming: boolean
  isWorkflowRunning?: boolean
  isChapterWorkflowRunning?: (chapterNumber: number) => boolean
  llmMode: string
  projectId: string
  runDetail: RunDetailData | null
  runsForChapter: Run[]
  sseSteps: Record<string, StepStatus>
  onGenerate: () => void
  onGenerateNext?: () => void
  onMarkRunStuck?: (runId: string) => Promise<void> | void
  onPublish?: () => void
  onResetRunRecovery?: (runId: string) => Promise<void> | void
  onResetRunRecoveryForChapter?: (chapterNumber: number) => Promise<void> | void
  publishPending?: boolean
  markStuckPending?: boolean
  resetRecoveryPending?: boolean
  onGenerateChapter?: (chapterNumber: number) => void
  onGenerateNextFromChapter?: (chapterNumber: number) => void
  onPublishChapter?: (chapterNumber: number) => void
  onOpenChapterView?: (chapterNumber: number, tab: SurfaceTabKey) => void
  onSelectChapter: (chapterNumber: number) => void
  onTabChange: (tab: SurfaceTabKey) => void
  onViewContent: () => void
  onViewWorkflow: (runId: string) => void
  onRefreshContent?: () => void
}

export default function AuthorWorkbench({
  activeTab,
  chapterDetail,
  chapterLoading,
  chapters,
  currentChapter,
  currentChapterRecord,
  genError,
  genErrorDetails,
  isLaunching,
  isStub,
  isStreaming,
  isWorkflowRunning,
  isChapterWorkflowRunning,
  llmMode,
  projectId,
  runDetail,
  runsForChapter,
  sseSteps,
  onGenerate,
  onGenerateNext,
  onMarkRunStuck,
  onPublish,
  onResetRunRecovery,
  onResetRunRecoveryForChapter,
  publishPending,
  markStuckPending,
  resetRecoveryPending,
  onGenerateChapter,
  onGenerateNextFromChapter,
  onPublishChapter,
  onOpenChapterView,
  onSelectChapter,
  onTabChange,
  onViewContent,
  onViewWorkflow,
  onRefreshContent,
}: AuthorWorkbenchProps) {
  return (
    <div className="author-workbench">
      <AuthorChapterRail
        chapters={chapters}
        currentChapter={currentChapter}
        llmMode={llmMode}
        isChapterWorkflowRunning={isChapterWorkflowRunning}
        onSelectChapter={onSelectChapter}
        onGenerateChapter={onGenerateChapter}
        onGenerateNextFromChapter={onGenerateNextFromChapter}
        onPublishChapter={onPublishChapter}
        onResetRunRecoveryForChapter={onResetRunRecoveryForChapter}
        onOpenChapterView={onOpenChapterView}
      />
      <AuthorWritingSurface
        activeTab={activeTab}
        chapterDetail={chapterDetail}
        chapterLoading={chapterLoading}
        currentChapter={currentChapter}
        currentChapterRecord={currentChapterRecord}
        genError={genError}
        genErrorDetails={genErrorDetails}
        isLaunching={isLaunching}
        isStub={isStub}
        isStreaming={isStreaming}
        isWorkflowRunning={isWorkflowRunning}
        llmMode={llmMode}
        projectId={projectId}
        runDetail={runDetail}
        runsForChapter={runsForChapter}
        sseSteps={sseSteps}
        onGenerate={onGenerate}
        onGenerateNext={onGenerateNext}
        onMarkRunStuck={onMarkRunStuck}
        onPublish={onPublish}
        onResetRunRecovery={onResetRunRecovery}
        publishPending={publishPending}
        markStuckPending={markStuckPending}
        resetRecoveryPending={resetRecoveryPending}
        onTabChange={onTabChange}
        onViewContent={onViewContent}
        onViewWorkflow={onViewWorkflow}
        onRefreshContent={onRefreshContent}
      />
      <AuthorAgentPanel
        currentChapter={currentChapter}
        currentChapterRecord={currentChapterRecord}
        llmMode={llmMode}
        runDetail={runDetail}
        runsForChapter={runsForChapter}
        isStreaming={isStreaming}
        isWorkflowRunning={isWorkflowRunning}
        sseSteps={sseSteps}
        genError={genError}
        onGenerate={onGenerate}
        onMarkRunStuck={onMarkRunStuck}
        onPublish={onPublish}
        onGenerateNext={onGenerateNext}
        onResetRunRecovery={onResetRunRecovery}
        publishPending={publishPending}
        markStuckPending={markStuckPending}
        resetRecoveryPending={resetRecoveryPending}
        onViewContent={onViewContent}
        onViewWorkflow={onViewWorkflow}
      />
    </div>
  )
}
