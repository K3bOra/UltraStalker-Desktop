from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

try:
    import keyring
except ModuleNotFoundError:
    from ultrastalker_desktop.storage.credentials import MISSING_KEYRING as keyring

from ultrastalker_desktop.storage.credentials import ensure_secure_backend, SecureCredentialBackendError

APP_DIR = Path(os.getenv("APPDATA") or (Path.home() / ".ultrastalker")) / "UltraStalker"
FILE = APP_DIR / "settings.json"
SERVICE = "UltraStalkerDesktop"
TMDB_KEY = "settings:tmdb_api_key"
_UNKNOWN = object()
log = logging.getLogger(__name__)


class SettingsStorageError(RuntimeError):
    pass


class SettingsMetadataCorruptError(SettingsStorageError):
    pass


def _record_corrupt_metadata(exc: Exception) -> None:
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "file": FILE.name,
            "detected_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error_type": type(exc).__name__,
        }
        if FILE.is_file():
            raw = FILE.read_bytes()
            payload["size"] = len(raw)
            payload["sha256"] = hashlib.sha256(raw).hexdigest()
        (APP_DIR / "settings_corruption.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _read_metadata(*, strict: bool = False) -> dict:
    try:
        value = json.loads(FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        _record_corrupt_metadata(exc)
        if strict:
            raise SettingsMetadataCorruptError(
                f"Settings metadata is unreadable ({type(exc).__name__}); original file was left untouched."
            ) from exc
        return {}
    if not isinstance(value, dict):
        exc = ValueError("settings metadata root is not an object")
        _record_corrupt_metadata(exc)
        if strict:
            raise SettingsMetadataCorruptError(
                "Settings metadata has an invalid structure; original file was left untouched."
            )
        return {}
    return value


def migrate_legacy_settings_secret() -> bool:
    """Move a legacy plaintext TMDb API key into secure credential storage."""
    data = _read_metadata(strict=True)
    if not data and not FILE.exists():
        return False
    legacy = str(data.get("tmdb_api_key") or "").strip()
    if not legacy:
        return False

    try:
        ensure_secure_backend(keyring)
    except SecureCredentialBackendError as exc:
        raise SettingsStorageError(
            f"Secure credential storage is unavailable ({type(exc).__name__})."
        ) from exc

    previous = _UNKNOWN
    staged = False
    try:
        previous = keyring.get_password(SERVICE, TMDB_KEY)
        if not previous:
            keyring.set_password(SERVICE, TMDB_KEY, legacy)
            # Register rollback immediately after a successful write. The
            # subsequent read-back can fail or return a mismatched value even
            # though the credential was already changed.
            staged = True
            if keyring.get_password(SERVICE, TMDB_KEY) != legacy:
                raise SettingsStorageError("Windows Credential Manager did not verify the migrated TMDb API key.")
        clean = dict(data)
        clean.pop("tmdb_api_key", None)
        _write_atomic(clean)
        return True
    except Exception as exc:
        if staged:
            _restore_secret(previous)
        if isinstance(exc, SettingsStorageError):
            raise
        raise SettingsStorageError(
            f"Could not migrate legacy settings securely ({type(exc).__name__})."
        ) from exc


def load_settings():
    try:
        migrate_legacy_settings_secret()
    except SettingsStorageError as exc:
        log.warning("Could not migrate legacy settings credential: %s", type(exc).__name__)
    data = _read_metadata(strict=False)
    try:
        ensure_secure_backend(keyring)
        data["tmdb_api_key"] = keyring.get_password(SERVICE, TMDB_KEY) or ""
    except Exception:
        data["tmdb_api_key"] = ""
    return data


def _write_atomic(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(FILE.suffix + ".tmp")
    try:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, FILE)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _restore_secret(previous) -> None:
    if previous is _UNKNOWN:
        return
    try:
        if previous is None:
            try:
                keyring.delete_password(SERVICE, TMDB_KEY)
            except Exception:
                pass
        else:
            keyring.set_password(SERVICE, TMDB_KEY, previous)
    except Exception:
        pass


def save_settings(data):
    """Save settings atomically; the TMDb key never falls back to plaintext."""
    plain = dict(data or {})
    secret = str(plain.pop("tmdb_api_key", "") or "").strip()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # Never overwrite an existing corrupt settings file. Validate metadata
    # before changing Credential Manager so a failed save leaves both sources
    # exactly as they were.
    _read_metadata(strict=True)
    try:
        ensure_secure_backend(keyring)
    except SecureCredentialBackendError as exc:
        raise SettingsStorageError(
            f"Secure credential storage is unavailable ({type(exc).__name__})."
        ) from exc

    previous = _UNKNOWN
    try:
        previous = keyring.get_password(SERVICE, TMDB_KEY)
        if secret:
            keyring.set_password(SERVICE, TMDB_KEY, secret)
            if keyring.get_password(SERVICE, TMDB_KEY) != secret:
                raise SettingsStorageError("Windows Credential Manager did not verify the TMDb API key.")
        elif previous is not None:
            keyring.delete_password(SERVICE, TMDB_KEY)
            if keyring.get_password(SERVICE, TMDB_KEY) is not None:
                raise SettingsStorageError("Windows Credential Manager did not remove the TMDb API key.")
    except SettingsStorageError:
        _restore_secret(previous)
        raise
    except Exception as exc:
        _restore_secret(previous)
        raise SettingsStorageError(
            f"Could not store settings securely ({type(exc).__name__})."
        ) from exc

    try:
        _write_atomic(plain)
    except Exception as exc:
        _restore_secret(previous)
        raise SettingsStorageError(
            f"Could not save settings metadata ({type(exc).__name__})."
        ) from exc
