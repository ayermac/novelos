import * as path from 'path';
import { app } from 'electron';

export function getUserDataPath(): string {
  return app.getPath('userData');
}

export interface AppDirectories {
  dataDir: string;
  configDir: string;
  logsDir: string;
  backupsDir: string;
}

export function ensureAppDirectories(): AppDirectories {
  const userData = getUserDataPath();
  const dirs: AppDirectories = {
    dataDir: path.join(userData, 'data'),
    configDir: path.join(userData, 'config'),
    logsDir: path.join(userData, 'logs'),
    backupsDir: path.join(userData, 'backups'),
  };

  for (const dir of Object.values(dirs)) {
    if (!fsExists(dir)) {
      fsMkdir(dir);
    }
  }

  return dirs;
}

function fsExists(p: string): boolean {
  try {
    const fs = require('fs');
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

function fsMkdir(p: string): void {
  try {
    const fs = require('fs');
    fs.mkdirSync(p, { recursive: true });
  } catch {
    // Silent fail
  }
}
