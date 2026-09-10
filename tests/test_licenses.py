from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import collect_runtime_licenses as licenses
from tools import collect_python_runtime_license as cpython_license


class FakeDist:
    def __init__(self, root: Path, name: str, version: str, requires=None, files=None, meta=None):
        self._root = root
        self.version = version
        self.requires = list(requires or [])
        self.files = [Path(x) for x in (files or [])]
        self.metadata = {"Name": name, "License": "MIT", **(meta or {})}

    def locate_file(self, entry):
        return self._root / str(entry)


class RuntimeLicenseCollectorTests(unittest.TestCase):
    def test_collects_roots_transitive_dependencies_and_license_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in ("pyside/LICENSE.txt", "requests/LICENSE", "keyring/LICENSE", "dep/COPYING"):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("license body", encoding="utf-8")
            dists = [
                FakeDist(root, "PySide6", "6.9", ["shiboken6>=6.9"], ["pyside/LICENSE.txt"]),
                FakeDist(root, "requests", "2.32", [], ["requests/LICENSE"]),
                FakeDist(root, "keyring", "25", [], ["keyring/LICENSE"]),
                FakeDist(root, "shiboken6", "6.9", [], ["dep/COPYING"]),
            ]
            with mock.patch.object(licenses.metadata, "distributions", return_value=dists), \
                 mock.patch.object(licenses.sys, "platform", "linux"):
                out = root / "out"
                manifest = licenses.collect(out)
            names = {x["name"] for x in manifest["distributions"]}
            self.assertEqual(names, {"PySide6", "requests", "keyring", "shiboken6"})
            self.assertEqual(manifest["missing_roots"], [])
            copied = [p for p in out.rglob("*") if p.is_file()]
            self.assertTrue(any(p.name.lower().startswith("license") for p in copied))

    def test_windows_collection_requires_pywin32_ctypes_for_win_vault(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dists = [
                FakeDist(root, "PySide6", "6.9"),
                FakeDist(root, "requests", "2.32"),
                FakeDist(root, "keyring", "25"),
            ]
            with mock.patch.object(licenses.metadata, "distributions", return_value=dists), \
                 mock.patch.object(licenses.sys, "platform", "win32"):
                with self.assertRaisesRegex(RuntimeError, "pywin32-ctypes"):
                    licenses.collect(root / "out")

    def test_windows_collection_includes_pywin32_ctypes_when_keyring_requires_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in ("pyside/LICENSE.txt", "requests/LICENSE", "keyring/LICENSE", "win/LICENSE.txt"):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("license body", encoding="utf-8")
            dists = [
                FakeDist(root, "PySide6", "6.9", files=["pyside/LICENSE.txt"]),
                FakeDist(root, "requests", "2.32", files=["requests/LICENSE"]),
                FakeDist(root, "keyring", "25", ["pywin32-ctypes>=0.2; sys_platform == 'win32'"], ["keyring/LICENSE"]),
                FakeDist(root, "pywin32-ctypes", "0.2.3", files=["win/LICENSE.txt"]),
            ]
            with mock.patch.object(licenses.metadata, "distributions", return_value=dists), \
                 mock.patch.object(licenses.sys, "platform", "win32"):
                manifest = licenses.collect(root / "out")
            names = {x["name"] for x in manifest["distributions"]}
            self.assertIn("pywin32-ctypes", names)

    def test_missing_root_package_is_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dists = [
                FakeDist(root, "PySide6", "6.9"),
                FakeDist(root, "requests", "2.32"),
            ]
            with mock.patch.object(licenses.metadata, "distributions", return_value=dists):
                with self.assertRaisesRegex(RuntimeError, "keyring"):
                    licenses.collect(root / "out")


class CPythonRuntimeLicenseCollectorTests(unittest.TestCase):
    def test_collects_exact_interpreter_license_and_safe_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "Python313"
            base.mkdir()
            source_bytes = ("Python Software Foundation License fixture\n" * 60).encode("utf-8")
            (base / "LICENSE.txt").write_bytes(source_bytes)
            out = root / "out"
            data = cpython_license.collect_python_runtime_license(
                out, base_prefix=base, version="3.13.0"
            )
            self.assertEqual((out / "PYTHON_LICENSE.txt").read_bytes(), source_bytes)
            self.assertEqual(data["product"], "CPython")
            self.assertEqual(data["implementation"], "CPython")
            self.assertEqual(data["version"], "3.13.0")
            self.assertEqual(data["license_sha256"], hashlib.sha256(source_bytes).hexdigest())
            self.assertEqual(data["source_license_name"], "LICENSE.txt")
            raw = (out / "PYTHON_RUNTIME_PROVENANCE.json").read_text(encoding="utf-8")
            self.assertNotIn(str(root), raw)
            parsed = json.loads(raw)
            self.assertNotIn("source_path", parsed)
            self.assertNotIn("base_prefix", parsed)

    def test_missing_interpreter_license_is_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "Python313"
            base.mkdir()
            with self.assertRaisesRegex(RuntimeError, "LICENSE.txt"):
                cpython_license.collect_python_runtime_license(
                    root / "out", base_prefix=base, version="3.13.0"
                )


if __name__ == "__main__":
    unittest.main()
