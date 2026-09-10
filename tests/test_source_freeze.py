from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.source_freeze import snapshot, tree_hash, verify_manifest, write_manifest

ROOT = Path(__file__).resolve().parents[1]


class SourceFreezeTests(unittest.TestCase):
    def _mini_project(self, td: str) -> Path:
        root = Path(td)
        (root / 'ultrastalker_desktop').mkdir()
        (root / 'ultrastalker_desktop' / '__init__.py').write_text('__version__ = "0.1.0"\nAUTHOR = "Ahmed L-HadarY"\n', encoding='utf-8')
        (root / 'provenance.json').write_text(json.dumps({
            'reference': 'Ultra Stalker 8.4.1',
            'reference_artifact': 'UltraStalker_V7_UPDATE.ipk',
            'reference_artifact_sha256': 'abc',
            'reference_parity': 'behavioral-reference; original 8.4.1 source bytes unavailable',
        }), encoding='utf-8')
        (root / 'README.md').write_text('hello\n', encoding='utf-8')
        return root

    def test_write_then_verify(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._mini_project(td)
            write_manifest(root, unittest_count=3)
            manifest = verify_manifest(root)
            self.assertEqual(manifest['validation']['unittest_count'], 3)
            self.assertEqual(manifest['source_tree_sha256'], tree_hash(snapshot(root)))

    def test_modified_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._mini_project(td)
            write_manifest(root)
            (root / 'README.md').write_text('changed\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'README.md'):
                verify_manifest(root)

    def test_new_source_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._mini_project(td)
            write_manifest(root)
            (root / 'NEW.txt').write_text('new\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'file set mismatch'):
                verify_manifest(root)

    def test_generated_directories_are_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._mini_project(td)
            write_manifest(root)
            (root / 'dist').mkdir()
            (root / 'dist' / 'generated.bin').write_bytes(b'x')
            verify_manifest(root)

    def test_manifest_itself_is_not_self_hashed(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._mini_project(td)
            write_manifest(root)
            files = snapshot(root)
            self.assertNotIn('SOURCE_FREEZE.json', files)


if __name__ == '__main__':
    unittest.main()
