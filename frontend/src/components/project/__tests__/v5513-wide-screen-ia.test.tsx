import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import {
  tSessionStopLabel,
  tWorkflowNodeLabel,
  tActionKey,
  tStepResult,
  WORKFLOW_NODE_LABEL,
  ACTION_KEY_LABEL,
  STEP_RESULT_LABEL,
} from '../../../lib/state-labels'

/* ------------------------------------------------------------------ */
/*  State label tests                                                  */
/* ------------------------------------------------------------------ */

describe('v5.5.13 state-labels', () => {
  describe('tSessionStopLabel', () => {
    it('returns 正在生产 for running status', () => {
      expect(tSessionStopLabel('running')).toBe('正在生产')
    })

    it('returns 已完成 for completed status', () => {
      expect(tSessionStopLabel('completed')).toBe('已完成')
    })

    it('returns 已取消 for cancelled status', () => {
      expect(tSessionStopLabel('cancelled')).toBe('已取消')
    })

    it('returns 试运行完成 for dry_run status', () => {
      expect(tSessionStopLabel('dry_run')).toBe('试运行完成')
    })

    it('returns 连接已断开，可重新接入 for paused + client_disconnected', () => {
      expect(tSessionStopLabel('paused', 'client_disconnected')).toBe('连接已断开，可重新接入')
    })

    it('returns 已暂停 for paused without client_disconnected', () => {
      expect(tSessionStopLabel('paused')).toBe('已暂停')
    })

    it('returns 已暂停 for paused with other stop_reason', () => {
      expect(tSessionStopLabel('paused', 'manual')).toBe('已暂停')
    })

    it('returns specific labels for stopped + known stop_reasons', () => {
      expect(tSessionStopLabel('stopped', 'token_budget_exceeded')).toBe('已因预算上限停止')
      expect(tSessionStopLabel('stopped', 'repeated_failure')).toBe('同一步多次失败，已停止')
      expect(tSessionStopLabel('stopped', 'consecutive_no_progress')).toBe('连续无进展，已停止')
      expect(tSessionStopLabel('stopped', 'review_required')).toBe('需要人工审核')
      expect(tSessionStopLabel('stopped', 'blocked')).toBe('被阻塞')
      expect(tSessionStopLabel('stopped', 'max_steps_reached')).toBe('已达最大步数')
      expect(tSessionStopLabel('stopped', 'completed')).toBe('已完成')
      expect(tSessionStopLabel('stopped', 'dry_run_preview')).toBe('试运行完成')
      expect(tSessionStopLabel('stopped', 'unsupported_action')).toBe('遇到不支持的操作，已停止')
    })

    it('returns 已停止 for stopped with unknown stop_reason', () => {
      expect(tSessionStopLabel('stopped')).toBe('已停止')
      expect(tSessionStopLabel('stopped', 'unknown_reason')).toBe('已停止')
    })

    it('returns 运行失败 for failed status', () => {
      expect(tSessionStopLabel('failed')).toBe('运行失败')
    })

    it('returns raw status for unknown status', () => {
      expect(tSessionStopLabel('unknown_status')).toBe('unknown_status')
    })

    it('never returns raw English for known statuses', () => {
      const knownStatuses = ['running', 'completed', 'cancelled', 'dry_run', 'paused', 'stopped', 'failed']
      for (const status of knownStatuses) {
        const label = tSessionStopLabel(status)
        expect(label).not.toBe(status)
      }
    })
  })

  describe('tWorkflowNodeLabel', () => {
    it('returns Chinese labels for all known nodes', () => {
      expect(tWorkflowNodeLabel('planner')).toBe('规划')
      expect(tWorkflowNodeLabel('screenwriter')).toBe('编剧')
      expect(tWorkflowNodeLabel('author')).toBe('执笔')
      expect(tWorkflowNodeLabel('polisher')).toBe('润色')
      expect(tWorkflowNodeLabel('editor')).toBe('审稿')
      expect(tWorkflowNodeLabel('publisher')).toBe('发布')
      expect(tWorkflowNodeLabel('publish')).toBe('发布')
      expect(tWorkflowNodeLabel('human_review')).toBe('人工审核')
    })

    it('returns — for null/undefined', () => {
      expect(tWorkflowNodeLabel(null)).toBe('—')
      expect(tWorkflowNodeLabel(undefined)).toBe('—')
    })

    it('returns raw node name for unknown nodes', () => {
      expect(tWorkflowNodeLabel('custom_node')).toBe('custom_node')
    })
  })

  describe('tActionKey', () => {
    it('returns Chinese labels for known action keys', () => {
      expect(tActionKey('generate_chapter')).toBe('生成章节')
      expect(tActionKey('review_chapter')).toBe('审核章节')
      expect(tActionKey('generate_genesis')).toBe('生成创世设定')
      expect(tActionKey('none')).toBe('无待办')
    })

    it('returns — for null/undefined', () => {
      expect(tActionKey(null)).toBe('—')
      expect(tActionKey(undefined)).toBe('—')
    })

    it('returns raw key for unknown keys', () => {
      expect(tActionKey('custom_action')).toBe('custom_action')
    })
  })

  describe('tStepResult', () => {
    it('returns Chinese labels for known results', () => {
      expect(tStepResult('success')).toBe('成功')
      expect(tStepResult('failed')).toBe('失败')
      expect(tStepResult('skipped')).toBe('跳过')
      expect(tStepResult('dry_run')).toBe('试运行')
      expect(tStepResult('blocked')).toBe('阻塞')
    })

    it('returns — for null/undefined', () => {
      expect(tStepResult(null)).toBe('—')
      expect(tStepResult(undefined)).toBe('—')
    })
  })

  describe('label maps are complete', () => {
    it('WORKFLOW_NODE_LABEL covers all expected nodes', () => {
      expect(Object.keys(WORKFLOW_NODE_LABEL)).toEqual(
        expect.arrayContaining(['screenwriter', 'author', 'polisher', 'editor', 'publish', 'human_review'])
      )
    })

    it('ACTION_KEY_LABEL covers all expected keys', () => {
      expect(Object.keys(ACTION_KEY_LABEL)).toEqual(
        expect.arrayContaining([
          'generate_genesis', 'review_genesis', 'wait_genesis',
          'repair_title_contract', 'generate_missing_context',
          'apply_memory_updates', 'generate_chapter', 'continue_next_chapter',
          'view_running_workflow', 'review_chapter', 'recover_blocked_run', 'generate_arc_plan', 'none',
        ])
      )
    })

    it('STEP_RESULT_LABEL covers all expected results', () => {
      expect(Object.keys(STEP_RESULT_LABEL)).toEqual(
        expect.arrayContaining(['success', 'failed', 'skipped', 'dry_run', 'blocked', 'unsupported', 'unknown'])
      )
    })
  })
})

