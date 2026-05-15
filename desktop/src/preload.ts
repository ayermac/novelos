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
  secretStatus: () => ipcRenderer.invoke('novelos:secret-status'),
  setApiKey: (envName: string, value: string) => ipcRenderer.invoke('novelos:set-api-key', envName, value),
  deleteApiKey: (envName: string) => ipcRenderer.invoke('novelos:delete-api-key', envName),
});
