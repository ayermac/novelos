import './AuthorWorkbench.css'
import AuthorChapterRail from './AuthorChapterRail'
import AuthorWritingSurface, { SurfaceTabKey, GenerationErrorDetails } from './AuthorWritingSurface'
import AuthorAgentPanel from './AuthorAgentPanel'
import { StepStatus } from '../../hooks/useSSEStream'
import type { WorkflowTimelineData } from '../../lib/api'

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
  current_node?: string | null
}

interface Step {
  key: string
  label: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  error_message?: string
  logs?: {
    id?: string
    timestamp?: string
    level?: 'info' | 'success' | 'warning' | 'error'
    message: string
  }[]
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
  run_doctor?: RunDoctor
}

interface RunDoctor {
  category?: string
  severity?: 'info' | 'warning' | 'error' | string
  summary?: string
  next_action?: string
  evidence?: Record<string, unknown>
}

export interface PreflightWarning {
  code: string
  message: string
  severity: 'warning' | 'info'
  details?: Record<string, unknown>
}

interface AuthorWorkbenchProps {
  activeTab: SurfaceTabKey
  chapterDetail: ChapterDetail | null
  chapterLoading: boolean
  chapters: Chapter[]
  currentChapter: number
  currentChapterRecord: Chapter | null
  genError: string
  genErrorDetails: GenerationErrorDetails | null
  isLaunching: boolean
  isStub: boolean
  isStreaming: boolean
  isWorkflowRunning?: boolean
  isChapterWorkflowRunning?: (chapterNumber: number) => boolean
  isProjectWorkflowRunning?: boolean
  runningWorkflowChapter?: number | null
  llmMode: string
  projectId: string
  runDetail: RunDetailData | null
  runsForChapter: Run[]
  sseSteps: Record<string, StepStatus>
  timeline?: WorkflowTimelineData | null
  timelineError?: string
  preflightWarnings?: PreflightWarning[]
  onGenerate: () => void
  onConfirmRegenerate?: () => void
  onGenerateNext?: () => void
  onMarkRunStuck?: (runId: string) => Promise<void> | void
  onPublish?: () => void
  onResetRunRecovery?: (runId: string) => Promise<void> | void
  onRetryRunNode?: (runId: string) => Promise<void> | void
  onBackfillMemory?: (runId: string, force?: boolean) => Promise<void> | void
  onWorkflowDone?: (runId: string, status: string | null) => void
  onResetRunRecoveryForChapter?: (chapterNumber: number) => Promise<void> | void
  publishPending?: boolean
  markStuckPending?: boolean
  resetRecoveryPending?: boolean
  memoryBackfillPending?: boolean
  regeneratePending?: boolean
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
  isProjectWorkflowRunning,
  runningWorkflowChapter,
  llmMode,
  projectId,
  runDetail,
  runsForChapter,
  sseSteps,
  timeline,
  timelineError,
  preflightWarnings,
  onGenerate,
  onConfirmRegenerate,
  onGenerateNext,
  onMarkRunStuck,
  onPublish,
  onResetRunRecovery,
  onRetryRunNode,
  onBackfillMemory,
  onWorkflowDone,
  onResetRunRecoveryForChapter,
  publishPending,
  markStuckPending,
  resetRecoveryPending,
  memoryBackfillPending,
  regeneratePending,
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
        isProjectWorkflowRunning={isProjectWorkflowRunning}
        runningWorkflowChapter={runningWorkflowChapter}
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
        isProjectWorkflowRunning={isProjectWorkflowRunning}
        runningWorkflowChapter={runningWorkflowChapter}
        llmMode={llmMode}
        projectId={projectId}
        runDetail={runDetail}
        runsForChapter={runsForChapter}
        sseSteps={sseSteps}
        timeline={timeline}
        timelineError={timelineError}
        preflightWarnings={preflightWarnings}
        onGenerate={onGenerate}
        onConfirmRegenerate={onConfirmRegenerate}
        onGenerateNext={onGenerateNext}
        onMarkRunStuck={onMarkRunStuck}
        onPublish={onPublish}
        onResetRunRecovery={onResetRunRecovery}
        onRetryRunNode={onRetryRunNode}
        onBackfillMemory={onBackfillMemory}
        onWorkflowDone={onWorkflowDone}
        publishPending={publishPending}
        markStuckPending={markStuckPending}
        resetRecoveryPending={resetRecoveryPending}
        memoryBackfillPending={memoryBackfillPending}
        regeneratePending={regeneratePending}
        onTabChange={onTabChange}
        onViewContent={onViewContent}
        onViewWorkflow={onViewWorkflow}
        onRefreshContent={onRefreshContent}
      />
      <AuthorAgentPanel
        activeTab={activeTab}
        currentChapter={currentChapter}
        currentChapterRecord={currentChapterRecord}
        llmMode={llmMode}
        runDetail={runDetail}
        runsForChapter={runsForChapter}
        isStreaming={isStreaming}
        isWorkflowRunning={isWorkflowRunning}
        isProjectWorkflowRunning={isProjectWorkflowRunning}
        runningWorkflowChapter={runningWorkflowChapter}
        sseSteps={sseSteps}
        genError={genError}
        timeline={timeline}
        onGenerate={onGenerate}
        onConfirmRegenerate={onConfirmRegenerate}
        onPublish={onPublish}
        onGenerateNext={onGenerateNext}
        onBackfillMemory={onBackfillMemory}
        publishPending={publishPending}
        memoryBackfillPending={memoryBackfillPending}
        regeneratePending={regeneratePending}
        onViewContent={onViewContent}
        onViewWorkflow={onViewWorkflow}
      />
    </div>
  )
}
