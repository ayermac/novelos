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

### One-command local build

For local client validation, prefer the full build script from the repo root:

```bash
bash packaging/scripts/build-desktop-mac.sh --dir
```

This builds the React frontend, freezes the Python sidecar, and packages the unsigned macOS `.app` in one pass.

To also create a DMG:

```bash
bash packaging/scripts/build-desktop-mac.sh --dmg
```

From the `desktop/` directory, the same flows are available as:

```bash
npm run pack:mac:full
npm run dist:mac:full
```

Use `--skip-sidecar` only when the frozen sidecar already exists and you are only rebuilding frontend or Electron changes:

```bash
bash packaging/scripts/build-desktop-mac.sh --dir --skip-sidecar
```

### Manual build steps

The full script above runs these steps for you. Run them manually only when debugging a specific build layer.

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
npm run dist:mac     # Also produces release/Novelos-6.5.0-m3-arm64.dmg
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

The desktop package does not expose a public web server. The sidecar listens only on `127.0.0.1` with a random local port, and the Electron renderer receives that port through `window.__NOVELOS_DESKTOP__`.

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

## Secure API Key Storage (M4)

M4 introduces secure desktop API key storage using Electron's built-in `safeStorage`.

### How it works

- API keys are **never written to YAML config files**.
- Keys are encrypted by Electron `safeStorage` and stored in `<userData>/config/secrets.json`.
- The `secrets.json` file only contains encrypted base64 blobs — no plaintext.
- Plaintext keys exist only **briefly in the Electron main process memory** when:
  - The user saves a new key through the UI.
  - The sidecar starts and keys are injected into the sidecar environment.
- The renderer process **cannot read decrypted keys**.
- The backend API **never returns API key values**.

### Sidecar key injection

On startup, Electron reads `api_key_env` values from the desktop config profile(s). For each env name that has a stored secret, it decrypts the value and injects it into the sidecar process environment. The backend receives `NOVELOS_DESKTOP_SECRET_KEYS` so it can distinguish securely stored keys from ordinary environment variables.

Priority: **Electron secure storage > OS environment > `.env` file**.

### UI

Navigate to **配置中心 → 桌面运行时 → 桌面配置 → API Key 安全存储**:

- View the current profile's `api_key_env` and status:
  - **已安全保存** — key is in Electron safeStorage.
  - **来自环境变量** — key is set in the OS environment.
  - **未配置** — no key found.
- Enter a key and click **保存到本机安全存储**.
- Click **删除本机保存的 Key** to remove the stored key (uses a confirmation dialog).
- After saving or deleting, a message appears: **"重启客户端后生效"**.

### Limitations for M4

- Keys saved while the app is running require a restart to take effect (no automatic sidecar restart yet).
- If `safeStorage` is unavailable on the system, key storage will fail with a clear error (no silent plaintext fallback).

## Known Limitations for M4

- **No code signing**: The `.app` is unsigned. macOS Gatekeeper may block it on first launch (right-click → Open to bypass).
- **No notarization**: Required for distribution outside the Mac App Store.
- **No auto-update**: Distribution and update mechanisms are future work.
- **macOS only**: Windows (`nsis`) and Linux (`AppImage`) targets are configured in `electron-builder.yml` but not yet verified.
- **Stub mode default**: The desktop app currently defaults to `--llm-mode stub` for safety.
- **No menu bar customization**: Uses default Electron menus.
- **No automatic sidecar restart after key changes**: Requires app restart.

## Runtime Stability and Recovery (M5)

M5 focuses on runtime reliability, health monitoring, sidecar crash recovery, and diagnostics.

### Sidecar lifecycle enhancements

- `SidecarManager` now tracks state: `starting`, `healthy`, `exited`, `failed`, `stopping`.
- Records last error with exit code, signal, timestamp, and stderr log path.
- Never logs env values or API keys.

### Restart sidecar without quitting the app

- **Settings → Desktop Runtime → Restart Local Service** stops and restarts the sidecar.
- A new random port may be selected; the renderer updates `apiBaseUrl` automatically.
- SafeStorage keys are re-injected into the new sidecar process.

### Runtime health banner

- A non-blocking banner appears at the top of the window when the backend becomes unreachable.
- Actions: **Retry connection**, **Restart local service**, **Open logs directory**.
- Banner auto-hides when health recovers.

