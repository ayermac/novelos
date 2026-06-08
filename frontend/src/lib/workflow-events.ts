import type { WorkflowExecutionEvent } from './api'

export function workflowEventContentKey(event: WorkflowExecutionEvent): string {
  const payload = event.payload ? JSON.stringify(event.payload) : ''
  return [
    event.node_name || '',
    event.agent_id || '',
    event.event_type || '',
    event.status || '',
    event.message || '',
    event.token_count ?? '',
    event.latency_ms ?? '',
    payload,
  ].join(':')
}
