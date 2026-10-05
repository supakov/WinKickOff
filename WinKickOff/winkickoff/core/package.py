"""Catalog packages: the records of imported policy templates in one JSON file (task T23, editor 1.3.0).

A package is what "Export imported templates" writes and "Import a catalog file" reads, and the form of the catalogs
that ship with the program (catalogs/ next to the rules; the portable build compresses them with xz). It holds the
records exactly as core/admx.py keeps them in admx/<id>/policies.json, inside an envelope:

    {"format": "winkickoff-catalog", "version": 1, "kind": "admx", "name": "...", "windows": "10.0.26200",
     "created": "2026-10-04T12:00:00", "comment": ["..."], "templates": {...the records...}}

A package is untrusted input, like a template file: it is read with size limits, plain or compressed with gzip or xz
(core/jsonfile.py), every record is checked by admx.check_templates, and nothing of it runs. Its policies become rules
that a person switches on, and the answer file writes their registry values as for any imported template. An import
of a package is kept like an import of templates (admx/<id>/), with the id "package-<date>-<time>", or
"bundled-<file name>" for a catalog of the program.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from winkickoff.core import jsonfile
from winkickoff.core.admx import (
    IMPORT_ID_RE,
    AdmxError,
    ImportInfo,
    check_name,
    fit_name,
    check_templates,
    list_imports,
    load_import,
    new_import_id,
    same_folder,
    store_import,
    without_paths,
)

PACKAGE_FORMAT = "winkickoff-catalog"
PACKAGE_VERSION = 1
PACKAGE_KINDS = ("admx",)
ENVELOPE_KEYS = ("format", "version", "kind", "name", "windows", "created", "comment", "templates")
MAX_PACKAGE_FILE = 64 * 1024 * 1024  # as stored: a compressed catalog of every template of Windows takes about 0.85 MB
MAX_PACKAGE_JSON = 64 * 1024 * 1024  # unpacked: the same catalog takes about 13 MB (and jsonfile.MAX_ITEMS bounds it)
WINDOWS_RE = re.compile(r"^[0-9][0-9.]{0,31}$")  # the Windows version of the templates: "10.0.26200"


@dataclass(frozen=True)
class Package:
    name: str
    windows: str
    created: str
    comment: tuple[str, ...]
    templates: dict[str, Any]


@dataclass(frozen=True)
class BundledCatalog:
    """A catalog package that ships with the program (catalogs/<file>)."""

    path: Path
    import_id: str
    label: str


def package_id(text: str) -> str:
    """Lowercase words joined by "-": a part of an import id made of a file name."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-") or "catalog"


def _stem(path: Path) -> str:
    name = path.name
    for suffix in sorted(jsonfile.SUFFIXES, key=len, reverse=True):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def envelope(info: ImportInfo, templates: dict[str, Any], comment: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"format": PACKAGE_FORMAT, "version": PACKAGE_VERSION, "kind": "admx",
                           "name": fit_name(info.name), "windows": info.windows, "created": info.created}
    if comment:
        out["comment"] = list(comment)
    out["templates"] = templates
    return out


def export_package(admx_root: Path, import_id: str, target: Path) -> ImportInfo:
    """Write a saved import as a package file (canonical JSON, not compressed). The folder the templates came from
    is not written, and the messages about unreadable files keep only file names: they are paths of this computer."""
    info, data = load_import(admx_root, import_id)
    data = dict(data, problems=[without_paths(problem) for problem in data.get("problems", [])])
    text = jsonfile.dumps(envelope(info, data))
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    tmp.replace(target)
    return info


