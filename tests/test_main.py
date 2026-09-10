from __future__ import annotations

import os
import sys
import tempfile
import unittest
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import ultrastalker_desktop.main as app_main


class MainSelfTestModeTests(unittest.TestCase):
    def _build_marker(self, root: Path, nonce: str) -> Path:
        marker = root / app_main.BUILD_SELF_TEST_MARKER
        marker.write_text(nonce, encoding="ascii")
        return marker

    def test_build_self_test_is_refused_without_release_marker(self):
        env = dict(os.environ)
        env.pop("ULTRASTALKER_RELEASE_BUILD_SELF_TEST", None)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, env, clear=True), \
             patch.object(app_main, "executable_dir", return_value=Path(tmp)), \
             patch.object(sys, "argv", ["UltraStalkerDesktop.exe", "--self-test-build"]), \
             patch.object(app_main, "_self_test") as run:
            code = app_main.main()
        self.assertEqual(code, 3)
        run.assert_not_called()

    def test_build_self_test_is_refused_with_env_only(self):
        nonce = "a" * 64
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"ULTRASTALKER_RELEASE_BUILD_SELF_TEST": nonce}, clear=False), \
             patch.object(app_main, "executable_dir", return_value=Path(tmp)), \
             patch.object(sys, "argv", ["UltraStalkerDesktop.exe", "--self-test-build"]), \
             patch.object(app_main, "_self_test") as run:
            code = app_main.main()
        self.assertEqual(code, 3)
        run.assert_not_called()

    def test_build_self_test_is_refused_with_mismatched_nonce(self):
        nonce = "a" * 64
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_marker(root, "b" * 64)
            with patch.dict(os.environ, {"ULTRASTALKER_RELEASE_BUILD_SELF_TEST": nonce}, clear=False), \
                 patch.object(app_main, "executable_dir", return_value=root), \
                 patch.object(sys, "argv", ["UltraStalkerDesktop.exe", "--self-test-build"]), \
                 patch.object(app_main, "_self_test") as run:
                code = app_main.main()
        self.assertEqual(code, 3)
        run.assert_not_called()

    def test_build_self_test_runs_only_with_matching_release_nonce(self):
        nonce = "0123456789abcdef" * 4
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_marker(root, nonce)
            with patch.dict(os.environ, {"ULTRASTALKER_RELEASE_BUILD_SELF_TEST": nonce}, clear=False), \
                 patch.object(app_main, "executable_dir", return_value=root), \
                 patch.object(sys, "argv", ["UltraStalkerDesktop.exe", "--self-test-build"]), \
                 patch.object(app_main, "_self_test", return_value=0) as run:
                code = app_main.main()
        self.assertEqual(code, 0)
        run.assert_called_once_with(build_report=True)

    def test_normal_self_test_always_uses_runtime_report(self):
        with patch.object(sys, "argv", ["UltraStalkerDesktop.exe", "--self-test"]), \
             patch.object(app_main, "_self_test", return_value=0) as run:
            code = app_main.main()
        self.assertEqual(code, 0)
        run.assert_called_once_with(build_report=False)

    def test_installed_runtime_self_test_requests_full_release_integrity(self):
        import ultrastalker_desktop.diagnostics as diagnostics
        report = {
            'passed': True,
            'checks': {
                'sqlite': True, 'mpv': True, 'credential_manager': True,
                'qt_runtime': True, 'release_integrity': True,
            },
            'release_integrity': {'status': 'ok', 'full': True},
        }
        with patch.object(diagnostics, 'run_self_test', return_value=(True, report.copy())) as run, \
             patch.object(diagnostics, 'write_runtime_self_test_report') as write_runtime, \
             patch.object(sys, 'frozen', True, create=True):
            code = app_main._self_test(build_report=False)
        self.assertEqual(code, 0)
        run.assert_called_once_with(require_release_integrity=True)
        write_runtime.assert_called_once()
        self.assertTrue(write_runtime.call_args.args[0]['release_integrity']['full'])

    def test_build_self_test_does_not_require_pre_fingerprint_provenance(self):
        import ultrastalker_desktop.diagnostics as diagnostics
        report = {
            'passed': True,
            'checks': {
                'sqlite': True, 'mpv': True, 'credential_manager': True,
                'qt_runtime': True, 'release_integrity': True,
            },
            'release_integrity': {'status': 'development', 'full': False},
        }
        with patch.object(diagnostics, 'run_self_test', return_value=(True, report.copy())) as run, \
             patch.object(diagnostics, 'write_build_self_test_report') as write_build:
            code = app_main._self_test(build_report=True)
        self.assertEqual(code, 0)
        run.assert_called_once_with(require_release_integrity=False)
        write_build.assert_called_once()



