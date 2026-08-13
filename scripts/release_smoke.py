#!/usr/bin/env python3
"""Release smoke script — one-shot validation for release readiness.

Checks that runtime, API, CLI, and package versions are aligned and healthy.
Does not require a running API (can start one or check an existing one),
and does not depend on real LLM keys.

Usage:
    python3 scripts/release_smoke.py
    python3 scripts/release_smoke.py --api-url http://127.0.0.1:8765/api/health
    python3 scripts/release_smoke.py --json
    python3 scripts/release_smoke.py --api-url http://127.0.0.1:8765/api/health --json

Exit codes:
    0 — all required checks passed
    1 — one or more required checks failed
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from novel_factory.version import get_version, __version__  # noqa: E402


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_cli_version() -> dict:
    """Check that CLI --version reports the same as version.py."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "novel_factory.cli", "--version"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=15,
        )
        output = result.stdout.strip()
        expected = f"novelos {__version__}"
        passed = expected in output
        return {
            "name": "cli_version",
            "label": "CLI version",
            "passed": passed,
            "required": True,
            "message": output if passed else f"expected '{expected}', got '{output}'",
        }
    except Exception as exc:
        return {
            "name": "cli_version",
            "label": "CLI version",
            "passed": False,
            "required": True,
            "message": str(exc),
        }


def check_api_health(api_url: str) -> dict:
    """Check API health endpoint version and basic status."""
    try:
        req = urllib.request.Request(api_url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {
            "name": "api_health",
            "label": "API health",
            "passed": False,
            "required": True,
            "message": f"Could not reach {api_url}: {exc}",
        }

    if not body.get("ok"):
        return {
            "name": "api_health",
            "label": "API health",
            "passed": False,
            "required": True,
            "message": f"API returned ok=false: {body.get('error')}",
        }

    data = body.get("data", {})
    api_version = data.get("version", "")
    version_match = api_version == __version__
    db_connected = data.get("db_connected", False)
    llm_mode = data.get("llm_mode", "unknown")
    startup = data.get("startup", {})

    messages = []
    if not version_match:
        messages.append(
            f"VERSION MISMATCH: API={api_version}, runtime={__version__}"
        )
    if not db_connected:
        messages.append("DB not connected")
    messages.append(f"llm_mode={llm_mode}")
    if startup.get("started_at"):
        messages.append(f"started_at={startup['started_at']}")
    if startup.get("source_root"):
        messages.append(f"source_root={startup['source_root']}")

    return {
        "name": "api_health",
        "label": "API health",
        "passed": version_match and db_connected,
        "required": True,
        "message": "; ".join(messages) if messages else "healthy",
        "details": {
            "version": api_version,
            "db_connected": db_connected,
            "llm_mode": llm_mode,
            "startup": startup,
        },
    }


def check_frontend_version() -> dict:
    """Check frontend/package.json version matches runtime."""
    try:
        pkg = _load_json(REPO_ROOT / "frontend" / "package.json")
        version = pkg.get("version", "")
        passed = version == __version__
        return {
            "name": "frontend_version",
            "label": "Frontend package version",
            "passed": passed,
            "required": True,
            "message": version if passed else f"expected {__version__}, got {version}",
        }
    except Exception as exc:
        return {
            "name": "frontend_version",
            "label": "Frontend package version",
            "passed": False,
            "required": True,
            "message": str(exc),
        }


def check_desktop_version() -> dict:
    """Check desktop/package.json version matches runtime."""
    try:
        pkg = _load_json(REPO_ROOT / "desktop" / "package.json")
        version = pkg.get("version", "")
        passed = version == __version__
        return {
            "name": "desktop_version",
            "label": "Desktop package version",
            "passed": passed,
            "required": True,
            "message": version if passed else f"expected {__version__}, got {version}",
        }
    except Exception as exc:
        return {
            "name": "desktop_version",
            "label": "Desktop package version",
            "passed": False,
            "required": True,
            "message": str(exc),
        }


def check_desktop_smoke() -> dict:
    """Optional: desktop build check if node_modules exist."""
    desktop_dir = REPO_ROOT / "desktop"
    if not (desktop_dir / "node_modules").exists():
        return {
            "name": "desktop_smoke",
            "label": "Desktop build smoke",
            "passed": True,
            "required": False,
            "message": "skipped — node_modules not installed (run `cd desktop && npm install`)",
        }
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=desktop_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed = result.returncode == 0
        return {
            "name": "desktop_smoke",
            "label": "Desktop build smoke",
            "passed": passed,
            "required": False,
            "message": "build OK" if passed else result.stderr[:500],
        }
    except Exception as exc:
        return {
            "name": "desktop_smoke",
            "label": "Desktop build smoke",
            "passed": False,
            "required": False,
            "message": str(exc),
        }


def check_desktop_sidecar() -> dict:
    """Start desktop sidecar, verify health version matches desktop package version."""
    import os
    import tempfile
    import time
    import signal

    desktop_pkg = _load_json(REPO_ROOT / "desktop" / "package.json")
    desktop_version = desktop_pkg.get("version", "")

    def check_in_process(reason: str) -> dict:
        """Validate the same app factory when the environment forbids sockets."""
        try:
            from fastapi.testclient import TestClient
            from novel_factory.api_app import create_api_app

            app = create_api_app(db_path=":memory:", llm_mode="stub")
            with TestClient(app) as client:
                response = client.get("/api/health")
            body = response.json()
            api_version = body.get("data", {}).get("version", "")
            healthy = response.status_code == 200 and body.get("ok") is True
            version_match = api_version == desktop_version
            return {
                "name": "desktop_sidecar",
                "label": "Desktop sidecar health/version",
                "passed": healthy and version_match,
                "required": True,
                "message": (
                    f"in-process fallback version={api_version}, desktop package={desktop_version} "
                    f"({reason})"
                    if healthy and version_match
                    else f"in-process fallback failed: health={healthy}, sidecar={api_version}, "
                    f"desktop={desktop_version} ({reason})"
                ),
                "details": {"transport": "in-process", "fallback_reason": reason},
            }
        except Exception as exc:
            return {
                "name": "desktop_sidecar",
                "label": "Desktop sidecar health/version",
                "passed": False,
                "required": True,
                "message": f"in-process fallback failed ({type(exc).__name__})",
            }

    # Find a free port
    port = 0
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
    except PermissionError:
        return check_in_process("socket binding not permitted")
    except Exception as exc:
        return {
            "name": "desktop_sidecar",
            "label": "Desktop sidecar health/version",
            "passed": False,
            "required": True,
            "message": f"Could not find free port: {exc}",
        }

    db_path = tempfile.NamedTemporaryFile(delete=False, suffix="_smoke.db").name
    try:
        from novel_factory.db.connection import init_db
        init_db(db_path)
    except Exception as exc:
        return {
            "name": "desktop_sidecar",
            "label": "Desktop sidecar health/version",
            "passed": False,
            "required": True,
            "message": f"Could not init temp DB: {exc}",
        }

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "novel_factory.desktop_sidecar",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--db-path", db_path,
            "--llm-mode", "stub",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=REPO_ROOT,
    )

    health_url = f"http://127.0.0.1:{port}/api/health"
    health = None
    deadline = time.time() + 30
    try:
        while time.time() < deadline:
            try:
                req = urllib.request.Request(health_url, method="GET")
                req.add_header("Accept", "application/json")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    health = json.loads(resp.read().decode("utf-8"))
                    if health.get("ok") and health.get("data", {}).get("status") == "ok":
                        break
            except Exception:
                pass
            time.sleep(0.5)
    finally:
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        try:
            os.unlink(db_path)
        except Exception:
            pass

    if not health:
        return {
            "name": "desktop_sidecar",
            "label": "Desktop sidecar health/version",
            "passed": False,
            "required": True,
            "message": "Sidecar did not become healthy within 30s",
        }

    api_version = health.get("data", {}).get("version", "")
    version_match = api_version == desktop_version
    return {
        "name": "desktop_sidecar",
        "label": "Desktop sidecar health/version",
        "passed": version_match,
        "required": True,
        "message": (
            f"sidecar version={api_version}, desktop package={desktop_version}"
            if version_match
            else f"VERSION MISMATCH: sidecar={api_version}, desktop={desktop_version}"
        ),
    }


