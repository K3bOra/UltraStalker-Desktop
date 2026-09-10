from __future__ import annotations

import json
import os
from contextlib import closing
import sqlite3
import struct
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from ultrastalker_desktop import __version__, AUTHOR
from ultrastalker_desktop.runtime import diagnostics_dir, executable_dir, resource_candidates, verify_release_integrity
from ultrastalker_desktop.support_bundle import sanitize_text
from ultrastalker_desktop.storage.credentials import ensure_secure_backend, SecureCredentialBackendError
from ultrastalker_desktop.storage import database as storage_database


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_user_database_integrity() -> tuple[bool, str, str | None]:
    """Sanitized wrapper around the storage layer's read-only quick-check."""
    ok, status, error = storage_database.integrity_check()
    clean_error = sanitize_text(error).strip() if error else None
    return ok, status, clean_error or (type(error).__name__ if error else None)


def run_self_test(*, require_release_integrity: bool = False) -> tuple[bool, dict]:
    checks = {
        "python_bits": struct.calcsize("P") * 8,
        "runtime_platform": sys.platform,
    }

    # SQLite must be functional, not merely importable.
    try:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "selftest.db"
            c = sqlite3.connect(db)
            c.execute("create table t(x integer)")
            c.execute("insert into t values (7)")
            value = c.execute("select x from t").fetchone()[0]
            c.close()
            checks["sqlite"] = value == 7
    except Exception as exc:
        checks["sqlite"] = False
        checks["sqlite_error"] = sanitize_text(str(exc)).strip() or type(exc).__name__

    # Installed diagnostics also validate the persistent user database. Build
    # self-tests intentionally skip it so release creation never touches user
    # AppData on the build machine.
    if require_release_integrity:
        db_ok, db_status, db_error = _check_user_database_integrity()
        checks["database_integrity"] = db_ok
        checks["database_integrity_status"] = db_status
        if db_error:
            checks["database_integrity_error"] = db_error

    # Verify the packaged mpv runtime exists and can actually start.
    mpv = next((p for p in resource_candidates("mpv.exe") if p.is_file()), None)
    if not mpv:
        checks["mpv"] = False
        checks["mpv_error"] = "mpv.exe not found"
    else:
        try:
            cp = subprocess.run(
                [str(mpv), "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            checks["mpv"] = cp.returncode == 0
            if cp.returncode != 0:
                checks["mpv_error"] = f"exit code {cp.returncode}"
        except Exception as exc:
            checks["mpv"] = False
            checks["mpv_error"] = sanitize_text(str(exc)).strip() or type(exc).__name__

    # On Windows, force and verify the native Credential Manager backend.
    # keyring supports config/environment backend overrides; provider secrets
    # must never be redirected to an arbitrary third-party/plaintext backend.
    expected_backend = "keyring.backends.Windows.WinVaultKeyring"
    try:
        import keyring as keyring_module
        backend = ensure_secure_backend(keyring_module)
        checks["credential_backend_name"] = backend
        checks["credential_backend"] = (
            backend == expected_backend if sys.platform.startswith("win") else True
        )
    except Exception as exc:
        keyring_module = None
        checks["credential_backend"] = False
        checks["credential_backend_name"] = "unavailable"
        checks["credential_backend_error"] = sanitize_text(str(exc)).strip() or type(exc).__name__

    # Test the actual OS credential backend with an ephemeral value. Cleanup
    # belongs in finally so a backend that accepts a write and then fails on a
    # read does not leave probe credentials behind after every release build.
    service = "UltraStalkerDesktop-SelfTest"
    user = "probe-" + uuid.uuid4().hex
    secret = uuid.uuid4().hex
    credential_written = False
    checks["credential_cleanup"] = True
    try:
        if keyring_module is None:
            raise SecureCredentialBackendError("Secure credential backend is unavailable.")
        keyring_module.set_password(service, user, secret)
        credential_written = True
        got = keyring_module.get_password(service, user)
        checks["credential_manager"] = got == secret
    except Exception as exc:
        checks["credential_manager"] = False
        checks["credential_manager_error"] = sanitize_text(str(exc)).strip() or type(exc).__name__
    finally:
        if credential_written and keyring_module is not None:
            try:
                keyring_module.delete_password(service, user)
            except Exception as exc:
                checks["credential_cleanup"] = False
                checks["credential_cleanup_error"] = sanitize_text(str(exc)).strip() or type(exc).__name__

    # Load Qt and instantiate QApplication using the same platform plugin the
    # packaged application will use. On Windows, testing ``offscreen`` could
    # produce a false pass even if qwindows.dll is missing (or a false failure
    # if only the normal Windows plugin is packaged). Non-Windows dev/CI runs
    # keep the headless offscreen backend.
    try:
        qt_platform = "windows" if sys.platform.startswith("win") else "offscreen"
        os.environ["QT_QPA_PLATFORM"] = qt_platform
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        checks["qt_runtime"] = app is not None
        checks["qt_platform"] = qt_platform
        app.quit()
    except Exception as exc:
        checks["qt_runtime"] = False
        checks["qt_runtime_error"] = sanitize_text(str(exc)).strip() or type(exc).__name__

    # Installed release diagnostics must prove they are running from the same
    # fingerprinted payload that produced the installer. The build self-test
    # runs before provenance exists, so release integrity is collected there
    # as informational/development evidence but is mandatory only for the
    # installed frozen runtime.
    try:
        release_integrity = verify_release_integrity(full=require_release_integrity)
    except Exception as exc:
        release_integrity = {
            "status": "error",
            "checked": 0,
            "mismatches": [],
            "error": sanitize_text(str(exc)).strip() or type(exc).__name__,
        }
    if require_release_integrity:
        checks["release_integrity"] = release_integrity.get("status") == "ok"
        if not checks["release_integrity"]:
            checks["release_integrity_error"] = "Installed release integrity verification failed"
    else:
        checks["release_integrity"] = release_integrity.get("status") in ("ok", "development")

    mandatory = ["sqlite", "mpv", "credential_backend", "credential_manager", "credential_cleanup", "qt_runtime"]
    if require_release_integrity:
        mandatory.extend(["database_integrity", "release_integrity"])
    passed = all(checks.get(key) is True for key in mandatory)
    artifacts = {}
    app_exe = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False) and app_exe.is_file():
        try:
            artifacts["application_sha256"] = _sha256(app_exe)
        except OSError:
            pass
    if mpv and mpv.is_file():
        try:
            artifacts["mpv_sha256"] = _sha256(mpv)
        except OSError:
            pass
    report = {
        "product": "Ultra Stalker Desktop",
        "version": __version__,
        "developer": AUTHOR,
        "passed": passed,
        "checks": checks,
        "artifacts": artifacts,
        "release_integrity": release_integrity,
    }
    return passed, report


def _write_self_test_report(report: dict, path: Path, *, report_kind: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    payload["report_kind"] = report_kind
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_build_self_test_report(report: dict, path: Path | None = None) -> Path:
    """Write the immutable release-build self-test beside the packaged EXE.

    This file is part of the fingerprinted payload and must only be produced by
    the release pipeline before provenance is generated.
    """
    return _write_self_test_report(
        report, path or (executable_dir() / "SELF_TEST.json"), report_kind="build"
    )


def write_runtime_self_test_report(report: dict, path: Path | None = None) -> Path:
    """Write an installed/manual self-test outside the signed payload.

    Re-running diagnostics after installation must never mutate SELF_TEST.json
    beside the executable because that build report is covered by provenance.
    """
    return _write_self_test_report(
        report, path or (diagnostics_dir() / "SELF_TEST.json"), report_kind="runtime"
    )


def write_self_test_report(report: dict, path: Path | None = None) -> Path:
    """Backward-compatible alias for the safe installed/runtime report."""
    return write_runtime_self_test_report(report, path)
