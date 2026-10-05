# Catalogs of the program

Catalog packages that ship with WinKickOff: policy templates already imported, so a person can add, for example,
the policies of Windows 11 25H2 from the menu "ADMX", "Import a catalog of the program", without the templates on
the computer. The format is described in `../winkickoff/core/package.py` and in
`../../docs/technical/editor/03-data-model.md`, section 10.

- `<name>.json`: a package in the canonical layout (`tools/format_catalog.py`, checked by
  `tests/test_catalog_format.py` and `tests/test_package.py`); the file name without `.json` is the label of the menu
  entry and gives the import id `bundled-<the name in lowercase words>` ("Windows 11 25H2.json" gives
  `bundled-windows-11-25h2`). Two files that give the same id stop the build.
- Made by `tools/make_admx_catalogs.py` from a folder of ADMX and ADML files; edit the templates, not the package.
- The portable build compresses every package with xz into `_internal/catalogs/<name>.json.xz`
  (`tools/pack_catalogs.py`, called by `tools/build.ps1`); the repository keeps the plain JSON, so a change shows in
  the history line by line. The program also reads `*.json.gz` and `*.json.xz` here, but only `*.json` files are
  packed into the build.
- A package is untrusted input like any catalog file: the program reads it with size limits and checks every record
  before it imports anything.
- The texts of the templates are kept as Microsoft or the vendor wrote them, so the packages are outside the check for
  dashes: `tests/test_sources.py` does not read them, and the dash search of `AGENTS.md` (section 5) skips this folder.
  This README itself is checked like every Markdown file.

Status (04.10.2026): no package is committed yet. Microsoft templates may be shipped only after the license check
that the customer asked for; until then the folder holds only this file, and the menu entry is greyed out.
