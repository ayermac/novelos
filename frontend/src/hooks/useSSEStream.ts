/**
 * SSE Stream Hook for real-time chapter generation progress.
 *
 * v5.2 Phase C: Provides EventSource integration with graceful degradation.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { apiUrl } from '../lib/api';

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
    setPreflightWarnings([]);
    setError(null);
    setIsStreaming(true);

    if (typeof EventSource === 'undefined') {
      setError('浏览器不支持 SSE，请使用现代浏览器');
      setIsStreaming(false);
      return;
    }

    const launchAndObserve = async () => {
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
      const runId = data.run_id;
      onLaunch?.(data);
      const url = apiUrl(`/projects/${encodeURIComponent(projectId)}/chapters/${chapter}/workflow-stream?run_id=${encodeURIComponent(runId)}`);
      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => setIsConnected(true);

      const handleLegacyMessage = (e: MessageEvent<string>) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, event]);

        // v6.7.3: Handle preflight warnings from SSE stream
        if (event.type === 'preflight_warnings' && event.warnings) {
          setPreflightWarnings(event.warnings);
          return;
        }

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

      eventSource.onmessage = handleLegacyMessage;

      eventSource.addEventListener('workflow_event', (e) => {
        try {
          const event = JSON.parse((e as MessageEvent<string>).data) as WorkflowStreamEvent;
          const agentKey = normalizeAgentKey(event.node_name || event.agent_id);
          if (!agentKey) return;
          setSteps((prev) => ({
            ...prev,
            [agentKey]: {
              ...prev[agentKey],
              status: workflowEventStepStatus(event),
              started_at: prev[agentKey]?.started_at || event.created_at || new Date().toISOString(),
              completed_at: event.event_type === 'evidence_verified'
                ? event.created_at || new Date().toISOString()
                : prev[agentKey]?.completed_at,
              duration_ms: event.latency_ms ?? prev[agentKey]?.duration_ms,
              logs: appendStepLog(prev[agentKey], {
                timestamp: event.created_at || new Date().toISOString(),
                level: workflowEventLevel(event),
                message: event.message || '节点运行中。',
              }),
            },
          }));
        } catch (err) {
          console.error('Failed to parse workflow event:', err);
        }
      });

      eventSource.addEventListener('workflow_done', (e) => {
        let status = 'completed';
        try {
          const done = JSON.parse((e as MessageEvent<string>).data) as { status?: string; run_id?: string };
          status = done.status || status;
        } catch {
          // Ignore malformed done event and still close the observer.
        }
        setIsStreaming(false);
        setIsConnected(false);
        eventSource.close();
        if (status === 'failed' || status === 'blocked') {
          const message = status === 'blocked' ? '章节生成被阻塞，需要人工处理' : '章节生成失败';
          onError?.(message, { type: 'run_error', error: message, run_id: runId });
          return;
        }
        onComplete?.({ type: 'run_complete', run_id: runId });
      });

      eventSource.onerror = () => {
        const message = '直播连接断开，工作流仍在后台运行，可刷新查看进度';
        setError(message);
        setIsConnected(false);
        setIsStreaming(false);
        eventSource.close();
      };
    };

    launchAndObserve().catch((err) => {
      const message = err instanceof Error ? err.message : '启动章节生成失败';
      setError(message);
      setIsStreaming(false);
      onError?.(message);
    });
  }, [onComplete, onError, onLaunch]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return { isConnected, isStreaming, steps, events, preflightWarnings, error, startStream, stopStream };
}

export default useSSEStream;
