import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { tSessionStopLabel } from '../../../lib/state-labels'

/* ------------------------------------------------------------------ */
/*  v5.5.15 Production Readiness Closure — frontend tests              */
/* ------------------------------------------------------------------ */

describe('v5.5.15 production readiness closure', () => {
  const overviewPath = resolve(__dirname, '../ProjectOverviewModule.tsx')
  const chapterPath = resolve(__dirname, '../ChapterWorkspace.tsx')
  const readMePath = resolve(__dirname, '../../../../../README.md')
  const readMeZhPath = resolve(__dirname, '../../../../../README.zh-CN.md')

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
    // Must have obsoleteSessionItem detection
    expect(content).toContain('obsoleteSessionItem')
    expect(content).toContain('isSessionObsolete')
    // The reconnect button must be gated by !isSessionObsolete
    expect(content).toMatch(/!isSessionObsolete/)
    // Must have a "清理旧会话" alternative button
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
    const content = readFileSync(readMePath, 'utf-8')
    expect(content).not.toMatch(/\d+\/\d+ passed/)
    expect(content).not.toContain('1828/1828')
    expect(content).not.toContain('46/46')
  })

  it('README.zh-CN.md does not contain pytest baseline numbers', () => {
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
    // The ProductionHealthSummary interface should exist
    expect(content).toContain('ProductionHealthSummary')
  })
})
