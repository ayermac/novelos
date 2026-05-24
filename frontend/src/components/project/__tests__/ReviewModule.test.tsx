import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { HashRouter } from 'react-router-dom'
import ReviewModule from '../ReviewModule'
import { get, post } from '../../../lib/api'

vi.mock('../../../lib/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}))

const blockedWorkspace = {
  project: { project_id: 'novel_2cmh', name: '潮汐档案' },
  chapters: [
    {
      chapter_number: 7,
      status: 'blocking',
      word_count: 0,
      title: '第 7 章（待命名）',
    },
  ],
  stats: { status_counts: { published: 6 } },
  recent_runs: [
    {
      run_id: 'd3015c57-5bec-4867-bf65-7229c4c8412c',
      chapter_number: 7,
      status: 'blocked',
      error_message: 'Author 未完成场景 beat 覆盖，正文未写到章末钩子',
    },
  ],
}

describe('ReviewModule', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(get).mockResolvedValue({ ok: true, data: blockedWorkspace })
    vi.mocked(post).mockResolvedValue({ ok: true, data: null })
    window.location.hash = '/'
  })

  it('uses a hash-safe workflow link for blocked chapter details in the desktop router', async () => {
    render(
      <HashRouter>
        <ReviewModule projectId="novel_2cmh" />
      </HashRouter>
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /审核中心/ })).toBeInTheDocument()
    })

    const detailLink = screen.getByRole('link', { name: '查看详情' })
    expect(detailLink.getAttribute('href')).toBe(
      '#/projects/novel_2cmh?module=chapters&chapter=7&view=workflow'
    )
  })
})
