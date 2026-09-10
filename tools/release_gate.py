from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import json
import os
import stat
import re
import sys
from pathlib import Path

try:
    from tools.path_safety import is_linklike as _payload_is_linklike, walk_payload
    from tools.source_freeze import verify_manifest as verify_source_freeze
except ModuleNotFoundError:  # direct execution as tools/release_gate.py
    from path_safety import is_linklike as _payload_is_linklike, walk_payload
    from source_freeze import verify_manifest as verify_source_freeze

PRODUCT = "Ultra Stalker Desktop"
VERSION = "0.1.0"
DEVELOPER = "Ahmed L-HadarY"
REFERENCE = "Ultra Stalker 8.4.1"


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"[PASS] {msg}")


def _is_linklike(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction and is_junction():
            return True
        # CPython 3.11 does not expose Path.is_junction(). On Windows, junctions
        # and other filesystem indirections are reparse points, so reject those
        # too rather than silently following content outside the release root.
        if os.name == "nt":
            attrs = getattr(path.lstat(), "st_file_attributes", 0)
            if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                return True
        return False
    except OSError:
        return True


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()




def validate_powershell_structure(path: Path) -> None:
    """Conservative structural validation for PowerShell scripts on non-Windows CI.

    This is not a replacement for the PowerShell parser. It catches unmatched
    (), [], {}, and unterminated single/double quoted strings while ignoring
    line comments and PowerShell escape characters.
    """
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    stack: list[tuple[str, int]] = []
    pairs = {')': '(', ']': '[', '}': '{'}
    opens = set(pairs.values())
    quote = None
    i = 0
    line = 1
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            line += 1

        if quote == "'":
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        if quote == '"':
            if ch == '`':
                i += 2
                continue
            if ch == '"':
                quote = None
            i += 1
            continue

        if ch == '#':
            newline = text.find("\n", i)
            if newline < 0:
                break
            i = newline
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch == '`':
            i += 2
            continue
        if ch in opens:
            stack.append((ch, line))
        elif ch in pairs:
            if not stack or stack[-1][0] != pairs[ch]:
                raise ValueError(f"PowerShell structure error in {path.name} at line {line}: unexpected {ch}")
            stack.pop()
        i += 1

    if quote is not None:
        raise ValueError(f"PowerShell structure error in {path.name}: unterminated {quote} string")
    if stack:
        opener, opener_line = stack[-1]
        raise ValueError(f"PowerShell structure error in {path.name}: unclosed {opener} from line {opener_line}")


def static_gate(root: Path) -> None:
    source_roots = [root / "ultrastalker_desktop", root / "tools", root / "tests"]
    py_files = sorted(
        path for base in source_roots if base.exists() for path in base.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    if not py_files:
        fail("No Python source files found")
    enigma_imports = []
    syntax_errors = []
    for path in py_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_errors.append(f"{path}: {exc}")
            continue
        for node in ast.walk(tree):
            name = ""
            if isinstance(node, ast.Import):
                for item in node.names:
                    if item.name.startswith(("Components", "Screens", "NavigationInstance", "enigma")):
                        enigma_imports.append((str(path), item.name))
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                if name.startswith(("Components", "Screens", "NavigationInstance", "enigma")):
                    enigma_imports.append((str(path), name))
    if syntax_errors:
        fail("Python parse errors:\n" + "\n".join(syntax_errors))
    ok(f"Python AST parse {len(py_files)}/{len(py_files)}")
    if enigma_imports:
        fail(f"Enigma2 imports present: {enigma_imports}")
    ok("No Enigma2 imports")

    init = root / "ultrastalker_desktop" / "__init__.py"
    text = init.read_text(encoding="utf-8")
    if VERSION not in text or DEVELOPER not in text:
        fail("Version/author metadata mismatch")
    ok("Version and developer metadata coherent")

    source_provenance = root / "provenance.json"
    if not source_provenance.is_file():
        fail("Source provenance.json is missing")
    try:
        source_meta = json.loads(source_provenance.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        fail(f"Invalid source provenance.json: {exc}")
    expected_source_meta = {
        "product": PRODUCT,
        "version": VERSION,
        "developer": DEVELOPER,
        "platform": "source",
        "reference": REFERENCE,
        "reference_artifact": "UltraStalker_V7_UPDATE.ipk",
        "reference_parity": "behavioral-reference; original 8.4.1 source bytes unavailable",
    }
    for key, value in expected_source_meta.items():
        if source_meta.get(key) != value:
            fail(f"Source provenance mismatch for {key}: {source_meta.get(key)!r}")
    status = str(source_meta.get("status") or "").lower()
    if not status.startswith("release-candidate source"):
        fail("Source provenance must remain explicitly release-candidate until Windows acceptance")
    ok("Source provenance remains distinct from final Windows release identity")

    build = root / "build_windows.bat"
    build_ps1 = root / "build_windows.ps1"
    iss = root / "installer" / "UltraStalkerDesktop.iss"
    notices = root / "THIRD_PARTY_NOTICES.txt"
    license_files = [
        root / "licenses" / "GPL-2.0.txt",
        root / "licenses" / "GPL-3.0.txt",
        root / "licenses" / "LGPL-2.1.txt",
        root / "licenses" / "LGPL-3.0.txt",
    ]
    collector = root / "tools" / "collect_runtime_licenses.py"
    python_runtime_collector = root / "tools" / "collect_python_runtime_license.py"
    smoke_installer = root / "tools" / "smoke_installer.ps1"
    version_resource = root / "resources" / "version_info.txt"
    release_requirements = root / "requirements-release.txt"
    for needed in (build, build_ps1, root / "UltraStalkerDesktop.spec", version_resource, iss, root / "requirements.txt", root / "requirements-build.txt", release_requirements, root / "pyproject.toml", root / "tools" / "finalize_release.py", root / "tools" / "verify_final_release.ps1", smoke_installer, notices, collector, python_runtime_collector, *license_files):
        if not needed.is_file():
            fail(f"Missing build/release file: {needed.name}")
    if notices.stat().st_size < 500:
        fail("THIRD_PARTY_NOTICES.txt is unexpectedly small")
    if any(path.stat().st_size < 5000 for path in license_files):
        fail("One or more bundled GPL/LGPL license texts are incomplete")
    requirements_build = (root / "requirements-build.txt").read_text(encoding="utf-8", errors="replace").lower()
    if "packaging" not in requirements_build:
        fail("Runtime license collector dependency 'packaging' is not pinned in requirements-build.txt")
    release_requirements_text = release_requirements.read_text(encoding="utf-8", errors="replace").lower()
    release_root_pins = (
        "pyside6==6.11.2",
        "requests==2.34.2",
        "keyring==25.7.0",
        "pywin32-ctypes==0.2.3",
        "pyinstaller==6.22.2",
        "packaging==26.3",
    )
    missing_release_pins = [pin for pin in release_root_pins if pin not in release_requirements_text]
    if missing_release_pins:
        fail("Windows release root dependencies are not exactly pinned: " + ", ".join(missing_release_pins))
    bootstrap_text = (root / "tools" / "bootstrap_windows.ps1").read_text(encoding="utf-8", errors="replace")
    for token in ("requirements-release.txt", "WINDOWS_DEPENDENCY_LOCK.txt", "Rebuilding final venv from exact dependency lock", "Compare-Object", "ChosenPythonVersion", "VenvVersion"):
        if token not in bootstrap_text:
            fail(f"Windows bootstrap does not enforce two-pass dependency locking: {token}")
    if "WINDOWS_DEPENDENCY_LOCK.txt" not in build_ps1.read_text(encoding="utf-8", errors="replace"):
        fail("Windows build does not package the exact resolved dependency lock")
    build_license_text = build_ps1.read_text(encoding="utf-8", errors="replace")
    if "collect_runtime_licenses.py" not in build_license_text or "THIRD_PARTY_NOTICES.txt" not in build_license_text:
        fail("Windows build does not assemble third-party notices/runtime license metadata")
    if "collect_python_runtime_license.py" not in build_license_text:
        fail("Windows build does not collect the exact CPython runtime license")
    notices_text = notices.read_text(encoding="utf-8", errors="replace")
    if "CPython runtime" not in notices_text or "PYTHON_LICENSE.txt" not in notices_text or "PYTHON_RUNTIME_PROVENANCE.json" not in notices_text:
        fail("Third-party notices do not document the bundled CPython runtime license")
    if "licenses" not in build_license_text:
        fail("Windows build does not package license texts")
    ok("Windows build files and third-party notices present")

    for ps1 in sorted([build_ps1, *(root / "tools").glob("*.ps1")]):
        try:
            validate_powershell_structure(ps1)
        except ValueError as exc:
            fail(str(exc))
    ok("PowerShell release scripts pass structural validation")
    bat_text = build.read_text(encoding="utf-8", errors="replace")
    system_ps_token = r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
    if system_ps_token not in bat_text:
        fail("Windows batch entry point does not use the system Windows PowerShell host")
    ps_host_token = "System32\\WindowsPowerShell\\v1.0\\powershell.exe"
    smoke_text_for_host = smoke_installer.read_text(encoding="utf-8", errors="replace")
    bootstrap_text_for_host = (root / "tools" / "bootstrap_windows.ps1").read_text(encoding="utf-8", errors="replace")
    for label, text in (
        ("build", build_license_text),
        ("bootstrap", bootstrap_text_for_host),
        ("installer smoke", smoke_text_for_host),
    ):
        if ps_host_token not in text:
            fail(f"{label} script does not pin the system Windows PowerShell host")
        if re.search(r"(?mi)^\s*&\s+powershell(?:\.exe)?\b", text):
            fail(f"{label} script invokes PowerShell through PATH instead of the system host")
    ok("Windows release pipeline pins the system PowerShell host")
    gitattrs = root / ".gitattributes"
    if not gitattrs.is_file():
        fail(".gitattributes is missing; Windows checkout could rewrite frozen source line endings")
    gitattrs_text = gitattrs.read_text(encoding="utf-8", errors="replace")
    if "* text=auto eol=lf" not in gitattrs_text:
        fail(".gitattributes does not force LF line endings for frozen source")
    ok("Git checkout preserves LF line endings across Windows runners")
    workflow = root / ".github" / "workflows" / "windows-release.yml"
    if not workflow.is_file():
        fail("Pinned GitHub Windows release workflow is missing")
    workflow_text = workflow.read_text(encoding="utf-8", errors="replace")
    workflow_requirements = (
        "workflow_dispatch:",
        "runs-on: windows-2025",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "tools\\source_freeze.py --root .",
        "build_windows.bat",
        "release\\VERIFY_RELEASE.ps1",
        "mpv.exe",
        "release/**",
    )
    missing_workflow = [token for token in workflow_requirements if token not in workflow_text]
    if missing_workflow:
        fail("GitHub Windows release workflow is incomplete: " + ", ".join(missing_workflow))
    if "windows-latest" in workflow_text or re.search(r"actions/(?:checkout|upload-artifact)@v\d", workflow_text):
        fail("GitHub Windows release workflow uses a floating runner/action reference")
    if re.search(r"(?m)^\s{2}(?:push|pull_request):", workflow_text):
        fail("GitHub Windows release workflow must remain manually triggered")
    ok("GitHub Windows release runner is pinned and release-gated")
    freeze_manifest = root / "SOURCE_FREEZE.json"
    freeze_tool = root / "tools" / "source_freeze.py"
    if not freeze_manifest.is_file() or not freeze_tool.is_file():
        fail("Frozen source manifest/tool is missing")
    if "tools\\source_freeze.py --root ." not in bootstrap_text_for_host:
        fail("Windows bootstrap does not verify SOURCE_FREEZE.json before dependency setup")
    if bootstrap_text_for_host.find("source_freeze.py --root .") > bootstrap_text_for_host.find("Step 'Resolving exact Windows release dependency set'"):
        fail("Source freeze verification occurs too late in Windows bootstrap")
    try:
        verify_source_freeze(root)
    except Exception as exc:
        fail(f"Source freeze verification failed: {type(exc).__name__}: {exc}")
    ok("Source freeze manifest matches the current source tree")
    ok("Source freeze verification is wired into the Windows bootstrap")
    fingerprint_text = (root / "tools" / "release_fingerprint.py").read_text(encoding="utf-8", errors="replace")
    finalizer_text = (root / "tools" / "finalize_release.py").read_text(encoding="utf-8", errors="replace")
    final_verify_text = (root / "tools" / "verify_final_release.ps1").read_text(encoding="utf-8", errors="replace")
    for label, text in (
        ("portable fingerprint", fingerprint_text),
        ("final release", finalizer_text),
        ("final verifier", final_verify_text),
    ):
        for token in ("source_tree_sha256", "source_freeze_sha256", "SOURCE_FREEZE.json"):
            if token not in text:
                fail(f"{label} is not linked to the frozen source tree: missing {token}")
    ok("Final Windows release is cryptographically linked to the frozen source tree")

    spec_text = (root / "UltraStalkerDesktop.spec").read_text(encoding="utf-8", errors="replace")
    version_text = version_resource.read_text(encoding="utf-8", errors="replace")
    if "version='resources/version_info.txt'" not in spec_text:
        fail("PyInstaller executable is missing its Windows version resource")
    for hidden in (
        "keyring.backends.Windows",
        "win32ctypes.pywin32.pywintypes",
        "win32ctypes.pywin32.win32cred",
    ):
        if hidden not in spec_text:
            fail(f"PyInstaller spec is missing required Windows credential backend import: {hidden}")
    requirements_text = (root / "requirements.txt").read_text(encoding="utf-8", errors="replace").lower()
    pyproject_lower = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace").lower()
    if "pywin32-ctypes" not in requirements_text or "pywin32-ctypes" not in pyproject_lower:
        fail("Windows Credential Manager bridge pywin32-ctypes is not an explicit runtime dependency")
    for expected in ("Ultra Stalker Desktop", VERSION, DEVELOPER, "UltraStalkerDesktop.exe"):
        if expected not in version_text:
            fail(f"Windows executable version resource missing metadata: {expected}")
    ok("Windows executable version metadata coherent")

    # Ensure version/author are coherent across packaging metadata too.
    iss_text = iss.read_text(encoding="utf-8", errors="replace")
    fingerprint_text = (root / "tools" / "release_fingerprint.py").read_text(encoding="utf-8", errors="replace")
    if VERSION not in iss_text or DEVELOPER not in iss_text:
        fail("Installer metadata does not match runtime version/developer")
    if "MinVersion=10.0.17763" not in iss_text:
        fail("Installer does not enforce the Qt/PySide6 Windows 10 1809 minimum")
    if VERSION not in fingerprint_text or DEVELOPER not in fingerprint_text:
        fail("Fingerprint metadata does not match runtime version/developer")
    if "UltraStalker_V7_UPDATE.ipk" not in fingerprint_text or "behavioral-reference" not in fingerprint_text:
        fail("Fingerprint provenance overstates or omits the 8.4.1 reference artifact semantics")
    ok("Packaging metadata coherent")

    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
    if 'requires-python = ">=3.11,<3.15"' not in pyproject_text:
        fail("Project Python metadata does not match the Windows CPython 3.11-3.14 release policy")
    if f'version = "{VERSION}"' not in pyproject_text or f'name = "{DEVELOPER}"' not in pyproject_text:
        fail("pyproject metadata does not match runtime version/developer")
    finalizer_text = (root / "tools" / "finalize_release.py").read_text(encoding="utf-8", errors="replace")
    if VERSION not in finalizer_text or DEVELOPER not in finalizer_text:
        fail("Final release metadata does not match runtime version/developer")
    if "finalize_release.py" not in (root / "build_windows.ps1").read_text(encoding="utf-8", errors="replace"):
        fail("Windows build does not finalize installer manifest")
    ok("Project and final-release metadata coherent")

    fetch = root / "tools" / "fetch_mpv.ps1"
    fetch_text = fetch.read_text(encoding="utf-8") if fetch.is_file() else ""
    pinned = "4e197f729f5071c6772f35fffd96e0f36e3e8a044bd9479b136bb09b7c6a80ff"
    if pinned not in fetch_text or "mpv-v0.41.0-x86_64-pc-windows-msvc.zip" not in fetch_text:
        fail("Pinned mpv Windows runtime metadata missing or changed")
    if "executable_sha256" not in fetch_text or "packaged_files = @('mpv.exe')" not in fetch_text:
        fail("mpv fetcher does not fingerprint/minimize the extracted runtime")
    bootstrap_text = (root / "tools" / "bootstrap_windows.ps1").read_text(encoding="utf-8", errors="replace")
    if "Test-MpvVendor" not in bootstrap_text or "Get-FileHash -Algorithm SHA256" not in bootstrap_text:
        fail("Cached mpv runtime is not re-verified during bootstrap")
    if 'struct.calcsize("P") * 8 == 64' not in bootstrap_text:
        fail("Windows bootstrap does not enforce a 64-bit Python build runtime")
    if "-m pip check" not in bootstrap_text:
        fail("Windows bootstrap does not enforce dependency consistency with pip check")
    if "Tls12" not in fetch_text or "SecurityProtocol" not in fetch_text:
        fail("mpv downloader does not explicitly support TLS 1.2 on Windows PowerShell 5.1")
    ok("Pinned and locally verified mpv Windows runtime enforced")

    build_text = (root / "build_windows.ps1").read_text(encoding="utf-8", errors="replace")
    if "${env:ProgramFiles(x86)}" not in build_text:
        fail("Inno Setup x86 Program Files lookup is not PowerShell-safe")
    if "Inno Setup 7" not in build_text or "Inno Setup 6" not in build_text:
        fail("Windows build does not discover both supported Inno Setup 7 and 6 installations")
    if r"vendor\mpv\*" in build_text:
        fail("Windows build copies the whole mpv developer archive instead of the minimal runtime")
    if r"vendor\mpv\mpv.exe" not in build_text:
        fail("Windows build does not copy the verified mpv.exe explicitly")
    ok("Minimal mpv runtime packaging enforced")
    if "--self-test-build" not in build_text:
        fail("Packaged executable build self-test is not enforced by build script")
    if "ULTRASTALKER_RELEASE_BUILD_SELF_TEST" not in build_text or "Remove-Item Env:ULTRASTALKER_RELEASE_BUILD_SELF_TEST" not in build_text:
        fail("Release build self-test marker is not scoped and cleaned by the build script")
    if ".ultrastalker-build-self-test" not in build_text or "[Guid]::NewGuid()" not in build_text:
        fail("Release build self-test does not use a transient per-build nonce marker")
    if "Remove-Item $BuildSelfTestMarker" not in build_text:
        fail("Transient build self-test nonce marker is not removed by the build script")

    release_order = [
        ("payload assembly", "Step 'Adding verified mpv runtime'"),
        ("packaged self-test", "Step 'Running packaged executable self-test'"),
        ("build environment capture", "Step 'Capturing build environment'"),
        ("portable fingerprint", "Step 'Fingerprinting portable payload'"),
        ("distribution gate", r'tools\release_gate.py --root . --dist'),
        ("installer build", "Step 'Building installer with Inno Setup'"),
        ("installed release smoke test", "Step 'Smoke-testing installed Windows release'"),
        ("final release manifest", "Step 'Finalizing installer release manifest'"),
    ]
    positions = []
    for label, token in release_order:
        pos = build_text.find(token)
        if pos < 0:
            fail(f"Windows release pipeline step missing: {label}")
        positions.append(pos)
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        fail("Windows release pipeline order is unsafe: assemble -> self-test -> environment -> fingerprint -> gate -> installer -> smoke-test -> finalizer")
    fingerprint_pos = positions[3]
    marker_cleanup_pos = build_text.find("Remove-Item $BuildSelfTestMarker")
    if marker_cleanup_pos < 0 or marker_cleanup_pos > fingerprint_pos:
        fail("Transient build self-test marker is not removed before fingerprinting")
    for line in build_text[fingerprint_pos:].splitlines():
        stripped = line.strip()
        if r"dist\$App" in stripped and stripped.startswith(("Copy-Item", "Set-Content", "New-Item", "Remove-Item")):
            fail("Windows build mutates the portable payload after fingerprinting")
    ok("Windows release pipeline ordering prevents post-fingerprint payload mutation")
    main_text = (root / "ultrastalker_desktop" / "main.py").read_text(encoding="utf-8", errors="replace")
    if "--self-test-build" not in main_text:
        fail("Runtime does not distinguish build self-test from installed self-test")
    if "ULTRASTALKER_RELEASE_BUILD_SELF_TEST" not in main_text:
        fail("Installed runtime can mutate the fingerprinted build self-test without a release marker")
    if ".ultrastalker-build-self-test" not in main_text or "stored == nonce" not in main_text:
        fail("Build self-test authorization is not bound to the transient per-build nonce marker")
    diagnostics_text = (root / "ultrastalker_desktop" / "diagnostics.py").read_text(encoding="utf-8", errors="replace")
    if "write_build_self_test_report" not in diagnostics_text or "write_runtime_self_test_report" not in diagnostics_text:
        fail("Build and installed self-test reports are not separated")
    if "diagnostics_dir()" not in diagnostics_text:
        fail("Installed self-test is not written outside the fingerprinted payload")
    if "require_release_integrity" not in diagnostics_text or "verify_release_integrity" not in diagnostics_text:
        fail("Installed self-test is not bound to release-integrity verification")
    if "full=require_release_integrity" not in diagnostics_text:
        fail("Installed self-test does not verify the complete fingerprinted payload")
    if 'getattr(sys, "frozen", False)' not in main_text:
        fail("Installed frozen self-test does not require release-integrity verification")
    ok("Build and installed Windows self-tests are safely separated")
    if "Final Windows release requires an installer" not in build_text or "exit 0" in build_text:
        fail("Windows release may succeed without creating the required installer")
    ok("Final Windows installer is mandatory")
    smoke_text = smoke_installer.read_text(encoding="utf-8", errors="replace")
    smoke_required = (
        "INSTALLER_SMOKE_TEST.json",
        "Assert-InstalledPayload",
        "verify_installed_runtime.ps1",
        "UltraStalker\\diagnostics\\SELF_TEST.json",
        "payload_immutable_after_runtime_test",
        "smoke_registry_isolated",
        "production_registry_unchanged",
        "smoke_registry_removed",
        "ProductionUninstallKey",
        "SmokeUninstallKey",
        "upgrade_passed",
        "upgrade_user_data_preserved",
        "upgrade_stale_runtime_cleanup_passed",
        "uninstall_passed",
        "uninstall_user_data_preserved",
        "ultrastalker-smoke-obsolete.tmp",
        "Get-FileHash -LiteralPath",
        "UltraStalker-Smoke-",
    )
    for token in smoke_required:
        if token not in smoke_text:
            fail(f"Installer smoke test is missing required behavior: {token}")
    if "$FallbackUninstaller -and -not $UninstallAttempted" in smoke_text:
        fail("Installer smoke-test cleanup does not retry a failed prior uninstall")
    if "if ($FallbackUninstaller)" not in smoke_text:
        fail("Installer smoke-test cleanup does not include an unconditional fallback-uninstaller retry")
    if "smoke_installer.ps1" not in build_text or "INSTALLER_SMOKE_TEST.json" not in build_text:
        fail("Windows build does not execute and retain the installer smoke test")
    if "installer_smoke_test_passed" not in finalizer_text or "INSTALLER_SMOKE_TEST.json" not in finalizer_text:
        fail("Finalizer is not bound to the Windows installer smoke-test report")
    ok("Windows installer smoke test is mandatory and release-bound")
    if 'Name: "{group}\\Ultra Stalker Desktop"' not in iss_text:
        fail("Installer Start Menu shortcut is not tied to the selected program group")
    production_app_id = "{8B1EF58E-7E5F-4D2F-9BC5-7A5D0C1E2026}"
    if "AppId={code:GetAppId}" not in iss_text or "function GetAppId" not in iss_text:
        fail("Installer AppId is not isolated through the scripted production/smoke identity")
    if production_app_id not in iss_text or "{param:SMOKETEST|}" not in iss_text or "-smoke-" not in iss_text:
        fail("Installer smoke AppId isolation is incomplete")
    if '"/SMOKETEST=$SmokeId"' not in smoke_text:
        fail("Installer smoke test does not use an isolated random AppId")
    if "'/NOICONS'" not in smoke_text or "'/TASKS='" not in smoke_text:
        fail("Installer smoke test may leave user shortcuts behind")
    if "[InstallDelete]" not in iss_text or "{app}\\_internal" not in iss_text:
        fail("Installer does not clean stale PyInstaller runtime files during upgrade")
    ok("Installer upgrade cleanup preserves AppData and removes stale runtime payload")
    if "THIRD_PARTY_NOTICES.txt" not in iss_text or "licenses" not in iss_text:
        # The installer includes dist\UltraStalkerDesktop recursively, so this
        # guard is mostly documentary: it also ensures upgrade cleanup knows
        # about the bundled notice/license payload.
        if "{app}\\licenses" not in iss_text:
            fail("Installer upgrade rules do not account for bundled license files")
    verifier_text = (root / "tools" / "verify_final_release.ps1").read_text(encoding="utf-8", errors="replace")
    if "Get-FileHash -Algorithm SHA256" not in verifier_text or "FINAL_RELEASE.json" not in verifier_text:
        fail("Final release verification script does not verify installer SHA256")
    if "INSTALLER_SMOKE_TEST.json" not in verifier_text or "installer_smoke_test_passed" not in verifier_text:
        fail("Final release verifier does not verify the installer smoke-test evidence")
    if "runtime_database_integrity" not in verifier_text:
        fail("Final release verifier does not enforce runtime database-integrity evidence")
    for registry_field in ("smoke_registry_isolated", "production_registry_unchanged", "smoke_registry_removed"):
        if registry_field not in verifier_text:
            fail(f"Final release verifier does not enforce smoke registry isolation: {registry_field}")
    if "Ultra Stalker 8.4.1" not in verifier_text or "UltraStalker_V7_UPDATE.ipk" not in verifier_text:
        fail("Final release verifier does not verify reference identity")
    for token in ("build_environment", "python_version_file_sha256", "build_dependencies_sha256", "dependency_lock_sha256", "python_runtime_provenance_sha256", "python_runtime_license_sha256"):
        if token not in verifier_text:
            fail(f"Final release verifier does not enforce build environment identity: {token}")
    if "VERIFY_RELEASE.ps1" not in build_text or "VERIFY_INSTALLED.ps1" not in build_text or "WINDOWS_ACCEPTANCE.md" not in build_text:
        fail("Final release does not include release/installed verification and acceptance documents")
    installed_verifier = root / "tools" / "verify_installed_runtime.ps1"
    if not installed_verifier.is_file():
        fail("Installed Windows runtime verifier is missing")
    installed_verifier_text = installed_verifier.read_text(encoding="utf-8", errors="replace")
    for required in ("UltraStalkerDesktop.exe", "mpv.exe", "SELF_TEST.json", "RELEASE_SHA256.json", "--self-test", "report_kind", "runtime_platform", "python_bits", "qt_platform", "credential_cleanup", "database_integrity", "release_integrity", "Get-FileHash -LiteralPath"):
        if required not in installed_verifier_text:
            fail(f"Installed Windows runtime verifier is missing check: {required}")
    if "Ahmed L-HadarY" not in installed_verifier_text or "Ultra Stalker Desktop" not in installed_verifier_text:
        fail("Installed Windows runtime verifier does not bind release identity")
    ok("Final release verification bundle is enforced")

    readme = (root / "README.md").read_text(encoding="utf-8", errors="replace")
    acceptance = (root / "WINDOWS_ACCEPTANCE.md").read_text(encoding="utf-8", errors="replace")
    for token in ("session-only", "schema version 1", "read-only integrity diagnostics", "corruption markers"):
        if token not in readme:
            fail(f"README is missing current persistence/security behavior: {token}")
    for token in ("PRAGMA user_version", "session-only connection", "corruption marker", "SQLite integrity status"):
        if token not in acceptance:
            fail(f"Windows acceptance is missing current persistence/security check: {token}")
    ok("Persistence/security documentation matches the current release behavior")

    ok("Generated Python caches are excluded from release source checks")

    # Guard against accidentally committing literal credentials into runtime source.
    suspicious_names = {"password", "passwd", "api_key", "apikey", "token", "secret"}
    literal_secrets = []
    for path in py_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            continue
        for node in ast.walk(tree):
            pairs = []
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                pairs = [(t.id, node.value.value) for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and isinstance(node.value, ast.Constant):
                pairs = [(node.target.id, node.value.value)]
            for name, value in pairs:
                if name.lower() in suspicious_names and isinstance(value, str) and value.strip():
                    # Test fixtures use deliberate fake values; runtime source may not.
                    if "tests" not in path.parts:
                        literal_secrets.append(f"{path.relative_to(root)}:{name}")
    if literal_secrets:
        fail("Hard-coded credential literals found: " + ", ".join(literal_secrets))
    ok("No hard-coded runtime credential literals found")


def dist_gate(dist: Path) -> None:
    for path in walk_payload(dist):
        if _payload_is_linklike(path):
            fail("Release payload contains symlink/junction path: " + str(path.relative_to(dist)).replace("\\", "/"))
    exe = dist / "UltraStalkerDesktop.exe"
    mpv = dist / "mpv.exe"
    provenance = dist / "provenance.json"
    build_deps = dist / "BUILD_DEPENDENCIES.txt"
    dependency_lock = dist / "WINDOWS_DEPENDENCY_LOCK.txt"
    python_version = dist / "PYTHON_VERSION.txt"
    mpv_provenance = dist / "MPV_PROVENANCE.json"
    self_test = dist / "SELF_TEST.json"
    notices = dist / "THIRD_PARTY_NOTICES.txt"
    license_dir = dist / "licenses"
    runtime_license_manifest = license_dir / "python" / "PYTHON_RUNTIME_LICENSES.json"
    python_runtime_license = license_dir / "PYTHON_LICENSE.txt"
    python_runtime_provenance = license_dir / "PYTHON_RUNTIME_PROVENANCE.json"
    license_files = [
        license_dir / "GPL-2.0.txt",
        license_dir / "GPL-3.0.txt",
        license_dir / "LGPL-2.1.txt",
        license_dir / "LGPL-3.0.txt",
    ]
    for needed in (exe, mpv, provenance, build_deps, dependency_lock, python_version, mpv_provenance, self_test, notices, runtime_license_manifest, python_runtime_license, python_runtime_provenance, *license_files):
        if not needed.is_file():
            fail(f"Release payload missing {needed.relative_to(dist).as_posix()}")
    if notices.stat().st_size < 500 or any(path.stat().st_size < 5000 for path in license_files):
        fail("Release payload contains incomplete third-party notice/license text")
    if python_runtime_license.stat().st_size < 1000:
        fail("Bundled CPython runtime license is unexpectedly small")
    try:
        license_manifest = json.loads(runtime_license_manifest.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        fail(f"Invalid Python runtime license manifest: {exc}")
    distributions = license_manifest.get("distributions") or []
    names = {str(item.get("name", "")).lower() for item in distributions if isinstance(item, dict)}
    missing_roots = sorted({"pyside6", "requests", "keyring", "pywin32-ctypes"} - names)
    if missing_roots:
        fail("Runtime license manifest is missing root packages: " + ", ".join(missing_roots))
    if not all(isinstance(item.get("license_files"), list) for item in distributions if isinstance(item, dict)):
        fail("Runtime license manifest has invalid license file metadata")
    try:
        python_runtime_meta = json.loads(python_runtime_provenance.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        fail(f"Invalid CPython runtime provenance: {exc}")
    if python_runtime_meta.get("product") != "CPython" or python_runtime_meta.get("implementation") != "CPython":
        fail("CPython runtime provenance has the wrong product/implementation")
    if python_runtime_meta.get("license_file") != "PYTHON_LICENSE.txt":
        fail("CPython runtime provenance points to an unexpected license file")
    if python_runtime_meta.get("license_sha256") != sha256(python_runtime_license):
        fail("CPython runtime license SHA256 does not match its provenance")
    version_text = python_version.read_text(encoding="utf-8-sig", errors="replace").strip()
    expected_python_version = version_text.removeprefix("Python ").strip()
    if not expected_python_version or python_runtime_meta.get("version") != expected_python_version:
        fail("CPython runtime provenance version does not match PYTHON_VERSION.txt")
    if any(key in python_runtime_meta for key in ("source_path", "base_prefix", "interpreter_path")):
        fail("CPython runtime provenance leaks a build-machine path")
    source_license_name = str(python_runtime_meta.get("source_license_name") or "")
    if not source_license_name or Path(source_license_name).name != source_license_name:
        fail("CPython runtime provenance contains an unsafe source license path")
    ok("CPython runtime license is present and bound to the exact build interpreter")
    dependency_text = build_deps.read_text(encoding="utf-8-sig", errors="replace")
    dependency_lower = dependency_text.lower()
    required_dependencies = ("pyside6==", "requests==", "keyring==", "pywin32-ctypes==", "pyinstaller==", "packaging==")
    missing_dependencies = [name[:-2] for name in required_dependencies if name not in dependency_lower]
    if missing_dependencies:
        fail("BUILD_DEPENDENCIES.txt is missing required distributions: " + ", ".join(missing_dependencies))
    release_root_pins = {
        "pyside6==6.11.2",
        "requests==2.34.2",
        "keyring==25.7.0",
        "pywin32-ctypes==0.2.3",
        "pyinstaller==6.22.2",
        "packaging==26.3",
    }
    frozen_lines = {line.strip().lower() for line in dependency_text.splitlines() if line.strip()}
    missing_pins = sorted(release_root_pins - frozen_lines)
    if missing_pins:
        fail("Final build environment does not contain the pinned Windows release roots: " + ", ".join(missing_pins))
    lock_text = dependency_lock.read_text(encoding="utf-8-sig", errors="replace")
    lock_lines = {line.strip().lower() for line in lock_text.splitlines() if line.strip()}
    invalid_lock_lines = sorted(line for line in lock_lines if not re.fullmatch(r"[a-z0-9_.-]+==[^\s]+", line))
    if invalid_lock_lines:
        fail("WINDOWS_DEPENDENCY_LOCK.txt contains non-version-pinned dependencies: " + ", ".join(invalid_lock_lines[:5]))
    dependency_normalized = (dependency_text + "\n" + lock_text).lower().replace(chr(92), "/")
    local_dependency_patterns = (" @ file:", " @ file://", "-e file:", "-e .", "/users/", "/home/")
    if any(pattern in dependency_normalized for pattern in local_dependency_patterns):
        fail("Dependency manifests contain a local/direct build-machine dependency")
    if lock_lines != frozen_lines:
        fail("BUILD_DEPENDENCIES.txt does not exactly match WINDOWS_DEPENDENCY_LOCK.txt")
    ok("Executable, mpv runtime, self-test, license payload, and exact dependency lock present")

    try:
        self_test_data = json.loads(self_test.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"Invalid SELF_TEST.json: {exc}")
    if self_test_data.get("passed") is not True:
        fail("Packaged self-test did not pass")
    if self_test_data.get("report_kind") != "build":
        fail("Packaged SELF_TEST.json is not a release build self-test report")
    checks = self_test_data.get("checks") or {}
    mandatory_checks = ("sqlite", "mpv", "credential_manager", "credential_cleanup", "qt_runtime")
    missing_or_failed = [name for name in mandatory_checks if checks.get(name) is not True]
    if missing_or_failed:
        fail("Packaged self-test mandatory checks missing/failed: " + ", ".join(missing_or_failed))
    if checks.get("qt_platform") != "windows":
        fail("Packaged self-test did not exercise the real Windows Qt platform")
    if checks.get("python_bits") != 64:
        fail("Packaged self-test did not run under a 64-bit Python runtime")
    runtime_platform = str(checks.get("runtime_platform") or "").lower()
    if not runtime_platform.startswith("win"):
        fail("Packaged self-test did not run on Windows")
    tested = self_test_data.get("artifacts") or {}
    if tested.get("application_sha256") != sha256(exe):
        fail("Packaged self-test is not bound to the final application executable")
    if tested.get("mpv_sha256") != sha256(mpv):
        fail("Packaged self-test is not bound to the final mpv executable")
    ok("Packaged self-test hashes match the final executable payload")

    try:
        data = json.loads(provenance.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"Invalid provenance.json: {exc}")
    expected = {
        "product": PRODUCT,
        "version": VERSION,
        "developer": DEVELOPER,
        "platform": "windows-x64",
        "reference": REFERENCE,
        "reference_artifact": "UltraStalker_V7_UPDATE.ipk",
        "reference_artifact_sha256": "d845f917a3a1507c454a7848dd12714ffe720bf568966e0196c06f14f2131876",
        "reference_parity": "behavioral-reference; original 8.4.1 source bytes unavailable",
    }
    for key, value in expected.items():
        if data.get(key) != value:
            fail(f"Provenance mismatch for {key}: {data.get(key)!r}")
    if data.get("reference_sha256") != "d845f917a3a1507c454a7848dd12714ffe720bf568966e0196c06f14f2131876":
        fail("Reference 8.4.1 SHA256 missing or changed")
    build_id = str(data.get("build_id") or "")
    if not re.fullmatch(r"USD-WIN-\d{8}-\d{6}-[0-9a-f]{8}", build_id):
        fail("Release Build ID has an invalid or non-unique format")
    try:
        build_utc = datetime.datetime.fromisoformat(str(data.get("build_utc") or ""))
    except ValueError:
        fail("Release build_utc is not valid ISO-8601")
    if build_utc.tzinfo is None or build_utc.utcoffset() != datetime.timedelta(0):
        fail("Release build_utc is not timezone-aware UTC")
    ok("Release provenance coherent")

    try:
        mpv_meta = json.loads(mpv_provenance.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        fail(f"Invalid MPV_PROVENANCE.json: {exc}")
    if mpv_meta.get("archive_sha256") != "4e197f729f5071c6772f35fffd96e0f36e3e8a044bd9479b136bb09b7c6a80ff":
        fail("mpv provenance archive SHA256 mismatch")
    if mpv_meta.get("version") != "0.41.0":
        fail("mpv provenance version mismatch")
    if mpv_meta.get("packaged_files") != ["mpv.exe"]:
        fail("mpv provenance does not describe the minimal runtime")
    if mpv_meta.get("executable_sha256") != sha256(mpv):
        fail("mpv executable SHA256 does not match its verified provenance")
    forbidden_mpv = ["mpv.pdb", "mpv.com", "mpv-register.bat", "mpv-unregister.bat"]
    present_forbidden = [name for name in forbidden_mpv if (dist / name).exists()]
    if present_forbidden:
        fail("Unneeded mpv developer/helper files present: " + ", ".join(present_forbidden))
    ok("mpv provenance coherent and runtime minimal")

    digest_file = dist / "RELEASE_SHA256.json"
    if not digest_file.is_file():
        fail("RELEASE_SHA256.json is missing from fingerprinted payload")
    try:
        hashes = json.loads(digest_file.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"Invalid RELEASE_SHA256.json: {exc}")
    expected_hashes = {
        "UltraStalkerDesktop.exe": sha256(exe),
        "mpv.exe": sha256(mpv),
    }
    if hashes != expected_hashes:
        fail("RELEASE_SHA256.json does not match final executable payload")
    files = data.get("files") or {}
    if files.get("RELEASE_SHA256.json") != sha256(digest_file):
        fail("provenance.json does not cover RELEASE_SHA256.json")
    for name, digest_value in expected_hashes.items():
        if files.get(name) != digest_value:
            fail(f"provenance.json does not cover final {name}")
    ok("Release executable hashes verified and covered by provenance")

    current_files = {}
    windows_names = {}
    for path in walk_payload(dist):
        if _payload_is_linklike(path):
            fail("Release payload contains symlink/junction path: " + str(path.relative_to(dist)).replace("\\", "/"))
        if not path.is_file() or path.name == "provenance.json":
            continue
        name = str(path.relative_to(dist)).replace("\\", "/")
        folded = name.casefold()
        previous = windows_names.get(folded)
        if previous is not None and previous != name:
            fail(f"Windows case-insensitive payload path collision: {previous} <> {name}")
        windows_names[folded] = name
        current_files[name] = sha256(path)
    if current_files != files:
        recorded_names = set(files)
        current_names = set(current_files)
        added = sorted(current_names - recorded_names)
        removed = sorted(recorded_names - current_names)
        changed = sorted(
            name for name in current_names & recorded_names
            if current_files[name] != files[name]
        )
        details = []
        if added:
            details.append("added=" + ",".join(added[:5]))
        if removed:
            details.append("removed=" + ",".join(removed[:5]))
        if changed:
            details.append("changed=" + ",".join(changed[:5]))
        fail("Complete payload does not match provenance manifest: " + "; ".join(details))
    ok("Complete portable payload matches the provenance manifest")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--dist")
    args = p.parse_args()
    root = Path(args.root).resolve()
    static_gate(root)
    if args.dist:
        dist_gate(Path(args.dist).resolve())
    print("[OK] Ultra Stalker Desktop release gate passed")


if __name__ == "__main__":
    main()
