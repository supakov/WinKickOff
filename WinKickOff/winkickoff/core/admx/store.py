"""The store of imports next to the program (admx/<id>/ with import.json and policies.json): ids, names, the
trust order, saving, listing, strict loading and deletion."""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from winkickoff.core import jsonfile
from winkickoff.core.catalog import IMPORT_KINDS, import_kind, import_rank
from winkickoff.core.admx.base import (
    FORMAT_VERSION,
    READ_FORMATS,
    META_FILE,
    DATA_FILE,
    IMPORT_ID_RE,
    _CONTROL,
    AdmxError,
)
from winkickoff.core.admx.check import check_templates, conform

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- store


@dataclass(frozen=True)
class ImportInfo:
    id: str
    name: str
    folder: str
    created: str
    windows: str
    cultures: tuple[str, ...]
    policies: int
    skipped: int
    renamed: bool = False  # the user gave the name; an update of the import keeps it


MAX_NAME = 120
# The source of an import is the first word of its id. When two imports hold the same policy, the rule comes from the
# most trusted source: the catalogs that ship with the program, then the templates of this Windows, then a folder of
# templates, then a catalog file (core/package.py); the other trees show it as an alias with the same check mark.
def trust_order(import_ids: Iterable[str]) -> list[str]:
    """The ids in the order their rules are made: by source (IMPORT_KINDS of core/catalog.py), then as given."""
    ids = list(dict.fromkeys(import_ids))
    position = {import_id: index for index, import_id in enumerate(ids)}
    return sorted(ids, key=lambda i: (import_rank(import_kind(i)), position[i]))


def check_name(name: str) -> str:
    """The name of an import (the title of its tree) with single spaces; AdmxError when it cannot be one."""
    name = " ".join(str(name).split())
    if not name or len(name) > MAX_NAME or set(name) & set(_CONTROL):
        raise AdmxError(f"bad name {jsonfile.short(name)}")
    return name


def fit_name(name: str) -> str:
    """A name made by the program (a folder name and a date, or a name saved by an older version) cut to MAX_NAME."""
    name = " ".join(str(name).replace(chr(0), " ").split())
    return check_name(name if len(name) <= MAX_NAME else name[:MAX_NAME - 3].rstrip() + "...")


def system_folder() -> Path:
    """PolicyDefinitions of this Windows (read only)."""
    return Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "C:\\Windows") / "PolicyDefinitions"


def new_import_id(admx_root: Path, kind: str, now: datetime) -> str:
    base = f"{kind}-{now:%Y%m%d-%H%M%S}"
    candidate, index = base, 2
    while (admx_root / candidate).exists():
        candidate, index = f"{base}-{index}", index + 1
    return candidate


def _write_file(path: Path, text: str) -> None:
    """Through a temporary file in the same folder, so an interrupted update never leaves half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)


def _meta(info: ImportInfo, files: int) -> str:
    meta = {"format": FORMAT_VERSION, "id": info.id, "name": info.name, "renamed": info.renamed, "folder": info.folder,
            "created": info.created, "windows": info.windows, "cultures": list(info.cultures), "policies": info.policies,
            "skipped": info.skipped, "files": files}
    return (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n")


def same_folder(a: str | Path, b: str | Path) -> bool:
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))
    except OSError:
        return False


def find_imports(admx_root: Path, folder: Path) -> list[ImportInfo]:
    """Saved imports of the same folder, oldest first."""
    return [info for info in list_imports(admx_root) if same_folder(info.folder, folder)]


def save_import(admx_root: Path, folder: Path, data: dict[str, Any], *, system: bool, now: datetime | None = None,
                replace: ImportInfo | None = None) -> ImportInfo:
    """Keep an import in admx_root/<id>/ (the program folder) and return its description. With replace, that import
    is updated in place: same id (so the tree and the profiles keep working), a name the user gave is kept."""
    now = now or datetime.now()
    kind = "system" if system else "folder"
    import_id = replace.id if replace is not None else new_import_id(admx_root, kind, now)
    windows = platform.version() if system else ""
    label = f"PolicyDefinitions {windows}" if system and windows else folder.name or str(folder)
    stamp = f", {now:%Y-%m-%d %H:%M}"
    if len(label) + len(stamp) > MAX_NAME:  # a long folder name: the date stays, the folder name is cut
        label = label[:MAX_NAME - len(stamp) - 3].rstrip() + "..."
    return store_import(admx_root, import_id, str(folder), data, label + stamp, windows, now=now, replace=replace)


def store_import(admx_root: Path, import_id: str, source: str, data: dict[str, Any], name: str, windows: str, *,
                 now: datetime | None = None, replace: ImportInfo | None = None) -> ImportInfo:
    """Keep checked records as admx_root/<import_id>/ (policies.json and import.json). With replace, that import is
    updated in place, and a name the user gave it is kept."""
    check_templates(data)
    now = now or datetime.now()
    renamed = replace is not None and replace.renamed
    info = ImportInfo(import_id, replace.name if renamed else check_name(name), source, now.isoformat(timespec="seconds"),
                      windows, tuple(data.get("cultures", [])), len(data.get("policies", [])), len(data.get("skipped", [])),
                      renamed)
    records = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    meta = _meta(info, int(data.get("files", 0)))
    records.encode("utf-8"), meta.encode("utf-8")  # a text that cannot be written fails before the folder is made
    target = admx_root / import_id
    target.mkdir(parents=True, exist_ok=replace is not None or import_kind(import_id) == "bundled")
    _write_file(target / DATA_FILE, records)
    _write_file(target / META_FILE, meta)
    log.info("templates imported from %s as %s%s: %d policies, %d skipped", source, import_id,
             " (updated)" if replace is not None else "", info.policies, info.skipped)
    return info


def rename_import(admx_root: Path, import_id: str, name: str) -> ImportInfo:
    """Give an import a name of the user's choice (the title of its tree)."""
    name = check_name(name)
    info, data = load_import(admx_root, import_id)
    renamed = ImportInfo(info.id, name, info.folder, info.created, info.windows, info.cultures, info.policies, info.skipped, True)
    _write_file(admx_root / import_id / META_FILE, _meta(renamed, int(data.get("files", 0))))
    return renamed


