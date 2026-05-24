/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import WorkflowTimeline from '../WorkflowTimeline'

describe('WorkflowTimeline null safety', () => {
  it('renders without crash when event payload is null', () => {
    // safePayload must handle null payload
    const { container } = render(
      <WorkflowTimeline
        steps={[
          {
            key: 'author',
            label: '执笔',
            description: '生成正文',
            status: 'completed',
            events: [
              {
                id: 1,
                node_name: 'author',
                event_type: 'llm_completed',
                status: 'pass',
                message: 'LLM done',
                payload: null as any,
              },
            ],
            evidence: {
              has_evidence: true,
              event_count: 1,
            },
          },
        ]}
      />,
    )
    expect(container.textContent).toContain('执笔')
  })

  it('renders without crash when event payload is not an object', () => {
    const { container } = render(
      <WorkflowTimeline
        steps={[
          {
            key: 'editor',
            label: '审核',
            description: '审核内容',
            status: 'completed',
            events: [
              {
                id: 2,
                node_name: 'editor',
                event_type: 'evidence_verified',
                status: 'pass',
                message: 'verified',
                payload: 'not-an-object' as any,
              },
            ],
            evidence: {
              has_evidence: true,
              event_count: 1,
            },
          },
        ]}
      />,
    )
    expect(container.textContent).toContain('审核')
  })

  it('renders without crash when event payload is undefined', () => {
    const { container } = render(
      <WorkflowTimeline
        steps={[
          {
            key: 'planner',
            label: '规划',
            description: '生成规划',
            status: 'completed',
            events: [
              {
                id: 3,
                node_name: 'planner',
                event_type: 'llm_completed',
                status: 'pass',
                message: 'done',
              },
            ],
            evidence: {
              has_evidence: true,
              event_count: 1,
            },
          },
        ]}
      />,
    )
    expect(container.textContent).toContain('规划')
  })

  it('sorts logs with null/undefined timestamps to the end stably', () => {
    // Render a step with mixed timestamp logs
    const { container } = render(
      <WorkflowTimeline
        steps={[
          {
            key: 'author',
            label: '执笔',
            description: '生成正文',
            status: 'completed',
            logs: [
              { id: 'log-1', timestamp: undefined as any, level: 'info' as const, message: 'No timestamp' },
              { id: 'log-2', timestamp: '2026-01-01T10:00:00', level: 'info' as const, message: 'Has timestamp' },
              { id: 'log-3', timestamp: null as any, level: 'info' as const, message: 'Null timestamp' },
            ],
          },
        ]}
      />,
    )
    // Should render without crash
    expect(container.textContent).toContain('执笔')
    expect(container.textContent).toContain('Has timestamp')
    expect(container.textContent).toContain('No timestamp')
    expect(container.textContent).toContain('Null timestamp')
  })

  it('renders without crash when step has missing optional fields', () => {
    const { container } = render(
      <WorkflowTimeline
        steps={[
          {
            key: 'screenwriter',
            label: '编剧',
            description: '场景规划',
            status: 'running',
            // No node_status, domain_status, severity, flags, etc.
          },
        ]}
      />,
    )
    expect(container.textContent).toContain('编剧')
  })

  it('renders without crash with extremely long log message', () => {
    const longMessage = 'A'.repeat(50000)
    const { container } = render(
      <WorkflowTimeline
        steps={[
          {
            key: 'author',
            label: '执笔',
            description: '生成正文',
            status: 'completed',
            logs: [
              { id: 'log-long', timestamp: '2026-01-01T10:00:00', level: 'info' as const, message: longMessage },
            ],
          },
        ]}
      />,
    )
    expect(container.textContent).toContain('执笔')
  })
})
