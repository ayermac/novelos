import * as fs from 'fs';
import * as path from 'path';

const MAX_LOG_SIZE = 5 * 1024 * 1024; // 5 MB

let logFilePath: string | null = null;

function rotateLogIfNeeded(filePath: string): void {
  try {
    if (fs.existsSync(filePath)) {
      const stats = fs.statSync(filePath);
      if (stats.size > MAX_LOG_SIZE) {
        const rotated = `${filePath}.1`;
        if (fs.existsSync(rotated)) {
          fs.unlinkSync(rotated);
        }
        fs.renameSync(filePath, rotated);
      }
    }
  } catch {
    // Silent fail on rotation errors
  }
}

export function initLogging(logsDir: string): void {
  if (!fs.existsSync(logsDir)) {
    fs.mkdirSync(logsDir, { recursive: true });
  }
  logFilePath = path.join(logsDir, 'electron.log');
  rotateLogIfNeeded(logFilePath);
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

export function getRotatedLogPath(logsDir: string, basename: string): string {
  const filePath = path.join(logsDir, basename);
  rotateLogIfNeeded(filePath);
  return filePath;
}
