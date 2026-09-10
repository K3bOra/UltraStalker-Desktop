from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

from tools.finalize_release import finalize_release
from tools.release_fingerprint import generate_fingerprint
from tools.release_gate import dist_gate
from tools.path_safety import walk_payload as real_walk_payload
MPV_ARCHIVE_SHA = '4e197f729f5071c6772f35fffd96e0f36e3e8a044bd9479b136bb09b7c6a80ff'
RELEASE_DEPS = 'PySide6==6.11.2\nrequests==2.34.2\nkeyring==25.7.0\npywin32-ctypes==0.2.3\npyinstaller==6.22.2\npackaging==26.3\n'


def add_license_payload(dist: Path) -> None:
    (dist / 'THIRD_PARTY_NOTICES.txt').write_text(
        (ROOT / 'THIRD_PARTY_NOTICES.txt').read_text(encoding='utf-8'), encoding='utf-8'
    )
    license_root = dist / 'licenses'
    license_root.mkdir(parents=True, exist_ok=True)
    for name in ('GPL-2.0.txt', 'GPL-3.0.txt', 'LGPL-2.1.txt', 'LGPL-3.0.txt'):
        shutil.copy2(ROOT / 'licenses' / name, license_root / name)
    python_root = license_root / 'python'
    python_root.mkdir(parents=True, exist_ok=True)
    (python_root / 'PYTHON_RUNTIME_LICENSES.json').write_text(json.dumps({
        'roots': ['PySide6', 'requests', 'keyring'],
        'distributions': [
            {'name': 'PySide6', 'version': '6.9.0', 'license_expression': 'LGPL-3.0-only OR GPL-3.0-only', 'license_metadata': '', 'license_files': []},
            {'name': 'requests', 'version': '2.32.0', 'license_expression': 'Apache-2.0', 'license_metadata': '', 'license_files': []},
            {'name': 'keyring', 'version': '25.0.0', 'license_expression': 'MIT', 'license_metadata': '', 'license_files': []},
            {'name': 'pywin32-ctypes', 'version': '0.2.3', 'license_expression': 'BSD-3-Clause', 'license_metadata': '', 'license_files': []},
        ],
    }), encoding='utf-8')
    python_license = ('CPython test license fixture.\n' * 80).encode('utf-8')
    (license_root / 'PYTHON_LICENSE.txt').write_bytes(python_license)
    (license_root / 'PYTHON_RUNTIME_PROVENANCE.json').write_text(json.dumps({
        'product': 'CPython',
        'version': '3.13.0',
        'implementation': 'CPython',
        'license_file': 'PYTHON_LICENSE.txt',
        'license_sha256': hashlib.sha256(python_license).hexdigest(),
        'source_license_name': 'LICENSE.txt',
    }), encoding='utf-8')




def run_dist_gate(dist: Path) -> tuple[bool, str]:
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            dist_gate(dist.resolve())
        return True, output.getvalue()
    except SystemExit:
        return False, output.getvalue()


def write_smoke_report(dist: Path, installer: Path, **overrides) -> Path:
    provenance_path = dist / 'provenance.json'
    provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
    payload = {
        'product': 'Ultra Stalker Desktop',
        'version': '0.1.0',
        'developer': 'Ahmed L-HadarY',
        'platform': 'windows-x64',
        'passed': True,
        'build_id': provenance['build_id'],
        'installer_sha256': hashlib.sha256(installer.read_bytes()).hexdigest(),
        'portable_provenance_sha256': hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
        'installed_payload_file_count': len(provenance['files']) + 1,
        'installed_payload_verified': True,
        'runtime_self_test_passed': True,
        'runtime_self_test_sha256': hashlib.sha256(b'runtime-self-test').hexdigest(),
        'runtime_release_integrity': 'ok',
        'runtime_database_integrity': 'not_created',
        'payload_immutable_after_runtime_test': True,
        'smoke_registry_isolated': True,
        'production_registry_unchanged': True,
        'smoke_registry_removed': True,
        'upgrade_passed': True,
        'upgrade_user_data_preserved': True,
        'upgrade_stale_runtime_cleanup_passed': True,
        'uninstall_passed': True,
        'uninstall_user_data_preserved': True,
    }
    payload.update(overrides)
    path = installer.parent / 'INSTALLER_SMOKE_TEST.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


