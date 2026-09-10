from __future__ import annotations

import json
import logging
import hashlib
import os
import re
import sys
import stat
from pathlib import Path
from logging.handlers import RotatingFileHandler

PRODUCT_DIR = "UltraStalker"


def app_data_dir() -> Path:
    base = os.getenv("APPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".ultrastalker"
    path = root / PRODUCT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".ultrastalker"
    path = root / PRODUCT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = local_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def diagnostics_dir() -> Path:
    path = local_data_dir() / "diagnostics"
    path.mkdir(parents=True, exist_ok=True)
    return path


def executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_candidates(name: str) -> list[Path]:
    candidates = [executable_dir() / name]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / name)
    candidates.append(Path.cwd() / name)
    # preserve order while removing duplicates
    seen = set()
    out = []
    for p in candidates:
        q = p.resolve()
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out





def _is_linklike(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction and is_junction():
            return True
        # CPython 3.11 does not expose Path.is_junction(). On Windows, junctions
        # and other filesystem indirections are reparse points, so reject those
        # too rather than silently following content outside the release root.
        if os.name == "nt":
            attrs = getattr(path.lstat(), "st_file_attributes", 0)
            if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                return True
        return False
    except OSError:
        return True


def _walk_payload(root: Path):
    """Yield payload paths while pruning link-like directories before descent."""
    root = Path(root).resolve()

    def raise_error(exc: OSError) -> None:
        raise exc

    for current, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=raise_error
    ):
        base = Path(current)
        kept_dirs = []
        for name in sorted(dirnames):
            path = base / name
            yield path
            if not _is_linklike(path):
                kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            yield base / name


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_release_integrity(root: Path | None = None, app_exe: Path | None = None, *, full: bool = False) -> dict:
    """Verify critical installed payload files against release provenance.

    This is intentionally on-demand (used by diagnostics), not part of normal
    startup, so hashing the application/player does not penalize launch speed.
    No paths, URLs, credentials, or user data are returned.
    """
    root = Path(root or executable_dir()).resolve()
    provenance_path = root / "provenance.json"
    if not provenance_path.is_file():
        return {"status": "development", "checked": 0, "mismatches": []}
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8-sig"))
        if str(provenance.get("platform") or "").lower() == "source":
            return {"status": "development", "checked": 0, "mismatches": []}
        recorded = provenance.get("files") or {}
        if not isinstance(recorded, dict):
            raise ValueError("invalid file manifest")
    except Exception:
        return {"status": "invalid-provenance", "checked": 0, "mismatches": ["provenance.json"]}

    candidates: list[tuple[str, Path]] = []
    exe_path = Path(app_exe).resolve() if app_exe else Path(sys.executable).resolve()
    # A frozen executable is recorded under its basename at the payload root.
    exe_name = exe_path.name
    if full:
        for name in sorted(recorded):
            target = exe_path if name == exe_name else (root / name)
            # When the caller supplied a differently named executable path,
            # preserve the canonical release name binding as well.
            if name == "UltraStalkerDesktop.exe" and exe_name != name:
                target = root / name
            candidates.append((name, target))
    else:
        if exe_name in recorded:
            candidates.append((exe_name, exe_path))
        elif "UltraStalkerDesktop.exe" in recorded:
            candidates.append(("UltraStalkerDesktop.exe", root / "UltraStalkerDesktop.exe"))
        for name in ("mpv.exe", "RELEASE_SHA256.json", "SELF_TEST.json", "MPV_PROVENANCE.json"):
            if name in recorded:
                candidates.append((name, root / name))

    mismatches = []
    checked = 0
    for name, path in candidates:
        checked += 1
        try:
            actual = _sha256_file(path) if path.is_file() and not _is_linklike(path) else ""
        except OSError:
            actual = ""
        if actual != recorded.get(name):
            mismatches.append(name)

    # RELEASE_SHA256.json independently binds the two executable artifacts.
    digest_path = root / "RELEASE_SHA256.json"
    if digest_path.is_file():
        try:
            digest_data = json.loads(digest_path.read_text(encoding="utf-8"))
            for name in ("UltraStalkerDesktop.exe", "mpv.exe"):
                target = root / name
                if name in digest_data:
                    checked += 1
                    if not target.is_file() or _is_linklike(target) or _sha256_file(target) != digest_data.get(name):
                        if name not in mismatches:
                            mismatches.append(name)
        except Exception:
            mismatches.append("RELEASE_SHA256.json")

    unexpected = []
    if full:
        expected_names = set(recorded) | {"provenance.json"}
        try:
            paths = _walk_payload(root)
            for path in paths:
                name = str(path.relative_to(root)).replace("\\", "/")
                if _is_linklike(path):
                    unexpected.append(name)
                    continue
                if not path.is_file():
                    continue
                if name in expected_names:
                    continue
                # Inno Setup writes its own uninstaller bookkeeping beside the
                # fingerprinted payload after installation. Those files are
                # expected and are independently exercised by the installer smoke
                # test, so they are not release-payload mismatches.
                if re.fullmatch(r"unins\d+\.(?:exe|dat|msg)", name, flags=re.I):
                    continue
                unexpected.append(name)
        except OSError:
            unexpected.append("<payload-scan-error>")

    return {
        "status": "ok" if not mismatches and not unexpected else "mismatch",
        "checked": checked,
        "mismatches": sorted(set(mismatches)),
        "unexpected": sorted(set(unexpected)),
        "build_id": provenance.get("build_id"),
        "full": bool(full),
    }

def release_info() -> dict:
    info = {}
    for name in ("provenance.json", "FINAL_RELEASE.json"):
        path = executable_dir() / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                info.update(data)
        except Exception:
            continue
    return info

def configure_logging() -> Path:
    path = log_dir() / "ultrastalker-desktop.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    target = path.resolve()
    has_our_handler = any(
        isinstance(h, RotatingFileHandler)
        and Path(getattr(h, "baseFilename", "")).resolve() == target
        for h in root.handlers
        if getattr(h, "baseFilename", None)
    )
    if not has_our_handler:
        handler = RotatingFileHandler(
            path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        root.addHandler(handler)
    logging.getLogger(__name__).info("Application logging initialized")
    return path
