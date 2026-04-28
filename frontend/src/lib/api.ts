const API_BASE = '/api'

export interface EnvelopeResponse<T = unknown> {
  ok: boolean
  error?: {
    code: string
    message: string
    details?: {
      missing?: string[]
      actions?: string[]
      [key: string]: unknown
    }
  }
  data?: T
}

export async function api<T = unknown>(
  path: string,
  options?: RequestInit
): Promise<EnvelopeResponse<T>> {
  const url = `${API_BASE}${path}`
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  const data = await response.json()
  return data as EnvelopeResponse<T>
}

export async function get<T = unknown>(path: string): Promise<EnvelopeResponse<T>> {
  return api<T>(path, { method: 'GET' })
}

export async function post<T = unknown>(
  path: string,
  body?: unknown
): Promise<EnvelopeResponse<T>> {
  return api<T>(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  })
}

export async function del<T = unknown>(path: string): Promise<EnvelopeResponse<T>> {
  return api<T>(path, { method: 'DELETE' })
}

export async function put<T = unknown>(
  path: string,
  body?: unknown
): Promise<EnvelopeResponse<T>> {
  return api<T>(path, {
    method: 'PUT',
    body: body ? JSON.stringify(body) : undefined,
  })
}
