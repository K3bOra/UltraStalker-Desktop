from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from logging.handlers import RotatingFileHandler

from ultrastalker_desktop import runtime


class RuntimePathTests(unittest.TestCase):
    def test_frozen_executable_dir_is_exe_parent_not_working_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            install = root / 'Program Files' / 'Ultra Stalker Desktop'
            cwd = root / 'Windows' / 'System32'
            install.mkdir(parents=True)
            cwd.mkdir(parents=True)
            exe = install / 'UltraStalkerDesktop.exe'
            exe.write_bytes(b'exe')
            old_cwd = Path.cwd()
            try:
                os.chdir(cwd)
                with patch.object(sys, 'frozen', True, create=True), \
                     patch.object(sys, 'executable', str(exe)):
                    self.assertEqual(runtime.executable_dir(), install.resolve())
            finally:
                os.chdir(old_cwd)

    def test_resource_candidates_prioritize_exe_dir_in_frozen_onedir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            install = root / 'install'
            bundle = install / '_internal'
            cwd = root / 'cwd'
            for p in (install, bundle, cwd):
                p.mkdir(parents=True)
            exe = install / 'UltraStalkerDesktop.exe'
            exe.write_bytes(b'exe')
            old_cwd = Path.cwd()
            try:
                os.chdir(cwd)
                with patch.object(sys, 'frozen', True, create=True), \
                     patch.object(sys, 'executable', str(exe)), \
                     patch.object(sys, '_MEIPASS', str(bundle), create=True):
                    candidates = runtime.resource_candidates('mpv.exe')
            finally:
                os.chdir(old_cwd)
            self.assertEqual(candidates[0], (install / 'mpv.exe').resolve())
            self.assertEqual(candidates[1], (bundle / 'mpv.exe').resolve())
            self.assertEqual(candidates[2], (cwd / 'mpv.exe').resolve())

    def test_resource_candidates_deduplicate_same_bundle_and_exe_dir(self):
        with tempfile.TemporaryDirectory() as td:
            install = Path(td).resolve()
            exe = install / 'UltraStalkerDesktop.exe'
            exe.write_bytes(b'exe')
            old_cwd = Path.cwd()
            try:
                os.chdir(install)
                with patch.object(sys, 'frozen', True, create=True), \
                     patch.object(sys, 'executable', str(exe)), \
                     patch.object(sys, '_MEIPASS', str(install), create=True):
                    candidates = runtime.resource_candidates('mpv.exe')
            finally:
                os.chdir(old_cwd)
            self.assertEqual(candidates, [(install / 'mpv.exe').resolve()])

    def test_release_info_reads_metadata_from_frozen_exe_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            install = root / 'install'
            other = root / 'other'
            install.mkdir()
            other.mkdir()
            exe = install / 'UltraStalkerDesktop.exe'
            exe.write_bytes(b'exe')
            (install / 'provenance.json').write_text(
                json.dumps({'build_id': 'BUILD-123', 'version': '0.1.0'}),
                encoding='utf-8',
            )
            (install / 'FINAL_RELEASE.json').write_text(
                json.dumps({'installer_sha256': 'abc'}), encoding='utf-8'
            )
            old_cwd = Path.cwd()
            try:
                os.chdir(other)
                with patch.object(sys, 'frozen', True, create=True), \
                     patch.object(sys, 'executable', str(exe)):
                    info = runtime.release_info()
            finally:
                os.chdir(old_cwd)
            self.assertEqual(info['build_id'], 'BUILD-123')
            self.assertEqual(info['version'], '0.1.0')
            self.assertEqual(info['installer_sha256'], 'abc')

    def test_diagnostics_dir_uses_local_appdata_and_is_outside_install_dir(self):
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / 'LocalAppData'
            install = Path(td) / 'Install'
            install.mkdir()
            exe = install / 'UltraStalkerDesktop.exe'
            exe.write_bytes(b'exe')
            with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}, clear=False), \
                 patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, 'executable', str(exe)):
                diag = runtime.diagnostics_dir()
                self.assertEqual(diag, local / 'UltraStalker' / 'diagnostics')
                self.assertNotEqual(diag.parent.resolve(), install.resolve())


    def test_full_release_integrity_detects_nested_payload_tamper_and_extra_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            internal = root / '_internal'; internal.mkdir()
            exe = root / 'UltraStalkerDesktop.exe'; exe.write_bytes(b'app')
            mpv = root / 'mpv.exe'; mpv.write_bytes(b'mpv')
            nested = internal / 'Qt6Core.dll'; nested.write_bytes(b'qt-good')
            files = {
                'UltraStalkerDesktop.exe': runtime._sha256_file(exe),
                'mpv.exe': runtime._sha256_file(mpv),
                '_internal/Qt6Core.dll': runtime._sha256_file(nested),
            }
            (root / 'provenance.json').write_text(json.dumps({
                'platform': 'windows-x64', 'build_id': 'BUILD-FULL', 'files': files
            }), encoding='utf-8')

            report = runtime.verify_release_integrity(root, app_exe=exe, full=True)
            self.assertEqual(report['status'], 'ok')
            self.assertTrue(report['full'])
            self.assertEqual(report['checked'], 3)

            nested.write_bytes(b'qt-tampered')
            report = runtime.verify_release_integrity(root, app_exe=exe, full=True)
            self.assertEqual(report['status'], 'mismatch')
            self.assertIn('_internal/Qt6Core.dll', report['mismatches'])

            nested.write_bytes(b'qt-good')
            (internal / 'unexpected.dll').write_bytes(b'extra')
            report = runtime.verify_release_integrity(root, app_exe=exe, full=True)
            self.assertEqual(report['status'], 'mismatch')
            self.assertIn('_internal/unexpected.dll', report['unexpected'])

    def test_full_release_integrity_rejects_expected_file_replaced_by_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            external = root.parent / (root.name + '-external-mpv.bin')
            external.write_bytes(b'mpv')
            try:
                exe = root / 'UltraStalkerDesktop.exe'; exe.write_bytes(b'app')
                link = root / 'mpv.exe'
                try:
                    link.symlink_to(external)
                except OSError:
                    self.skipTest('symlinks unavailable on this platform')
                files = {
                    'UltraStalkerDesktop.exe': runtime._sha256_file(exe),
                    'mpv.exe': hashlib.sha256(b'mpv').hexdigest(),
                }
                (root / 'provenance.json').write_text(json.dumps({'platform':'windows-x64','build_id':'BUILD-LINK','files':files}), encoding='utf-8')
                report = runtime.verify_release_integrity(root, app_exe=exe, full=True)
                self.assertEqual(report['status'], 'mismatch')
                self.assertIn('mpv.exe', report['mismatches'])
            finally:
                try: external.unlink()
                except OSError: pass

    def test_full_release_integrity_prunes_directory_symlink_targets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            external = root.parent / (root.name + '-outside-tree')
            external.mkdir()
            try:
                (external / 'must-not-be-enumerated.bin').write_bytes(b'outside')
                exe = root / 'UltraStalkerDesktop.exe'; exe.write_bytes(b'app')
                files = {'UltraStalkerDesktop.exe': runtime._sha256_file(exe)}
                (root / 'provenance.json').write_text(json.dumps({
                    'platform': 'windows-x64', 'build_id': 'BUILD-DIR-LINK', 'files': files
                }), encoding='utf-8')
                link = root / 'linked-dir'
                try:
                    link.symlink_to(external, target_is_directory=True)
                except OSError:
                    self.skipTest('directory symlinks unavailable on this platform')
                report = runtime.verify_release_integrity(root, app_exe=exe, full=True)
                self.assertEqual(report['status'], 'mismatch')
                self.assertIn('linked-dir', report['unexpected'])
                self.assertFalse(any('must-not-be-enumerated.bin' in x for x in report['unexpected']))
            finally:
                import shutil
                shutil.rmtree(external, ignore_errors=True)

    def test_full_release_integrity_ignores_inno_uninstaller_bookkeeping(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / 'UltraStalkerDesktop.exe'; exe.write_bytes(b'app')
            files = {'UltraStalkerDesktop.exe': runtime._sha256_file(exe)}
            (root / 'provenance.json').write_text(json.dumps({
                'platform': 'windows-x64', 'build_id': 'BUILD-FULL', 'files': files
            }), encoding='utf-8')
            (root / 'unins000.exe').write_bytes(b'uninstaller')
            (root / 'unins000.dat').write_bytes(b'data')
            report = runtime.verify_release_integrity(root, app_exe=exe, full=True)
            self.assertEqual(report['status'], 'ok')
            self.assertEqual(report['unexpected'], [])

    def test_configure_logging_ignores_unrelated_rotating_handler_and_deduplicates_own(self):
        with tempfile.TemporaryDirectory() as td:
            root_dir = Path(td)
            logs = root_dir / 'logs'; logs.mkdir()
            other = RotatingFileHandler(root_dir / 'other.log', maxBytes=1024, backupCount=1, encoding='utf-8')
            root_logger = logging.getLogger()
            before = list(root_logger.handlers)
            root_logger.addHandler(other)
            try:
                with patch.object(runtime, 'log_dir', return_value=logs):
                    path1 = runtime.configure_logging()
                    path2 = runtime.configure_logging()
                ours = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler) and Path(getattr(h,'baseFilename','')).resolve() == path1.resolve()]
                self.assertEqual(path1, path2)
                self.assertEqual(len(ours), 1)
                self.assertIn(other, root_logger.handlers)
            finally:
                for handler in list(root_logger.handlers):
                    if handler not in before:
                        root_logger.removeHandler(handler)
                        try: handler.close()
                        except Exception: pass

    def test_source_provenance_is_reported_as_development_not_installed_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'provenance.json').write_text(
                json.dumps({'platform': 'source', 'files': {}}), encoding='utf-8'
            )
            report = runtime.verify_release_integrity(root)
            self.assertEqual(report['status'], 'development')
            self.assertEqual(report['checked'], 0)



if __name__ == '__main__':
    unittest.main()
