from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Local\UltraStalkerDesktop-8B1EF58E-7E5F-4D2F-9BC5-7A5D0C1E2026"


def _windows_mutex_api():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    create_mutex.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    return create_mutex, close_handle, ctypes.get_last_error


class SingleInstanceGuard:
    """Per-Windows-session guard for mutable local application state.

    Profiles/settings are atomic files, but two GUI processes can still perform
    stale read/modify/write cycles against them.  A named Windows mutex prevents
    that class of lost update without affecting explicit ``--self-test`` modes.
    Non-Windows development runs remain unrestricted.
    """

    def __init__(self, name: str = MUTEX_NAME, *, platform_name: str | None = None):
        self.name = name
        self.platform_name = platform_name or os.name
        self._handle = None
        self._close_handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        if self.platform_name != "nt":
            # Development convenience; the production requirement is Windows.
            self._handle = True
            return True

        create_mutex, close_handle, get_last_error = _windows_mutex_api()
        handle = create_mutex(None, False, self.name)
        error = int(get_last_error() or 0)
        if not handle:
            raise OSError(error, "Could not create the Ultra Stalker single-instance mutex")
        if error == ERROR_ALREADY_EXISTS:
            close_handle(handle)
            return False
        self._handle = handle
        self._close_handle = close_handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        close_handle = self._close_handle
        self._close_handle = None
        if self.platform_name == "nt" and handle is not None and close_handle is not None:
            try:
                close_handle(handle)
            except Exception:
                # Process exit releases the kernel handle anyway; release remains
                # best-effort and must never mask the application's exit code.
                pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Ultra Stalker Desktop is already running")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
