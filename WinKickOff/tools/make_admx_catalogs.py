"""Make a catalog package of the program (catalogs/<name>.json) from a folder of ADMX templates.

The templates are read exactly as "Import templates from a folder" reads them (core/admx.py: only reading, DTDs
refused, size limits) with the ADML files of every language of the program, and written as a package
(core/package.py) in the canonical layout of tools/format_catalog.py. The menu "ADMX", "Import a catalog of the
program", lists every package of catalogs/; the portable build ships them compressed (tools/pack_catalogs.py).

Before a package is committed, the license of its templates must allow shipping them (catalogs/README.md).

    cd WinKickOff
    python tools/make_admx_catalogs.py <templates folder> <catalogs/name.json> --name "<tree name>" [--windows 10.0.26200]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from winkickoff.core import jsonfile  # noqa: E402
from winkickoff.core.admx import AdmxError, ImportInfo, check_name, read_templates  # noqa: E402
from winkickoff.core.i18n import available_languages  # noqa: E402
from winkickoff.core.package import WINDOWS_RE, envelope, parse_package  # noqa: E402


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Make a catalog package from a folder of ADMX templates.")
    parser.add_argument("folder", type=Path, help="folder with *.admx files and their language folders")
    parser.add_argument("target", type=Path, help="the package file to write (.json)")
    parser.add_argument("--name", required=True, help="the name of the tree, such as \"Windows 11 25H2 (26200)\"")
    parser.add_argument("--windows", default="", help="the Windows version of the templates, such as 10.0.26200")
    args = parser.parse_args(argv)
    if args.target.suffix.lower() != ".json":
        raise SystemExit("the package is written as plain .json; the build compresses it")
    if args.windows and not WINDOWS_RE.match(args.windows):
        raise SystemExit(f"--windows takes a version such as 10.0.26200, not {args.windows!r}")
    try:
        name = check_name(args.name)
        codes = list(available_languages(ROOT / "resources", ROOT / "rules"))
        data = read_templates(args.folder, codes)
        info = ImportInfo("bundled-x", name, "", datetime.now().isoformat(timespec="seconds"), args.windows,
                          tuple(data["cultures"]), len(data["policies"]), len(data["skipped"]))
        comment = [f"Policy templates of {name}: {data['files']} ADMX files, cultures {', '.join(data['cultures'])}.",
                   "Made by tools/make_admx_catalogs.py; edit the templates, not this file."]
        value = envelope(info, data, comment)
        package = parse_package(jsonfile.loads(jsonfile.dumps(value), nulls=True))  # checked before anything is written
    except (AdmxError, jsonfile.JsonFileError) as exc:
        raise SystemExit(f"no package written: {exc}") from None
    tmp = args.target.with_name(args.target.name + ".tmp")
    jsonfile.write(tmp, value)
    tmp.replace(args.target)
    print(f"written {args.target}: {len(package.templates['policies'])} policies, {info.skipped} skipped")


if __name__ == "__main__":
    main(sys.argv[1:])
