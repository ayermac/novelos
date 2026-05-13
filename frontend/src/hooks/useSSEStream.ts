/**
 * SSE Stream Hook for real-time chapter generation progress.
 *
 * v5.2 Phase C: Provides EventSource integration with graceful degradation.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface SSEEvent {
  type: 'step_start' | 'step_complete' | 'step_log' | 'run_complete' | 'run_error';
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
}

export interface StepStatus {
  status: 'pending' | 'running' | 'completed' | 'failed';
  duration_ms?: number;
  started_at?: string;
  completed_at?: string;
  logs?: WorkflowNodeLog[];
}

export interface WorkflowNodeLog {
  id: string;
  timestamp: string;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
}

export interface UseSSEStreamResult {
  isConnected: boolean;
  isStreaming: boolean;
  steps: Record<string, StepStatus>;
  events: SSEEvent[];
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

/**
 * Hook for SSE streaming of chapter generation progress.
 */
export function useSSEStream(
  onComplete?: (event: SSEEvent) => void,
  onError?: (error: string, event?: SSEEvent) => void
): UseSSEStreamResult {
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [steps, setSteps] = useState<Record<string, StepStatus>>({});
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  const stopStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsStreaming(false);
    setIsConnected(false);
  }, []);

  const startStream = useCallback((projectId: string, chapter: number) => {
    setSteps({});
    setEvents([]);
    setError(null);
    setIsStreaming(true);

    if (typeof EventSource === 'undefined') {
      setError('浏览器不支持 SSE，请使用现代浏览器');
      setIsStreaming(false);
      return;
    }

    const url = `/api/run/chapter/stream?project_id=${encodeURIComponent(projectId)}&chapter=${chapter}`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => setIsConnected(true);

    eventSource.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, event]);

        switch (event.type) {
          case 'step_start':
            setSteps((prev) => ({
              ...prev,
              [normalizeAgentKey(event.agent)]: {
                ...prev[normalizeAgentKey(event.agent)],
                status: 'running',
                started_at: event.timestamp || new Date().toISOString(),
                logs: appendStepLog(prev[normalizeAgentKey(event.agent)], {
                  timestamp: event.timestamp || new Date().toISOString(),
                  level: 'info',
                  message: event.message || '节点已开始处理，正在等待模型或工具返回。',
                }),
              },
            }));
            break;

          case 'step_complete':
            setSteps((prev) => ({
              ...prev,
              [normalizeAgentKey(event.agent)]: {
                ...prev[normalizeAgentKey(event.agent)],
                status: 'completed',
                duration_ms: event.duration_ms,
                completed_at: event.timestamp || new Date().toISOString(),
                logs: appendStepLog(prev[normalizeAgentKey(event.agent)], {
                  timestamp: event.timestamp || new Date().toISOString(),
                  level: 'success',
                  message: event.message || `节点处理完成${event.duration_ms ? `，耗时 ${event.duration_ms}ms` : ''}。`,
                }),
              },
            }));
            break;

          case 'step_log':
            setSteps((prev) => {
              const agentKey = normalizeAgentKey(event.agent);
              if (!agentKey) return prev;
              return {
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
              };
            });
            break;

          case 'run_complete':
            setIsStreaming(false);
            eventSource.close();
            onComplete?.(event);
            break;

          case 'run_error':
            setError(event.error || '未知错误');
            setSteps((prev) => {
              const agentKey = normalizeAgentKey(event.agent);
              if (agentKey) {
                return {
                  ...prev,
                  [agentKey]: {
                    ...prev[agentKey],
                    status: 'failed',
                    logs: appendStepLog(prev[agentKey], {
                      timestamp: event.timestamp || new Date().toISOString(),
                      level: 'error',
                      message: event.error || '节点运行失败。',
                    }),
                  },
                };
              }
              const runningKey = Object.entries(prev).find(([, step]) => step.status === 'running')?.[0];
              if (!runningKey) return prev;
              return {
                ...prev,
                [runningKey]: {
                  ...prev[runningKey],
                  status: 'failed',
                  logs: appendStepLog(prev[runningKey], {
                    timestamp: event.timestamp || new Date().toISOString(),
                    level: 'error',
                    message: event.error || '节点运行失败。',
                  }),
                },
              };
            });
            setIsStreaming(false);
            eventSource.close();
            onError?.(event.error || '未知错误', event);
            break;
        }
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };

    eventSource.onerror = () => {
      const message = 'SSE 连接断开';
      setError(message);
      setIsConnected(false);
      setIsStreaming(false);
      eventSource.close();
      onError?.(message);
    };
  }, [onComplete, onError]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return { isConnected, isStreaming, steps, events, error, startStream, stopStream };
}

export default useSSEStream;
