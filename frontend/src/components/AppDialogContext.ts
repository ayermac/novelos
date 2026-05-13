import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'

export type DialogTone = 'default' | 'info' | 'success' | 'warning' | 'danger'

export interface BaseDialogOptions {
  title?: string
  message: ReactNode
  tone?: DialogTone
  confirmLabel?: string
  cancelLabel?: string
  details?: ReactNode
}

export interface PromptDialogOptions extends BaseDialogOptions {
  initialValue?: string
  placeholder?: string
}

export interface AppDialogApi {
  alert: (options: BaseDialogOptions | string) => Promise<void>
  confirm: (options: BaseDialogOptions | string) => Promise<boolean>
  prompt: (options: PromptDialogOptions) => Promise<string | null>
}

const noopDialog: AppDialogApi = {
  alert: async () => undefined,
  confirm: async () => false,
  prompt: async () => null,
}

export const AppDialogContext = createContext<AppDialogApi>(noopDialog)

export function normalizeDialogOptions(options: BaseDialogOptions | string): BaseDialogOptions {
  return typeof options === 'string' ? { message: options } : options
}

export function useAppDialog() {
  return useContext(AppDialogContext)
}
