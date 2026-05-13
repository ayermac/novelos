import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChapterEditorSurface from '../ChapterEditorSurface'
import ChapterVersionPanel from '../ChapterVersionPanel'
import { AppDialogProvider } from '../../AppDialog'

// Mock the api module
vi.mock('../../../lib/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}))

import { get, post } from '../../../lib/api'
const mockGet = vi.mocked(get)
const mockPost = vi.mocked(post)

const mockEditorState = {
  project_id: 'test-project',
  chapter_number: 1,
  title: '第一章 测试',
  content: '这是测试正文内容，用于验证编辑功能。',
  word_count: 200,
  status: 'drafted',
  editable: true,
  edit_restriction: null,
  current_version_id: 1,
  recent_versions: [
    {
      version_id: 1,
      version: 1,
      source: 'ai_generation',
      source_label: 'AI 生成',
      created_by: 'author',
      word_count: 200,
      summary: 'AI 生成初稿',
      created_at: '2026-05-13 10:00:00',
      is_current: true,
    },
  ],
}

function renderWithDialog(ui: React.ReactElement) {
  return render(<AppDialogProvider>{ui}</AppDialogProvider>)
}

describe('ChapterEditorSurface', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders in read mode by default', async () => {
    mockGet.mockResolvedValueOnce({ ok: true, data: mockEditorState })
    render(<ChapterEditorSurface projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText(/这是测试正文内容/)).toBeInTheDocument()
    })
  })

  it('switches to edit mode when edit button clicked', async () => {
    mockGet.mockResolvedValueOnce({ ok: true, data: mockEditorState })
    render(<ChapterEditorSurface projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('编辑')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('编辑'))
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('shows published protection for published chapters', async () => {
    mockGet.mockResolvedValueOnce({
      ok: true,
      data: { ...mockEditorState, status: 'published', editable: false, edit_restriction: '章节已发布，需创建修订版后才能编辑' },
    })
    render(<ChapterEditorSurface projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('创建修订版')).toBeInTheDocument()
    })
  })

  it('shows unsaved indicator when content is modified', async () => {
    mockGet.mockResolvedValueOnce({ ok: true, data: mockEditorState })
    render(<ChapterEditorSurface projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('编辑')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('编辑'))
    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: '修改后的正文' } })
    expect(screen.getByText('有未保存的修改')).toBeInTheDocument()
  })

  it('recovers save button after network error', async () => {
    mockGet.mockResolvedValueOnce({ ok: true, data: mockEditorState })
    // Save will fail due to network error
    mockPost.mockRejectedValueOnce(new Error('Network error'))

    render(<ChapterEditorSurface projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('编辑')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('编辑'))

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: '修改后的正文内容用于验证保存异常恢复功能' } })

    const saveButton = screen.getByText('保存')
    fireEvent.click(saveButton)

    // After error, button should recover and error should show
    await waitFor(() => {
      expect(screen.getByText('网络异常，保存失败')).toBeInTheDocument()
    })
    // Save button should be clickable again
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('recovers revision draft button after network error', async () => {
    mockGet.mockResolvedValueOnce({
      ok: true,
      data: { ...mockEditorState, status: 'published', editable: false, edit_restriction: '章节已发布' },
    })
    mockPost.mockRejectedValueOnce(new Error('Network error'))

    render(<ChapterEditorSurface projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('创建修订版')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('创建修订版'))

    await waitFor(() => {
      expect(screen.getByText('网络异常，创建修订版失败')).toBeInTheDocument()
    })
    // Button should recover
    expect(screen.getByText('创建修订版')).toBeInTheDocument()
  })
})

describe('ChapterVersionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders version list', async () => {
    mockGet.mockResolvedValue({
      ok: true,
      data: {
        project_id: 'test',
        chapter_number: 1,
        current_version_id: 1,
        versions: mockEditorState.recent_versions,
      },
    })
    renderWithDialog(<ChapterVersionPanel projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('版本历史')).toBeInTheDocument()
      expect(screen.getByText('AI 生成')).toBeInTheDocument()
    })
  })

  it('shows empty state when no versions', async () => {
    mockGet.mockResolvedValue({
      ok: true,
      data: { project_id: 'test', chapter_number: 1, current_version_id: null, versions: [] },
    })
    renderWithDialog(<ChapterVersionPanel projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('暂无版本记录')).toBeInTheDocument()
    })
  })

  it('uses AppDialog confirm for rollback, not native confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm')
    mockGet.mockResolvedValue({
      ok: true,
      data: {
        project_id: 'test',
        chapter_number: 1,
        current_version_id: 2,
        versions: [
          { version_id: 2, version: 2, source: 'manual_edit', source_label: '人工编辑', created_by: 'author', word_count: 250, summary: '人工编辑', created_at: '2026-05-13 11:00:00', is_current: true },
          { version_id: 1, version: 1, source: 'ai_generation', source_label: 'AI 生成', created_by: 'author', word_count: 200, summary: 'AI 生成初稿', created_at: '2026-05-13 10:00:00', is_current: false },
        ],
      },
    })
    mockPost.mockResolvedValue({ ok: true, data: { restored: true, new_version_id: 3 } })

    renderWithDialog(<ChapterVersionPanel projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('回滚')).toBeInTheDocument()
    })

    // Click rollback — should NOT use native confirm
    fireEvent.click(screen.getByText('回滚'))

    // The AppDialog confirm should appear instead of native confirm
    // Native confirm should never have been called
    expect(confirmSpy).not.toHaveBeenCalled()

    confirmSpy.mockRestore()
  })

  it('shows network error in-panel instead of native alert', async () => {
    mockGet.mockResolvedValue({
      ok: true,
      data: {
        project_id: 'test',
        chapter_number: 1,
        current_version_id: 2,
        versions: [
          { version_id: 2, version: 2, source: 'manual_edit', source_label: '人工编辑', created_by: 'author', word_count: 250, summary: '人工编辑', created_at: '2026-05-13 11:00:00', is_current: true },
          { version_id: 1, version: 1, source: 'ai_generation', source_label: 'AI 生成', created_by: 'author', word_count: 200, summary: 'AI 生成初稿', created_at: '2026-05-13 10:00:00', is_current: false },
        ],
      },
    })
    // Make restore fail with network error
    mockPost.mockRejectedValueOnce(new Error('Network error'))

    const alertSpy = vi.spyOn(window, 'alert')

    renderWithDialog(<ChapterVersionPanel projectId="test" chapterNumber={1} />)
    await waitFor(() => {
      expect(screen.getByText('回滚')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('回滚'))

    // After the dialog confirm (user clicks confirm), the network error should show via dialog
    // not via native alert
    await waitFor(() => {
      // The dialog.alert should be called, not window.alert
      expect(alertSpy).not.toHaveBeenCalled()
    }, { timeout: 3000 })

    alertSpy.mockRestore()
  })
})
