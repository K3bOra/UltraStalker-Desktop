from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
import zipfile
import uuid
from pathlib import Path

from ultrastalker_desktop import AUTHOR, __version__
from ultrastalker_desktop.runtime import app_data_dir, diagnostics_dir, local_data_dir, log_dir, executable_dir, verify_release_integrity
from ultrastalker_desktop.storage import database as storage_database


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()



def sanitize_text(text: str) -> str:
    # Logs can contain exception strings from remote servers. Strip common
    # credential-bearing values before a support bundle ever leaves the PC.
    text = re.sub(r"https?://[^\s\"\'<>]+", "<redacted-url>", text, flags=re.I)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)([^\s,;]+)", r"\1<redacted>", text)
    text = re.sub(r"(?i)((?:password|passwd|token|api[_-]?key|secret)\s*[:=]\s*)([^\s,;]+)", r"\1<redacted>", text)
    text = re.sub(r"(?i)((?:username|user|login)\s*[:=]\s*)([^\s,;]+)", r"\1<redacted-user>", text)
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "<redacted-email>", text)
    text = re.sub(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", "<redacted-mac>", text)
    # Exception strings can expose the local account name through file paths.
    # Preserve enough path shape for diagnostics without shipping that identity.
    text = re.sub(r"(?i)([A-Z]:(?:\\)+Users(?:\\)+)[^\\/\s]+", r"\1<redacted-user>", text)
    text = re.sub(r"(?i)(/home/)[^/\s]+", r"\1<redacted-user>", text)
    return text

# Backward-compatible internal alias for older call sites/tests.
_sanitize_text = sanitize_text


def _runtime_report() -> dict:
    exe = Path(sys.executable).resolve()
    report = {
        "product": "Ultra Stalker Desktop",
        "version": __version__,
        "developer": AUTHOR,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable_name": exe.name,
        "release_integrity": verify_release_integrity(),
    }
    if exe.is_file():
        try:
            report["executable_sha256"] = _sha256(exe)
        except OSError:
            pass
    try:
        db_ok, db_status, db_error = storage_database.integrity_check()
        report["database_integrity"] = {
            "passed": bool(db_ok),
            "status": db_status,
        }
        if db_error:
            report["database_integrity"]["error"] = sanitize_text(db_error).strip() or type(db_error).__name__
    except Exception as exc:
        report["database_integrity"] = {
            "passed": False,
            "status": "error",
            "error": sanitize_text(str(exc)).strip() or type(exc).__name__,
        }
    return report


def create_support_bundle() -> Path:
    """Create a diagnostics ZIP that intentionally excludes profiles and secrets."""
    out_dir = diagnostics_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    output = out_dir / f"UltraStalkerDesktop_Diagnostics_{stamp}-{uuid.uuid4().hex[:8]}.zip"

    with tempfile.TemporaryDirectory(prefix="ultrastalker-support-") as td:
        root = Path(td)
        (root / "runtime.json").write_text(
            json.dumps(_runtime_report(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Copy only known-safe logs and build metadata. Never include profiles,
        # settings, database files, portal URLs, usernames, MAC addresses, or tokens.
        for path in sorted(log_dir().glob("*.log")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                (root / path.name).write_text(sanitize_text(text), encoding="utf-8")
            except OSError:
                pass

        for name in (
            "provenance.json",
            "SELF_TEST.json",
            "RELEASE_SHA256.json",
            "PYTHON_VERSION.txt",
            "BUILD_DEPENDENCIES.txt",
            "MPV_PROVENANCE.json",
        ):
            src = executable_dir() / name
            if src.is_file():
                try:
                    target = "BUILD_SELF_TEST.json" if name == "SELF_TEST.json" else name
                    shutil.copy2(src, root / target)
                except OSError:
                    pass

        runtime_self_test = diagnostics_dir() / "SELF_TEST.json"
        if runtime_self_test.is_file():
            try:
                shutil.copy2(runtime_self_test, root / "RUNTIME_SELF_TEST.json")
            except OSError:
                pass

        # Corruption markers contain hashes/sizes/error classes only, never the
        # damaged metadata contents. They are safe and useful for support.
        for name in ("profiles_corruption.json", "settings_corruption.json"):
            marker = app_data_dir() / name
            if marker.is_file():
                try:
                    shutil.copy2(marker, root / name)
                except OSError:
                    pass

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(root).as_posix())
    return output
