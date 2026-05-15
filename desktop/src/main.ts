import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron';
import * as path from 'path';
import * as net from 'net';
import * as fs from 'fs';
import * as http from 'http';
import { SidecarManager } from './sidecar';
import { ensureAppDirectories, ensureDefaultConfig, getUserDataPath } from './paths';
import { initLogging, log, getRotatedLogPath } from './logging';
import {
  setApiKey as storeApiKey,
  deleteApiKey as removeApiKey,
  getApiKeyForSidecar,
  listSecretStatuses,
} from './secrets';

let mainWindow: BrowserWindow | null = null;
const sidecarManager = new SidecarManager();
let apiBaseUrl = '';
let sidecarPort = 0;

function getIsDev(): boolean {
  return !app.isPackaged;
}

async function findAvailablePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (address && typeof address !== 'string') {
        const port = address.port;
        server.close(() => resolve(port));
      } else {
        server.close();
        reject(new Error('Could not determine available port'));
      }
    });
    server.on('error', reject);
  });
}

async function checkHealth(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/api/health`, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve(parsed.ok === true && parsed.data?.status === 'ok');
        } catch {
          resolve(false);
        }
      });
    });
    req.on('error', () => resolve(false));
    req.setTimeout(3000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForHealth(port: number, timeoutMs = 60000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await checkHealth(port)) {
      return true;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function createErrorWindow(message: string): BrowserWindow {
  const win = new BrowserWindow({
    width: 600,
    height: 400,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  const html = `
    <!DOCTYPE html>
    <html>
      <head><meta charset="utf-8"><title>启动失败</title></head>
      <body style="font-family:sans-serif;padding:24px;">
        <h1 style="color:#c0392b;">Novelos 启动失败</h1>
        <p style="white-space:pre-wrap;">${message.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</p>
        <p style="margin-top:24px;color:#666;">请检查日志文件获取详细信息。</p>
      </body>
    </html>
  `;
  win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
  return win;
}

async function createMainWindow(): Promise<BrowserWindow> {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    title: 'Novelos',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (getIsDev()) {
    try {
      await win.loadURL('http://localhost:5173');
      win.webContents.openDevTools();
      return win;
    } catch {
      // Dev server unavailable, fall through to dist
    }
    const distPath = path.join(__dirname, '..', '..', 'frontend', 'dist', 'index.html');
    if (fs.existsSync(distPath)) {
      await win.loadFile(distPath);
      return win;
    }
    const errorMsg = '开发模式下 Vite 服务器未启动，且未找到 frontend/dist。请先运行 npm run dev。';
    win.close();
    return createErrorWindow(errorMsg);
  }

  const distPath = path.join(process.resourcesPath, 'frontend', 'dist', 'index.html');
  if (fs.existsSync(distPath)) {
    await win.loadFile(distPath);
    return win;
  }
  const errorMsg = '未找到前端资源。请重新安装应用。';
  win.close();
  return createErrorWindow(errorMsg);
}

function getPlatformArch(): string {
  return `${process.platform}-${process.arch}`;
}

function getFrozenSidecarPath(): string {
  const exeName = process.platform === 'win32' ? 'novelos-sidecar.exe' : 'novelos-sidecar';
  return path.join(process.resourcesPath, 'sidecar', getPlatformArch(), exeName);
}

function resolveSidecar(): { command: string; args: string[] } {
  // 1. Env override always wins for explicit binary path
  const envCmd = process.env.NOVELOS_DESKTOP_SIDECAR_CMD;
  if (envCmd) {
    return { command: envCmd, args: [] };
  }

  // 2. Packaged mode: prefer frozen binary
  if (!getIsDev()) {
    const frozenPath = getFrozenSidecarPath();
    if (fs.existsSync(frozenPath)) {
      return { command: frozenPath, args: [] };
    }
    log('warn', `Frozen sidecar not found at ${frozenPath}, falling back to python3`);
  }

  // 3. Dev mode or fallback: python3 module
  return { command: 'python3', args: ['-m', 'novel_factory.desktop_sidecar'] };
}

function readConfigLlmMode(configDir: string): string {
  const configPath = path.join(configDir, 'local.yaml');
  if (!fs.existsSync(configPath)) {
    return 'stub';
  }
  try {
    // Simple YAML line scan for llm_mode to avoid adding a yaml parser dependency
    const content = fs.readFileSync(configPath, 'utf-8');
    const match = content.match(/^llm_mode:\s*(\S+)/m);
    return normalizeYamlScalar(match?.[1]) || 'stub';
  } catch {
    return 'stub';
  }
}

function normalizeYamlScalar(value: string | undefined): string {
  if (!value) {
    return '';
  }
  const withoutComment = value.split('#')[0]?.trim() || '';
  if (
    (withoutComment.startsWith('"') && withoutComment.endsWith('"')) ||
    (withoutComment.startsWith("'") && withoutComment.endsWith("'"))
  ) {
    return withoutComment.slice(1, -1).trim();
  }
  return withoutComment;
}

function readConfigApiKeyEnvs(configDir: string): string[] {
  const configPath = path.join(configDir, 'local.yaml');
  if (!fs.existsSync(configPath)) {
    return [];
  }
  try {
    const content = fs.readFileSync(configPath, 'utf-8');
    const envs: string[] = [];
    const matches = content.matchAll(/api_key_env:\s*(\S+)/g);
    for (const m of matches) {
      const envName = normalizeYamlScalar(m[1]);
      if (envName) envs.push(envName);
    }
    return [...new Set(envs)];
  } catch {
    return [];
  }
}

function buildSidecarArgs(port: number, dataDir: string, configDir: string): string[] {
  const dbPath = path.join(dataDir, 'novelos.db');
  const configPath = path.join(configDir, 'local.yaml');
  const hasConfig = fs.existsSync(configPath);
  const llmMode = readConfigLlmMode(configDir);

  return [
    '--host', '127.0.0.1',
    '--port', String(port),
    '--db-path', dbPath,
    ...(hasConfig ? ['--config-path', configPath] : []),
    '--llm-mode', llmMode,
  ];
}

async function startApp(): Promise<void> {
  const gotLock = app.requestSingleInstanceLock();
  if (!gotLock) {
    log('warn', 'Another instance is already running. Quitting.');
    app.quit();
    return;
  }

  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  await app.whenReady();

  const { dataDir, configDir, logsDir } = ensureAppDirectories();
  ensureDefaultConfig(configDir);
  initLogging(logsDir);

  log('info', `Novelos Desktop starting. userData: ${getUserDataPath()}`);

  sidecarPort = await findAvailablePort();
  log('info', `Selected port: ${sidecarPort}`);
  apiBaseUrl = `http://127.0.0.1:${sidecarPort}/api`;

  const { command, args: baseArgs } = resolveSidecar();
  const sidecarArgs = buildSidecarArgs(sidecarPort, dataDir, configDir);
  const allArgs = [...baseArgs, ...sidecarArgs];
  const isPython = command === 'python3';
  const cwd = isPython ? process.cwd() : process.resourcesPath;
  const stdoutLog = getRotatedLogPath(logsDir, 'sidecar.stdout.log');
  const stderrLog = getRotatedLogPath(logsDir, 'sidecar.stderr.log');

  // Collect secure API keys for sidecar env injection
  const apiKeyEnvs = readConfigApiKeyEnvs(configDir);
  const sidecarEnv: NodeJS.ProcessEnv = {
    NOVELOS_DESKTOP: '1',
    NOVELOS_APP_DATA_DIR: getUserDataPath(),
    NOVELOS_DATA_DIR: dataDir,
    NOVELOS_CONFIG_DIR: configDir,
    NOVELOS_CONFIG_PATH: path.join(configDir, 'local.yaml'),
    NOVELOS_LOGS_DIR: logsDir,
    NOVELOS_BACKUPS_DIR: path.join(getUserDataPath(), 'backups'),
    NOVELOS_PLATFORM: getPlatformArch(),
  };
  const injectedKeys: string[] = [];
  for (const envName of apiKeyEnvs) {
    const keyValue = getApiKeyForSidecar(configDir, envName);
    if (keyValue) {
      sidecarEnv[envName] = keyValue;
      injectedKeys.push(envName);
    }
  }
  if (injectedKeys.length > 0) {
    sidecarEnv['NOVELOS_DESKTOP_SECRET_KEYS'] = injectedKeys.join(',');
  }

  log('info', `Sidecar command: ${command} ${allArgs.join(' ')}`);

  sidecarManager.start({
    command,
    args: allArgs,
    cwd,
    env: sidecarEnv,
    stdoutLogPath: stdoutLog,
    stderrLogPath: stderrLog,
  });

  const healthy = await waitForHealth(sidecarPort);
  if (!healthy) {
    log('error', 'Sidecar failed health check');
    sidecarManager.stop();

    const errorMsg = `后端服务未能在 60 秒内启动。\n\n命令: ${command} ${allArgs.join(' ')}\n\n日志目录: ${logsDir}\n\n请检查 sidecar.stderr.log 获取详细错误信息。`;
    dialog.showErrorBox('启动失败', errorMsg);
    createErrorWindow(errorMsg);
    return;
  }

  log('info', 'Sidecar is healthy. Opening window.');
  mainWindow = await createMainWindow();

  app.on('window-all-closed', () => {
    sidecarManager.stop();
    mainWindow = null;
    app.quit();
  });

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = await createMainWindow();
    }
  });

  app.on('before-quit', () => {
    sidecarManager.stop();
  });
}

