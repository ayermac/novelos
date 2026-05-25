import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type React from 'react'
import Dashboard from '../Dashboard'

vi.mock('../../hooks/useApiQuery', () => ({
  useApiQuery: vi.fn((key: unknown[]) => {
    if (key[0] === 'dashboard') {
      return {
        data: {
          project_count: 1,
          recent_runs: [
            {
              run_id: 'run-18',
              project_id: 'novel_2cmh',
              project_name: '潮汐档案',
              chapter: 18,
              status: 'completed',
              created_at: '2026-05-24T18:00:00',
            },
          ],
          queue_count: 0,
          review_count: 0,
          llm_mode: 'real',
          attention_items: [],
        },
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      }
    }
    return {
      data: [
        {
          project_id: 'novel_2cmh',
          name: '潮汐档案',
          chapter_count: 18,
          created_at: '2026-05-24T18:00:00',
        },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    }
  }),
}))

vi.mock('react-router-dom', () => ({
  Link: ({ children, to, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string; children: React.ReactNode }) => (
    <a href={to} {...props}>{children}</a>
  ),
}))

describe('Dashboard', () => {
  it('continues to the chapter workbench without inventing the next chapter URL', () => {
    render(<Dashboard />)

    const link = screen.getByRole('link', { name: /进入工作台/ })
    expect(link).toHaveAttribute('href', '/projects/novel_2cmh?module=chapters')
    expect(link).not.toHaveAttribute('href', expect.stringContaining('chapter=19'))
  })
})
