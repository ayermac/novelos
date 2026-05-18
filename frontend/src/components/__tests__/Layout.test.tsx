import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Layout from '../Layout'

vi.mock('../../lib/api', () => ({
  get: vi.fn().mockResolvedValue({ ok: true, data: null }),
}))

function renderLayout() {
  return render(
    <MemoryRouter
      initialEntries={['/projects']}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route path="projects" element={<div>项目列表</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Layout', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
    delete window.__NOVELOS_DESKTOP__
  })

  it('collapses and expands the desktop sidebar', () => {
    const { container } = renderLayout()
    const sidebar = screen.getByLabelText('主菜单')
    const mainArea = container.querySelector('.main-area')

    expect(sidebar).not.toHaveClass('collapsed')
    expect(mainArea).not.toHaveClass('sidebar-collapsed')

    fireEvent.click(screen.getByRole('button', { name: '收起主菜单' }))

    expect(sidebar).toHaveClass('collapsed')
    expect(mainArea).toHaveClass('sidebar-collapsed')
    expect(screen.getByRole('button', { name: '展开主菜单' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('link', { name: '项目' })).toHaveAttribute('title', '项目')

    fireEvent.click(screen.getByRole('button', { name: '展开主菜单' }))

    expect(sidebar).not.toHaveClass('collapsed')
    expect(mainArea).not.toHaveClass('sidebar-collapsed')
    expect(screen.getByRole('button', { name: '收起主菜单' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('toggles and persists the visual theme', () => {
    renderLayout()

    expect(document.documentElement.dataset.theme).toBe('light')

    fireEvent.click(screen.getByRole('button', { name: '切换到夜间模式' }))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(window.localStorage.getItem('novelos.theme')).toBe('dark')
    expect(screen.getByRole('button', { name: '切换到日间模式' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '切换到日间模式' }))

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(window.localStorage.getItem('novelos.theme')).toBe('light')
  })

  it('uses a relative logo path inside the desktop client', () => {
    Object.defineProperty(window, '__NOVELOS_DESKTOP__', {
      configurable: true,
      value: { apiBaseUrl: 'http://127.0.0.1:8765' },
    })

    const { container } = renderLayout()

    expect(container.querySelector('.brand-icon img')).toHaveAttribute('src', './logo.png')
  })
})
