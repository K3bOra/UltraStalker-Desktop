from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import re
import shutil
import sys
from pathlib import Path

try:
    from packaging.requirements import Requirement
except Exception:  # packaging is part of the Windows build toolchain via pip
    Requirement = None

ROOTS = ("PySide6", "requests", "keyring")
LICENSE_WORDS = ("license", "licence", "copying", "notice", "copyright", "authors")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_distributions() -> list[metadata.Distribution]:
    by_name = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            by_name[norm(name)] = dist

    queue = list(ROOTS)
    seen: set[str] = set()
    out: list[metadata.Distribution] = []
    while queue:
        requested = queue.pop(0)
        key = norm(requested)
        if key in seen:
            continue
        seen.add(key)
        dist = by_name.get(key)
        if not dist:
            continue
        out.append(dist)
        for raw in dist.requires or []:
            try:
                req = Requirement(raw) if Requirement else None
                if req is None:
                    continue
                if req.marker is not None and not req.marker.evaluate():
                    continue
                queue.append(req.name)
            except Exception:
                continue
    return sorted(out, key=lambda d: norm(d.metadata.get("Name", "")))


def is_license_file(rel: Path) -> bool:
    lower_parts = [p.lower() for p in rel.parts]
    name = rel.name.lower()
    if "licenses" in lower_parts or "license" in lower_parts:
        return True
    return any(word in name for word in LICENSE_WORDS)


def safe_rel(rel: Path) -> Path:
    # Keep just enough hierarchy to distinguish multiple notices while avoiding
    # paths outside the distribution metadata root.
    parts = [re.sub(r"[^A-Za-z0-9._-]+", "_", p) for p in rel.parts[-4:]]
    return Path(*parts)


def collect(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    distributions = runtime_distributions()
    discovered = {norm(d.metadata.get("Name", "")) for d in distributions}
    missing_roots = [name for name in ROOTS if norm(name) not in discovered]
    if missing_roots:
        raise RuntimeError("Missing runtime distributions: " + ", ".join(missing_roots))
    if sys.platform.startswith("win") and norm("pywin32-ctypes") not in discovered:
        raise RuntimeError("Missing Windows credential bridge distribution: pywin32-ctypes")
    records = []
    for dist in distributions:
        name = dist.metadata.get("Name", "unknown")
        version = dist.version
        target = output / re.sub(r"[^A-Za-z0-9._-]+", "_", f"{name}-{version}")
        copied = []
        for entry in dist.files or []:
            rel = Path(str(entry))
            if not is_license_file(rel):
                continue
            src = Path(dist.locate_file(entry))
            if not src.is_file():
                continue
            dst = target / safe_rel(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(dst.relative_to(output).as_posix())
        records.append({
            "name": name,
            "version": version,
            "license_expression": dist.metadata.get("License-Expression") or "",
            "license_metadata": dist.metadata.get("License") or "",
            "license_files": sorted(set(copied)),
        })
    manifest = {
        "roots": list(ROOTS),
        "missing_roots": [],
        "distributions": records,
    }
    (output / "PYTHON_RUNTIME_LICENSES.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()
    manifest = collect(Path(args.output))
    if not manifest["distributions"]:
        raise SystemExit("No runtime Python distributions were discovered")
    print(f"[OK] Runtime license metadata collected for {len(manifest['distributions'])} distributions")


if __name__ == "__main__":
    main()
