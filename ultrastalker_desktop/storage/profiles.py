from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import keyring
except ModuleNotFoundError:
    from ultrastalker_desktop.storage.credentials import MISSING_KEYRING as keyring

from ultrastalker_desktop.core.models import Profile
from ultrastalker_desktop.storage.credentials import ensure_secure_backend, SecureCredentialBackendError

APP_DIR = Path(os.getenv("APPDATA") or (Path.home() / ".ultrastalker")) / "UltraStalker"
FILE = APP_DIR / "profiles.json"
SERVICE = "UltraStalkerDesktop"
log = logging.getLogger(__name__)
_UNKNOWN = object()


class ProfileStorageError(RuntimeError):
    pass


class ProfileMetadataCorruptError(ProfileStorageError):
    pass


def _password_key(p: Profile) -> str:
    return p.name + "|xtream|" + (p.username or "default")


def _mac_key(p: Profile) -> str:
    return p.name + "|stalker|mac"


def _m3u_key(p: Profile) -> str:
    return p.name + "|m3u|url"


def _endpoint_key(p: Profile) -> str:
    return p.name + "|" + p.source_type + "|endpoint"


_SENSITIVE_ENDPOINT_KEYS = {
    "password", "passwd", "pass", "token", "key", "api_key", "apikey",
    "auth", "authorization", "signature", "sig", "secret", "access_token",
}


