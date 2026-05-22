# v6.2 Desktop Client Foundation Spec

Status: planning alias and extracted scope for v6.2, derived from `novel-factory-cross-platform-desktop-client-plan.md` and the completed v6.2 report.

## Goal

Move Novelos from a WebUI plus manually started local API into a macOS desktop client foundation with Electron, a Python sidecar, local user data, secure API key storage, runtime diagnostics, and packaging verification.

## Source Plan

The full desktop roadmap lives in `novel-factory-cross-platform-desktop-client-plan.md`. This file exists so v6.2 can be found by version number from `planning/`.

## Scope

### M0: Electron Technical Validation

- Add `desktop/` Electron app.
- Start the Python API sidecar from the Electron main process.
- Inject dynamic API base URL into the React renderer.
- Support dynamic ports, sidecar health polling, window lifecycle, and graceful shutdown.

### M1: Python Sidecar Freeze

- Add `novel_factory/desktop_sidecar.py`.
- Build the backend with PyInstaller.
- Include schema, migrations, config, skills, and agent role resources.
- Smoke test the frozen sidecar.

### M2: Electron App Packaging

- Add Electron Builder configuration.
- Package `frontend/dist` and the frozen sidecar into the macOS app.
- Use userData paths for database/config/logs in packaged mode.

### M3: Desktop Runtime Settings

- Generate safe stub defaults on first start.
- Add desktop runtime/config APIs.
- Add Settings UI for runtime paths, LLM mode, config status, DB status, logs, and restart/open-folder operations.
- Add log rotation.

### M4: Secure API Key Storage

- Store API keys through Electron `safeStorage`.
- Never write plaintext API keys to YAML.
- Inject decrypted keys into the sidecar environment.
- Expose key status/source but not plaintext.
- Support key save/delete from Settings.

### M5: Runtime Stability And Recovery

- Add sidecar status and recent error tracking.
- Support sidecar restart from the UI.
- Update API base URL after sidecar restart.
- Add runtime failure banner.
- Show a self-contained diagnostic window on startup failure.
- Add packaged app smoke verification.

### v6.2.1-v6.2.4 Follow-Through

- Desktop packaging verification pipeline.
- Desktop first-run real LLM setup.
- Packaged desktop first-run acceptance.
- Desktop release diagnostics and recovery.

## Acceptance

1. macOS dev mode opens an Electron window backed by the local FastAPI sidecar.
2. Packaged `.app` starts the frozen sidecar without manually starting API/Vite.
3. User data lives in the desktop userData directory.
4. API keys use secure storage and are never returned in plaintext.
5. Runtime failures are visible and recoverable from Settings or failure UI.
6. Diagnostic packages are exportable and redacted.
7. `verify-desktop-mac.sh` can build and smoke the packaged app.

## Verification Source

See `../reports/novel-factory-v6.2-desktop-client-completion-report.md` and `../reviews/novel-factory-v6.2-desktop-client-review.md`.

## Known Limits

- macOS signing/notarization deferred.
- Windows/Linux packaging not accepted in v6.2.
- Automatic updates deferred.
- Real LLM end-to-end creative acceptance depends on user-provided API keys and was not a hard gate for desktop foundation.

