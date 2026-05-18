import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProjectHeader from '../ProjectHeader'

describe('ProjectHeader', () => {
  it('shows project id and copies it for support diagnostics', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })

    render(
      <MemoryRouter>
        <ProjectHeader projectId="novel_support_case" projectName="测试项目" isStub={false} />
      </MemoryRouter>
    )

    expect(screen.getByText('测试项目')).toBeInTheDocument()
    expect(screen.getByText('novel_support_case')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '复制项目 ID' }))
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('novel_support_case')
    })
  })
})
