"""Write every JSON file of the rule catalog in the canonical layout of core/jsonfile.py.

The catalog files (rules/*.json, rules/lang/*.json) and the catalogs of the program (catalogs/*.json) are strict JSON
with two spaces of indent and short objects on one line, so that a change of one rule changes only its own lines. A
catalog of the program is a catalog file (core/package.py): it may hold null and is checked like one.
Run it after editing a file by hand; tests/test_catalog_format.py fails on a file that is not canonical.

    cd WinKickOff
    python tools/format_catalog.py           rewrite the files that are not canonical (exit code 0)
    python tools/format_catalog.py --check   only list them (exit code 1 if there are any)
A file that cannot be read is listed with the reason and left as it is (exit code 2).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from winkickoff.core import jsonfile  # noqa: E402
from winkickoff.core.admx import AdmxError  # noqa: E402
from winkickoff.core.package import MAX_PACKAGE_FILE, MAX_PACKAGE_JSON, parse_package  # noqa: E402


def catalog_files(root: Path = ROOT) -> list[Path]:
    """The JSON files kept in the canonical layout."""
    return sorted([*(root / "rules").glob("*.json"), *(root / "rules" / "lang").glob("*.json"),
                   *(root / "catalogs").glob("*.json")])


def canonical(path: Path) -> bytes:
    """The bytes the file should have: canonical JSON, CRLF line endings, UTF-8 without a byte order mark. A catalog
    of the program is read and checked as a catalog file (AdmxError when it is not one)."""
    if path.parent.name == "catalogs":
        value = jsonfile.read(path, file_limit=MAX_PACKAGE_FILE, json_limit=MAX_PACKAGE_JSON, nulls=True)
        parse_package(value)
    else:
        value = jsonfile.read(path)
    return jsonfile.dumps(value).replace("\n", "\r\n").encode("utf-8")


def main(argv: list[str], root: Path = ROOT) -> int:
    check = "--check" in argv
    wrong, broken = [], []
    for path in catalog_files(root):
        name = str(path.relative_to(root))
        try:
            expected = canonical(path)
        except (jsonfile.JsonFileError, AdmxError) as exc:
            broken.append(f"{name}: {exc}")
            continue
        if path.read_bytes() != expected:
            wrong.append(name)
            if not check:
                path.write_bytes(expected)
    for name in wrong:
        print(("not canonical: " if check else "formatted: ") + name)
    for line in broken:
        print("cannot be read: " + line)
    if broken:
        return 2
    return 1 if check and wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
