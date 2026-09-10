from __future__ import annotations

from pathlib import Path
import datetime
import hashlib
import json
import secrets
import sys

try:
    from tools.path_safety import is_linklike as _is_linklike, walk_payload
except ModuleNotFoundError:  # direct execution as tools/release_fingerprint.py
    from path_safety import is_linklike as _is_linklike, walk_payload

PRODUCT = "Ultra Stalker Desktop"
VERSION = "0.1.0"
DEVELOPER = "Ahmed L-HadarY"
PLATFORM = "windows-x64"
REFERENCE = "Ultra Stalker 8.4.1"
REFERENCE_SHA256 = "d845f917a3a1507c454a7848dd12714ffe720bf568966e0196c06f14f2131876"
REFERENCE_ARTIFACT = "UltraStalker_V7_UPDATE.ipk"
REFERENCE_PARITY = "behavioral-reference; original 8.4.1 source bytes unavailable"
TRANSIENT_BUILD_MARKER = ".ultrastalker-build-self-test"
SOURCE_FREEZE_NAME = "SOURCE_FREEZE.json"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_freeze_identity() -> tuple[str, str]:
    path = Path(__file__).resolve().parents[1] / SOURCE_FREEZE_NAME
    if not path.is_file():
        raise SystemExit("SOURCE_FREEZE.json not found; refusing to fingerprint an unfrozen source tree")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid SOURCE_FREEZE.json: {type(exc).__name__}") from None
    tree = str(obj.get("source_tree_sha256") or "").lower()
    if len(tree) != 64 or any(ch not in "0123456789abcdef" for ch in tree):
        raise SystemExit("SOURCE_FREEZE.json has an invalid source_tree_sha256")
    return tree, digest(path)


def generate_fingerprint(root: Path) -> dict:
    root = Path(root).resolve()
    if not root.is_dir():
        raise SystemExit(f"Release directory not found: {root}")
    if (root / TRANSIENT_BUILD_MARKER).exists():
        raise SystemExit("transient build self-test marker still present; refusing to fingerprint")

    # Generate the small top-level executable digest file *before* the complete
    # payload fingerprint. This guarantees the installer payload cannot gain a
    # post-fingerprint file during release gating.
    release_hashes = {}
    for name in ("UltraStalkerDesktop.exe", "mpv.exe"):
        path = root / name
        if path.is_file():
            release_hashes[name] = digest(path)
    if release_hashes:
        (root / "RELEASE_SHA256.json").write_text(
            json.dumps(release_hashes, indent=2), encoding="utf-8"
        )

    # provenance.json is generated after all payload files exist so it cannot
    # hash itself, but it does cover RELEASE_SHA256.json and every other file.
    all_paths = list(walk_payload(root))
    linklike = [p for p in all_paths if _is_linklike(p)]
    if linklike:
        names = ", ".join(str(p.relative_to(root)).replace("\\", "/") for p in linklike[:5])
        raise SystemExit("Release payload contains symlink/junction paths: " + names)
    payload = [p for p in all_paths if p.is_file() and p.name != "provenance.json"]
    rows = {}
    windows_names = {}
    for path in payload:
        name = str(path.relative_to(root)).replace("\\", "/")
        windows_key = name.casefold()
        previous = windows_names.get(windows_key)
        if previous is not None and previous != name:
            raise SystemExit(
                f"Windows case-insensitive payload path collision: {previous} <> {name}"
            )
        windows_names[windows_key] = name
        rows[name] = digest(path)
    source_tree_sha256, source_freeze_sha256 = source_freeze_identity()
    now = datetime.datetime.now(datetime.timezone.utc)
    obj = {
        "product": PRODUCT,
        "version": VERSION,
        "developer": DEVELOPER,
        "platform": PLATFORM,
        "reference": REFERENCE,
        "reference_sha256": REFERENCE_SHA256,
        "reference_artifact": REFERENCE_ARTIFACT,
        "reference_artifact_sha256": REFERENCE_SHA256,
        "reference_parity": REFERENCE_PARITY,
        "source_tree_sha256": source_tree_sha256,
        "source_freeze_sha256": source_freeze_sha256,
        "source_freeze_file": SOURCE_FREEZE_NAME,
        "build_id": now.strftime("USD-WIN-%Y%m%d-%H%M%S-") + secrets.token_hex(4),
        "build_utc": now.isoformat(),
        "files": rows,
    }
    (root / "provenance.json").write_text(
        json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return obj


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    obj = generate_fingerprint(root)
    print(f"fingerprinted {len(obj['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
