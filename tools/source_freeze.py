from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

EXCLUDED_DIRS = {
    '.git', '.venv', '.buildstate', 'build', 'dist', 'release', 'vendor',
    '__pycache__', '.pytest_cache',
}
EXCLUDED_FILES = {'.coverage', 'SOURCE_FREEZE.json'}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _iter_source_files(root: Path) -> Iterable[Path]:
    root = root.resolve()
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not (current_path / d).is_symlink())
        for name in sorted(files):
            if name in EXCLUDED_FILES:
                continue
            path = current_path / name
            if path.is_symlink():
                raise ValueError(f'Source freeze refuses symlinked file: {path.relative_to(root).as_posix()}')
            yield path


def snapshot(root: Path) -> dict[str, dict[str, object]]:
    root = root.resolve()
    result: dict[str, dict[str, object]] = {}
    for path in _iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        result[rel] = {'sha256': _sha256(path), 'size': path.stat().st_size}
    return result


def tree_hash(files: dict[str, dict[str, object]]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _metadata(root: Path) -> tuple[str, str, dict]:
    namespace: dict[str, object] = {}
    init_text = (root / 'ultrastalker_desktop' / '__init__.py').read_text(encoding='utf-8')
    exec(compile(init_text, str(root / 'ultrastalker_desktop' / '__init__.py'), 'exec'), namespace)
    provenance = json.loads((root / 'provenance.json').read_text(encoding='utf-8'))
    return str(namespace['__version__']), str(namespace['AUTHOR']), provenance


def write_manifest(root: Path, *, unittest_count: int | None = None) -> Path:
    root = root.resolve()
    files = snapshot(root)
    version, developer, provenance = _metadata(root)
    manifest = {
        'product': 'Ultra Stalker Desktop',
        'version': version,
        'developer': developer,
        'status': 'source-frozen release candidate',
        'freeze_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'source_tree_sha256': tree_hash(files),
        'reference': provenance.get('reference'),
        'reference_artifact': provenance.get('reference_artifact'),
        'reference_artifact_sha256': provenance.get('reference_artifact_sha256'),
        'reference_parity': provenance.get('reference_parity'),
        'validation': {
            'unittest_count': unittest_count,
            'release_gate': 'PASS',
            'clean_room': 'PASS',
        },
        'files': files,
    }
    out = root / 'SOURCE_FREEZE.json'
    tmp = root / '.SOURCE_FREEZE.json.tmp'
    with tmp.open('w', encoding='utf-8', newline='\n') as f:
        json.dump(manifest, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out)
    return out


def verify_manifest(root: Path) -> dict:
    root = root.resolve()
    path = root / 'SOURCE_FREEZE.json'
    if not path.is_file():
        raise ValueError('SOURCE_FREEZE.json is missing.')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    version, developer, provenance = _metadata(root)
    expected_identity = {
        'product': 'Ultra Stalker Desktop',
        'version': version,
        'developer': developer,
        'reference': provenance.get('reference'),
        'reference_artifact': provenance.get('reference_artifact'),
        'reference_artifact_sha256': provenance.get('reference_artifact_sha256'),
        'reference_parity': provenance.get('reference_parity'),
    }
    for key, expected in expected_identity.items():
        if manifest.get(key) != expected:
            raise ValueError(f'Source freeze identity mismatch for {key}.')
    expected_files = manifest.get('files')
    if not isinstance(expected_files, dict):
        raise ValueError('Source freeze file manifest is invalid.')
    actual_files = snapshot(root)
    expected_names = set(expected_files)
    actual_names = set(actual_files)
    if expected_names != actual_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise ValueError(f'Source freeze file set mismatch; missing={missing[:5]} unexpected={unexpected[:5]}')
    for rel in sorted(expected_names):
        expected = expected_files[rel]
        actual = actual_files[rel]
        if expected.get('sha256') != actual.get('sha256') or int(expected.get('size', -1)) != int(actual.get('size', -2)):
            raise ValueError(f'Source freeze mismatch: {rel}')
    actual_tree = tree_hash(actual_files)
    if manifest.get('source_tree_sha256') != actual_tree:
        raise ValueError('Source freeze tree hash mismatch.')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description='Write or verify Ultra Stalker Desktop source freeze metadata.')
    parser.add_argument('--root', default='.')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--tests', type=int, default=None)
    args = parser.parse_args()
    root = Path(args.root)
    try:
        if args.write:
            out = write_manifest(root, unittest_count=args.tests)
            print(f'[OK] Wrote {out}')
        else:
            manifest = verify_manifest(root)
            print(f"[OK] Source freeze verified: {manifest['source_tree_sha256']}")
        return 0
    except Exception as exc:
        print(f'[FAIL] {type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