def _endpoint_needs_vault(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    candidate = raw if "://" in raw else "http://" + raw
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return False
    if parts.username or parts.password:
        return True
    return any(key.casefold() in _SENSITIVE_ENDPOINT_KEYS for key, _ in parse_qsl(parts.query, keep_blank_values=True))


def _safe_endpoint_metadata(value: str) -> str:
    """Strip credential-bearing URL components while retaining a useful endpoint."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    had_scheme = "://" in raw
    candidate = raw if had_scheme else "http://" + raw
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return raw
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = "[" + host + "]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port:
        host += f":{port}"
    safe_query = urlencode([
        (key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key.casefold() not in _SENSITIVE_ENDPOINT_KEYS
    ], doseq=True)
    clean = urlunsplit((parts.scheme or "http", host, parts.path, safe_query, ""))
    if not had_scheme and clean.startswith("http://"):
        clean = clean[len("http://"): ]
    return clean


def _possible_secret_keys(p: Profile) -> set[str]:
    keys = set()
    primary = _secret_key(p)
    if primary:
        keys.add(primary)
    if p.source_type in ("stalker", "xtream"):
        keys.add(_endpoint_key(p))
    return keys


def _desired_credentials(p: Profile) -> dict[str, str]:
    out = {}
    primary = _secret_key(p)
    value = _credential_value(p)
    if primary and value:
        out[primary] = value
    if p.source_type in ("stalker", "xtream") and _endpoint_needs_vault(p.portal_url):
        out[_endpoint_key(p)] = p.portal_url
    return out


def _secret_key(p: Profile) -> str | None:
    if p.source_type == "stalker":
        return _mac_key(p)
    if p.source_type == "xtream":
        return _password_key(p)
    if p.source_type == "m3u":
        return _m3u_key(p)
    return None



_PROFILE_FIELDS = set(Profile.__dataclass_fields__)


def _profile_from_row(row: dict) -> Profile:
    """Load known profile fields while tolerating metadata from newer/older builds."""
    return Profile(**{key: row.get(key, "") for key in _PROFILE_FIELDS})


def _record_corrupt_metadata(exc: Exception) -> None:
    """Record safe evidence of metadata corruption without copying secrets."""
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
        (APP_DIR / "profiles_corruption.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _read_rows(*, strict: bool = False) -> list[dict]:
    try:
        value = json.loads(FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception as exc:
        _record_corrupt_metadata(exc)
        if strict:
            raise ProfileMetadataCorruptError(
                f"Profile metadata is unreadable ({type(exc).__name__}); original file was left untouched."
            ) from exc
        return []
    if not isinstance(value, list):
        exc = ValueError("profile metadata root is not a list")
        _record_corrupt_metadata(exc)
        if strict:
            raise ProfileMetadataCorruptError("Profile metadata has an invalid structure; original file was left untouched.")
        return []
    invalid = [item for item in value if not isinstance(item, dict)]
    if invalid and strict:
        exc = ValueError("profile metadata contains invalid rows")
        _record_corrupt_metadata(exc)
        raise ProfileMetadataCorruptError("Profile metadata contains invalid entries; original file was left untouched.")
    return [x for x in value if isinstance(x, dict)]


def _legacy_secret(row: dict, profile: Profile) -> str:
    source = (profile.source_type or "").strip().lower()
    if source == "stalker":
        return str(row.get("mac") or "").strip()
    if source == "xtream":
        return str(row.get("password") or "")
    if source == "m3u":
        return str(row.get("m3u_url") or row.get("portal_url") or "").strip()
    return ""


def _scrub_row_secret(row: dict, source_type: str) -> dict:
    clean = dict(row)
    source = (source_type or "").strip().lower()
    clean["password"] = ""
    if source == "stalker":
        clean["mac"] = ""
        clean["portal_url"] = _safe_endpoint_metadata(clean.get("portal_url", ""))
    elif source == "xtream":
        clean["portal_url"] = _safe_endpoint_metadata(clean.get("portal_url", ""))
    elif source == "m3u":
        clean["m3u_url"] = ""
        clean["portal_url"] = ""
    return clean


def migrate_legacy_profile_secrets() -> bool:
    """Move legacy plaintext provider credentials into the secure backend.

    The metadata file is scrubbed only after every newly staged credential has
    been written and read back successfully. Existing secure credentials win
    over legacy plaintext so an upgrade cannot silently roll a credential back.
    Sensitive portal/server URLs are migrated as a separate secure credential.
    """
    rows = _read_rows(strict=True)
    work: list[tuple[int, Profile, dict[str, str]]] = []
    for index, row in enumerate(rows):
        try:
            profile = _profile_from_row(row)
        except Exception:
            continue
        desired: dict[str, str] = {}
        secret = _legacy_secret(row, profile)
        key = _secret_key(profile)
        if secret and key:
            desired[key] = secret
        raw_endpoint = str(row.get("portal_url") or "")
        if profile.source_type in ("stalker", "xtream") and _endpoint_needs_vault(raw_endpoint):
            desired[_endpoint_key(profile)] = raw_endpoint
        if desired:
            work.append((index, profile, desired))
    if not work:
        return False

    ensure_secure_backend(keyring)
    staged: list[tuple[str, object]] = []
    clean_rows = [dict(row) for row in rows]
    try:
        for index, profile, desired in work:
            for key, secret in desired.items():
                previous = keyring.get_password(SERVICE, key)
                # A secure value already present is authoritative. The migration's
                # job in that case is only to remove the obsolete plaintext copy.
                if not previous:
                    keyring.set_password(SERVICE, key, secret)
                    # Register rollback immediately after the write succeeds.
                    # Verification itself can fail, and that must still restore
                    # the pre-migration vault state.
                    staged.append((key, previous))
                    if keyring.get_password(SERVICE, key) != secret:
                        raise ProfileStorageError("Windows Credential Manager did not verify a migrated credential.")
            clean_rows[index] = _scrub_row_secret(clean_rows[index], profile.source_type)
        _write_atomic(clean_rows)
        return True
    except Exception as exc:
        for key, previous in reversed(staged):
            _restore_secret(key, previous)
        if isinstance(exc, ProfileStorageError):
            raise
        raise ProfileStorageError(
            f"Could not migrate legacy profile credentials securely ({type(exc).__name__})."
        ) from exc


def _metadata_profiles(*, strict: bool = True) -> list[Profile]:
    out: list[Profile] = []
    for row in _read_rows(strict=strict):
        try:
            out.append(_profile_from_row(row))
        except Exception:
            continue
    return out



def _fail_closed_profile(p: Profile) -> Profile:
    """Return profile metadata with every provider credential removed.

    This is used whenever the approved credential backend is unavailable or a
    per-profile credential read fails. Legacy JSON may still contain plaintext
    values if migration could not complete, so returning the raw dataclass
    would violate the fail-closed storage contract.
    """
    p.password = ""
    if p.source_type == "stalker":
        p.mac = ""
        p.portal_url = _safe_endpoint_metadata(p.portal_url)
    elif p.source_type == "xtream":
        p.portal_url = _safe_endpoint_metadata(p.portal_url)
    elif p.source_type == "m3u":
        p.m3u_url = ""
        p.portal_url = ""
    return p

def load_profiles() -> list[Profile]:
    out: list[Profile] = []
    backend_available = True
    try:
        migrate_legacy_profile_secrets()
    except (SecureCredentialBackendError, ProfileStorageError) as exc:
        # Keep metadata visible and fail closed on the secret. A later save or
        # successful startup can retry the migration without losing plaintext.
        log.warning("Could not migrate legacy profile credentials: %s", type(exc).__name__)
    
    backend_available = True
    try:
        ensure_secure_backend(keyring)
    except SecureCredentialBackendError:
        # Keep metadata visible so a backend problem can be diagnosed/repaired,
        # but never read provider secrets through an unapproved backend.
        backend_available = False
    for p in _metadata_profiles(strict=False):
        try:
            if not backend_available and p.source_type in ("stalker", "xtream", "m3u"):
                _fail_closed_profile(p)
            elif p.source_type == "stalker":
                p.mac = keyring.get_password(SERVICE, _mac_key(p)) or ""
                p.portal_url = keyring.get_password(SERVICE, _endpoint_key(p)) or p.portal_url
            elif p.source_type == "xtream":
                p.password = keyring.get_password(SERVICE, _password_key(p)) or ""
                p.portal_url = keyring.get_password(SERVICE, _endpoint_key(p)) or p.portal_url
            elif p.source_type == "m3u":
                secret_url = keyring.get_password(SERVICE, _m3u_key(p)) or ""
                p.m3u_url = secret_url
                p.portal_url = secret_url
            out.append(p)
        except Exception:
            # A damaged/unavailable credential backend must not make the whole
            # profile list unreadable, but legacy JSON can still contain
            # plaintext credentials if migration failed. Return metadata only.
            out.append(_fail_closed_profile(p))
    return out


def _safe_rows(profiles: list[Profile]) -> list[dict]:
    rows = []
    for x in profiles:
        d = dict(x.__dict__)
        d["password"] = ""
        if x.source_type == "stalker":
            d["mac"] = ""
            d["portal_url"] = _safe_endpoint_metadata(x.portal_url)
        if x.source_type == "xtream":
            d["portal_url"] = _safe_endpoint_metadata(x.portal_url)
        if x.source_type == "m3u":
            d["m3u_url"] = ""
            d["portal_url"] = ""
        rows.append(d)
    return rows


def _write_atomic(rows: list[dict]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(FILE.suffix + ".tmp")
    data = json.dumps(rows, indent=2, ensure_ascii=False)
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, FILE)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _credential_value(p: Profile) -> str:
    if p.source_type == "stalker":
        return p.mac
    if p.source_type == "xtream":
        return p.password
    if p.source_type == "m3u":
        return p.m3u_url or p.portal_url
    return ""


def _restore_secret(key: str, previous) -> None:
    if previous is _UNKNOWN:
        return
    try:
        if previous is None:
            try:
                keyring.delete_password(SERVICE, key)
            except Exception:
                pass
        else:
            keyring.set_password(SERVICE, key, previous)
    except Exception as exc:
        # Do not persist raw keyring/backend exception text or tracebacks.
        # OS credential errors can contain user/profile paths or backend details.
        log.warning("Could not roll back secure credential entry: %s", type(exc).__name__)


def save_profile(p: Profile) -> None:
    """Persist a profile without plaintext secrets or half-written state."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        ensure_secure_backend(keyring)
    except SecureCredentialBackendError as exc:
        raise ProfileStorageError(
            f"Secure credential storage is unavailable ({type(exc).__name__})."
        ) from exc

    # Upgrade every legacy row before rewriting the shared metadata file.
    # Otherwise saving one profile could scrub another legacy profile's
    # plaintext secret before that secret reached Credential Manager.
    migrate_legacy_profile_secrets()
    old_profiles = _metadata_profiles()
    old_same_name = [x for x in old_profiles if x.name == p.name]
    desired = _desired_credentials(p)
    new_secret = _credential_value(p)

    if p.source_type == "stalker" and not new_secret:
        raise ProfileStorageError("Stalker MAC is empty.")
    if p.source_type == "xtream" and not new_secret:
        raise ProfileStorageError("Xtream password is empty.")
    if p.source_type == "m3u" and not new_secret:
        raise ProfileStorageError("M3U URL is empty.")

    staged: list[tuple[str, object]] = []
    try:
        for key, value in desired.items():
            previous = keyring.get_password(SERVICE, key)
            keyring.set_password(SERVICE, key, value)
            # Register rollback before read-back verification. A backend can
            # accept a write and then fail/mismatch on the subsequent read.
            staged.append((key, previous))
            probe = keyring.get_password(SERVICE, key)
            if probe != value:
                raise ProfileStorageError("Windows Credential Manager did not verify the saved credential.")
    except ProfileStorageError:
        for key, previous in reversed(staged):
            _restore_secret(key, previous)
        raise
    except Exception as exc:
        for key, previous in reversed(staged):
            _restore_secret(key, previous)
        raise ProfileStorageError(
            f"Could not store credentials securely ({type(exc).__name__})."
        ) from exc

    profiles = [x for x in old_profiles if x.name != p.name] + [p]
    try:
        _write_atomic(_safe_rows(profiles))
    except Exception as exc:
        for key, previous in reversed(staged):
            _restore_secret(key, previous)
        raise ProfileStorageError(
            f"Could not save profile metadata ({type(exc).__name__})."
        ) from exc

    # Only after metadata is safely committed do we remove obsolete secrets.
    # Failure here leaves at worst an orphaned credential, never a broken
    # active profile.
    desired_keys = set(desired)
    obsolete = set()
    for old in old_same_name:
        obsolete.update(_possible_secret_keys(old))
    # Also remove a formerly-secure endpoint when the replacement URL no longer
    # contains credential-bearing components.
    obsolete.update(_possible_secret_keys(p) - desired_keys)
    for key in sorted(obsolete - desired_keys):
        try:
            keyring.delete_password(SERVICE, key)
        except Exception:
            log.warning("Could not remove obsolete secure credential entry")


def delete_profile(name: str) -> bool:
    """Delete one saved profile and best-effort remove its secure credential."""
    name = str(name or "").strip()
    if not name:
        return False
    profiles = _metadata_profiles()
    victims = [p for p in profiles if p.name == name]
    if not victims:
        return False

    survivors = [p for p in profiles if p.name != name]
    try:
        _write_atomic(_safe_rows(survivors))
    except Exception as exc:
        raise ProfileStorageError(
            f"Could not delete profile metadata ({type(exc).__name__})."
        ) from exc

    try:
        ensure_secure_backend(keyring)
    except SecureCredentialBackendError:
        # The profile is already removed. Leave any inaccessible credential
        # orphaned rather than touching an unapproved backend.
        return True

    for p in victims:
        for key in _possible_secret_keys(p):
            try:
                keyring.delete_password(SERVICE, key)
            except Exception:
                # Metadata is already safely gone. An inaccessible orphaned
                # secret is preferable to resurrecting a deleted profile.
                log.warning("Could not remove secure credential for deleted profile")
    return True