MAX_META_BYTES = 64 * 1024
MAX_RECORDS_BYTES = 64 * 1024 * 1024


def _info(meta: Any) -> ImportInfo:
    """The description of an import from its import.json; AdmxError unless every field has the type it should."""
    if not isinstance(meta, dict):
        raise AdmxError("import.json must hold an object")
    import_id = meta.get("id", "")
    fmt = meta.get("format", 0)
    if not isinstance(import_id, str) or not IMPORT_ID_RE.match(import_id) or fmt not in READ_FORMATS or isinstance(fmt, bool):
        raise AdmxError(f"unsupported import {jsonfile.short(import_id)}")
    texts = {key: meta.get(key, default) for key, default in
             (("name", import_id), ("folder", ""), ("created", ""), ("windows", ""))}
    counts = {key: meta.get(key, 0) for key in ("policies", "skipped", "files")}
    cultures = meta.get("cultures", [])
    if (not all(isinstance(v, str) and len(v) <= 4096 for v in texts.values())
            or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in counts.values())
            or not isinstance(cultures, list) or not all(isinstance(c, str) and len(c) <= 40 for c in cultures)
            or not isinstance(meta.get("renamed", False), bool)):
        raise AdmxError(f"{import_id}: import.json has a field of the wrong type")
    return ImportInfo(import_id, texts["name"], texts["folder"], texts["created"], texts["windows"], tuple(cultures),
                      counts["policies"], counts["skipped"], meta.get("renamed") is True)


def _read_meta(folder: Path) -> ImportInfo:
    try:
        return _info(jsonfile.read(folder / META_FILE, file_limit=MAX_META_BYTES, json_limit=MAX_META_BYTES))
    except jsonfile.JsonFileError as exc:
        raise AdmxError(f"{folder.name}: import.json: {exc}") from exc


def list_imports(admx_root: Path) -> list[ImportInfo]:
    """Saved imports, oldest first; broken ones are left out (and logged)."""
    found: list[ImportInfo] = []
    if not admx_root.is_dir():
        return found
    for folder in sorted(admx_root.iterdir()):
        meta_path = folder / META_FILE
        if not (folder.is_dir() and IMPORT_ID_RE.match(folder.name) and meta_path.is_file()):
            continue
        try:
            info = _read_meta(folder)
            if info.id == folder.name:
                found.append(info)
        except AdmxError as exc:
            log.warning("import %s skipped: %s", folder.name, exc)
    return sorted(found, key=lambda i: (i.created, i.id))


def load_import(admx_root: Path, import_id: str) -> tuple[ImportInfo, dict[str, Any]]:
    if not IMPORT_ID_RE.match(import_id):
        raise AdmxError(f"bad import id {import_id!r}")
    folder = admx_root / import_id
    info = _read_meta(folder)
    if info.id != import_id:  # the kind of an import and its group ids come from its folder, never from a file in it
        raise AdmxError(f"{import_id}: import.json names another import ({jsonfile.short(info.id)})")
    try:  # the folder is writable by anyone who can change the program folder: read and check it like a package
        data = jsonfile.read(folder / DATA_FILE, file_limit=MAX_RECORDS_BYTES, json_limit=MAX_RECORDS_BYTES, nulls=True)
        conform(data)  # an import of an older version may hold a policy the parser now skips; it checks each policy
        check_templates(data, policies=False)  # so only the sections are checked again
    except (jsonfile.JsonFileError, AdmxError) as exc:
        raise AdmxError(f"{import_id}: {exc}") from exc
    return info, data


def delete_import(admx_root: Path, import_id: str) -> None:
    """Remove one saved import (a folder this program created inside its own folder)."""
    if not IMPORT_ID_RE.match(import_id):
        raise AdmxError(f"bad import id {import_id!r}")
    folder = (admx_root / import_id).resolve()
    if folder.parent != admx_root.resolve() or not (folder / META_FILE).is_file():
        raise AdmxError(f"{import_id}: not an import folder")
    shutil.rmtree(folder)
