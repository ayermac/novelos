import * as fs from 'fs';
import * as path from 'path';

let logFilePath: string | null = null;

export function initLogging(logsDir: string): void {
  if (!fs.existsSync(logsDir)) {
    fs.mkdirSync(logsDir, { recursive: true });
  }
  logFilePath = path.join(logsDir, 'electron.log');
}

export function log(level: 'info' | 'warn' | 'error', message: string): void {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
  // eslint-disable-next-line no-console
  console.log(`[${level.toUpperCase()}] ${message}`);
  if (logFilePath) {
    try {
      fs.appendFileSync(logFilePath, line);
    } catch {
      // Silent fail if log file is not writable
    }
  }
}