class ReleaseToolTests(unittest.TestCase):
    def _fixture(self, root: Path, passed: bool = True):
        dist = root / 'dist'; dist.mkdir()
        release = root / 'release'; release.mkdir()
        (dist / 'UltraStalkerDesktop.exe').write_bytes(b'app-v1')
        (dist / 'mpv.exe').write_bytes(b'mpv-v1')
        (dist / 'SELF_TEST.json').write_text(json.dumps({
            'report_kind': 'build',
            'passed': passed,
            'checks': {
                'sqlite': True, 'mpv': True, 'credential_manager': True, 'credential_cleanup': True,
                'qt_runtime': True, 'qt_platform': 'windows',
                'python_bits': 64, 'runtime_platform': 'win32',
            },
            'artifacts': {
                'application_sha256': hashlib.sha256(b'app-v1').hexdigest(),
                'mpv_sha256': hashlib.sha256(b'mpv-v1').hexdigest(),
            },
        }), encoding='utf-8')
        (dist / 'BUILD_DEPENDENCIES.txt').write_text(RELEASE_DEPS, encoding='utf-8')
        (dist / 'WINDOWS_DEPENDENCY_LOCK.txt').write_text(RELEASE_DEPS, encoding='utf-8')
        (dist / 'PYTHON_VERSION.txt').write_text('Python 3.13.0\n', encoding='ascii')
        (dist / 'MPV_PROVENANCE.json').write_text(json.dumps({
            'product': 'mpv',
            'version': '0.41.0',
            'archive_sha256': MPV_ARCHIVE_SHA,
            'executable_sha256': hashlib.sha256(b'mpv-v1').hexdigest(),
            'packaged_files': ['mpv.exe'],
        }), encoding='utf-8')
        add_license_payload(dist)
        generate_fingerprint(dist)
        installer = release / 'UltraStalkerDesktop_Setup_0.1.0_x64.exe'
        installer.write_bytes(b'fake-installer-payload')
        write_smoke_report(dist, installer)
        return dist, installer



    def test_build_id_is_unique_even_for_immediate_repeated_fingerprints(self):
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td) / 'dist'; dist.mkdir()
            (dist / 'payload.bin').write_bytes(b'x')
            first = generate_fingerprint(dist)['build_id']
            second = generate_fingerprint(dist)['build_id']
            self.assertRegex(first, r'^USD-WIN-\d{8}-\d{6}-[0-9a-f]{8}$')
            self.assertRegex(second, r'^USD-WIN-\d{8}-\d{6}-[0-9a-f]{8}$')
            self.assertNotEqual(first, second)

    def test_fingerprint_rejects_symlink_payload(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist = root / 'dist'; dist.mkdir()
            target = root / 'outside.bin'; target.write_bytes(b'outside')
            link = dist / 'linked.bin'
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest('symlinks unavailable on this platform')
            with self.assertRaises(SystemExit) as cm:
                generate_fingerprint(dist)
            self.assertIn('symlink/junction', str(cm.exception).lower())

    def test_fingerprint_rejects_directory_symlink_without_traversing_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist = root / 'dist'; dist.mkdir()
            outside = root / 'outside'; outside.mkdir()
            (outside / 'should-never-be-walked.bin').write_bytes(b'outside')
            link = dist / 'linked-dir'
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('directory symlinks unavailable on this platform')
            with self.assertRaises(SystemExit) as cm:
                generate_fingerprint(dist)
            text = str(cm.exception).lower()
            self.assertIn('symlink/junction', text)
            self.assertIn('linked-dir', text)
            self.assertNotIn('should-never-be-walked.bin', text)

    def test_finalizer_rejects_directory_symlink_added_after_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            outside = root / 'outside'; outside.mkdir()
            (outside / 'external.bin').write_bytes(b'outside')
            link = dist / 'late-linked-dir'
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('directory symlinks unavailable on this platform')
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('symlink/junction', str(cm.exception).lower())
            self.assertNotIn('external.bin', str(cm.exception).lower())

    def test_fingerprint_rejects_windows_case_insensitive_path_collision(self):
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td) / 'dist'; dist.mkdir()
            resolved = dist.resolve()
            upper = resolved / 'Plugin.dll'
            lower = resolved / 'plugin.dll'
            upper.write_bytes(b'one')
            if not lower.exists():
                lower.write_bytes(b'two')
            # A real Windows filesystem cannot hold both names at once, so feed
            # the validator both lexical paths directly and verify its Windows
            # case-folding rule on every host.
            with patch('tools.release_fingerprint.walk_payload', return_value=[upper, lower]):
                with self.assertRaises(SystemExit) as cm:
                    generate_fingerprint(dist)
            self.assertIn('case-insensitive payload path collision', str(cm.exception).lower())

    def test_finalizer_rejects_case_collision_added_after_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            resolved = dist.resolve()
            upper = resolved / 'Late.dll'
            lower = resolved / 'late.dll'
            upper.write_bytes(b'one')
            if not lower.exists():
                lower.write_bytes(b'two')
            paths = [p for p in real_walk_payload(resolved) if p.name.casefold() != 'late.dll']
            paths.extend([upper, lower])
            with patch('tools.finalize_release.walk_payload', return_value=paths):
                with self.assertRaises(SystemExit) as cm:
                    finalize_release(dist, installer)
            self.assertIn('case-insensitive payload path collision', str(cm.exception).lower())

    def test_fingerprint_refuses_transient_build_self_test_marker(self):
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td) / 'dist'; dist.mkdir()
            (dist / '.ultrastalker-build-self-test').write_text('a' * 64, encoding='ascii')
            with self.assertRaises(SystemExit) as cm:
                generate_fingerprint(dist)
            self.assertIn('transient build self-test marker', str(cm.exception).lower())

    def test_finalizer_refuses_transient_build_self_test_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            (dist / '.ultrastalker-build-self-test').write_text('a' * 64, encoding='ascii')
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('transient build self-test marker', str(cm.exception).lower())

    def test_finalizer_requires_installer_smoke_test_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            (installer.parent / 'INSTALLER_SMOKE_TEST.json').unlink()
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('smoke-test report not found', str(cm.exception).lower())

    def test_finalizer_rejects_smoke_report_from_different_installer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            write_smoke_report(dist, installer, installer_sha256=hashlib.sha256(b'other').hexdigest())
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('not bound to the final installer', str(cm.exception).lower())

    def test_finalizer_rejects_failed_installer_uninstall_smoke_check(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            write_smoke_report(dist, installer, uninstall_passed=False)
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('uninstall_passed', str(cm.exception).lower())

    def test_finalizer_rejects_smoke_that_touches_production_registry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            write_smoke_report(dist, installer, production_registry_unchanged=False)
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('production_registry_unchanged', str(cm.exception))

    def test_finalizer_rejects_smoke_registry_not_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            write_smoke_report(dist, installer, smoke_registry_removed=False)
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('smoke_registry_removed', str(cm.exception))

    def test_finalizer_rejects_failed_upgrade_smoke_check(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            write_smoke_report(dist, installer, upgrade_passed=False)
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('upgrade_passed', str(cm.exception))

    def test_finalizer_rejects_upgrade_that_does_not_preserve_user_data(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            write_smoke_report(dist, installer, upgrade_user_data_preserved=False)
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('upgrade_user_data_preserved', str(cm.exception))

    def test_finalizer_rejects_uninstall_that_removes_user_data(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            write_smoke_report(dist, installer, uninstall_user_data_preserved=False)
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('uninstall_user_data_preserved', str(cm.exception))

    def test_finalizer_hashes_installer_and_preserves_build_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            provenance = json.loads((dist / 'provenance.json').read_text(encoding='utf-8'))
            output = finalize_release(dist, installer)
            self.assertEqual(output, (installer.parent / 'FINAL_RELEASE.json').resolve())
            manifest = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(manifest['build_id'], provenance['build_id'])
            self.assertTrue(manifest['self_test_passed'])
            self.assertTrue(manifest['installer_smoke_test_passed'])
            self.assertRegex(manifest['installer_smoke_test_sha256'], r'^[0-9a-f]{64}$')
            self.assertRegex(manifest['runtime_self_test_sha256'], r'^[0-9a-f]{64}$')
            self.assertEqual(manifest['installer']['sha256'], hashlib.sha256(installer.read_bytes()).hexdigest())
            self.assertGreater(manifest['portable_payload_file_count'], 0)
            self.assertRegex(manifest['portable_payload_root_sha256'], r'^[0-9a-f]{64}$')
            env = manifest['build_environment']
            self.assertEqual(env['python_version'], '3.13.0')
            self.assertEqual(env['python_version_file_sha256'], hashlib.sha256((dist / 'PYTHON_VERSION.txt').read_bytes()).hexdigest())
            self.assertEqual(env['build_dependencies_sha256'], hashlib.sha256((dist / 'BUILD_DEPENDENCIES.txt').read_bytes()).hexdigest())
            self.assertEqual(env['dependency_lock_sha256'], hashlib.sha256((dist / 'WINDOWS_DEPENDENCY_LOCK.txt').read_bytes()).hexdigest())
            self.assertEqual(env['python_runtime_provenance_sha256'], hashlib.sha256((dist / 'licenses' / 'PYTHON_RUNTIME_PROVENANCE.json').read_bytes()).hexdigest())
            self.assertEqual(env['python_runtime_license_sha256'], hashlib.sha256((dist / 'licenses' / 'PYTHON_LICENSE.txt').read_bytes()).hexdigest())
            self.assertEqual(env['python_runtime_license_sha256'], env['python_runtime_license_recorded_sha256'])
            source_freeze = json.loads((ROOT / 'SOURCE_FREEZE.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['source_tree_sha256'], source_freeze['source_tree_sha256'])
            self.assertEqual(manifest['source_freeze_file'], 'SOURCE_FREEZE.json')
            self.assertEqual(manifest['source_freeze_sha256'], hashlib.sha256((ROOT / 'SOURCE_FREEZE.json').read_bytes()).hexdigest())
            copied_freeze = installer.parent / 'SOURCE_FREEZE.json'
            self.assertEqual(copied_freeze.read_bytes(), (ROOT / 'SOURCE_FREEZE.json').read_bytes())

    def test_finalizer_rejects_failed_runtime_database_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist, installer = self._fixture(root)
            write_smoke_report(dist, installer, runtime_database_integrity='corrupt')
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('database integrity', str(cm.exception).lower())

    def test_finalizer_rejects_runtime_self_test_report_kind(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            report_path = dist / 'SELF_TEST.json'
            report = json.loads(report_path.read_text(encoding='utf-8'))
            report['report_kind'] = 'runtime'
            report_path.write_text(json.dumps(report), encoding='utf-8')
            generate_fingerprint(dist)
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('release build self-test', str(cm.exception).lower())

    def test_finalizer_rejects_failed_packaged_self_test(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, False)
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('self-test', str(cm.exception).lower())
            self.assertFalse((installer.parent / 'FINAL_RELEASE.json').exists())

    def test_finalizer_rejects_payload_changed_after_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            (dist / 'UltraStalkerDesktop.exe').write_bytes(b'app-mutated-after-installer')
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('changed after fingerprint', str(cm.exception).lower())
            self.assertFalse((installer.parent / 'FINAL_RELEASE.json').exists())

    def test_finalizer_rejects_file_added_after_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, installer = self._fixture(root, True)
            (dist / 'late-file.dll').write_bytes(b'late')
            with self.assertRaises(SystemExit) as cm:
                finalize_release(dist, installer)
            self.assertIn('added=late-file.dll', str(cm.exception).lower())

    def test_fingerprint_covers_release_hash_file_and_gate_detects_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td) / 'dist'; dist.mkdir()
            (dist / 'UltraStalkerDesktop.exe').write_bytes(b'app-v1')
            (dist / 'mpv.exe').write_bytes(b'mpv-v1')
            (dist / 'BUILD_DEPENDENCIES.txt').write_text(RELEASE_DEPS, encoding='utf-8')
            (dist / 'WINDOWS_DEPENDENCY_LOCK.txt').write_text(RELEASE_DEPS, encoding='utf-8')
            (dist / 'PYTHON_VERSION.txt').write_text('Python 3.13.0\n', encoding='ascii')
            (dist / 'MPV_PROVENANCE.json').write_text(json.dumps({
                'product': 'mpv',
                'version': '0.41.0',
                'archive_sha256': MPV_ARCHIVE_SHA,
                'executable_sha256': hashlib.sha256(b'mpv-v1').hexdigest(),
                'packaged_files': ['mpv.exe'],
            }), encoding='utf-8')
            (dist / 'SELF_TEST.json').write_text(json.dumps({
                'report_kind': 'build',
                'passed': True,
                'checks': {
                    'sqlite': True, 'mpv': True, 'credential_manager': True, 'credential_cleanup': True,
                    'qt_runtime': True, 'qt_platform': 'windows',
                    'python_bits': 64, 'runtime_platform': 'win32',
                },
                'artifacts': {
                    'application_sha256': hashlib.sha256(b'app-v1').hexdigest(),
                    'mpv_sha256': hashlib.sha256(b'mpv-v1').hexdigest(),
                },
            }), encoding='utf-8')
            add_license_payload(dist)
            generate_fingerprint(dist)
            provenance = json.loads((dist / 'provenance.json').read_text(encoding='utf-8'))
            release_hashes = dist / 'RELEASE_SHA256.json'
            self.assertIn('RELEASE_SHA256.json', provenance['files'])
            self.assertEqual(
                provenance['files']['RELEASE_SHA256.json'],
                hashlib.sha256(release_hashes.read_bytes()).hexdigest(),
            )
            passed, message = run_dist_gate(dist)
            self.assertTrue(passed, message)
            (dist / 'UltraStalkerDesktop.exe').write_bytes(b'app-tampered')
            # Update only the self-test binding so this test reaches the next
            # integrity layer. RELEASE_SHA256/provenance intentionally remain
            # from the original payload and must reject the modified EXE.
            self_test = json.loads((dist / 'SELF_TEST.json').read_text(encoding='utf-8'))
            self_test['artifacts']['application_sha256'] = hashlib.sha256(b'app-tampered').hexdigest()
            (dist / 'SELF_TEST.json').write_text(json.dumps(self_test), encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            message = message.lower()
            self.assertTrue(
                'does not match final executable payload' in message
                or 'provenance.json does not cover final' in message
            )


    def test_dist_gate_rejects_invalid_build_id_format(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            provenance_path = dist / 'provenance.json'
            provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
            provenance['build_id'] = 'USD-WIN-NOT-UNIQUE'
            provenance_path.write_text(json.dumps(provenance), encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('build id', message.lower())

    def test_dist_gate_rejects_unfingerprinted_extra_payload_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            (dist / 'unexpected.dat').write_bytes(b'late')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('complete payload', message.lower())
            self.assertIn('unexpected.dat', message.lower())

    def test_dist_gate_rejects_self_test_using_offscreen_qt_on_windows_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            report = json.loads((dist / 'SELF_TEST.json').read_text(encoding='utf-8'))
            report['checks']['qt_platform'] = 'offscreen'
            (dist / 'SELF_TEST.json').write_text(json.dumps(report), encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('real windows qt platform', message.lower())

    def test_dist_gate_rejects_failed_credential_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            report = json.loads((dist / 'SELF_TEST.json').read_text(encoding='utf-8'))
            report['checks']['credential_cleanup'] = False
            (dist / 'SELF_TEST.json').write_text(json.dumps(report), encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('credential_cleanup', message.lower())

    def test_dist_gate_rejects_32_bit_packaged_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            report = json.loads((dist / 'SELF_TEST.json').read_text(encoding='utf-8'))
            report['checks']['python_bits'] = 32
            (dist / 'SELF_TEST.json').write_text(json.dumps(report), encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('64-bit', message.lower())

    def test_dist_gate_rejects_direct_url_dependency_in_lock(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            direct = 'example-package @ https://example.invalid/example.whl\n'
            (dist / 'WINDOWS_DEPENDENCY_LOCK.txt').write_text(RELEASE_DEPS + direct, encoding='utf-8')
            (dist / 'BUILD_DEPENDENCIES.txt').write_text(RELEASE_DEPS + direct, encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('non-version-pinned', message.lower())

    def test_dist_gate_rejects_dependency_lock_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            lock = dist / 'WINDOWS_DEPENDENCY_LOCK.txt'
            lock.write_text(lock.read_text(encoding='utf-8') + 'extra-package==1.0\n', encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('does not exactly match', message.lower())

    def test_dist_gate_rejects_local_build_dependency_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            deps = (dist / 'BUILD_DEPENDENCIES.txt')
            deps.write_text(deps.read_text(encoding='utf-8') + 'example @ file:///C:/Users/Alice/pkg.whl\n', encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('local/direct', message.lower())

    def test_dist_gate_rejects_missing_required_build_dependency(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            deps = dist / 'BUILD_DEPENDENCIES.txt'
            text = deps.read_text(encoding='utf-8').replace('keyring==25.7.0\n', '')
            deps.write_text(text, encoding='utf-8')
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('missing required distributions', message.lower())

    def test_dist_gate_rejects_self_test_from_different_executable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            self_test = json.loads((dist / 'SELF_TEST.json').read_text(encoding='utf-8'))
            self_test['artifacts']['application_sha256'] = hashlib.sha256(b'other-app').hexdigest()
            (dist / 'SELF_TEST.json').write_text(json.dumps(self_test), encoding='utf-8')
            generate_fingerprint(dist)
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('self-test is not bound', message.lower())

    def test_dist_gate_rejects_mpv_not_matching_vendor_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            (dist / 'mpv.exe').write_bytes(b'corrupted-mpv')
            self_test = json.loads((dist / 'SELF_TEST.json').read_text(encoding='utf-8'))
            self_test['artifacts']['mpv_sha256'] = hashlib.sha256(b'corrupted-mpv').hexdigest()
            (dist / 'SELF_TEST.json').write_text(json.dumps(self_test), encoding='utf-8')
            # Re-fingerprint the corrupt payload. The self-test binding is now
            # consistent, so the independent vendor provenance check must be
            # the layer that rejects the modified mpv binary.
            generate_fingerprint(dist)
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('mpv executable sha256', message.lower())

    def test_dist_gate_rejects_missing_third_party_notices(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            (dist / 'THIRD_PARTY_NOTICES.txt').unlink()
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('third_party_notices.txt', message.lower())

    def test_dist_gate_rejects_missing_runtime_license_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            manifest_path = dist / 'licenses' / 'python' / 'PYTHON_RUNTIME_LICENSES.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['distributions'] = [
                item for item in manifest['distributions'] if item['name'].lower() != 'keyring'
            ]
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            # Re-fingerprint so the license-content gate, not provenance tamper,
            # is the layer responsible for rejection.
            generate_fingerprint(dist)
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('missing root packages', message.lower())

    def test_dist_gate_rejects_missing_cpython_runtime_license(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            (dist / 'licenses' / 'PYTHON_LICENSE.txt').unlink()
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('python_license.txt', message.lower())

    def test_dist_gate_rejects_mismatched_cpython_runtime_license_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            meta_path = dist / 'licenses' / 'PYTHON_RUNTIME_PROVENANCE.json'
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            meta['license_sha256'] = hashlib.sha256(b'wrong').hexdigest()
            meta_path.write_text(json.dumps(meta), encoding='utf-8')
            generate_fingerprint(dist)
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('license sha256', message.lower())

    def test_dist_gate_rejects_cpython_runtime_version_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            meta_path = dist / 'licenses' / 'PYTHON_RUNTIME_PROVENANCE.json'
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            meta['version'] = '3.12.9'
            meta_path.write_text(json.dumps(meta), encoding='utf-8')
            generate_fingerprint(dist)
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('version does not match', message.lower())

    def test_dist_gate_rejects_cpython_runtime_provenance_path_leak(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dist, _installer = self._fixture(root, True)
            meta_path = dist / 'licenses' / 'PYTHON_RUNTIME_PROVENANCE.json'
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            meta['source_path'] = r'C:\Users\Builder\Python\LICENSE.txt'
            meta_path.write_text(json.dumps(meta), encoding='utf-8')
            generate_fingerprint(dist)
            passed, message = run_dist_gate(dist)
            self.assertFalse(passed)
            self.assertIn('build-machine path', message.lower())

    def test_windows_version_resource_matches_release_identity(self):
        spec = (ROOT / 'UltraStalkerDesktop.spec').read_text(encoding='utf-8')
        version = (ROOT / 'resources' / 'version_info.txt').read_text(encoding='utf-8')
        self.assertIn("version='resources/version_info.txt'", spec)
        self.assertIn('keyring.backends.Windows', spec)
        self.assertIn('win32ctypes.pywin32.pywintypes', spec)
        self.assertIn('win32ctypes.pywin32.win32cred', spec)
        self.assertIn("StringStruct('CompanyName', 'Ahmed L-HadarY')", version)
        self.assertIn("StringStruct('ProductName', 'Ultra Stalker Desktop')", version)
        self.assertIn("StringStruct('ProductVersion', '0.1.0')", version)
        self.assertIn("StringStruct('OriginalFilename', 'UltraStalkerDesktop.exe')", version)



if __name__ == '__main__':
    unittest.main()
