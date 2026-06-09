// ── Desktop integration ───────────────────────────────────────
export interface DesktopRuntimeStatus {
  status: string
  pid: number | null
  apiBaseUrl: string
  port: number
  startTime: string | null
  lastError: {
    exitCode: number | null
    signal: string | null
    timestamp: string
    reason: string
  } | null
  stdoutLogPath?: string
  stderrLogPath?: string
}

declare global {
  interface Window {
    __NOVELOS_DESKTOP__?: {
      apiBaseUrl: string
      getApiBaseUrl?: () => string
      platform: string
      userDataPath: string
      openDataDir?: () => Promise<void>
      openConfigDir?: () => Promise<void>
      openLogsDir?: () => Promise<void>
      secretStatus?: () => Promise<Record<string, { configured: boolean; storage: string }>>
      setApiKey?: (envName: string, value: string) => Promise<void>
      deleteApiKey?: (envName: string) => Promise<void>
      runtimeStatus?: () => Promise<DesktopRuntimeStatus>
      restartSidecar?: () => Promise<{ success: boolean; apiBaseUrl: string | null }>
      exportDiagnostics?: () => Promise<{ success: boolean; path: string; message: string }>
      quitApp?: () => Promise<void>
      onRuntimeStatus?: (callback: (status: DesktopRuntimeStatus) => void) => () => void
    }
  }
}

export function getApiBase(): string {
  if (typeof window !== 'undefined' && window.__NOVELOS_DESKTOP__?.getApiBaseUrl) {
    return window.__NOVELOS_DESKTOP__.getApiBaseUrl()
  }
  if (typeof window !== 'undefined' && window.__NOVELOS_DESKTOP__?.apiBaseUrl) {
    return window.__NOVELOS_DESKTOP__.apiBaseUrl
  }
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL as string
  }
  return '/api'
}

export function apiUrl(path: string): string {
  const base = getApiBase()
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  // Avoid double slash when base ends with / and path starts with /
  if (base.endsWith('/') && normalizedPath.startsWith('/')) {
    return base + normalizedPath.slice(1)
  }
  return base + normalizedPath
}

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
  const url = apiUrl(path)
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


export async function patch<
  T = unknown,
  B extends Record<string, unknown> = Record<string, unknown>,
>(
  path: string,
  body?: B,
): Promise<EnvelopeResponse<T>> {
  return api<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined })
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
  node_group?: 'system' | 'creative_agent' | 'support_agent' | 'terminal' | 'router' | 'unknown'
  node_type?: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'skipped'
  // v6.6.11: Node-level semantic fields
  node_status?: 'pending' | 'running' | 'succeeded' | 'warning' | 'failed' | 'skipped' | 'blocked'
  domain_status?: 'success' | 'partial_success' | 'fallback' | 'degraded' | 'failed' | 'blocked' | 'needs_human' | 'pending' | 'ignored'
  severity?: 'success' | 'info' | 'warning' | 'error'
  retryable?: boolean
  blocking?: boolean
  next_action?: string | null
  action_label?: string | null
  user_message?: string
  flags?: Record<string, boolean>
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  messages: string[]
  artifacts: WorkflowTimelineArtifact[]
  events?: WorkflowExecutionEvent[]
  evidence?: WorkflowNodeEvidence
}

// v6.1: Execution event and evidence types

export interface WorkflowExecutionEvent {
  id?: number
  node_name?: string
  agent_id?: string
  event_type: string
  status?: string
  message?: string
  payload?: Record<string, unknown>
  token_count?: number | null
  latency_ms?: number | null
  created_at?: string
}

export interface WorkflowNodeEvidence {
  has_evidence: boolean
  has_warnings?: boolean
  has_evidence_failure?: boolean
  latest_event_summary?: string
  event_count?: number
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

export interface WorkflowTimelineCheckpoint {
  checkpoint_exists: boolean
  checkpoint_node: string | null
  current_node: string | null
  checkpoint_summary: string | null
  state_keys: string[]
  recovery_available: boolean
}

export interface MemoryStatusSnapshot {
  memory_status: string
  memory_trusted: boolean
  batch_count?: number
  trusted_batch_count?: number
  fallback_batch_count?: number
  latest_memory_batch_id?: string | null
}

export interface WorkflowTimelineData {
  project_id: string
  chapter_number: number
  run_id: string | null
  run_status: string | null
  chapter_status?: string | null
  current_node: string | null
  started_at: string | null
  elapsed_minutes: number | null
  is_stale: boolean
  memory_curator_running?: boolean
  memory_curator_lock?: Record<string, unknown> | null
  memory_status?: MemoryStatusSnapshot | null
  recovery: WorkflowTimelineRecovery
  checkpoint?: WorkflowTimelineCheckpoint
  nodes: WorkflowTimelineNode[]
}
