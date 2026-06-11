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
            status: 'draft',
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

    await waitFor(() => expect(screen.getByText('状态: 草稿')).toBeInTheDocument())

    expect(screen.getByRole('link', { name: /全局风格管理/ })).toHaveAttribute('href', '#/style')
    expect(screen.getByRole('link', { name: /编辑/ })).toHaveAttribute('href', '#/style?project_id=novel_2cmh')
  })

  it('shows active status label correctly', async () => {
    vi.mocked(get).mockResolvedValue({
      ok: true,
      data: {
        style_bibles: [
          {
            project_id: 'novel_active',
            project_name: 'Active Project',
            status: 'active',
            version: '1.0.0',
            updated_at: '2026-06-01 10:00:00',
          },
        ],
        style_gate_configs: [],
        style_samples: [],
        health: { total_projects: 1, projects_with_bible: 1, gate_configs: 0 },
      },
    })

    render(
      <HashRouter>
        <StyleGuideModule projectId="novel_active" />
      </HashRouter>
    )

    await waitFor(() => expect(screen.getByText('状态: 已启用')).toBeInTheDocument())
  })

  it('shows needs_review status label correctly', async () => {
    vi.mocked(get).mockResolvedValue({
      ok: true,
      data: {
        style_bibles: [
          {
            project_id: 'novel_review',
            project_name: 'Review Project',
            status: 'needs_review',
            version: '1.0.0',
            updated_at: '2026-06-01 10:00:00',
          },
        ],
        style_gate_configs: [],
        style_samples: [],
        health: { total_projects: 1, projects_with_bible: 1, gate_configs: 0 },
      },
    })

    render(
      <HashRouter>
        <StyleGuideModule projectId="novel_review" />
      </HashRouter>
    )

    await waitFor(() => expect(screen.getByText('状态: 待确认')).toBeInTheDocument())
  })

  it('does not show unknown label for empty status', async () => {
    vi.mocked(get).mockResolvedValue({
      ok: true,
      data: {
        style_bibles: [
          {
            project_id: 'novel_empty',
            project_name: 'Empty Status Project',
            status: '',
            version: '1.0.0',
            updated_at: '2026-06-01 10:00:00',
          },
        ],
        style_gate_configs: [],
        style_samples: [],
        health: { total_projects: 1, projects_with_bible: 1, gate_configs: 0 },
      },
    })

    render(
      <HashRouter>
        <StyleGuideModule projectId="novel_empty" />
      </HashRouter>
    )

    await waitFor(() => expect(screen.getByText('状态: 已建立')).toBeInTheDocument())
    expect(screen.queryByText(/unknown/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/未知/i)).not.toBeInTheDocument()
  })

  it('shows init success hint after initialization', async () => {
    vi.mocked(get).mockResolvedValue({
      ok: true,
      data: {
        style_bibles: [],
        style_gate_configs: [],
        style_samples: [],
        health: { total_projects: 1, projects_with_bible: 0, gate_configs: 0 },
      },
    })

    render(
      <HashRouter>
        <StyleGuideModule projectId="novel_init" />
      </HashRouter>
    )

    await waitFor(() => expect(screen.getByText('暂无风格指南')).toBeInTheDocument())

    const initButton = screen.getByRole('button', { name: /初始化风格指南/ })
    initButton.click()

    await waitFor(() => expect(screen.getByText(/风格指南初始化成功/i)).toBeInTheDocument())
  })
})