class MainSingleInstanceIntegrationTests(unittest.TestCase):
    def _fake_qt_modules(self):
        qtwidgets = types.ModuleType("PySide6.QtWidgets")
        app = MagicMock(name="QApplicationInstance")
        app.exec.return_value = 27
        qapp_ctor = MagicMock(return_value=app)
        messages = types.SimpleNamespace(
            information=MagicMock(),
            critical=MagicMock(),
        )
        qtwidgets.QApplication = qapp_ctor
        qtwidgets.QMessageBox = messages
        pyside = types.ModuleType("PySide6")
        pyside.QtWidgets = qtwidgets

        window_module = types.ModuleType("ultrastalker_desktop.ui.main_window")
        window = MagicMock(name="UltraStalkerWindowInstance")
        window_ctor = MagicMock(return_value=window)
        window_module.UltraStalkerWindow = window_ctor
        return {
            "PySide6": pyside,
            "PySide6.QtWidgets": qtwidgets,
            "ultrastalker_desktop.ui.main_window": window_module,
        }, app, qapp_ctor, messages, window, window_ctor

    def test_duplicate_gui_instance_exits_before_logging_or_window_creation(self):
        modules, app, _qapp, messages, _window, window_ctor = self._fake_qt_modules()
        guard = MagicMock()
        guard.acquire.return_value = False
        with patch.dict(sys.modules, modules), \
             patch.object(sys, "argv", ["UltraStalkerDesktop.exe"]), \
             patch.object(app_main, "SingleInstanceGuard", return_value=guard), \
             patch.object(app_main, "configure_logging") as logging_setup, \
             patch.object(app_main, "_install_exception_hook") as exception_hook:
            code = app_main.main()
        self.assertEqual(code, 0)
        messages.information.assert_called_once()
        logging_setup.assert_not_called()
        exception_hook.assert_not_called()
        window_ctor.assert_not_called()
        app.exec.assert_not_called()
        guard.release.assert_not_called()

    def test_mutex_failure_is_fail_closed_before_runtime_writes(self):
        modules, app, _qapp, messages, _window, window_ctor = self._fake_qt_modules()
        guard = MagicMock()
        guard.acquire.side_effect = OSError(5, "denied")
        with patch.dict(sys.modules, modules), \
             patch.object(sys, "argv", ["UltraStalkerDesktop.exe"]), \
             patch.object(app_main, "SingleInstanceGuard", return_value=guard), \
             patch.object(app_main, "configure_logging") as logging_setup:
            code = app_main.main()
        self.assertEqual(code, 4)
        messages.critical.assert_called_once()
        logging_setup.assert_not_called()
        window_ctor.assert_not_called()
        app.exec.assert_not_called()

    def test_owned_gui_instance_releases_mutex_after_event_loop(self):
        modules, app, _qapp, messages, window, window_ctor = self._fake_qt_modules()
        guard = MagicMock()
        guard.acquire.return_value = True
        with patch.dict(sys.modules, modules), \
             patch.object(sys, "argv", ["UltraStalkerDesktop.exe"]), \
             patch.object(app_main, "SingleInstanceGuard", return_value=guard), \
             patch.object(app_main, "configure_logging") as logging_setup, \
             patch.object(app_main, "_install_exception_hook") as exception_hook:
            code = app_main.main()
        self.assertEqual(code, 27)
        logging_setup.assert_called_once()
        exception_hook.assert_called_once()
        window_ctor.assert_called_once()
        window.show.assert_called_once()
        app.exec.assert_called_once()
        guard.release.assert_called_once()
        messages.information.assert_not_called()

    def test_mutex_is_released_if_window_construction_fails(self):
        modules, _app, _qapp, _messages, _window, window_ctor = self._fake_qt_modules()
        window_ctor.side_effect = RuntimeError("ui init failed")
        guard = MagicMock()
        guard.acquire.return_value = True
        with patch.dict(sys.modules, modules), \
             patch.object(sys, "argv", ["UltraStalkerDesktop.exe"]), \
             patch.object(app_main, "SingleInstanceGuard", return_value=guard), \
             patch.object(app_main, "configure_logging"), \
             patch.object(app_main, "_install_exception_hook"):
            with self.assertRaises(RuntimeError):
                app_main.main()
        guard.release.assert_called_once()



if __name__ == "__main__":
    unittest.main()
