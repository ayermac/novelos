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

## Known Limitations for M0

- **No packaging**: `electron-builder` is not configured yet. The app only runs from source.
- **No PyInstaller sidecar**: The backend runs from the local Python installation.
- **macOS only**: Windows and Linux support is not yet implemented.
- **No secure API key storage**: LLM API keys continue to use `.env` or environment variables.
- **Stub mode default**: The desktop app currently defaults to `--llm-mode stub` for safety.
- **No auto-update**: Distribution and update mechanisms are future work.
- **No menu bar customization**: Uses default Electron menus.
- **Config handling**: User config must be manually placed in `<userData>/config/local.yaml` if desired.

## Next Recommended Milestone

**M1 — Python Sidecar Freeze**

- Add `novel_factory/desktop_sidecar.py` as a dedicated entry point
- Create PyInstaller spec to freeze the backend into a platform binary
- Electron dev/packaged mode detection for choosing source vs. frozen sidecar
- macOS: verify sidecar binary can start independently and serve `/api/health`

## Summary of Changed Files

- `desktop/package.json` — new Electron project manifest
- `desktop/tsconfig.json` — new TypeScript configuration
- `desktop/src/main.ts` — new Electron main process
- `desktop/src/preload.ts` — new preload script with safe API injection
- `desktop/src/sidecar.ts` — new sidecar process manager
- `desktop/src/paths.ts` — new app directory utilities
- `desktop/src/logging.ts` — new main process logging
- `desktop/README.md` — new documentation
- `novel_factory/desktop_sidecar.py` — new thin Python sidecar wrapper (optional)
- `frontend/src/lib/api.ts` — updated API base URL resolution for desktop awareness