def parse_package(value: Any) -> Package:
    """The envelope and the records of a package, checked; AdmxError otherwise."""
    if not isinstance(value, dict) or value.get("format") != PACKAGE_FORMAT:
        raise AdmxError(f"not a WinKickOff catalog file (\"format\" must be \"{PACKAGE_FORMAT}\")")
    unknown = set(value) - set(ENVELOPE_KEYS)
    if unknown:
        raise AdmxError(f"unknown fields {sorted(unknown)}")
    version = value.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != PACKAGE_VERSION:
        raise AdmxError(f"catalog file version {jsonfile.short(version)}; this program reads version {PACKAGE_VERSION}")
    if value.get("kind") not in PACKAGE_KINDS:
        raise AdmxError(f"unknown kind {jsonfile.short(value.get('kind'))}")
    windows, created, comment = value.get("windows", ""), value.get("created", ""), value.get("comment", [])
    if not isinstance(windows, str) or windows and not WINDOWS_RE.match(windows):
        raise AdmxError(f"bad Windows version {jsonfile.short(windows)}")
    if not isinstance(created, str) or len(created) > 40 or not re.fullmatch(r"[0-9T:.+\- ]*", created):
        raise AdmxError("bad date of creation")
    if not isinstance(comment, list) or len(comment) > 100 or not all(isinstance(c, str) and len(c) <= 1000 for c in comment):
        raise AdmxError("'comment' must be a list of lines")
    name = check_name(value.get("name") if isinstance(value.get("name"), str) else "")
    templates = value.get("templates")
    check_templates(templates)
    return Package(name, windows, created, tuple(comment), templates)


def read_package(path: Path) -> Package:
    """A package file, plain or compressed; AdmxError with the reason when it cannot be imported."""
    try:
        value = jsonfile.read(path, file_limit=MAX_PACKAGE_FILE, json_limit=MAX_PACKAGE_JSON, nulls=True)
    except jsonfile.JsonFileError as exc:
        raise AdmxError(f"{path.name}: {exc}") from exc
    try:
        return parse_package(value)
    except AdmxError as exc:
        raise AdmxError(f"{path.name}: {exc}") from exc


def find_package_imports(admx_root: Path, path: Path) -> list[ImportInfo]:
    """Saved imports of the same package file, oldest first."""
    return [info for info in list_imports(admx_root) if info.id.startswith("package-") and same_folder(info.folder, path)]


def import_package(admx_root: Path, path: Path, package: Package | None = None, *, replace: ImportInfo | None = None,
                   now: datetime | None = None) -> ImportInfo:
    """Keep a package file as an import (admx/package-<date>-<time>/); with replace, update that import in place."""
    package = package or read_package(path)
    now = now or datetime.now()
    import_id = replace.id if replace is not None else new_import_id(admx_root, "package", now)
    return store_import(admx_root, import_id, str(path), package.templates, package.name, package.windows, now=now,
                        replace=replace)


def _bundled_files(folder: Path) -> list[BundledCatalog]:
    try:
        files = sorted(p for p in folder.iterdir() if p.is_file())
    except OSError:
        return []
    found = []
    for path in files:
        if path.name.lower().endswith(jsonfile.SUFFIXES):
            stem = _stem(path)
            import_id = "bundled-" + package_id(stem)
            if IMPORT_ID_RE.match(import_id):
                found.append(BundledCatalog(path, import_id, stem))
    return found


def bundled_catalogs(folder: Path) -> list[BundledCatalog]:
    """The catalogs that ship with the program: catalogs/*.json, *.json.gz and *.json.xz (one per import id; the
    build refuses two files with the same id, see bundled_collisions)."""
    found: dict[str, BundledCatalog] = {}
    for catalog in _bundled_files(folder):
        found.setdefault(catalog.import_id, catalog)
    return sorted(found.values(), key=lambda c: c.label.lower())


def bundled_collisions(folder: Path) -> dict[str, list[str]]:
    """Import ids that two or more files of the folder would get ("Windows 11.json" and "windows-11.json"), with the
    file names; tools/pack_catalogs.py refuses them, because the menu could show only one of the files."""
    names: dict[str, list[str]] = {}
    for catalog in _bundled_files(folder):
        names.setdefault(catalog.import_id, []).append(catalog.path.name)
    return {import_id: files for import_id, files in names.items() if len(files) > 1}


def import_bundled(admx_root: Path, catalog: BundledCatalog, package: Package | None = None, *,
                   now: datetime | None = None) -> ImportInfo:
    """Keep a catalog of the program as the import "bundled-<name>"; an import of it again updates that import."""
    package = package or read_package(catalog.path)
    replace = next((info for info in list_imports(admx_root) if info.id == catalog.import_id), None)
    return store_import(admx_root, catalog.import_id, catalog.path.name, package.templates, package.name, package.windows,
                        now=now, replace=replace)
