# Novelos Desktop — M0 Technical Proof of Concept

This directory contains the Electron desktop shell for Novelos (M0 milestone).

## Prerequisites

- macOS (M0 targets local macOS development only)
- Node.js 18+
- Python 3.9+ with the `novel-factory` package installed in editable mode:
  ```bash
  cd /path/to/novelos
  python3 -m pip install -e .
  ```
- The frontend built or the Vite dev server available

## Dev Startup Steps

1. Install desktop dependencies:
   ```bash
   cd desktop
   npm install
   ```

2. Build the TypeScript sources:
   ```bash
   npm run build
   ```

3. Start the desktop app in development mode:
   ```bash
   npm run dev
   ```

In development mode, Electron will:
- Try to load `http://localhost:5173` (Vite dev server)
- Fallback to `../frontend/dist/index.html` if the dev server is not running
- Automatically start the Python backend sidecar on a dynamic port
- Open the React workbench inside the Electron window

To run with the Vite dev server:
```bash
cd frontend && npm run dev
# In another terminal:
cd desktop && npm run dev
```

## Expected Behavior

1. Electron acquires a single-instance lock.
2. App data directories are created under `~/Library/Application Support/novelos-desktop/` (macOS):
   - `data/` — SQLite database
   - `config/` — user configuration files
   - `logs/` — application and sidecar logs
   - `backups/` — reserved for future use
3. A random available localhost port is selected.
4. Python backend starts with:
   ```bash
   python3 -m novel_factory.desktop_sidecar --host 127.0.0.1 --port <port> --db-path <userData>/data/novelos.db --llm-mode stub
   ```
5. Electron polls `/api/health` until the backend is ready.
6. The BrowserWindow opens with the React frontend loaded.
7. The frontend detects `window.__NOVELOS_DESKTOP__` and uses the dynamically assigned `apiBaseUrl`.
8. Project list, chapter pages, and API calls work through the local backend.
9. Closing Electron terminates the sidecar cleanly.

## Environment Variables

| Variable | Description |
| --- | --- |
| `NOVELOS_DESKTOP_SIDECAR_CMD` | Override the sidecar command (default: `python3`) |

## Troubleshooting

### Backend fails to start
- Check `~/Library/Application Support/novelos-desktop/logs/sidecar.stderr.log`
- Ensure `python3 -m novel_factory.cli api --help` works from the repo root
- Verify the `novel-factory` package is installed: `python3 -m pip install -e .`

### Port conflicts
- The app picks a random available port automatically. If this fails, restart the app.

### Frontend loads but API calls fail
- Open DevTools (View → Toggle Developer Tools in dev mode)
- Check `window.__NOVELOS_DESKTOP__` in the console
- Verify the `apiBaseUrl` matches the sidecar port in the Electron logs

### Sidecar process left behind
- The app attempts to send `SIGTERM` and then `SIGKILL` after 5 seconds
- If a process remains, kill it manually: `pkill -f "novel_factory.cli api"`

## Building the Frozen Sidecar (M1)

M1 adds PyInstaller-based freezing so the desktop app can run without a local Python source environment.

### Prerequisites

```bash
python3 -m pip install pyinstaller
```

### Build

```bash
bash packaging/scripts/build-sidecar.sh
```

This will:
1. Clean previous PyInstaller output.
2. Run `pyinstaller packaging/pyinstaller/novelos-sidecar.spec --clean`.
3. Copy the resulting `dist/novelos-sidecar/` bundle to:
   `desktop/resources/sidecar/darwin-arm64/novelos-sidecar` (or `darwin-x64`).
4. Mark the binary executable.

### Smoke test the frozen sidecar

```bash
bash packaging/scripts/smoke-sidecar.sh
```

This will:
1. Find the frozen binary for the current platform.
2. Start it on a random free port with `--llm-mode stub`.
3. Poll `/api/health` until it returns OK.
4. Verify the SQLite database file was created.
5. Stop the sidecar and clean up.

### Sidecar resolution logic

Electron chooses the sidecar executable in this priority:

1. `NOVELOS_DESKTOP_SIDECAR_CMD` environment variable (always wins).
2. **Packaged mode** (`!app.isPackaged`): look for frozen binary at:
   `process.resourcesPath/sidecar/<platform-arch>/novelos-sidecar`
3. **Dev mode**: fall back to `python3 -m novel_factory.desktop_sidecar`.

Platform keys:
- `darwin-arm64`
- `darwin-x64`
- `linux-x64`
- `win32-x64`

## Packaging the Electron App (M2)

M2 produces a standalone macOS `.app` bundle that includes the frontend and the frozen Python sidecar.

### Prerequisites

1. Frontend built:
   ```bash
   cd frontend && npm run build
   ```
2. Frozen sidecar built:
   ```bash
   bash packaging/scripts/build-sidecar.sh
   ```
3. Desktop dependencies installed:
   ```bash
   cd desktop && npm install
   ```

### Build the macOS app

