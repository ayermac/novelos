import { app, BrowserWindow, ipcMain, shell } from 'electron';
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
import { getRuntimeStatus, setRuntimeStatus, onRuntimeStatusChange } from './runtimeStatus';

// ── Environment overrides ──────────────────────────────────────
const userDataOverride = process.env.NOVELOS_DESKTOP_USER_DATA_DIR;
if (userDataOverride) {
  app.setPath('userData', userDataOverride);
}

let mainWindow: BrowserWindow | null = null;
const sidecarManager = new SidecarManager();
let apiBaseUrl = '';
let sidecarPort = 0;

// Cached for rebuild on restart
let lastDataDir = '';
let lastConfigDir = '';
let lastLogsDir = '';

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

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

async function httpGetJson(url: string, timeoutMs = 3000): Promise<JsonValue> {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          resolve(JSON.parse(data) as JsonValue);
        } catch {
          resolve({
            ok: false,
            error: {
              code: 'INVALID_JSON',
              message: `Response was not valid JSON (HTTP ${res.statusCode ?? 'unknown'})`,
            },
          });
        }
      });
    });
    req.on('error', (err) => {
      resolve({
        ok: false,
        error: {
          code: 'REQUEST_FAILED',
          message: err.message,
        },
      });
    });
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      resolve({
        ok: false,
        error: {
          code: 'REQUEST_TIMEOUT',
          message: `Request timed out after ${timeoutMs}ms`,
        },
      });
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

function getPlatformArch(): string {
  return `${process.platform}-${process.arch}`;
}

function getFrozenSidecarPath(): string {
  const exeName = process.platform === 'win32' ? 'novelos-sidecar.exe' : 'novelos-sidecar';
  return path.join(process.resourcesPath, 'sidecar', getPlatformArch(), exeName);
}