def run_checks(api_url: str | None) -> list[dict]:
    """Run all checks and return results."""
    results = [
        check_cli_version(),
        check_frontend_version(),
        check_desktop_version(),
        check_desktop_sidecar(),
    ]
    if api_url:
        results.append(check_api_health(api_url))
    else:
        results.append({
            "name": "api_health",
            "label": "API health",
            "passed": True,
            "required": False,
            "message": "skipped — pass --api-url to check a running API",
        })
    results.append(check_desktop_smoke())
    return results


def print_human(results: list[dict]) -> int:
    """Print human-readable summary. Return exit code."""
    required_failed = 0
    optional_failed = 0

    print("=" * 60)
    print("Novelos Release Smoke")
    print(f"Expected version: {__version__}")
    print("=" * 60)

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        req_label = "required" if r["required"] else "optional"
        if not r["passed"]:
            if r["required"]:
                required_failed += 1
            else:
                optional_failed += 1
        print(f"  [{status}] {r['label']} ({req_label})")
        print(f"         {r['message']}")

    print("-" * 60)
    if required_failed == 0 and optional_failed == 0:
        print("Result: ALL CHECKS PASSED — release candidate looks good.")
        return 0
    if required_failed == 0:
        print(f"Result: REQUIRED PASSED, {optional_failed} optional warning(s).")
        return 0
    print(f"Result: {required_failed} required check(s) FAILED — do not release.")
    return 1


def print_json(results: list[dict]) -> int:
    """Print JSON summary. Return exit code."""
    required_failed = sum(1 for r in results if r["required"] and not r["passed"])
    optional_failed = sum(1 for r in results if not r["required"] and not r["passed"])
    output = {
        "ok": required_failed == 0,
        "version_expected": __version__,
        "required_failed": required_failed,
        "optional_failed": optional_failed,
        "checks": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if required_failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Novelos release smoke script")
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8765/api/health",
        help="API health endpoint URL (default: http://127.0.0.1:8765/api/health)",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip API health check (useful when API is not running)",
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    api_url = None if args.skip_api else args.api_url
    results = run_checks(api_url)

    if args.json:
        return print_json(results)
    return print_human(results)


if __name__ == "__main__":
    sys.exit(main())
