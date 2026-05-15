import { contextBridge, ipcRenderer } from 'electron';

const apiBaseUrl = ipcRenderer.sendSync('novelos:get-api-base-url') as string;
const platform = ipcRenderer.sendSync('novelos:get-platform') as string;
const userDataPath = ipcRenderer.sendSync('novelos:get-user-data-path') as string;

contextBridge.exposeInMainWorld('__NOVELOS_DESKTOP__', {
  apiBaseUrl,
  platform,
  userDataPath,
  openDataDir: () => ipcRenderer.invoke('novelos:open-data-dir'),
  openConfigDir: () => ipcRenderer.invoke('novelos:open-config-dir'),
  openLogsDir: () => ipcRenderer.invoke('novelos:open-logs-dir'),
});
