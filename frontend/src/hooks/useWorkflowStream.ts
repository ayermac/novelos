/**
 * v6.8.4: SSE Stream Hook with auto-reconnect, heartbeat timeout, and event dedup.
 *
 * Connects to /api/projects/{id}/chapters/{n}/workflow-stream
 * and provides live execution events for the workflow timeline.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { apiUrl } from '../lib/api'
import type { WorkflowExecutionEvent } from '../lib/api'

const MAX_RETRIES = 10
const INITIAL_DELAY_MS = 1000
const MAX_DELAY_MS = 16000
const HEARTBEAT_TIMEOUT_MS = 30000

export interface WorkflowStreamState {
  isConnected: boolean
  isStreaming: boolean
  isReconnecting: boolean
  liveEvents: WorkflowExecutionEvent[]
  error: string | null
  doneStatus: string | null
}

export function useWorkflowStream(
  projectId: string | null,
  chapterNumber: number | null,
  runId: string | null,
  isActive: boolean,
): WorkflowStreamState {
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isReconnecting, setIsReconnecting] = useState(false)
  const [liveEvents, setLiveEvents] = useState<WorkflowExecutionEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [doneStatus, setDoneStatus] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const previousRunRef = useRef<string | null>(null)
  const retryCountRef = useRef(0)
  const lastEventIdRef = useRef<number>(0)
  const receivedEventIds = useRef<Set<number>>(new Set())
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const heartbeatTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const triggerReconnectRef = useRef<() => void>(() => undefined)
  const connectSSERef = useRef<(url: string) => void>(() => undefined)
  const urlRef = useRef<string>('')

  const resetHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current)
    heartbeatTimerRef.current = setTimeout(() => {
      setError('心跳超时，正在重连...')
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      triggerReconnectRef.current()
    }, HEARTBEAT_TIMEOUT_MS)
  }, [])

  const triggerReconnect = useCallback(() => {
    if (doneStatus || !isActive) return
    if (retryCountRef.current >= MAX_RETRIES) {
      setError('重连失败，请刷新页面')
      setIsStreaming(false)
      setIsReconnecting(false)
      return
    }
    setIsReconnecting(true)
    setError(null)
    const delay = Math.min(INITIAL_DELAY_MS * Math.pow(2, retryCountRef.current), MAX_DELAY_MS)
    retryCountRef.current++
    reconnectTimerRef.current = setTimeout(() => {
      if (doneStatus || !isActive) return
      const url = urlRef.current + (lastEventIdRef.current ? `&since_id=${lastEventIdRef.current}` : '')
      connectSSERef.current(url)
    }, delay)
  }, [doneStatus, isActive])

  const connectSSE = useCallback((url: string) => {
    if (typeof EventSource === 'undefined') {
      setError('浏览器不支持 SSE')
      return
    }

    const eventSource = new EventSource(url)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setIsConnected(true)
      setIsReconnecting(false)
      retryCountRef.current = 0
      resetHeartbeat()
    }

    eventSource.addEventListener('workflow_event', ((e: MessageEvent) => {
      try {
        const event: WorkflowExecutionEvent = JSON.parse(e.data)
        // Dedup
        if (event.id && receivedEventIds.current.has(event.id)) return
        if (event.id) {
          receivedEventIds.current.add(event.id)
          lastEventIdRef.current = event.id
        }
        setLiveEvents((prev) => [...prev, event])
        resetHeartbeat()
      } catch {
        // ignore parse errors
      }
    }) as EventListener)

    eventSource.addEventListener('workflow_done', ((e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        setDoneStatus(data.status || 'done')
      } catch {
        setDoneStatus('done')
      }
      if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current)
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      setIsStreaming(false)
      setIsConnected(false)
      setIsReconnecting(false)
    }) as EventListener)

    // SSE comment messages (heartbeat) also reset the timer
    eventSource.onmessage = () => {
      resetHeartbeat()
    }

    eventSource.onerror = () => {
      setIsConnected(false)
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current)
      triggerReconnectRef.current()
    }
  }, [resetHeartbeat])

  triggerReconnectRef.current = triggerReconnect
  connectSSERef.current = connectSSE

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current)
    setIsStreaming(false)
    setIsConnected(false)
    setIsReconnecting(false)
  }, [])

  useEffect(() => {
    const streamKey = projectId && chapterNumber ? `${projectId}:${chapterNumber}:${runId || 'latest'}` : null
    if (previousRunRef.current !== streamKey) {
      previousRunRef.current = streamKey
      setDoneStatus(null)
      setLiveEvents([])
      setError(null)
      receivedEventIds.current.clear()
      lastEventIdRef.current = 0
      retryCountRef.current = 0
    }

    if (!isActive || !projectId || !chapterNumber || doneStatus) {
      stopStream()
      return
    }

    setLiveEvents([])
    setError(null)
    setIsStreaming(true)
    receivedEventIds.current.clear()
    lastEventIdRef.current = 0
    retryCountRef.current = 0

    let url = apiUrl(`/projects/${encodeURIComponent(projectId)}/chapters/${chapterNumber}/workflow-stream`)
    if (runId) {
      url += `?run_id=${encodeURIComponent(runId)}`
    }
    urlRef.current = url
    connectSSE(url)

    return () => {
      stopStream()
    }
  }, [isActive, projectId, chapterNumber, runId, doneStatus, stopStream, connectSSE])

  return { isConnected, isStreaming, isReconnecting, liveEvents, error, doneStatus }
}

export default useWorkflowStream