```bash
cd desktop
npm run pack:mac     # Builds release/mac-arm64/Novelos.app (unsigned, fast)
npm run dist:mac     # Also produces release/Novelos-6.4.0-m2-arm64.dmg
```

The packaged app will contain:
- `Novelos.app/Contents/Resources/app.asar` — Electron main/preload code
- `Novelos.app/Contents/Resources/frontend/dist` — React frontend assets
- `Novelos.app/Contents/Resources/sidecar/darwin-arm64/novelos-sidecar` — Frozen Python backend

### Launch the packaged app

```bash
open release/mac-arm64/Novelos.app
```

Or directly:
```bash
./release/mac-arm64/Novelos.app/Contents/MacOS/Novelos
```

### What happens on first launch

1. App data directories are created under `~/Library/Application Support/novelos-desktop/`:
   - `data/` — SQLite database
   - `config/` — user configuration files
   - `logs/` — application and sidecar logs
   - `backups/` — reserved for future use
2. A random available localhost port is selected.
3. The **frozen sidecar** starts from app resources (no local Python needed).
4. Electron polls `/api/health` until the backend is ready.
5. The BrowserWindow opens with the bundled frontend loaded.

## Desktop Runtime Settings (M3)

M3 adds user-facing data directory governance and config management.

### Default config auto-creation

On first launch, if `<userData>/config/local.yaml` does not exist, Electron creates a safe stub-mode default config with a `default` LLM profile. No API keys are included.

### Desktop Runtime settings page

Navigate to **配置中心 → 桌面运行时** to view:
- Current mode (Desktop / Browser)
- Platform and version
- LLM mode
- Config and DB file existence and paths
- Backend health status

Actions available in desktop mode:
- **打开数据目录** — opens `~/Library/Application Support/novelos-desktop/data/`
- **打开配置目录** — opens `~/Library/Application Support/novelos-desktop/config/`
- **打开日志目录** — opens `~/Library/Application Support/novelos-desktop/logs/`

### Desktop config editing

Under **桌面运行时 → 桌面配置**, you can safely edit non-secret fields:
- LLM mode (`stub` / `real`)
- Model name
- Base URL
- Temperature

API keys are never displayed or written through this UI. They must be managed via environment variables or manual file editing.

### Log rotation

Electron logs and sidecar stdout/stderr logs are automatically rotated when they exceed 5 MB:
- Current log → kept as-is
- Previous log → renamed to `.1`
- Only one backup (`.1`) is kept for M3.

## Known Limitations for M3

- **No code signing**: The `.app` is unsigned. macOS Gatekeeper may block it on first launch (right-click → Open to bypass).
- **No notarization**: Required for distribution outside the Mac App Store.
- **No auto-update**: Distribution and update mechanisms are future work.
- **macOS only**: Windows (`nsis`) and Linux (`AppImage`) targets are configured in `electron-builder.yml` but not yet verified.
- **No secure API key storage**: LLM API keys continue to use `.env` or environment variables.
- **Stub mode default**: The desktop app currently defaults to `--llm-mode stub` for safety.
- **No menu bar customization**: Uses default Electron menus.
- **Config editing limited to non-secret fields**: API keys cannot be edited through the UI.

## Next Recommended Milestone

**M4 — Secure Keychain & Distribution Polish**

- Integrate OS keychain for API key storage.
- Add in-app API key input with secure storage.
- Polish DMG layout and app icon.
- Code signing (optional for M4).

## Summary of Changed Files (M0 + M1 + M2 + M3)

- `desktop/package.json` — Electron project manifest with `electron-builder`
- `desktop/tsconfig.json` — TypeScript configuration
- `desktop/src/main.ts` — Electron main process with sidecar resolution, env vars, IPC handlers
- `desktop/src/preload.ts` — Preload script with safe API injection + directory open APIs
- `desktop/src/sidecar.ts` — Sidecar process manager
- `desktop/src/paths.ts` — App directory utilities + default config creation
- `desktop/src/logging.ts` — Main process logging + log rotation
- `desktop/electron-builder.yml` — Electron Builder configuration
- `desktop/build/entitlements.mac.plist` — macOS entitlements for unsigned packaging
- `desktop/README.md` — Documentation
- `desktop/resources/sidecar/.gitkeep` — Resource directory placeholder
- `packaging/pyinstaller/novelos-sidecar.spec` — PyInstaller spec
- `packaging/scripts/build-sidecar.sh` — macOS sidecar build script
- `packaging/scripts/smoke-sidecar.sh` — Sidecar standalone smoke test
- `novel_factory/desktop_sidecar.py` — Thin Python sidecar wrapper
- `novel_factory/api/routes/desktop.py` — Desktop runtime API (runtime-info, config read/write)
- `novel_factory/api_app.py` — Register desktop router
- `frontend/src/lib/api.ts` — API base URL resolution + desktop window types
- `frontend/src/pages/Settings.tsx` — Add desktop section to settings navigation
- `frontend/src/components/settings/SettingsConsoleSections.tsx` — DesktopRuntimeSection + DesktopConfigSection
