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

  it('shows node-specific narrative for running steps without logs', () => {
    render(
      <WorkflowTimeline
        steps={[
          {
            key: 'author',
            label: '执笔',
            description: '生成正文',
            status: 'running',
            logs: [],
          },
        ]}
      />,
    )

    expect(screen.getByText('正在撰写章节正文...')).toBeInTheDocument()
  })

  it('shows fallback_used event with human-readable narrative label', () => {
    render(
      <WorkflowTimeline
        steps={[
          {
            key: 'editor',
            label: '审稿',
            description: '审核内容',
            status: 'completed',
            events: [
              {
                id: 3,
                node_name: 'editor',
                event_type: 'fallback_used',
                status: 'warning',
                message: '审核维度不完整，使用兜底策略',
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
    expect(screen.getByText('降级兜底')).toBeInTheDocument()
    expect(screen.getByText('审核维度不完整，使用兜底策略')).toBeInTheDocument()
  })

  it('keeps LLM completion token and latency metadata in the right meta column', () => {
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
                id: 4,
                node_name: 'author',
                event_type: 'llm_completed',
                status: 'pass',
                message: 'LLM 调用完成：耗时 169.2s，3944 tokens',
                latency_ms: 169200,
                token_count: 3944,
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
    const eventRow = screen.getByText('LLM 调用完成').closest('.exec-event')
    expect(eventRow).toBeTruthy()
    const metas = eventRow?.querySelector('.exec-event-metas')
    expect(metas).toBeTruthy()
    expect(within(eventRow as HTMLElement).getByText('模型返回完成')).toBeInTheDocument()
    expect(within(metas as HTMLElement).getByText('3944 tokens')).toBeInTheDocument()
    expect(within(metas as HTMLElement).getByText('169.2s')).toBeInTheDocument()
  })
})
