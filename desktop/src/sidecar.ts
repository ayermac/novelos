import { spawn, ChildProcess } from 'child_process';
import * as fs from 'fs';
import { log } from './logging';

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

  start(options: SidecarOptions): ChildProcess {
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

    child.stdout?.on('data', (data: Buffer) => {
      this.stdoutStream?.write(data.toString());
    });

    child.stderr?.on('data', (data: Buffer) => {
      this.stderrStream?.write(data.toString());
    });

    child.on('exit', (code, signal) => {
      log('info', `Sidecar exited with code ${code}, signal ${signal}`);
      this.closeStreams();
      this.child = null;
    });

    child.on('error', (err) => {
      log('error', `Sidecar failed to start: ${err.message}`);
      this.closeStreams();
      this.child = null;
    });

    return child;
  }

  stop(): void {
    if (this.child && !this.child.killed) {
      log('info', 'Stopping sidecar...');
      const target = this.child;
      target.kill('SIGTERM');
      // Give it 5 seconds to exit gracefully, then SIGKILL
      setTimeout(() => {
        if (target.exitCode === null && target.signalCode === null) {
          log('warn', 'Sidecar did not exit gracefully, forcing SIGKILL');
          target.kill('SIGKILL');
        }
      }, 5000);
    }
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
