import { describe, expect, it, vi } from 'vitest'
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
})