function resolveSidecar(): { command: string; args: string[] } {
  const envCmd = process.env.NOVELOS_DESKTOP_SIDECAR_CMD;
  if (envCmd) {
    return { command: envCmd, args: [] };
  }
  if (!getIsDev()) {
    const frozenPath = getFrozenSidecarPath();
    if (fs.existsSync(frozenPath)) {
      return { command: frozenPath, args: [] };
    }
    log('warn', `Frozen sidecar not found at ${frozenPath}, falling back to python3`);
  }
  return { command: 'python3', args: ['-m', 'novel_factory.desktop_sidecar'] };
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

function readConfigLlmMode(configDir: string): string {
  const configPath = path.join(configDir, 'local.yaml');
  if (!fs.existsSync(configPath)) {
    return 'stub';
  }
  try {
    const content = fs.readFileSync(configPath, 'utf-8');
    const match = content.match(/^llm_mode:\s*(\S+)/m);
    return normalizeYamlScalar(match?.[1]) || 'stub';
  } catch {
    return 'stub';
  }
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

function buildSidecarEnv(configDir: string, dataDir: string, logsDir: string): NodeJS.ProcessEnv {
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
  const apiKeyEnvs = readConfigApiKeyEnvs(configDir);
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
  return sidecarEnv;
}

function redactSecrets(text: string): string {
  return text
    .replace(/(api_key\s*:\s*).+/gi, '$1***REDACTED***')
    .replace(/(secret\s*:\s*).+/gi, '$1***REDACTED***')
    .replace(/(token\s*:\s*).+/gi, '$1***REDACTED***')
    .replace(/(authorization\s*:\s*).+/gi, '$1***REDACTED***')
    .replace(/(password\s*:\s*).+/gi, '$1***REDACTED***')
    .replace(/sk-[A-Za-z0-9_-]{8,}/g, 'sk-***REDACTED***');
}

function readTextIfExists(filePath: string, maxBytes = 64 * 1024): string {
  try {
    if (!filePath || !fs.existsSync(filePath)) {
      return '';
    }
    const stat = fs.statSync(filePath);
    const start = Math.max(0, stat.size - maxBytes);
    const fd = fs.openSync(filePath, 'r');
    const buffer = Buffer.alloc(stat.size - start);
    fs.readSync(fd, buffer, 0, buffer.length, start);
    fs.closeSync(fd);
    return redactSecrets(buffer.toString('utf-8'));
  } catch (err) {
    return `Unable to read ${filePath}: ${(err as Error).message}`;
  }
}

function safeRuntimeStatusForDiagnostics(): JsonValue {
  const status = getRuntimeStatus();
  return {
    status: status.status,
    pid: status.pid,
    apiBaseUrl: status.apiBaseUrl,
    port: status.port,
    startTime: status.startTime,
    stdoutLogPath: status.stdoutLogPath,
    stderrLogPath: status.stderrLogPath,
    lastError: status.lastError
      ? {
          exitCode: status.lastError.exitCode,
          signal: status.lastError.signal,
          command: status.lastError.command,
          args: status.lastError.args,
          stderrLogPath: status.lastError.stderrLogPath,
          timestamp: status.lastError.timestamp,
          reason: status.lastError.reason,
        }
      : null,
  };
}

async function exportDiagnosticsPackage(): Promise<{ success: boolean; path: string; message: string }> {
  const dirs = ensureAppDirectories();
  const logsDir = lastLogsDir || dirs.logsDir;
  const dataDir = lastDataDir || dirs.dataDir;
  const configDir = lastConfigDir || dirs.configDir;
  const diagnosticsDir = path.join(logsDir, 'diagnostics');
  fs.mkdirSync(diagnosticsDir, { recursive: true });

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const outputPath = path.join(diagnosticsDir, `novelos-diagnostics-${timestamp}.json`);
  const runtime = getRuntimeStatus();
  const baseUrl = runtime.apiBaseUrl || apiBaseUrl;
  const configPath = path.join(configDir, 'local.yaml');
  const electronLogPath = path.join(logsDir, 'electron.log');
  const sidecarStdoutPath = runtime.stdoutLogPath || path.join(logsDir, 'sidecar.stdout.log');
  const sidecarStderrPath = runtime.stderrLogPath || path.join(logsDir, 'sidecar.stderr.log');

  const health = baseUrl ? await httpGetJson(`${baseUrl}/health`) : null;
  const runtimeInfo = baseUrl ? await httpGetJson(`${baseUrl}/desktop/runtime-info`) : null;

  const payload = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    app: {
      name: 'Novelos',
      version: app.getVersion(),
      is_packaged: app.isPackaged,
      platform: getPlatformArch(),
      user_data_path: getUserDataPath(),
    },
    paths: {
      app_data_dir: getUserDataPath(),
      data_dir: dataDir,
      config_dir: configDir,
      logs_dir: logsDir,
      db_path: path.join(dataDir, 'novelos.db'),
      config_path: configPath,
    },
    runtime_status: safeRuntimeStatusForDiagnostics(),
    api: {
      base_url: baseUrl,
      health,
      runtime_info: runtimeInfo,
    },
    config_redacted: readTextIfExists(configPath, 128 * 1024),
    logs: {
      electron_log_tail: readTextIfExists(electronLogPath),
      sidecar_stdout_tail: readTextIfExists(sidecarStdoutPath),
      sidecar_stderr_tail: readTextIfExists(sidecarStderrPath),
    },
  };

  fs.writeFileSync(outputPath, JSON.stringify(payload, null, 2), 'utf-8');
  log('info', `Desktop diagnostics exported: ${outputPath}`);
  shell.showItemInFolder(outputPath);
  return {
    success: true,
    path: outputPath,
    message: '诊断包已导出',
  };
}

async function launchSidecar(): Promise<boolean> {
  const { dataDir, configDir, logsDir } = ensureAppDirectories();
  ensureDefaultConfig(configDir);
  lastDataDir = dataDir;
  lastConfigDir = configDir;
  lastLogsDir = logsDir;

  sidecarPort = await findAvailablePort();
  apiBaseUrl = `http://127.0.0.1:${sidecarPort}/api`;

  const { command, args: baseArgs } = resolveSidecar();
  const sidecarArgs = buildSidecarArgs(sidecarPort, dataDir, configDir);
  const allArgs = [...baseArgs, ...sidecarArgs];
  const isPython = command === 'python3';
  const cwd = isPython ? process.cwd() : process.resourcesPath;
  const stdoutLog = getRotatedLogPath(logsDir, 'sidecar.stdout.log');
  const stderrLog = getRotatedLogPath(logsDir, 'sidecar.stderr.log');

  const sidecarEnv = buildSidecarEnv(configDir, dataDir, logsDir);

  setRuntimeStatus({
    status: 'starting',
    port: sidecarPort,
    apiBaseUrl,
    stdoutLogPath: stdoutLog,
    stderrLogPath: stderrLog,
    lastError: null,
  });

  // Only log command and args — never env values
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
    setRuntimeStatus({ status: 'failed' });
    await sidecarManager.stop();
    return false;
  }

  setRuntimeStatus({ status: 'healthy' });
  log('info', 'Sidecar is healthy.');
  return true;
}

