/**
 * SSE Stream Hook for real-time chapter generation progress.
 *
 * v5.2 Phase C: Provides EventSource integration with graceful degradation.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface SSEEvent {
  type: 'step_start' | 'step_complete' | 'run_complete' | 'run_error';
  agent?: string;
  timestamp?: string;
  duration_ms?: number;
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
              [event.agent || '']: { status: 'running' },
            }));
            break;

          case 'step_complete':
            setSteps((prev) => ({
              ...prev,
              [event.agent || '']: {
                status: 'completed',
                duration_ms: event.duration_ms,
              },
            }));
            break;

          case 'run_complete':
            setIsStreaming(false);
            eventSource.close();
            onComplete?.(event);
            break;

          case 'run_error':
            setError(event.error || '未知错误');
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
