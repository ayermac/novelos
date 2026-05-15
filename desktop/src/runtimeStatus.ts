export type SidecarStatus = 'starting' | 'healthy' | 'exited' | 'failed' | 'stopping' | 'unknown';

export interface SidecarErrorRecord {
  exitCode: number | null;
  signal: string | null;
  command: string;
  args: string[];
  stderrLogPath: string;
  timestamp: string;
  reason: string;
}

export interface RuntimeStatus {
  status: SidecarStatus;
  pid: number | null;
  apiBaseUrl: string;
  port: number;
  startTime: string | null;
  lastError: SidecarErrorRecord | null;
  stdoutLogPath: string;
  stderrLogPath: string;
}

let currentStatus: RuntimeStatus = {
  status: 'unknown',
  pid: null,
  apiBaseUrl: '',
  port: 0,
  startTime: null,
  lastError: null,
  stdoutLogPath: '',
  stderrLogPath: '',
};

const listeners: Array<(status: RuntimeStatus) => void> = [];

export function setRuntimeStatus(partial: Partial<RuntimeStatus>): void {
  currentStatus = { ...currentStatus, ...partial };
  for (const listener of listeners) {
    try {
      listener(currentStatus);
    } catch {
      // ignore listener errors
    }
  }
}

export function getRuntimeStatus(): RuntimeStatus {
  return { ...currentStatus };
}

export function onRuntimeStatusChange(listener: (status: RuntimeStatus) => void): () => void {
  listeners.push(listener);
  return () => {
    const index = listeners.indexOf(listener);
    if (index !== -1) {
      listeners.splice(index, 1);
    }
  };
}
