from __future__ import annotations

import importlib
import sys
from typing import Any

try:  # Keep source/dev imports usable even when optional runtime deps are absent.
    import keyring as _DEFAULT_KEYRING
except ModuleNotFoundError:  # pragma: no cover - exercised indirectly in dependency-light CI
    _DEFAULT_KEYRING = None


class SecureCredentialBackendError(RuntimeError):
    pass


class _MissingKeyring:
    """Import-safe fail-closed shim used when the optional backend is unavailable."""

    def _raise(self, *args, **kwargs):
        raise SecureCredentialBackendError(
            "The keyring package is unavailable; secure credential storage cannot be used."
        )

    get_password = _raise
    set_password = _raise
    delete_password = _raise
    get_keyring = _raise
    set_keyring = _raise


MISSING_KEYRING = _MissingKeyring()


def keyring_module() -> Any:
    """Return the available keyring module, or a fail-closed shim.

    The lookup is dynamic so unit tests can inject a fake ``keyring`` module
    after this module has already been imported. Packaged Windows releases
    still fail closed when the real dependency is absent.
    """
    module = sys.modules.get("keyring")
    if module is not None:
        return module
    if _DEFAULT_KEYRING is not None:
        return _DEFAULT_KEYRING
    try:
        return importlib.import_module("keyring")
    except ModuleNotFoundError:
        return MISSING_KEYRING


def backend_name(backend) -> str:
    cls = type(backend)
    return f"{cls.__module__}.{cls.__name__}"


def ensure_secure_backend(keyring_module_override=None) -> str:
    """Force the native Windows Credential Manager backend on Windows.

    ``keyring`` allows environment/config overrides. Ultra Stalker Desktop does
    not permit a third-party/plaintext backend for provider credentials. On
    non-Windows development/test hosts, leave backend selection untouched.

    Importing this module remains possible without ``keyring`` so lightweight
    source tests can inject a fake backend. Actual credential operations still
    fail closed if the dependency is missing.
    """
    module = keyring_module_override if keyring_module_override is not None else keyring_module()
    if module is MISSING_KEYRING:
        raise SecureCredentialBackendError(
            "The keyring package is unavailable; secure credential storage cannot be used."
        )

    if not sys.platform.startswith("win"):
        getter = getattr(module, "get_keyring", None)
        if callable(getter):
            try:
                return backend_name(getter())
            except Exception:
                pass
        return "non-windows"

    try:
        from keyring.backends.Windows import WinVaultKeyring

        getter = getattr(module, "get_keyring", None)
        setter = getattr(module, "set_keyring", None)
        if not callable(getter) or not callable(setter):
            raise SecureCredentialBackendError("Windows keyring backend API is unavailable.")

        current = getter()
        if not isinstance(current, WinVaultKeyring):
            # Deliberately override PYTHON_KEYRING_BACKEND/keyringrc choices so
            # provider secrets cannot silently fall back to a third-party or
            # plaintext backend.
            setter(WinVaultKeyring())
            current = getter()
        if not isinstance(current, WinVaultKeyring):
            raise SecureCredentialBackendError("Windows Credential Manager backend could not be selected.")
        return backend_name(current)
    except SecureCredentialBackendError:
        raise
    except Exception as exc:
        raise SecureCredentialBackendError(
            f"Windows Credential Manager backend is unavailable ({type(exc).__name__})."
        ) from exc
