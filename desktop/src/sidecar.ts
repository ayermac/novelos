import { spawn, ChildProcess } from 'child_process';
import * as fs from 'fs';
import { log } from './logging';
import { setRuntimeStatus, getRuntimeStatus, SidecarStatus } from './runtimeStatus';

export interface SidecarOptions {
  command: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
  stdoutLogPath: string;
  stderrLogPath: string;
}

export class SidecarManager {
  private child: ChildProcess | null = null;
  private stdoutStream: fs.WriteStream | null = null;
  private stderrStream: fs.WriteStream | null = null;
  private options: SidecarOptions | null = null;

  start(options: SidecarOptions): ChildProcess {
    this.options = options;
    setRuntimeStatus({
      status: 'starting',
      stdoutLogPath: options.stdoutLogPath,
      stderrLogPath: options.stderrLogPath,
      startTime: new Date().toISOString(),
      lastError: null,
    });

    log('info', `Starting sidecar: ${options.command} ${options.args.join(' ')}`);

    this.stdoutStream = fs.createWriteStream(options.stdoutLogPath, { flags: 'a' });
    this.stderrStream = fs.createWriteStream(options.stderrLogPath, { flags: 'a' });

    const child = spawn(options.command, options.args, {
      cwd: options.cwd,
      env: { ...process.env, ...options.env },
      detached: false,
      shell: false,
    });

    this.child = child;

    setRuntimeStatus({ pid: child.pid ?? null });

    child.stdout?.on('data', (data: Buffer) => {
      this.stdoutStream?.write(data.toString());
    });

    child.stderr?.on('data', (data: Buffer) => {
      this.stderrStream?.write(data.toString());
    });

    child.on('exit', (code, signal) => {
      const isExpectedShutdown = getRuntimeStatus().status === 'stopping';
      const reason = isExpectedShutdown
        ? 'Sidecar stopped by user request'
        : code === 0
          ? 'Sidecar exited normally'
          : `Sidecar exited unexpectedly (code: ${code}, signal: ${signal})`;

      log(isExpectedShutdown ? 'info' : 'error', reason);

      if (!isExpectedShutdown && (code !== 0 || signal)) {
        setRuntimeStatus({
          status: code !== null ? 'failed' : 'exited',
          lastError: {
            exitCode: code ?? null,
            signal: signal ?? null,
            command: options.command,
            args: options.args,
            stderrLogPath: options.stderrLogPath,
            timestamp: new Date().toISOString(),
            reason,
          },
        });
      } else {
        setRuntimeStatus({ status: 'exited' });
      }

      this.closeStreams();
      this.child = null;
    });

    child.on('error', (err) => {
      log('error', `Sidecar failed to start: ${err.message}`);
      setRuntimeStatus({
        status: 'failed',
        lastError: {
          exitCode: null,
          signal: null,
          command: options.command,
          args: options.args,
          stderrLogPath: options.stderrLogPath,
          timestamp: new Date().toISOString(),
          reason: `Failed to start: ${err.message}`,
        },
      });
      this.closeStreams();
      this.child = null;
    });

    return child;
  }

  async stop(): Promise<void> {
    if (!this.child || this.child.killed) {
      this.closeStreams();
      return;
    }

    setRuntimeStatus({ status: 'stopping' });
    log('info', 'Stopping sidecar...');
    const target = this.child;
    target.kill('SIGTERM');

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        if (target.exitCode === null && target.signalCode === null) {
          log('warn', 'Sidecar did not exit gracefully, forcing SIGKILL');
          target.kill('SIGKILL');
        }
      }, 5000);

      target.on('exit', () => {
        clearTimeout(timeout);
        this.closeStreams();
        resolve();
      });

      target.on('error', () => {
        clearTimeout(timeout);
        this.closeStreams();
        resolve();
      });
    });
  }

  get pid(): number | null {
    return this.child?.pid ?? null;
  }

  get exited(): boolean {
    return this.child === null;
  }

  private closeStreams(): void {
    try {
      this.stdoutStream?.end();
    } catch {
      // ignore
    }
    try {
      this.stderrStream?.end();
    } catch {
      // ignore
    }
    this.stdoutStream = null;
    this.stderrStream = null;
  }
}
