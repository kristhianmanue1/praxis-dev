#!/usr/bin/env python3.12
"""Build a reproducible ``praxis.pyz`` zipapp from the ``praxis_dev`` package.

The zipapp is the distribution artifact (``docs/distribucion-homebrew.md``): it
bundles the package plus a synthetic top-level ``__main__.py`` and a shebang,
but NOT the interpreter and NOT ``jsonschema`` (the runtime is stdlib-only).

Reproducibility: entries are written in sorted order with a fixed timestamp
(1980-01-01 00:00:00 UTC, the zipapp epoch), fixed file mode, and deterministic
DEFLATE compression. Given identical sources, two builds are byte-identical.

This script is a build tool, not a runtime dependency. It writes to ``dist/``
by default (gitignored); pass ``--output`` to target a temp directory in CI.
"""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "praxis_dev"
DEFAULT_OUTPUT = ROOT / "dist" / "praxis.pyz"
INTERPRETER = "python3.12"
# Fixed timestamp for every zip entry -> deterministic output.
EPOCH = (1980, 1, 1, 0, 0, 0)

_MAIN_TEMPLATE = b"""\
import sys
from praxis_dev.cli import main

if __name__ == "__main__":
    sys.exit(main())
"""


def _package_entries() -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = [("__main__.py", _MAIN_TEMPLATE)]
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix not in {".py"}:
            continue
        arcname = path.relative_to(ROOT).as_posix()
        entries.append((arcname, path.read_bytes()))
    entries.sort(key=lambda item: item[0])
    return entries


def build(target: Path = DEFAULT_OUTPUT) -> Path:
    """Build ``praxis.pyz`` at ``target`` and return its path."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    entries = _package_entries()
    with target.open("wb") as handle:
        handle.write(f"#!/usr/bin/env {INTERPRETER}\n".encode("ascii"))
        with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for arcname, data in entries:
                info = zipfile.ZipInfo(arcname, date_time=EPOCH)
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
    target.chmod(0o755)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    target = build(args.output)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"built {target} ({len(entries_for_log())} entries) sha256:{digest}")
    return 0


def entries_for_log() -> list[str]:
    return [arcname for arcname, _ in _package_entries()]


if __name__ == "__main__":
    raise SystemExit(main())
