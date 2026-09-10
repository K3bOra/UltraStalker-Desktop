from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from ultrastalker_desktop.storage import credentials


class SecureBackendTests(unittest.TestCase):
    def _windows_modules(self):
        backends = types.ModuleType('keyring.backends')
        windows = types.ModuleType('keyring.backends.Windows')

        class WinVaultKeyring:
            pass

        WinVaultKeyring.__module__ = 'keyring.backends.Windows'
        windows.WinVaultKeyring = WinVaultKeyring
        return backends, windows, WinVaultKeyring

    def test_windows_forces_win_vault_backend(self):
        backends, windows, WinVaultKeyring = self._windows_modules()
        insecure = type('PlaintextKeyring', (), {})()

        class FakeKeyring:
            def __init__(self): self.backend = insecure
            def get_keyring(self): return self.backend
            def set_keyring(self, backend): self.backend = backend

        fake = FakeKeyring()
        with patch.object(credentials.sys, 'platform', 'win32'), \
             patch.dict(sys.modules, {'keyring.backends': backends, 'keyring.backends.Windows': windows}):
            name = credentials.ensure_secure_backend(fake)
        self.assertIsInstance(fake.backend, WinVaultKeyring)
        self.assertEqual(name, 'keyring.backends.Windows.WinVaultKeyring')

    def test_windows_rejects_missing_backend_api(self):
        backends, windows, _ = self._windows_modules()
        with patch.object(credentials.sys, 'platform', 'win32'), \
             patch.dict(sys.modules, {'keyring.backends': backends, 'keyring.backends.Windows': windows}):
            with self.assertRaises(credentials.SecureCredentialBackendError):
                credentials.ensure_secure_backend(types.SimpleNamespace())


if __name__ == '__main__':
    unittest.main()
