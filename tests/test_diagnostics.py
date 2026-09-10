from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import ultrastalker_desktop.diagnostics as diagnostics


class DatabaseIntegrityTests(unittest.TestCase):
    def test_missing_user_database_is_valid_first_run_state(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "missing.db"
            with patch.object(diagnostics.storage_database, "DB", missing):
                ok, status, error = diagnostics._check_user_database_integrity()
        self.assertTrue(ok)
        self.assertEqual(status, "not_created")
        self.assertIsNone(error)

    def test_valid_user_database_passes_quick_check(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "user.db"
            c = sqlite3.connect(path)
            c.execute("create table t(x integer)")
            c.execute("insert into t values (1)")
            c.commit(); c.close()
            with patch.object(diagnostics.storage_database, "DB", path):
                ok, status, error = diagnostics._check_user_database_integrity()
        self.assertTrue(ok)
        self.assertEqual(status, "ok")
        self.assertIsNone(error)

    def test_corrupt_user_database_fails_with_sanitized_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "broken.db"
            path.write_bytes(b"not a sqlite database at C:\\Users\\Alice?token=secret")
            with patch.object(diagnostics.storage_database, "DB", path):
                ok, status, error = diagnostics._check_user_database_integrity()
        self.assertFalse(ok)
        self.assertEqual(status, "error")
        self.assertIsInstance(error, str)
        self.assertNotIn("Alice", error or "")
        self.assertNotIn("token=secret", error or "")


class DiagnosticsSelfTestTests(unittest.TestCase):
    def test_self_test_reaches_artifact_binding_and_sanitizes_errors(self):
        with tempfile.TemporaryDirectory() as td:
            mpv = Path(td) / 'mpv.exe'
            mpv.write_bytes(b'mpv-test')

            keyring = types.ModuleType('keyring')
            secrets = {}
            keyring.set_password = lambda service, user, value: secrets.__setitem__((service, user), value)
            keyring.get_password = lambda service, user: secrets.get((service, user))
            keyring.delete_password = lambda service, user: secrets.pop((service, user), None)

            qtwidgets = types.ModuleType('PySide6.QtWidgets')
            class FakeApplication:
                _instance = None
                def __init__(self, _args):
                    FakeApplication._instance = self
                @classmethod
                def instance(cls):
                    return cls._instance
                def quit(self):
                    pass
            qtwidgets.QApplication = FakeApplication
            pyside = types.ModuleType('PySide6')
            pyside.QtWidgets = qtwidgets

            result = types.SimpleNamespace(returncode=0)
            modules = {'keyring': keyring, 'PySide6': pyside, 'PySide6.QtWidgets': qtwidgets}
            with patch.dict(sys.modules, modules), \
                 patch.object(diagnostics, 'resource_candidates', return_value=[mpv]), \
                 patch.object(diagnostics.subprocess, 'run', return_value=result):
                passed, report = diagnostics.run_self_test()

            self.assertTrue(passed)
            self.assertTrue(report['checks']['sqlite'])
            self.assertTrue(report['checks']['mpv'])
            self.assertTrue(report['checks']['credential_manager'])
            self.assertTrue(report['checks']['qt_runtime'])
            self.assertEqual(
                report['artifacts']['mpv_sha256'],
                hashlib.sha256(b'mpv-test').hexdigest(),
            )


    def test_credential_probe_is_cleaned_even_when_read_fails(self):
        with tempfile.TemporaryDirectory() as td:
            mpv = Path(td) / 'mpv.exe'
            mpv.write_bytes(b'mpv-test')

            keyring = types.ModuleType('keyring')
            deleted = []
            keyring.set_password = lambda service, user, value: None
            def broken_get(service, user):
                raise RuntimeError('credential read failed')
            keyring.get_password = broken_get
            keyring.delete_password = lambda service, user: deleted.append((service, user))

            qtwidgets = types.ModuleType('PySide6.QtWidgets')
            class FakeApplication:
                _instance = None
                def __init__(self, _args):
                    FakeApplication._instance = self
                @classmethod
                def instance(cls):
                    return cls._instance
                def quit(self):
                    pass
            qtwidgets.QApplication = FakeApplication
            pyside = types.ModuleType('PySide6')
            pyside.QtWidgets = qtwidgets

            result = types.SimpleNamespace(returncode=0)
            modules = {'keyring': keyring, 'PySide6': pyside, 'PySide6.QtWidgets': qtwidgets}
            with patch.dict(sys.modules, modules), \
                 patch.object(diagnostics, 'resource_candidates', return_value=[mpv]), \
                 patch.object(diagnostics.subprocess, 'run', return_value=result):
                passed, report = diagnostics.run_self_test()

            self.assertFalse(passed)
            self.assertFalse(report['checks']['credential_manager'])
            self.assertEqual(len(deleted), 1)
            self.assertEqual(deleted[0][0], 'UltraStalkerDesktop-SelfTest')


    def test_self_test_fails_when_credential_probe_cannot_be_cleaned_up(self):
        with tempfile.TemporaryDirectory() as td:
            mpv = Path(td) / 'mpv.exe'
            mpv.write_bytes(b'mpv-test')

            keyring = types.ModuleType('keyring')
            secrets = {}
            keyring.set_password = lambda service, user, value: secrets.__setitem__((service, user), value)
            keyring.get_password = lambda service, user: secrets.get((service, user))
            def broken_delete(service, user):
                raise RuntimeError('credential cleanup failed')
            keyring.delete_password = broken_delete

            qtwidgets = types.ModuleType('PySide6.QtWidgets')
            class FakeApplication:
                _instance = None
                def __init__(self, _args): FakeApplication._instance = self
                @classmethod
                def instance(cls): return cls._instance
                def quit(self): pass
            qtwidgets.QApplication = FakeApplication
            pyside = types.ModuleType('PySide6'); pyside.QtWidgets = qtwidgets
            modules = {'keyring': keyring, 'PySide6': pyside, 'PySide6.QtWidgets': qtwidgets}
            result = types.SimpleNamespace(returncode=0)

            with patch.dict(sys.modules, modules), \
                 patch.object(diagnostics, 'resource_candidates', return_value=[mpv]), \
                 patch.object(diagnostics.subprocess, 'run', return_value=result), \
                 patch.object(diagnostics, 'verify_release_integrity', return_value={'status': 'development', 'checked': 0, 'mismatches': []}):
                passed, report = diagnostics.run_self_test()

            self.assertFalse(passed)
            self.assertTrue(report['checks']['credential_manager'])
            self.assertFalse(report['checks']['credential_cleanup'])
            self.assertIn('cleanup failed', report['checks']['credential_cleanup_error'])

    def test_windows_self_test_uses_real_qt_windows_platform(self):
        with tempfile.TemporaryDirectory() as td:
            mpv = Path(td) / 'mpv.exe'
            mpv.write_bytes(b'mpv-test')

            keyring = types.ModuleType('keyring')
            secrets = {}
            keyring.set_password = lambda service, user, value: secrets.__setitem__((service, user), value)
            keyring.get_password = lambda service, user: secrets.get((service, user))
            keyring.delete_password = lambda service, user: secrets.pop((service, user), None)

            qtwidgets = types.ModuleType('PySide6.QtWidgets')
            class FakeApplication:
                _instance = None
                def __init__(self, _args):
                    FakeApplication._instance = self
                @classmethod
                def instance(cls):
                    return cls._instance
                def quit(self):
                    pass
            qtwidgets.QApplication = FakeApplication
            pyside = types.ModuleType('PySide6')
            pyside.QtWidgets = qtwidgets

            result = types.SimpleNamespace(returncode=0)
            backends = types.ModuleType('keyring.backends')
            windows = types.ModuleType('keyring.backends.Windows')
            class WinVaultKeyring:
                pass
            WinVaultKeyring.__module__ = 'keyring.backends.Windows'
            windows.WinVaultKeyring = WinVaultKeyring
            active_backend = WinVaultKeyring()
            keyring.get_keyring = lambda: active_backend
            keyring.set_keyring = lambda backend: None
            modules = {
                'keyring': keyring,
                'keyring.backends': backends,
                'keyring.backends.Windows': windows,
                'PySide6': pyside,
                'PySide6.QtWidgets': qtwidgets,
            }
            old_platform = diagnostics.sys.platform
            old_qpa = diagnostics.os.environ.get('QT_QPA_PLATFORM')
            try:
                diagnostics.sys.platform = 'win32'
                with patch.dict(sys.modules, modules), \
                     patch.object(diagnostics, 'resource_candidates', return_value=[mpv]), \
                     patch.object(diagnostics.subprocess, 'run', return_value=result):
                    passed, report = diagnostics.run_self_test()
                self.assertTrue(passed)
                self.assertEqual(report['checks']['qt_platform'], 'windows')
                self.assertEqual(report['checks']['runtime_platform'], 'win32')
                self.assertEqual(report['checks']['python_bits'], 64)
                self.assertEqual(diagnostics.os.environ.get('QT_QPA_PLATFORM'), 'windows')
            finally:
                diagnostics.sys.platform = old_platform
                if old_qpa is None:
                    diagnostics.os.environ.pop('QT_QPA_PLATFORM', None)
                else:
                    diagnostics.os.environ['QT_QPA_PLATFORM'] = old_qpa

    def test_installed_self_test_requires_release_integrity_when_requested(self):
        with tempfile.TemporaryDirectory() as td:
            mpv = Path(td) / 'mpv.exe'
            mpv.write_bytes(b'mpv-test')

            keyring = types.ModuleType('keyring')
            secrets = {}
            keyring.set_password = lambda service, user, value: secrets.__setitem__((service, user), value)
            keyring.get_password = lambda service, user: secrets.get((service, user))
            keyring.delete_password = lambda service, user: secrets.pop((service, user), None)

            qtwidgets = types.ModuleType('PySide6.QtWidgets')
            class FakeApplication:
                _instance = None
                def __init__(self, _args): FakeApplication._instance = self
                @classmethod
                def instance(cls): return cls._instance
                def quit(self): pass
            qtwidgets.QApplication = FakeApplication
            pyside = types.ModuleType('PySide6'); pyside.QtWidgets = qtwidgets
            modules = {'keyring': keyring, 'PySide6': pyside, 'PySide6.QtWidgets': qtwidgets}
            result = types.SimpleNamespace(returncode=0)

            with patch.dict(sys.modules, modules), \
                 patch.object(diagnostics, 'resource_candidates', return_value=[mpv]), \
                 patch.object(diagnostics.subprocess, 'run', return_value=result), \
                 patch.object(diagnostics, 'verify_release_integrity', return_value={'status': 'ok', 'checked': 6, 'mismatches': [], 'build_id': 'BUILD-1'}):
                passed, report = diagnostics.run_self_test(require_release_integrity=True)

            self.assertTrue(passed)
            self.assertTrue(report['checks']['release_integrity'])
            self.assertEqual(report['release_integrity']['status'], 'ok')
            self.assertEqual(report['release_integrity']['build_id'], 'BUILD-1')

    def test_installed_self_test_fails_on_release_integrity_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            mpv = Path(td) / 'mpv.exe'
            mpv.write_bytes(b'mpv-test')

            keyring = types.ModuleType('keyring')
            secrets = {}
            keyring.set_password = lambda service, user, value: secrets.__setitem__((service, user), value)
            keyring.get_password = lambda service, user: secrets.get((service, user))
            keyring.delete_password = lambda service, user: secrets.pop((service, user), None)

            qtwidgets = types.ModuleType('PySide6.QtWidgets')
            class FakeApplication:
                _instance = None
                def __init__(self, _args): FakeApplication._instance = self
                @classmethod
                def instance(cls): return cls._instance
                def quit(self): pass
            qtwidgets.QApplication = FakeApplication
            pyside = types.ModuleType('PySide6'); pyside.QtWidgets = qtwidgets
            modules = {'keyring': keyring, 'PySide6': pyside, 'PySide6.QtWidgets': qtwidgets}
            result = types.SimpleNamespace(returncode=0)

            with patch.dict(sys.modules, modules), \
                 patch.object(diagnostics, 'resource_candidates', return_value=[mpv]), \
                 patch.object(diagnostics.subprocess, 'run', return_value=result), \
                 patch.object(diagnostics, 'verify_release_integrity', return_value={'status': 'mismatch', 'checked': 6, 'mismatches': ['mpv.exe'], 'build_id': 'BUILD-1'}):
                passed, report = diagnostics.run_self_test(require_release_integrity=True)

            self.assertFalse(passed)
            self.assertFalse(report['checks']['release_integrity'])
            self.assertEqual(report['release_integrity']['mismatches'], ['mpv.exe'])

    def test_build_and_runtime_self_test_reports_are_separated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe_dir = root / 'install'
            diag_dir = root / 'local' / 'diagnostics'
            exe_dir.mkdir(parents=True)
            report = {'passed': True, 'checks': {'sqlite': True}}
            with patch.object(diagnostics, 'executable_dir', return_value=exe_dir), \
                 patch.object(diagnostics, 'diagnostics_dir', return_value=diag_dir):
                build_path = diagnostics.write_build_self_test_report(report)
                runtime_path = diagnostics.write_runtime_self_test_report(report)

            self.assertEqual(build_path, exe_dir / 'SELF_TEST.json')
            self.assertEqual(runtime_path, diag_dir / 'SELF_TEST.json')
            self.assertTrue(build_path.is_file())
            self.assertTrue(runtime_path.is_file())
            self.assertEqual(json.loads(build_path.read_text(encoding='utf-8'))['report_kind'], 'build')
            self.assertEqual(json.loads(runtime_path.read_text(encoding='utf-8'))['report_kind'], 'runtime')
            self.assertNotEqual(build_path.resolve(), runtime_path.resolve())

    def test_backward_writer_alias_uses_safe_runtime_location(self):
        with tempfile.TemporaryDirectory() as td:
            diag_dir = Path(td) / 'diagnostics'
            report = {'passed': True}
            with patch.object(diagnostics, 'diagnostics_dir', return_value=diag_dir):
                path = diagnostics.write_self_test_report(report)
            self.assertEqual(path, diag_dir / 'SELF_TEST.json')



if __name__ == '__main__':
    unittest.main()
