import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { HashRouter } from 'react-router-dom'
import StyleGuideModule from '../StyleGuideModule'
import { get, post } from '../../../lib/api'

vi.mock('../../../lib/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}))

describe('StyleGuideModule', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(post).mockResolvedValue({ ok: true, data: null })
  })

  it('uses hash-router-safe links for global style management', async () => {
    vi.mocked(get).mockResolvedValue({
      ok: true,
      data: {
        style_bibles: [
          {
            project_id: 'novel_2cmh',
            project_name: '潮汐档案',
            status: 'unknown',
            version: '1.0.0',
            updated_at: '2026-05-24 11:19:25',
          },
        ],
        style_gate_configs: [],
        style_samples: [],
        health: { total_projects: 1, projects_with_bible: 1, gate_configs: 0 },
      },
    })

    render(
      <HashRouter>
        <StyleGuideModule projectId="novel_2cmh" />
      </HashRouter>
    )

    await waitFor(() => expect(screen.getByText('状态: 待确认')).toBeInTheDocument())

    expect(screen.getByRole('link', { name: /全局风格管理/ })).toHaveAttribute('href', '#/style')
    expect(screen.getByRole('link', { name: /编辑/ })).toHaveAttribute('href', '#/style')
  })
})
