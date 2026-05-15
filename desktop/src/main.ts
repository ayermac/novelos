import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import * as path from 'path';
import * as net from 'net';
import * as fs from 'fs';
import * as http from 'http';
import { SidecarManager } from './sidecar';
import { ensureAppDirectories, getUserDataPath } from './paths';
import { initLogging, log } from './logging';

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

function buildSidecarArgs(port: number, dataDir: string, configDir: string): { command: string; args: string[] } {
  const dbPath = path.join(dataDir, 'novelos.db');
  const configPath = path.join(configDir, 'local.yaml');
  const hasConfig = fs.existsSync(configPath);

  const args: string[] = [
    '-m', 'novel_factory.desktop_sidecar',
    '--host', '127.0.0.1',
    '--port', String(port),
    '--db-path', dbPath,
    ...(hasConfig ? ['--config-path', configPath] : []),
    '--llm-mode', 'stub',
  ];
  return { command: 'python3', args };
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
  initLogging(logsDir);

  log('info', `Novelos Desktop starting. userData: ${getUserDataPath()}`);

  sidecarPort = await findAvailablePort();
  log('info', `Selected port: ${sidecarPort}`);
  apiBaseUrl = `http://127.0.0.1:${sidecarPort}/api`;

  const { command, args } = buildSidecarArgs(sidecarPort, dataDir, configDir);
  const stdoutLog = path.join(logsDir, 'sidecar.stdout.log');
  const stderrLog = path.join(logsDir, 'sidecar.stderr.log');

  sidecarManager.start({
    command,
    args,
    cwd: process.cwd(),
    env: {},
    stdoutLogPath: stdoutLog,
    stderrLogPath: stderrLog,
  });

  const healthy = await waitForHealth(sidecarPort);
  if (!healthy) {
    log('error', 'Sidecar failed health check');
    sidecarManager.stop();

    const errorMsg = `后端服务未能在 60 秒内启动。\n\n命令: ${command} ${args.join(' ')}\n\n日志目录: ${logsDir}\n\n请检查 sidecar.stderr.log 获取详细错误信息。`;
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

startApp().catch((err) => {
  log('error', `Main process error: ${err.message}`);
  app.quit();
});