### Startup diagnostics window

- If the sidecar fails to start within 60 seconds, a diagnostics window is shown instead of a native alert box.
- Contents: error summary, start command (no env secrets), logs directory, stderr path.
- Buttons: **Retry launch**, **Open logs directory**, **Open config directory**, **Quit app**.
- If frontend resources are missing, shows the expected dist path.
- Diagnostics HTML is self-contained and does not depend on React frontend assets.

### LLM connectivity test

- **Settings → Desktop Runtime → Desktop Config → Test LLM connection** validates real LLM connectivity.
- In stub mode: prompts to switch to real mode and restart.
- If API key is missing: prompts to save the key and restart.
- Uses the existing `/settings/validate` endpoint with a minimal prompt.

### Smoke test script

```bash
bash packaging/scripts/smoke-desktop-app-mac.sh
```

Verifies the packaged `.app`:
- Bundle structure (frontend dist, frozen sidecar, executable flags)
- App launch and port detection
- `/api/health` response
- User data directory creation (DB, config, logs)
- Clean shutdown with no residual sidecar processes
- Uses `NOVELOS_DESKTOP_USER_DATA_DIR` to avoid polluting real user data.

### Environment variable for isolated user data

```bash
NOVELOS_DESKTOP_USER_DATA_DIR=/tmp/novelos-test \
  bash packaging/scripts/smoke-desktop-app-mac.sh
```

Also supported for manual launches:

```bash
NOVELOS_DESKTOP_USER_DATA_DIR=/tmp/novelos-test \
  ./desktop/release/mac-arm64/Novelos.app/Contents/MacOS/Novelos
```

## Next Recommended Milestone

**M6 — Cross-Platform CI & Release Pipeline**

- GitHub Actions matrix for macOS, Windows, Linux.
- Artifact naming with version, platform, architecture, and commit.
- Code signing and notarization (future work).

## Summary of Changed Files (M0 + M1 + M2 + M3 + M4 + M5)

- `desktop/package.json` — Electron project manifest with `electron-builder`
- `desktop/tsconfig.json` — TypeScript configuration
- `desktop/src/main.ts` — Electron main process with sidecar resolution, env vars, IPC handlers, secure key injection, diagnostics window, restart logic
- `desktop/src/preload.ts` — Preload script with safe API injection + directory open APIs + secret APIs + runtime status subscription
- `desktop/src/sidecar.ts` — Sidecar process manager with state machine and error recording
- `desktop/src/runtimeStatus.ts` — **NEW** Runtime status tracker and change subscriptions
- `desktop/src/paths.ts` — App directory utilities + default config creation + `NOVELOS_DESKTOP_USER_DATA_DIR` support
- `desktop/src/logging.ts` — Main process logging + log rotation
- `desktop/src/secrets.ts` — Electron safeStorage wrapper for API keys
- `desktop/electron-builder.yml` — Electron Builder configuration
- `desktop/build/entitlements.mac.plist` — macOS entitlements for unsigned packaging
- `desktop/README.md` — Documentation
- `desktop/resources/sidecar/.gitkeep` — Resource directory placeholder
- `packaging/pyinstaller/novelos-sidecar.spec` — PyInstaller spec
- `packaging/scripts/build-sidecar.sh` — macOS sidecar build script
- `packaging/scripts/smoke-sidecar.sh` — Sidecar standalone smoke test
- `packaging/scripts/build-desktop-mac.sh` — One-command frontend + sidecar + Electron macOS build
- `packaging/scripts/smoke-desktop-app-mac.sh` — **NEW** Packaged app smoke test
- `novel_factory/desktop_sidecar.py` — Thin Python sidecar wrapper
- `novel_factory/api/routes/desktop.py` — Desktop runtime API (runtime-info, config read/write with key source detection)
- `novel_factory/api_app.py` — Register desktop router
- `frontend/src/lib/api.ts` — API base URL resolution + desktop window types + dynamic base URL getter
- `frontend/src/pages/Settings.tsx` — Add desktop section to settings navigation
- `frontend/src/components/DesktopRuntimeBanner.tsx` — **NEW** Top health banner with retry/restart/logs actions
- `frontend/src/components/settings/SettingsConsoleSections.tsx` — DesktopRuntimeSection + DesktopConfigSection + DesktopApiKeyCard + LLM test button
