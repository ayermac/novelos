import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { LoadingButton, Skeleton, ToastProvider, useToast } from '../index'

function ToastTrigger() {
  const { showToast } = useToast()
  return (
    <button
      type="button"
      onClick={() => showToast({ tone: 'success', title: '已保存', message: '设置已更新', durationMs: 0 })}
    >
      show toast
    </button>
  )
}

describe('interaction primitives', () => {
  it('renders loading button with busy state and spinner label isolation', () => {
    render(
      <LoadingButton loading loadingText="保存中">
        保存
      </LoadingButton>,
    )

    const button = screen.getByRole('button', { name: '保存中' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('保存中')).toBeInTheDocument()
  })

  it('renders skeleton as decorative loading structure', () => {
    const { container } = render(<Skeleton height={24} width="80%" />)
    const skeleton = container.querySelector('.ui-skeleton')
    expect(skeleton).toBeInTheDocument()
    expect(skeleton).toHaveAttribute('aria-hidden', 'true')
    expect(skeleton).toHaveStyle({ height: '24px', width: '80%' })
  })

  it('shows and dismisses toast notifications', () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'show toast' }))

    expect(screen.getByText('已保存')).toBeInTheDocument()
    expect(screen.getByText('设置已更新')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '关闭通知' }))
    expect(screen.queryByText('已保存')).not.toBeInTheDocument()
  })

  it('allows useToast outside provider as a safe no-op for isolated component tests', () => {
    render(<ToastTrigger />)
    fireEvent.click(screen.getByRole('button', { name: 'show toast' }))
    expect(screen.queryByText('已保存')).not.toBeInTheDocument()
  })
})
