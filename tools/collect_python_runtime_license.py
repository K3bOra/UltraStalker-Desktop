from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _license_candidates(base_prefix: Path) -> list[Path]:
    # Standard CPython Windows installers place LICENSE.txt in the interpreter
    # root. Keep a small compatibility set for alternative official layouts.
    return [
        base_prefix / "LICENSE.txt",
        base_prefix / "LICENSE",
        base_prefix / "license.txt",
    ]


def collect_python_runtime_license(
    output_dir: Path,
    *,
    base_prefix: Path | None = None,
    version: str | None = None,
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = Path(base_prefix or sys.base_prefix).resolve()
    source = next((p for p in _license_candidates(base) if p.is_file()), None)
    if source is None:
        raise RuntimeError(
            "CPython runtime LICENSE.txt was not found beside the build interpreter. "
            "Refusing to create a Windows release without the interpreter license."
        )

    destination = output_dir / "PYTHON_LICENSE.txt"
    destination.write_bytes(source.read_bytes())
    digest = _sha256(destination)
    runtime_version = str(version or platform.python_version())
    provenance = {
        "product": "CPython",
        "version": runtime_version,
        "implementation": platform.python_implementation(),
        "license_file": destination.name,
        "license_sha256": digest,
        # Never persist an absolute build-machine path in release metadata.
        "source_license_name": source.name,
    }
    (output_dir / "PYTHON_RUNTIME_PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return provenance


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: collect_python_runtime_license.py <licenses-dir>")
    data = collect_python_runtime_license(Path(sys.argv[1]))
    print(f"[OK] CPython {data['version']} runtime license collected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
