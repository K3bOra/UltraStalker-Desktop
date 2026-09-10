from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
import hashlib
from pathlib import Path
from unittest.mock import patch

import ultrastalker_desktop.support_bundle as support


class SupportBundleTests(unittest.TestCase):
    def test_sanitizer_redacts_urls_mac_and_tokens(self):
        text = (
            'GET http://user:pass@example.test/live/u/p/1.ts?token=abc '\
            'MAC 00:1A:79:AA:BB:CC Authorization: BearerSecret password=hunter2 '
            'username=myuser login:otheruser contact=user@example.test'
        )
        out = support._sanitize_text(text)
        self.assertNotIn('example.test', out)
        self.assertNotIn('00:1A:79:AA:BB:CC', out)
        self.assertNotIn('BearerSecret', out)
        self.assertNotIn('hunter2', out)
        self.assertNotIn('myuser', out)
        self.assertNotIn('otheruser', out)
        self.assertNotIn('user@example.test', out)

    def test_sanitizer_redacts_api_key_inside_exception_url(self):
        raw = "HTTPSConnectionPool(host='api.themoviedb.org'): GET https://api.themoviedb.org/3/search/movie?api_key=super-secret&query=test"
        clean = support._sanitize_text(raw)
        self.assertNotIn('super-secret', clean)
        self.assertNotIn('api_key=', clean.lower())
        self.assertIn('<redacted-url>', clean)

    def test_sanitizer_redacts_username_assignments_and_emails(self):
        out = support._sanitize_text('username=customer login:agent email customer@example.test')
        self.assertNotIn('customer', out)
        self.assertNotIn('agent', out)
        self.assertNotIn('customer@example.test', out)


    def test_sanitizer_redacts_local_account_names_in_paths(self):
        win = support.sanitize_text(r"failed at C:\\Users\\Mai\\AppData\\Local\\x.log")
        unix = support.sanitize_text("failed at /home/mai/.cache/x.log")
        self.assertNotIn("Mai", win)
        self.assertNotIn("/home/mai/", unix)
        self.assertIn("<redacted-user>", win)
        self.assertIn("<redacted-user>", unix)

    def test_bundle_excludes_profiles_settings_and_database(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / 'logs'; logs.mkdir()
            exe = root / 'exe'; exe.mkdir()
            data = root / 'data'; data.mkdir()
            roaming = root / 'roaming'; roaming.mkdir()
            diagnostics = root / 'diagnostics'; diagnostics.mkdir()
            (logs / 'ultrastalker-desktop.log').write_text(
                'failed http://user:secret@example.test/x?token=abc 00:1A:79:AA:BB:CC',
                encoding='utf-8',
            )
            # Deliberately create sensitive files beside the safe inputs. They
            # must never be swept into the diagnostics ZIP.
            (data / 'profiles.json').write_text('supersecret', encoding='utf-8')
            (data / 'settings.json').write_text('api-secret', encoding='utf-8')
            (data / 'ultrastalker.db').write_bytes(b'secret-db')
            (exe / 'SELF_TEST.json').write_text(json.dumps({'passed': True, 'kind': 'build'}), encoding='utf-8')
            (diagnostics / 'SELF_TEST.json').write_text(json.dumps({'passed': True, 'kind': 'runtime'}), encoding='utf-8')
            (roaming / 'profiles_corruption.json').write_text(json.dumps({'file':'profiles.json','sha256':'a'*64,'size':12,'error_type':'JSONDecodeError'}), encoding='utf-8')
            (roaming / 'settings_corruption.json').write_text(json.dumps({'file':'settings.json','sha256':'b'*64,'size':8,'error_type':'JSONDecodeError'}), encoding='utf-8')

            with patch.object(support, 'local_data_dir', return_value=data), \
                 patch.object(support, 'app_data_dir', return_value=roaming), \
                 patch.object(support, 'diagnostics_dir', return_value=diagnostics), \
                 patch.object(support, 'log_dir', return_value=logs), \
                 patch.object(support, 'executable_dir', return_value=exe):
                bundle = support.create_support_bundle()

            with zipfile.ZipFile(bundle) as zf:
                names = set(zf.namelist())
                self.assertNotIn('profiles.json', names)
                self.assertNotIn('settings.json', names)
                self.assertNotIn('ultrastalker.db', names)
                self.assertIn('BUILD_SELF_TEST.json', names)
                self.assertIn('RUNTIME_SELF_TEST.json', names)
                self.assertIn('profiles_corruption.json', names)
                self.assertIn('settings_corruption.json', names)
                self.assertNotIn('SELF_TEST.json', names)
                log = zf.read('ultrastalker-desktop.log').decode('utf-8')
                self.assertNotIn('example.test', log)
                self.assertNotIn('00:1A:79:AA:BB:CC', log)
                self.assertNotIn('secret', log)

    def test_runtime_report_includes_sanitized_database_integrity(self):
        leaked = r'C:\Users\Alice\broken.db?token=secret'
        with patch.object(support.storage_database, 'integrity_check', return_value=(False, 'error', leaked)), \
             patch.object(support, 'verify_release_integrity', return_value={'status': 'development', 'mismatches': []}):
            report = support._runtime_report()
        self.assertFalse(report['database_integrity']['passed'])
        self.assertEqual(report['database_integrity']['status'], 'error')
        error = report['database_integrity']['error']
        self.assertNotIn('Alice', error)
        self.assertNotIn('token=secret', error)

    def test_support_bundle_names_are_unique_within_same_second(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            diagnostics = root / 'diagnostics'; diagnostics.mkdir()
            logs = root / 'logs'; logs.mkdir()
            exe = root / 'exe'; exe.mkdir()
            roaming = root / 'roaming'; roaming.mkdir()
            with patch.object(support, 'diagnostics_dir', return_value=diagnostics), \
                 patch.object(support, 'log_dir', return_value=logs), \
                 patch.object(support, 'executable_dir', return_value=exe), \
                 patch.object(support, 'app_data_dir', return_value=roaming), \
                 patch.object(support, 'verify_release_integrity', return_value={'status':'development','mismatches':[]}):
                first = support.create_support_bundle()
                second = support.create_support_bundle()
            self.assertNotEqual(first.name, second.name)
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())

    def test_release_integrity_detects_critical_file_tamper(self):
        from ultrastalker_desktop.runtime import verify_release_integrity
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app = root / 'UltraStalkerDesktop.exe'; app.write_bytes(b'app')
            mpv = root / 'mpv.exe'; mpv.write_bytes(b'mpv')
            hashes = {
                'UltraStalkerDesktop.exe': hashlib.sha256(b'app').hexdigest(),
                'mpv.exe': hashlib.sha256(b'mpv').hexdigest(),
            }
            (root / 'RELEASE_SHA256.json').write_text(json.dumps(hashes), encoding='utf-8')
            files = dict(hashes)
            files['RELEASE_SHA256.json'] = hashlib.sha256((root / 'RELEASE_SHA256.json').read_bytes()).hexdigest()
            (root / 'provenance.json').write_text(json.dumps({'build_id':'TEST','files':files}), encoding='utf-8')
            report = verify_release_integrity(root, app)
            self.assertEqual(report['status'], 'ok')
            mpv.write_bytes(b'tampered')
            report = verify_release_integrity(root, app)
            self.assertEqual(report['status'], 'mismatch')
            self.assertIn('mpv.exe', report['mismatches'])

    def test_release_integrity_is_development_without_provenance(self):
        from ultrastalker_desktop.runtime import verify_release_integrity
        with tempfile.TemporaryDirectory() as td:
            report = verify_release_integrity(Path(td))
            self.assertEqual(report['status'], 'development')
            self.assertEqual(report['mismatches'], [])


if __name__ == '__main__':
    unittest.main()
