import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import WorkflowTimeline from '../WorkflowTimeline'

describe('WorkflowTimeline', () => {
  it('surfaces evidence failure on the collapsed node header', () => {
    render(
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
                event_type: 'evidence_verified',
                status: 'fail',
                message: '正文产物未保存',
              },
            ],
            evidence: {
              has_evidence: true,
              has_evidence_failure: true,
              event_count: 1,
            },
          },
        ]}
      />,
    )

    const authorNode = screen.getByText('执笔').closest('.step-item')
    expect(authorNode).toBeTruthy()
    expect(within(authorNode as HTMLElement).getByText('证据校验失败')).toBeInTheDocument()
  })

  it('shows execution process events after expansion', () => {
    render(
      <WorkflowTimeline
        steps={[
          {
            key: 'polisher',
            label: '润色',
            description: '优化文字表达',
            status: 'completed',
            events: [
              {
                id: 2,
                node_name: 'polisher',
                event_type: 'diff_generated',
                status: 'info',
                message: '生成润色差异：修改 12 处表达',
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

    fireEvent.click(screen.getByRole('button', { name: '查看过程' }))
    expect(screen.getByText('实时工作过程')).toBeInTheDocument()
    expect(screen.getByText('生成润色差异：修改 12 处表达')).toBeInTheDocument()
  })
})