/* ------------------------------------------------------------------ */
/*  CSS grid structure tests (static file checks)                     */
/* ------------------------------------------------------------------ */

describe('v5.5.13 wide-screen grid structure', () => {
  const projectDetailPath = resolve(__dirname, '../../../pages/ProjectDetail.tsx')
  const overviewPath = resolve(__dirname, '../ProjectOverviewModule.tsx')

  it('ProjectDetail.tsx contains .project-overview-grid CSS rules', () => {
    const css = readFileSync(projectDetailPath, 'utf-8')
    expect(css).toContain('.project-overview-grid')
    expect(css).toContain('.overview-main')
    expect(css).toContain('.overview-sidebar')
  })

  it('ProjectDetail.tsx has responsive breakpoints for overview grid', () => {
    const css = readFileSync(projectDetailPath, 'utf-8')
    expect(css).toContain('grid-template-columns: 1fr 340px')
    expect(css).toContain('grid-template-columns: 1fr 400px')
    expect(css).toContain('grid-template-columns: 1fr 440px')
  })

  it('ProjectOverviewModule uses .project-overview-grid wrapper', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('project-overview-grid')
    expect(content).toContain('overview-main')
    expect(content).toContain('overview-sidebar')
  })

  it('ProjectOverviewModule imports from state-labels.ts', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain("from '../../lib/state-labels'")
    expect(content).toContain('tSessionStopLabel')
    expect(content).toContain('tActionKey')
    expect(content).toContain('tStepResult')
  })

  it('ProjectOverviewModule does NOT have local STOP_REASON_MAP', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).not.toContain('STOP_REASON_MAP')
    expect(content).not.toContain('ACTION_KEY_MAP')
    expect(content).not.toContain('RESULT_MAP')
  })

  it('ProjectOverviewModule splits chapter progress into book target and batch', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('全书')
    expect(content).toContain('批次')
    expect(content).toContain('total_chapters_planned')
  })

  it('ProjectOverviewModule CTA has 查看实时进度 for disconnected+running', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('查看第')
    expect(content).toContain('章实时进度')
    expect(content).toContain('hasRunningWorkflow')
  })

  it('ProjectOverviewModule link uses module=chapters (not module=chapter)', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('module=chapters')
    expect(content).not.toContain('module=chapter&')
    expect(content).toContain('view=workflow')
  })

  it('ProjectDetail routes overview menu to ProjectOverviewModule, not chapter workbench', () => {
    const content = readFileSync(projectDetailPath, 'utf-8')
    expect(content).toContain("activeModule === 'chapters' ?")
    expect(content).not.toContain("activeModule === 'chapters' || activeModule === 'overview'")
    expect(content).toContain("case 'overview':")
    expect(content).toContain('return <ProjectOverviewModule')
  })

  it('ProjectOverviewModule disables main CTA when any target workflow is running', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('has_running_target_workflow')
    expect(content).toContain('targetCh')
    expect(content).toContain('处理第')
    expect(content).toMatch(/disabled=\{[^}]*hasRunningWorkflow/)
  })

  it('ProjectOverviewModule keeps view-running-workflow CTA clickable while a workflow is running', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain("action.key === 'view_running_workflow'")
    expect(content).toContain("nextActionKey === 'view_running_workflow'")
    expect(content).toContain('hasRunningWorkflow && !isPrimaryNavigationAction')
  })

  it('ChapterWorkspace RunDetailSidebar uses translated chapter status', () => {
    const wsContent = readFileSync(resolve(__dirname, '../ChapterWorkspace.tsx'), 'utf-8')
    expect(wsContent).toContain('tChapterStatus(runDetail.chapter_status)')
    expect(wsContent).not.toContain('章节状态：{runDetail.chapter_status}')
  })

  it('ChapterWorkspace RunDetailSidebar uses translated run status in recent runs', () => {
    const wsContent = readFileSync(resolve(__dirname, '../ChapterWorkspace.tsx'), 'utf-8')
    expect(wsContent).toContain('tWorkflowStatus(run.status)')
  })

  it('ChapterWorkspace RunDetailSidebar disables generate when running', () => {
    const wsContent = readFileSync(resolve(__dirname, '../ChapterWorkspace.tsx'), 'utf-8')
    expect(wsContent).toContain('isStreaming || workflowStatus')
    expect(wsContent).toContain('生成中...')
  })

  it('ChapterWorkspace ContentTab disables generate when isWorkflowRunning', () => {
    const wsContent = readFileSync(resolve(__dirname, '../ChapterWorkspace.tsx'), 'utf-8')
    // ContentTab empty-state button should check isWorkflowRunning
    expect(wsContent).toContain('isWorkflowRunning')
    // ContentTab props should accept isWorkflowRunning
    expect(wsContent).toMatch(/function ContentTab\(\{[^}]*isWorkflowRunning/)
  })

  it('ProjectDetail auto_generate effect guards against workspace not loaded', () => {
    const pdContent = readFileSync(resolve(__dirname, '../../../pages/ProjectDetail.tsx'), 'utf-8')
    // handleGenerate should require workspace before checking recent_runs
    expect(pdContent).toMatch(/handleGenerate.*if.*!workspace/s)
    // auto_generate effect should bail if workspace is undefined
    expect(pdContent).toMatch(/if.*!workspace.*generating.*isStreaming/s)
  })

  it('ProjectDetail polls running workflow details while workflow view stays open', () => {
    const pdContent = readFileSync(resolve(__dirname, '../../../pages/ProjectDetail.tsx'), 'utf-8')
    expect(pdContent).toContain('window.setInterval')
    expect(pdContent).toContain("activeTab !== 'workflow'")
    expect(pdContent).toContain("workflow_status === 'running'")
    expect(pdContent).toContain('loadRunDetail(pollingRunId, { silent: true })')
  })
})

/* ------------------------------------------------------------------ */
/*  v5.5.14 stabilization structure tests                             */
/* ------------------------------------------------------------------ */

describe('v5.5.14 release stabilization health summary', () => {
  const overviewPath = resolve(__dirname, '../ProjectOverviewModule.tsx')

  it('ProjectOverviewModule fetches the project health summary', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('ProductionHealthSummary')
    expect(content).toContain('/production/health-summary')
    expect(content).toContain('setHealthSummary')
  })

  it('ProjectOverviewModule renders author-facing health actions', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain('项目健康需要处理')
    expect(content).toContain('handleHealthAction')
    expect(content).toContain('item.action_label')
  })

  it('obsolete session health action deletes the explicit session instead of bulk cleanup', () => {
    const content = readFileSync(overviewPath, 'utf-8')
    expect(content).toContain("item.key.startsWith('obsolete_session') && item.session_id")
    expect(content).toContain('handleDeleteSession(item.session_id)')
    expect(content).not.toContain('await handleCleanupSessions()')
  })
})
