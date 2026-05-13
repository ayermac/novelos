import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AppDialogProvider } from '../AppDialog'
import { useAppDialog } from '../AppDialogContext'

function ConfirmHarness({ onResult }: { onResult: (value: boolean) => void }) {
  const dialog = useAppDialog()
  return (
    <button
      onClick={async () => {
        const ok = await dialog.confirm({
          title: '删除项目',
          message: '确认删除？',
          tone: 'danger',
          confirmLabel: '删除',
        })
        onResult(ok)
      }}
    >
      open
    </button>
  )
}

function PromptHarness({ onResult }: { onResult: (value: string | null) => void }) {
  const dialog = useAppDialog()
  return (
    <button
      onClick={async () => {
        const value = await dialog.prompt({
          title: '初始化',
          message: '输入项目 ID',
          placeholder: 'project_id',
        })
        onResult(value)
      }}
    >
      prompt
    </button>
  )
}

describe('AppDialogProvider', () => {
  it('renders in-app confirm dialog and resolves confirm result', async () => {
    const onResult = vi.fn()
    render(
      <AppDialogProvider>
        <ConfirmHarness onResult={onResult} />
      </AppDialogProvider>
    )

    fireEvent.click(screen.getByRole('button', { name: 'open' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('删除项目')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('supports prompt input without native browser prompt', async () => {
    const onResult = vi.fn()
    render(
      <AppDialogProvider>
        <PromptHarness onResult={onResult} />
      </AppDialogProvider>
    )

    fireEvent.click(screen.getByRole('button', { name: 'prompt' }))
    fireEvent.change(screen.getByPlaceholderText('project_id'), { target: { value: 'novel_3v2o' } })
    fireEvent.click(screen.getByRole('button', { name: '确认' }))

    await waitFor(() => expect(onResult).toHaveBeenCalledWith('novel_3v2o'))
  })
})
