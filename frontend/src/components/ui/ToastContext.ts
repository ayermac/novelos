import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'

export type ToastTone = 'success' | 'info' | 'warning' | 'danger'

export interface ToastInput {
  title: string
  message?: ReactNode
  tone?: ToastTone
  durationMs?: number
}

export interface ToastContextValue {
  showToast: (toast: ToastInput) => number
  dismissToast: (id: number) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

const noopToastContext: ToastContextValue = {
  showToast: () => 0,
  dismissToast: () => {},
}

export function useToast() {
  const context = useContext(ToastContext)
  return context ?? noopToastContext
}