function createDiagnosticsWindow(info: {
  title: string;
  summary: string;
  command: string;
  logsDir: string;
  stderrPath: string;
  showRetry: boolean;
  showFrontendMissing: boolean;
  expectedDistPath?: string;
}): BrowserWindow {
  const win = new BrowserWindow({
    width: 720,
    height: 520,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const retryButton = info.showRetry
    ? `<button id="retryBtn" style="padding:10px 18px;background:#1d4ed8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px;margin-right:10px;">重试启动</button>`
    : '';

  const frontendMissingBlock = info.showFrontendMissing
    ? `<div style="margin-top:16px;padding:12px;background:#fef3c7;border-radius:6px;color:#92400e;font-size:13px;">
         <strong>前端资源缺失</strong>
         <div style="margin-top:4px;">请重新安装或重新打包应用。</div>
         <div style="margin-top:4px;font-size:12px;word-break:break-all;">预期路径: ${(info.expectedDistPath || '').replace(/</g, '&lt;')}</div>
       </div>`
    : '';

  const html = `
    <!DOCTYPE html>
    <html>
      <head><meta charset="utf-8"><title>${info.title}</title></head>
      <body style="font-family:sans-serif;padding:28px;background:#fafafa;color:#333;">
        <h1 style="color:#c0392b;margin-top:0;">${info.title}</h1>
        <div style="background:#fff;padding:16px;border-radius:8px;border:1px solid #e5e5e5;margin-bottom:16px;">
          <div style="font-weight:600;margin-bottom:8px;">错误摘要</div>
          <div style="white-space:pre-wrap;font-size:13px;color:#555;">${info.summary.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
        </div>
        <div style="background:#fff;padding:16px;border-radius:8px;border:1px solid #e5e5e5;margin-bottom:16px;">
          <div style="font-weight:600;margin-bottom:8px;">启动命令</div>
          <code style="font-size:12px;background:#1f2937;color:#f9fafb;padding:8px 12px;border-radius:6px;display:block;word-break:break-all;">${info.command.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code>
        </div>
        <div style="background:#fff;padding:16px;border-radius:8px;border:1px solid #e5e5e5;margin-bottom:16px;">
          <div style="font-weight:600;margin-bottom:8px;">日志</div>
          <div style="font-size:13px;color:#555;margin-bottom:6px;">日志目录: <code>${info.logsDir}</code></div>
          <div style="font-size:13px;color:#555;">stderr: <code>${info.stderrPath}</code></div>
        </div>
        ${frontendMissingBlock}
        <div style="margin-top:20px;">
          ${retryButton}
          <button onclick="window.__NOVELOS_DESKTOP__?.exportDiagnostics?.()" style="padding:10px 18px;background:#ecfeff;color:#155e75;border:1px solid #a5f3fc;border-radius:6px;cursor:pointer;font-size:14px;margin-right:10px;">导出诊断包</button>
          <button onclick="window.__NOVELOS_DESKTOP__?.openLogsDir?.()" style="padding:10px 18px;background:#f3f4f6;color:#374151;border:1px solid #d1d5db;border-radius:6px;cursor:pointer;font-size:14px;margin-right:10px;">打开日志目录</button>
          <button onclick="window.__NOVELOS_DESKTOP__?.openConfigDir?.()" style="padding:10px 18px;background:#f3f4f6;color:#374151;border:1px solid #d1d5db;border-radius:6px;cursor:pointer;font-size:14px;margin-right:10px;">打开配置目录</button>
          <button onclick="window.__NOVELOS_DESKTOP__?.quitApp?.()" style="padding:10px 18px;background:#fee2e2;color:#991b1b;border:1px solid #fecaca;border-radius:6px;cursor:pointer;font-size:14px;">退出应用</button>
        </div>
        <script>
          const retryBtn = document.getElementById('retryBtn');
          if (retryBtn) {
            retryBtn.addEventListener('click', () => {
              retryBtn.disabled = true;
              retryBtn.textContent = '重试中...';
              window.__NOVELOS_DESKTOP__?.restartSidecar?.().then((res) => {
                if (res?.success) {
                  retryBtn.textContent = '启动成功，即将打开主窗口...';
                } else {
                  retryBtn.disabled = false;
                  retryBtn.textContent = '重试启动';
                }
              }).catch(() => {
                retryBtn.disabled = false;
                retryBtn.textContent = '重试启动';
              });
            });
          }
        </script>
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
    return createDiagnosticsWindow({
      title: '启动失败',
      summary: errorMsg,
      command: 'npm run dev',
      logsDir: lastLogsDir || path.join(getUserDataPath(), 'logs'),
      stderrPath: lastLogsDir ? path.join(lastLogsDir, 'sidecar.stderr.log') : '',
      showRetry: false,
      showFrontendMissing: true,
      expectedDistPath: distPath,
    });
  }

  const distPath = path.join(process.resourcesPath, 'frontend', 'dist', 'index.html');
  if (fs.existsSync(distPath)) {
    await win.loadFile(distPath);
    return win;
  }
  const errorMsg = '未找到前端资源。请重新安装应用。';
  win.close();
  return createDiagnosticsWindow({
    title: '启动失败',
    summary: errorMsg,
    command: resolveSidecar().command,
    logsDir: lastLogsDir || path.join(getUserDataPath(), 'logs'),
    stderrPath: lastLogsDir ? path.join(lastLogsDir, 'sidecar.stderr.log') : '',
    showRetry: false,
    showFrontendMissing: true,
    expectedDistPath: distPath,
  });
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

  const healthy = await launchSidecar();
  if (!healthy) {
    const status = getRuntimeStatus();
    const { command, args } = resolveSidecar();
    const allArgs = [...args, ...buildSidecarArgs(sidecarPort || 0, dataDir, configDir)];
    const errorMsg = '后端服务未能在 60 秒内启动。';

    mainWindow = createDiagnosticsWindow({
      title: '启动诊断',
      summary: errorMsg,
      command: `${command} ${allArgs.join(' ')}`,
      logsDir,
      stderrPath: status.stderrLogPath || path.join(logsDir, 'sidecar.stderr.log'),
      showRetry: true,
      showFrontendMissing: false,
    });
    return;
  }

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

// ── IPC Handlers ───────────────────────────────────────────────

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

// M5: runtime status and sidecar restart
ipcMain.handle('novelos:runtime-status', async () => {
  const status = getRuntimeStatus();
  return {
    status: status.status,
    pid: status.pid,
    apiBaseUrl: status.apiBaseUrl,
    port: status.port,
    startTime: status.startTime,
    lastError: status.lastError
      ? {
          exitCode: status.lastError.exitCode,
          signal: status.lastError.signal,
          command: status.lastError.command,
          args: status.lastError.args,
          stderrLogPath: status.lastError.stderrLogPath,
          timestamp: status.lastError.timestamp,
          reason: status.lastError.reason,
        }
      : null,
    stdoutLogPath: status.stdoutLogPath,
    stderrLogPath: status.stderrLogPath,
  };
});

ipcMain.handle('novelos:restart-sidecar', async () => {
  log('info', 'Restarting sidecar by user request');
  await sidecarManager.stop();
  const ok = await launchSidecar();
  if (ok) {
    if (mainWindow && !mainWindow.isDestroyed()) {
      const url = mainWindow.webContents.getURL();
      if (url.startsWith('data:')) {
        // Diagnostics window: replace with main window
        mainWindow.close();
        mainWindow = await createMainWindow();
      } else {
        mainWindow.webContents.send('novelos:api-base-url-changed', apiBaseUrl);
      }
    }
  }
  return { success: ok, apiBaseUrl: ok ? apiBaseUrl : null };
});

ipcMain.handle('novelos:export-diagnostics', async () => {
  return exportDiagnosticsPackage();
});

// Quit app helper (used by diagnostics window)
ipcMain.handle('novelos:quit-app', async () => {
  app.quit();
});

// Notify renderer of status changes
onRuntimeStatusChange((status) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('novelos:runtime-status-changed', {
      status: status.status,
      pid: status.pid,
      apiBaseUrl: status.apiBaseUrl,
      port: status.port,
      startTime: status.startTime,
      lastError: status.lastError
        ? {
            exitCode: status.lastError.exitCode,
            signal: status.lastError.signal,
            timestamp: status.lastError.timestamp,
            reason: status.lastError.reason,
          }
        : null,
    });
  }
});

startApp().catch((err) => {
  log('error', `Main process error: ${err.message}`);
  app.quit();
});
