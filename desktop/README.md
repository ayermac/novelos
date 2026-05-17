# Novelos Desktop Client

This directory contains the Electron desktop client for Novelos.

For the full product overview, see the root README:

- [English](../README.md)
- [中文](../README.zh-CN.md)

## Current Runtime Model

The desktop client is the primary user-facing runtime. It embeds the React author workbench and starts a local FastAPI sidecar automatically.

At launch, Electron:

1. acquires a single-instance lock;
2. creates app data directories under `~/Library/Application Support/novelos-desktop/` on macOS;
3. selects a random available localhost port;
4. starts the Python sidecar;
5. waits for `/api/health`;
6. loads the React workbench in the BrowserWindow;
7. injects `window.__NOVELOS_DESKTOP__` so the renderer can call the dynamic local API base URL;
8. stops the sidecar when the desktop app exits.

The sidecar listens only on `127.0.0.1` and is not exposed as a public server.

## Directory Responsibilities

| Path | Purpose |
| --- | --- |
| `src/main.ts` | Electron main process, window lifecycle, sidecar startup, IPC handlers |
| `src/preload.ts` | safe renderer bridge for desktop runtime APIs |
| `src/sidecar.ts` | sidecar process management |
| `src/secrets.ts` | encrypted API key storage through Electron `safeStorage` |
| `src/runtimeStatus.ts` | desktop runtime status helpers |
| `build/` | icon and entitlement assets |
| `resources/sidecar/` | frozen sidecar bundle created by packaging scripts |
| `release/` | local Electron build output |

## Development

Install dependencies:

```bash
cd desktop
npm install
```

Build TypeScript:

```bash
npm run build
```

Start the desktop app:

```bash
npm run dev
```

For frontend hot reload, start Vite separately from the repository root:

```bash
cd frontend
npm run dev
```

Then run `npm run dev` in `desktop/`. Electron will prefer the Vite dev server and fall back to `../frontend/dist` when Vite is not running.

## Sidecar Resolution

Electron chooses the sidecar executable in this priority order:

1. `NOVELOS_DESKTOP_SIDECAR_CMD` environment variable.
2. Packaged frozen binary at `process.resourcesPath/sidecar/<platform-arch>/novelos-sidecar`.
3. Development fallback: `python3 -m novel_factory.desktop_sidecar`.

Supported platform keys include:

- `darwin-arm64`
- `darwin-x64`
- `linux-x64`
- `win32-x64`

## Build

The preferred build entry point is the repository-level script:

```bash
bash packaging/scripts/build-desktop-mac.sh --dir
```

This builds:

1. the React frontend;
2. the frozen Python sidecar;
3. the Electron macOS app.

Output:

```text
desktop/release/mac-arm64/Novelos.app
```

Build a DMG:

```bash
bash packaging/scripts/build-desktop-mac.sh --dmg
```

Equivalent npm shortcuts:

```bash
npm run pack:mac:full
npm run dist:mac:full
```

Use `--skip-sidecar` only when the frozen sidecar already exists:

```bash
bash packaging/scripts/build-desktop-mac.sh --dir --skip-sidecar
```

## Desktop Data

On macOS, runtime data lives under:

```text
~/Library/Application Support/novelos-desktop/
```

| Directory | Purpose |
| --- | --- |
| `data/` | SQLite database and local runtime data |
| `config/` | desktop YAML config and generated runtime config |
| `logs/` | Electron and sidecar logs |
| `backups/` | backup/restore workspace |

## LLM Secrets

The desktop client stores API keys through Electron `safeStorage`. The renderer never needs direct filesystem access to secret files. When the sidecar starts, Electron injects configured secret values into the sidecar environment.

Provider profiles and agent routing are managed from the desktop Settings page and mirrored into local runtime configuration.

## Diagnostics

Useful checks:

```bash
cd desktop
npm run typecheck
npm run build
```

Sidecar smoke:

```bash
bash packaging/scripts/smoke-sidecar.sh
```

Packaged app verification:

```bash
bash packaging/scripts/verify-desktop-mac.sh
```

Troubleshooting locations:

- sidecar stderr: `~/Library/Application Support/novelos-desktop/logs/sidecar.stderr.log`
- sidecar stdout: `~/Library/Application Support/novelos-desktop/logs/sidecar.stdout.log`
- Electron logs: `~/Library/Application Support/novelos-desktop/logs/`

If a development sidecar is left behind, stop it manually:

```bash
pkill -f "novel_factory.desktop_sidecar"
```