ipcMain.on('novelos:get-api-base-url', (event) => {
  event.returnValue = apiBaseUrl;
});

ipcMain.on('novelos:get-platform', (event) => {
  event.returnValue = process.platform;
});

ipcMain.on('novelos:get-user-data-path', (event) => {
  event.returnValue = getUserDataPath();
});

ipcMain.handle('novelos:open-data-dir', async () => {
  const userData = getUserDataPath();
  const dir = path.join(userData, 'data');
  await shell.openPath(dir);
});

ipcMain.handle('novelos:open-config-dir', async () => {
  const userData = getUserDataPath();
  const dir = path.join(userData, 'config');
  await shell.openPath(dir);
});

ipcMain.handle('novelos:open-logs-dir', async () => {
  const userData = getUserDataPath();
  const dir = path.join(userData, 'logs');
  await shell.openPath(dir);
});

ipcMain.handle('novelos:secret-status', async () => {
  const { configDir } = ensureAppDirectories();
  return listSecretStatuses(configDir);
});

ipcMain.handle('novelos:set-api-key', async (_event, envName: string, value: string) => {
  if (typeof envName !== 'string' || typeof value !== 'string') {
    throw new Error('Invalid arguments');
  }
  const { configDir } = ensureAppDirectories();
  storeApiKey(configDir, envName, value);
});

ipcMain.handle('novelos:delete-api-key', async (_event, envName: string) => {
  if (typeof envName !== 'string') {
    throw new Error('Invalid arguments');
  }
  const { configDir } = ensureAppDirectories();
  removeApiKey(configDir, envName);
});

startApp().catch((err) => {
  log('error', `Main process error: ${err.message}`);
  app.quit();
});
