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

  let data: unknown
  try {
    data = await response.json()
  } catch {
    return {
      ok: false,
      error: {
        code: `HTTP_${response.status}`,
        message: response.statusText || '请求失败',
      },
    }
  }
  const maybeEnvelope = data as { ok?: unknown; detail?: unknown }
  if (typeof maybeEnvelope.ok !== 'boolean') {
    return {
      ok: false,
      error: {
        code: `HTTP_${response.status}`,
        message: typeof maybeEnvelope.detail === 'string' ? maybeEnvelope.detail : response.statusText || '请求失败',
      },
    }
  }
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

export async function del<T = unknown>(path: string, body?: unknown): Promise<EnvelopeResponse<T>> {
  return api<T>(path, {
    method: 'DELETE',
    body: body ? JSON.stringify(body) : undefined,
  })
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

// ── v5.7 Version API types ────────────────────────────────

export interface VersionSummary {
  version_id: number
  version: number
  source: string
  source_label: string
  created_by: string
  word_count: number
  summary: string | null
  created_at: string
  is_current: boolean
}

export interface EditorState {
  project_id: string
  chapter_number: number
  title: string
  content: string
  word_count: number
  status: string
  editable: boolean
  edit_restriction: string | null
  current_version_id: number | null
  recent_versions: VersionSummary[]
}

export interface VersionDetail {
  version_id: number
  version: number
  content: string
  word_count: number
  source: string
  source_label: string
  created_by: string
  base_version_id: number | null
  summary: string | null
  metadata: unknown
  created_at: string
  is_current: boolean
}

export interface VersionDiff {
  left_version_id: number
  right_version_id: number
  added: string
  removed: string
  unchanged: string
  changed_blocks: { type: string; lines?: string[]; removed_lines?: string[]; added_lines?: string[] }[]
  word_count_delta: number
}

export interface LocalRevisionResult {
  replacement_text: string
  change_summary: string
  risk_notes: string[]
  selection_start: number
  selection_end: number
  mode: string
}

// ── v5.8 Workflow Timeline types ──────────────────────────

export interface WorkflowTimelineArtifact {
  type: string
  label: string
  artifact_id: string
}

export interface WorkflowTimelineNode {
  node_name: string
  label: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  messages: string[]
  artifacts: WorkflowTimelineArtifact[]
}

export interface WorkflowTimelineRecovery {
  recommended_action: string | null
  reason: string | null
  safe_actions: {
    key: string
    label: string
    safe: boolean
    note?: string
  }[]
}

export interface WorkflowTimelineData {
  project_id: string
  chapter_number: number
  run_id: string | null
  run_status: string | null
  current_node: string | null
  started_at: string | null
  elapsed_minutes: number | null
  is_stale: boolean
  recovery: WorkflowTimelineRecovery
  nodes: WorkflowTimelineNode[]
}
