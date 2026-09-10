from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.release_gate import validate_powershell_structure


class PowerShellStructureTests(unittest.TestCase):
    def _script(self, root: Path, text: str) -> Path:
        path = root / "sample.ps1"
        path.write_text(text, encoding="utf-8")
        return path

    def test_all_release_powershell_scripts_are_structurally_balanced(self):
        root = Path(__file__).resolve().parents[1]
        scripts = [root / "build_windows.ps1", *sorted((root / "tools").glob("*.ps1"))]
        self.assertGreaterEqual(len(scripts), 5)
        for script in scripts:
            with self.subTest(script=script.name):
                validate_powershell_structure(script)

    def test_validator_rejects_unterminated_quoted_string(self):
        with tempfile.TemporaryDirectory() as td:
            script = self._script(Path(td), 'Write-Host "broken\n')
            with self.assertRaises(ValueError) as cm:
                validate_powershell_structure(script)
            self.assertIn("unterminated", str(cm.exception).lower())

    def test_validator_rejects_unclosed_brace(self):
        with tempfile.TemporaryDirectory() as td:
            script = self._script(Path(td), 'if ($true) {\n  Write-Host "x"\n')
            with self.assertRaises(ValueError) as cm:
                validate_powershell_structure(script)
            self.assertIn("unclosed", str(cm.exception).lower())

    def test_validator_ignores_brackets_inside_strings_and_comments(self):
        with tempfile.TemporaryDirectory() as td:
            script = self._script(
                Path(td),
                '# comment with } ] )\nWrite-Host "literal { [ ("\n$x = @(1, 2, 3)\n',
            )
            validate_powershell_structure(script)

    def test_release_pipeline_uses_system_windows_powershell_not_path_lookup(self):
        root = Path(__file__).resolve().parents[1]
        bat = (root / "build_windows.bat").read_text(encoding="utf-8")
        build = (root / "build_windows.ps1").read_text(encoding="utf-8")
        smoke = (root / "tools" / "smoke_installer.ps1").read_text(encoding="utf-8")
        self.assertIn(r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe", bat)
        for text in (build, smoke):
            self.assertIn("System32\\WindowsPowerShell\\v1.0\\powershell.exe", text)
            self.assertNotRegex(text, r"(?mi)^\s*&\s+powershell(?:\.exe)?\b")

    def test_bootstrap_pins_system_powershell_for_nested_scripts(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "tools" / "bootstrap_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("System32\\WindowsPowerShell\\v1.0\\powershell.exe", text)
        self.assertNotRegex(text, r"(?mi)^\s*&\s+powershell(?:\.exe)?\b")
        self.assertIn("& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File tools\\fetch_mpv.ps1", text)

    def test_gitattributes_forces_lf_for_frozen_windows_checkout(self):
        root = Path(__file__).resolve().parents[1]
        attrs = (root / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("* text=auto eol=lf", attrs)

    def test_github_windows_release_workflow_is_manual_pinned_and_windows_2025(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github" / "workflows" / "windows-release.yml")
        self.assertTrue(workflow.is_file())
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotRegex(text, r"(?m)^\s{2}(?:push|pull_request):")
        self.assertIn("runs-on: windows-2025", text)
        self.assertNotIn("windows-latest", text)
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", text)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", text)
        self.assertNotRegex(text, r"actions/(?:checkout|upload-artifact)@v\d")

    def test_github_windows_release_workflow_runs_frozen_build_and_verification(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")
        for token in (
            "tools\\source_freeze.py --root .",
            "build_windows.bat",
            "release\\VERIFY_RELEASE.ps1",
            "dist"):
            self.assertIn(token, text)
        self.assertIn("UltraStalkerDesktop", text)
        self.assertIn("mpv.exe", text)
        self.assertIn("release/**", text)
        self.assertIn("if-no-files-found: error", text)


if __name__ == "__main__":
    unittest.main()
