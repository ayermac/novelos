/**
 * v6.1: SSE Stream Hook for real-time workflow execution events.
 *
 * Connects to /api/projects/{id}/chapters/{n}/workflow-stream
 * and provides live execution events for the workflow timeline.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import type { WorkflowExecutionEvent } from '../lib/api'

export interface WorkflowStreamState {
  isConnected: boolean
  isStreaming: boolean
  liveEvents: WorkflowExecutionEvent[]
  error: string | null
  doneStatus: string | null
}

/**
 * Hook for SSE streaming of workflow execution events.
 * Connects when a run is active, provides live events, auto-closes on done.
 */
export function useWorkflowStream(
  projectId: string | null,
  chapterNumber: number | null,
  runId: string | null,
  isActive: boolean,
): WorkflowStreamState {
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [liveEvents, setLiveEvents] = useState<WorkflowExecutionEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [doneStatus, setDoneStatus] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const previousRunRef = useRef<string | null>(null)

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsStreaming(false)
    setIsConnected(false)
  }, [])

  useEffect(() => {
    const streamKey = projectId && chapterNumber ? `${projectId}:${chapterNumber}:${runId || 'latest'}` : null
    if (previousRunRef.current !== streamKey) {
      previousRunRef.current = streamKey
      setDoneStatus(null)
      setLiveEvents([])
      setError(null)
    }

    // Only connect when a run is actively in progress
    if (!isActive || !projectId || !chapterNumber || doneStatus) {
      stopStream()
      return
    }

    if (typeof EventSource === 'undefined') {
      setError('浏览器不支持 SSE')
      return
    }

    setLiveEvents([])
    setError(null)
    setIsStreaming(true)

    let url = `/api/projects/${encodeURIComponent(projectId)}/chapters/${chapterNumber}/workflow-stream`
    if (runId) {
      url += `?run_id=${encodeURIComponent(runId)}`
    }

    const eventSource = new EventSource(url)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => setIsConnected(true)

    eventSource.addEventListener('workflow_event', (e: MessageEvent) => {
      try {
        const event: WorkflowExecutionEvent = JSON.parse(e.data)
        setLiveEvents((prev) => [...prev, event])
      } catch {
        // ignore parse errors
      }
    })

    eventSource.addEventListener('workflow_done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        setDoneStatus(data.status || 'done')
      } catch {
        setDoneStatus('done')
      }
      stopStream()
    })

    eventSource.onerror = () => {
      setError('SSE 连接断开')
      stopStream()
    }

    return () => {
      stopStream()
    }
  }, [isActive, projectId, chapterNumber, runId, doneStatus, stopStream])

  return { isConnected, isStreaming, liveEvents, error, doneStatus }
}

export default useWorkflowStream
