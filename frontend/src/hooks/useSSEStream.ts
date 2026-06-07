/**
 * SSE Stream Hook for real-time chapter generation progress.
 *
 * v6.10.0: Unified SSE with reconnection, last-event-id resume, dedup.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { apiUrl, type WorkflowExecutionEvent } from '../lib/api';

export interface PreflightWarning {
  code: string;
  message: string;
  severity: 'warning' | 'info';
  details?: Record<string, unknown>;
}

export interface SSEEvent {
  type: 'step_start' | 'step_complete' | 'step_log' | 'run_complete' | 'run_error' | 'preflight_warnings';
  agent?: string;
  timestamp?: string;
  duration_ms?: number;
  message?: string;
  level?: 'info' | 'success' | 'warning' | 'error';
  chapter_status?: string;
  run_id?: string;
  awaiting_publish?: boolean;
  error?: string;
  context_incomplete?: boolean;
  missing?: string[];
  actions?: string[];
  details?: Record<string, unknown>;
  warnings?: PreflightWarning[];
}

interface WorkflowStreamEvent {
  id?: number;
  run_id?: string;
  node_name?: string;
  agent_id?: string;
  event_type?: string;
  status?: string;
  message?: string;
  payload?: Record<string, unknown>;
  token_count?: number | null;
  latency_ms?: number | null;
  created_at?: string;
}

interface LaunchResponse {
  run_id: string;
  workflow_status: string;
  chapter: number;
  project_id: string;
}

export interface StepStatus {
  status: 'pending' | 'running' | 'completed' | 'failed';
  duration_ms?: number;
  started_at?: string;
  completed_at?: string;
  logs?: WorkflowNodeLog[];
  events?: WorkflowExecutionEvent[];
}

export interface WorkflowNodeLog {
  id: string;
  timestamp: string;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
}

const MAX_RETRIES = 10
const INITIAL_DELAY_MS = 1000
const MAX_DELAY_MS = 16000

export interface UseSSEStreamResult {
  isConnected: boolean;
  isStreaming: boolean;
  isReconnecting: boolean;
  steps: Record<string, StepStatus>;
  events: SSEEvent[];
  preflightWarnings: PreflightWarning[];
  error: string | null;
  startStream: (projectId: string, chapter: number) => void;
  stopStream: () => void;
}

function normalizeAgentKey(agent?: string): string {
  if (!agent) return ''
  if (agent === 'publisher' || agent === 'awaiting_publish') return 'publish'
  return agent
}

function appendStepLog(
  step: StepStatus | undefined,
  log: Omit<WorkflowNodeLog, 'id'>,
): WorkflowNodeLog[] {
  const logs = step?.logs || [];
  return [
    ...logs,
    {
      ...log,
      id: `${log.timestamp}-${logs.length}-${log.message}`,
    },
  ];
}

function workflowEventLevel(event: WorkflowStreamEvent): WorkflowNodeLog['level'] {
  if (event.status === 'failed' || event.event_type === 'llm_failed') return 'error';
  if (event.status === 'warning') return 'warning';
  if (event.status === 'pass' || event.event_type === 'evidence_verified') return 'success';
  return 'info';
}

function workflowEventStepStatus(event: WorkflowStreamEvent): StepStatus['status'] {
  if (event.status === 'failed' || event.event_type === 'llm_failed') return 'failed';
  if (event.event_type === 'evidence_verified') return 'completed';
  return 'running';
}

/**
 * Hook for SSE streaming of chapter generation progress.
 */
