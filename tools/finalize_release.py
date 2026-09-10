from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

try:
    from tools.path_safety import is_linklike as _is_linklike, walk_payload
except ModuleNotFoundError:  # direct execution as tools/finalize_release.py
    from path_safety import is_linklike as _is_linklike, walk_payload

PRODUCT = "Ultra Stalker Desktop"
VERSION = "0.1.0"
DEVELOPER = "Ahmed L-HadarY"
REFERENCE = "Ultra Stalker 8.4.1"
REFERENCE_SHA256 = "d845f917a3a1507c454a7848dd12714ffe720bf568966e0196c06f14f2131876"
REFERENCE_ARTIFACT = "UltraStalker_V7_UPDATE.ipk"
REFERENCE_PARITY = "behavioral-reference; original 8.4.1 source bytes unavailable"
TRANSIENT_BUILD_MARKER = ".ultrastalker-build-self-test"
SMOKE_REPORT = "INSTALLER_SMOKE_TEST.json"
SOURCE_FREEZE_NAME = "SOURCE_FREEZE.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_freeze_identity() -> tuple[Path, dict, str]:
    path = Path(__file__).resolve().parents[1] / SOURCE_FREEZE_NAME
    if not path.is_file():
        raise SystemExit("SOURCE_FREEZE.json not found during finalization")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid SOURCE_FREEZE.json: {type(exc).__name__}") from None
    tree = str(obj.get("source_tree_sha256") or "").lower()
    if len(tree) != 64 or any(ch not in "0123456789abcdef" for ch in tree):
        raise SystemExit("SOURCE_FREEZE.json has an invalid source_tree_sha256")
    return path, obj, sha256(path)


def payload_files(dist: Path) -> dict[str, str]:
    files = {}
    windows_names = {}
    for path in walk_payload(dist):
        if _is_linklike(path):
            name = str(path.relative_to(dist)).replace("\\", "/")
            raise SystemExit(f"Release payload contains symlink/junction path: {name}")
        if not path.is_file() or path.name == "provenance.json":
            continue
        name = str(path.relative_to(dist)).replace("\\", "/")
        windows_key = name.casefold()
        previous = windows_names.get(windows_key)
        if previous is not None and previous != name:
            raise SystemExit(
                f"Windows case-insensitive payload path collision: {previous} <> {name}"
            )
        windows_names[windows_key] = name
        files[name] = sha256(path)
    return files


def payload_root_hash(files: dict[str, str]) -> str:
    # A compact digest of the canonical path->SHA256 manifest. This is not a
    # substitute for per-file verification; it gives FINAL_RELEASE.json a
    # convenient single identity for the complete portable payload.
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_distribution(dist: Path) -> None:
    """Re-run the distribution gate and preserve its human-readable reason."""
    try:
        from tools.release_gate import dist_gate
    except ModuleNotFoundError:  # direct execution as tools/finalize_release.py
        from release_gate import dist_gate

    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            dist_gate(dist)
    except SystemExit as exc:
        lines = [line.strip() for line in output.getvalue().splitlines() if line.strip()]
        reason = next((line[7:] for line in reversed(lines) if line.startswith("[FAIL] ")), None)
        raise SystemExit(reason or f"distribution release gate failed ({exc.code})") from None


