"""Compress the catalog packages of catalogs/ with xz for the portable build (tools/build.ps1).

Every catalogs/<name>.json is checked (core/package.py reads it as the program will), written as
<target>/<name>.json.xz and read back; the program then reads the compressed file with the same size limits. The
repository keeps the plain JSON, so a change of a catalog shows in the history line by line.

    cd WinKickOff
    python tools/pack_catalogs.py <target folder>
"""

from __future__ import annotations

import lzma
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from winkickoff.core.package import bundled_collisions, read_package  # noqa: E402


def pack(source: Path, target: Path) -> list[Path]:
    """Write <target>/<name>.json.xz for every <source>/<name>.json; return the files written. Two files that would get
    the same import id (the menu could offer only one of them) stop the build."""
    collisions = bundled_collisions(source)
    if collisions:
        raise SystemExit("catalogs with the same import id: " + "; ".join(
            f"{import_id}: {', '.join(files)}" for import_id, files in sorted(collisions.items())))
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for path in sorted(source.glob("*.json")):
        package = read_package(path)
        packed = target / (path.name + ".xz")
        packed.write_bytes(lzma.compress(path.read_bytes(), format=lzma.FORMAT_XZ, preset=9 | lzma.PRESET_EXTREME))
        if read_package(packed) != package:
            raise SystemExit(f"{packed.name}: the compressed catalog differs from {path.name}")
        print(f"{path.name}: {path.stat().st_size // 1024} KB -> {packed.name}: {packed.stat().st_size // 1024} KB, "
              f"{len(package.templates['policies'])} policies")
        written.append(packed)
    return written


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    files = pack(ROOT / "catalogs", Path(sys.argv[1]))
    print(f"{len(files)} catalogs packed")