export function useSSEStream(
  onComplete?: (event: SSEEvent) => void,
  onError?: (error: string, event?: SSEEvent) => void,
  onLaunch?: (event: LaunchResponse) => void
): UseSSEStreamResult {
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [steps, setSteps] = useState<Record<string, StepStatus>>({});
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [preflightWarnings, setPreflightWarnings] = useState<PreflightWarning[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const lastEventIdRef = useRef<number>(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamUrlRef = useRef<string | null>(null);
  const runIdRef = useRef<string | null>(null);
  const isStoppedRef = useRef(false);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const stopStream = useCallback(() => {
    isStoppedRef.current = true;
    cleanup();
    setIsStreaming(false);
    setIsConnected(false);
    setIsReconnecting(false);
    streamUrlRef.current = null;
    runIdRef.current = null;
  }, [cleanup]);

  const connectAndListen = useCallback((url: string) => {
    if (typeof EventSource === 'undefined') {
      setError('浏览器不支持 SSE');
      setIsStreaming(false);
      return;
    }

    cleanup();

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setIsReconnecting(false);
      setError(null);
      retryCountRef.current = 0;
    };

    // Unified workflow_event handler
    eventSource.addEventListener('workflow_event', ((e: MessageEvent) => {
      try {
        const event = JSON.parse((e as MessageEvent<string>).data) as WorkflowStreamEvent;
        if (event.id) lastEventIdRef.current = event.id;

        const agentKey = normalizeAgentKey(event.node_name || event.agent_id);
        if (!agentKey) return;

        const execEvent: WorkflowExecutionEvent = {
          id: event.id,
          node_name: event.node_name,
          agent_id: event.agent_id,
          event_type: event.event_type || 'unknown',
          status: event.status,
          message: event.message,
          payload: event.payload,
          token_count: event.token_count ?? null,
          latency_ms: event.latency_ms ?? null,
          created_at: event.created_at,
        };

        setSteps((prev) => {
          const prevEvents = prev[agentKey]?.events || [];
          const nextEvents = [...prevEvents, execEvent];
          const isTextChunk = event.event_type === 'text_chunk';
          return {
            ...prev,
            [agentKey]: {
              ...prev[agentKey],
              status: workflowEventStepStatus(event),
              started_at: prev[agentKey]?.started_at || event.created_at || new Date().toISOString(),
              completed_at: event.event_type === 'evidence_verified'
                ? event.created_at || new Date().toISOString()
                : prev[agentKey]?.completed_at,
              duration_ms: event.latency_ms ?? prev[agentKey]?.duration_ms,
              events: nextEvents,
              logs: isTextChunk
                ? (prev[agentKey]?.logs || [])
                : appendStepLog(prev[agentKey], {
                    timestamp: event.created_at || new Date().toISOString(),
                    level: workflowEventLevel(event),
                    message: event.message || '节点运行中。',
                  }),
            },
          };
        });
      } catch (err) {
        console.error('Failed to parse workflow event:', err);
      }
    }) as EventListener);

    // Unified workflow_done handler
    eventSource.addEventListener('workflow_done', ((e: MessageEvent) => {
      let status = 'completed';
      try {
        const done = JSON.parse((e as MessageEvent<string>).data) as { status?: string; run_id?: string };
        status = done.status || status;
      } catch {
        // Ignore malformed done event
      }

      cleanup();
      setIsStreaming(false);
      setIsConnected(false);
      setIsReconnecting(false);

      if (status === 'failed') {
        onError?.('章节生成失败', { type: 'run_error', error: '章节生成失败', run_id: runIdRef.current || undefined });
        return;
      }
      if (status === 'blocked') {
        onComplete?.({ type: 'run_complete', run_id: runIdRef.current || undefined } as SSEEvent);
        return;
      }
      onComplete?.({ type: 'run_complete', run_id: runIdRef.current || undefined });
    }) as EventListener);

    // Legacy message handler (for backward compat)
    eventSource.onmessage = ((e: MessageEvent<string>) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, event]);

        if (event.type === 'preflight_warnings' && event.warnings) {
          setPreflightWarnings(event.warnings);
          return;
        }

        const agentKey = normalizeAgentKey(event.agent);
        if (!agentKey && event.type !== 'run_complete' && event.type !== 'run_error') return;

        switch (event.type) {
          case 'step_start':
            setSteps((prev) => ({
              ...prev,
              [agentKey]: {
                ...prev[agentKey],
                status: 'running',
                started_at: event.timestamp || new Date().toISOString(),
                logs: appendStepLog(prev[agentKey], {
                  timestamp: event.timestamp || new Date().toISOString(),
                  level: 'info',
                  message: event.message || '节点已开始处理。',
                }),
              },
            }));
            break;

          case 'step_complete':
            setSteps((prev) => ({
              ...prev,
              [agentKey]: {
                ...prev[agentKey],
                status: 'completed',
                duration_ms: event.duration_ms,
                completed_at: event.timestamp || new Date().toISOString(),
                logs: appendStepLog(prev[agentKey], {
                  timestamp: event.timestamp || new Date().toISOString(),
                  level: 'success',
                  message: event.message || `节点处理完成${event.duration_ms ? `，耗时 ${event.duration_ms}ms` : ''}。`,
                }),
              },
            }));
            break;

          case 'step_log':
            setSteps((prev) => ({
              ...prev,
              [agentKey]: {
                ...prev[agentKey],
                status: prev[agentKey]?.status || 'running',
                logs: appendStepLog(prev[agentKey], {
                  timestamp: event.timestamp || new Date().toISOString(),
                  level: event.level || 'info',
                  message: event.message || '节点运行中。',
                }),
              },
            }));
            break;

          case 'run_complete':
            cleanup();
            setIsStreaming(false);
            setIsConnected(false);
            onComplete?.(event);
            break;

          case 'run_error':
            setError(event.error || '未知错误');
            cleanup();
            setIsStreaming(false);
            setIsConnected(false);
            onError?.(event.error || '未知错误', event);
            break;
        }
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    }) as unknown as EventListener;

    // Error handler with reconnection
    eventSource.onerror = () => {
      setIsConnected(false);
      eventSource.close();
      eventSourceRef.current = null;

      if (isStoppedRef.current) return;

      // Auto-reconnect with exponential backoff
      if (retryCountRef.current >= MAX_RETRIES) {
        setError('连接断开，请刷新页面查看进度');
        setIsStreaming(false);
        setIsReconnecting(false);
        return;
      }

      setIsReconnecting(true);
      const delay = Math.min(INITIAL_DELAY_MS * Math.pow(2, retryCountRef.current), MAX_DELAY_MS);
      retryCountRef.current++;

      reconnectTimerRef.current = setTimeout(() => {
        if (isStoppedRef.current) return;
        const baseUrl = streamUrlRef.current;
        if (!baseUrl) return;
        const resumeUrl = lastEventIdRef.current
          ? `${baseUrl}&since_id=${lastEventIdRef.current}`
          : baseUrl;
        connectAndListen(resumeUrl);
      }, delay);
    };
  }, [cleanup, onComplete, onError]);

  const startStream = useCallback((projectId: string, chapter: number) => {
    isStoppedRef.current = false;
    setSteps({});
    setEvents([]);
    setPreflightWarnings([]);
    setError(null);
    setIsStreaming(true);
    retryCountRef.current = 0;
    lastEventIdRef.current = 0;

    const launchAndConnect = async () => {
      const response = await fetch(apiUrl('/run/chapter/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, chapter }),
      });
      const launch = await response.json();

      if (!launch.ok || !launch.data?.run_id) {
        const event: SSEEvent = {
          type: 'run_error',
          error: launch.error?.message || '启动章节生成失败',
          context_incomplete: Boolean(launch.error?.details?.missing),
          missing: launch.error?.details?.missing || [],
          actions: launch.error?.details?.actions || [],
          details: launch.error?.details || {},
        };
        setError(event.error || '启动章节生成失败');
        setIsStreaming(false);
        onError?.(event.error || '启动章节生成失败', event);
        return;
      }

      const data = launch.data as LaunchResponse;
      runIdRef.current = data.run_id;
      onLaunch?.(data);

      const url = apiUrl(`/projects/${encodeURIComponent(projectId)}/chapters/${chapter}/workflow-stream?run_id=${encodeURIComponent(data.run_id)}`);
      streamUrlRef.current = url;
      connectAndListen(url);
    };

    launchAndConnect().catch((err) => {
      const message = err instanceof Error ? err.message : '启动章节生成失败';
      setError(message);
      setIsStreaming(false);
      onError?.(message);
    });
  }, [connectAndListen, onError, onLaunch]);

  useEffect(() => {
    return () => {
      isStoppedRef.current = true;
      cleanup();
    };
  }, [cleanup]);

  return { isConnected, isStreaming, isReconnecting, steps, events, preflightWarnings, error, startStream, stopStream };
}

export default useSSEStream;