def validate_installer_smoke_report(dist: Path, installer: Path, provenance: dict) -> tuple[Path, dict]:
    smoke_path = installer.parent / SMOKE_REPORT
    if not smoke_path.is_file():
        raise SystemExit("installer smoke-test report not found")
    try:
        smoke = json.loads(smoke_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SystemExit(f"invalid installer smoke-test report: {exc}") from None

    expected = {
        "product": PRODUCT,
        "version": VERSION,
        "developer": DEVELOPER,
        "platform": "windows-x64",
        "build_id": provenance.get("build_id"),
    }
    for key, value in expected.items():
        if smoke.get(key) != value:
            raise SystemExit(f"installer smoke-test mismatch for {key}")

    required_true = (
        "passed",
        "installed_payload_verified",
        "runtime_self_test_passed",
        "payload_immutable_after_runtime_test",
        "smoke_registry_isolated",
        "production_registry_unchanged",
        "smoke_registry_removed",
        "upgrade_passed",
        "upgrade_user_data_preserved",
        "upgrade_stale_runtime_cleanup_passed",
        "uninstall_passed",
        "uninstall_user_data_preserved",
    )
    failed = [name for name in required_true if smoke.get(name) is not True]
    if failed:
        raise SystemExit("installer smoke-test checks missing/failed: " + ", ".join(failed))
    if smoke.get("runtime_release_integrity") != "ok":
        raise SystemExit("installer smoke-test runtime integrity did not pass")
    if smoke.get("runtime_database_integrity") not in {"ok", "not_created"}:
        raise SystemExit("installer smoke-test user database integrity did not pass")
    if smoke.get("installer_sha256") != sha256(installer):
        raise SystemExit("installer smoke-test is not bound to the final installer")
    provenance_path = dist / "provenance.json"
    if smoke.get("portable_provenance_sha256") != sha256(provenance_path):
        raise SystemExit("installer smoke-test is not bound to the portable provenance")
    try:
        count = int(smoke.get("installed_payload_file_count"))
    except (TypeError, ValueError):
        count = 0
    if count != len(provenance.get("files") or {}) + 1:
        # +1 is provenance.json, which deliberately cannot include its own hash.
        raise SystemExit("installer smoke-test installed payload file count mismatch")
    runtime_hash = str(smoke.get("runtime_self_test_sha256") or "")
    if len(runtime_hash) != 64 or any(c not in "0123456789abcdef" for c in runtime_hash.lower()):
        raise SystemExit("installer smoke-test runtime self-test SHA256 is invalid")
    return smoke_path, smoke


def finalize_release(dist: Path, installer: Path) -> Path:
    dist = Path(dist).resolve()
    installer = Path(installer).resolve()
    if (dist / TRANSIENT_BUILD_MARKER).exists():
        raise SystemExit("transient build self-test marker present in final payload")
    provenance_path = dist / "provenance.json"
    if not provenance_path.is_file():
        raise SystemExit("portable provenance.json not found")
    if not installer.is_file():
        raise SystemExit("installer not found")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    build_id = str(provenance.get("build_id") or "")
    import re
    if not re.fullmatch(r"USD-WIN-\d{8}-\d{6}-[0-9a-f]{8}", build_id):
        raise SystemExit("provenance Build ID has an invalid or non-unique format")
    for key, expected in {
        "product": PRODUCT,
        "version": VERSION,
        "developer": DEVELOPER,
        "reference": REFERENCE,
        "reference_sha256": REFERENCE_SHA256,
        "reference_artifact": REFERENCE_ARTIFACT,
        "reference_artifact_sha256": REFERENCE_SHA256,
        "reference_parity": REFERENCE_PARITY,
    }.items():
        if provenance.get(key) != expected:
            raise SystemExit(f"provenance mismatch for {key}")

    source_freeze_path, source_freeze, source_freeze_sha256 = source_freeze_identity()
    for key, expected in {
        "source_tree_sha256": source_freeze.get("source_tree_sha256"),
        "source_freeze_sha256": source_freeze_sha256,
        "source_freeze_file": SOURCE_FREEZE_NAME,
    }.items():
        if provenance.get(key) != expected:
            raise SystemExit(f"source freeze mismatch for {key}")

    recorded_files = provenance.get("files")
    if not isinstance(recorded_files, dict) or not recorded_files:
        raise SystemExit("portable provenance file manifest is missing")
    current_files = payload_files(dist)
    if current_files != recorded_files:
        recorded_names = set(recorded_files)
        current_names = set(current_files)
        added = sorted(current_names - recorded_names)
        removed = sorted(recorded_names - current_names)
        changed = sorted(
            name for name in current_names & recorded_names
            if current_files[name] != recorded_files[name]
        )
        details = []
        if added:
            details.append("added=" + ",".join(added[:5]))
        if removed:
            details.append("removed=" + ",".join(removed[:5]))
        if changed:
            details.append("changed=" + ",".join(changed[:5]))
        raise SystemExit("portable payload changed after fingerprint: " + "; ".join(details))

    # Re-run all distribution policy checks after proving the payload is still
    # byte-for-byte identical to the fingerprinted manifest. This keeps tamper
    # errors precise while making the finalizer safe as a standalone entrypoint.
    validate_distribution(dist)

    smoke_path, smoke = validate_installer_smoke_report(dist, installer, provenance)

    self_test = dist / "SELF_TEST.json"
    self_test_passed = False
    if self_test.is_file():
        try:
            self_test_passed = bool(json.loads(self_test.read_text(encoding="utf-8")).get("passed"))
        except Exception:
            pass
    if not self_test_passed:
        raise SystemExit("packaged self-test did not pass")

    python_version_path = dist / "PYTHON_VERSION.txt"
    build_dependencies_path = dist / "BUILD_DEPENDENCIES.txt"
    dependency_lock_path = dist / "WINDOWS_DEPENDENCY_LOCK.txt"
    python_runtime_provenance_path = dist / "licenses" / "PYTHON_RUNTIME_PROVENANCE.json"
    python_runtime_license_path = dist / "licenses" / "PYTHON_LICENSE.txt"
    python_runtime_meta = json.loads(python_runtime_provenance_path.read_text(encoding="utf-8-sig"))
    python_version_value = python_version_path.read_text(encoding="utf-8-sig", errors="replace").strip().removeprefix("Python ").strip()

    obj = {
        "product": PRODUCT,
        "version": VERSION,
        "developer": DEVELOPER,
        "platform": "windows-x64",
        "build_id": provenance.get("build_id"),
        "build_utc": provenance.get("build_utc"),
        "reference": REFERENCE,
        "reference_sha256": REFERENCE_SHA256,
        "reference_artifact": REFERENCE_ARTIFACT,
        "reference_artifact_sha256": REFERENCE_SHA256,
        "reference_parity": REFERENCE_PARITY,
        "source_tree_sha256": provenance.get("source_tree_sha256"),
        "source_freeze_sha256": source_freeze_sha256,
        "source_freeze_file": SOURCE_FREEZE_NAME,
        "installer": {
            "name": installer.name,
            "size": installer.stat().st_size,
            "sha256": sha256(installer),
        },
        "portable_provenance_sha256": sha256(provenance_path),
        "portable_payload_file_count": len(current_files),
        "portable_payload_root_sha256": payload_root_hash(current_files),
        "build_environment": {
            "python_version": python_version_value,
            "python_version_file_sha256": sha256(python_version_path),
            "build_dependencies_sha256": sha256(build_dependencies_path),
            "dependency_lock_sha256": sha256(dependency_lock_path),
            "python_runtime_provenance_sha256": sha256(python_runtime_provenance_path),
            "python_runtime_license_sha256": sha256(python_runtime_license_path),
            "python_runtime_license_recorded_sha256": python_runtime_meta.get("license_sha256"),
        },
        "self_test_passed": True,
        "installer_smoke_test_passed": True,
        "installer_smoke_test_sha256": sha256(smoke_path),
        "runtime_self_test_sha256": smoke.get("runtime_self_test_sha256"),
        "runtime_database_integrity": smoke.get("runtime_database_integrity"),
    }

    source_freeze_output = installer.parent / SOURCE_FREEZE_NAME
    source_freeze_output.write_bytes(source_freeze_path.read_bytes())
    if sha256(source_freeze_output) != source_freeze_sha256:
        raise SystemExit("copied SOURCE_FREEZE.json hash mismatch")

    output = installer.parent / "FINAL_RELEASE.json"
    output.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    (installer.with_suffix(installer.suffix + ".sha256.txt")).write_text(
        f'{obj["installer"]["sha256"]}  {installer.name}\n', encoding="ascii"
    )
    return output


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: finalize_release.py <dist-dir> <installer.exe>")
    output = finalize_release(Path(sys.argv[1]), Path(sys.argv[2]))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
