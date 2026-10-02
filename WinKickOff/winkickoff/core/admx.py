"""Policy templates (ADMX files with their ADML translations) imported as catalog rules.

An import reads every *.admx of a folder (by default the PolicyDefinitions folder of this Windows) and the ADML
files of the wanted languages, keeps what the rules need in <program folder>/admx/<id>/ (import.json: name,
source, counts; policies.json: the policies), and turns the policies into the rules of a subtree
"admx.<id>" in the interface language. Every text of that subtree comes from the ADML files; en-US is the
fallback.

A policy becomes:
- one rule with the parameter "state" (Enabled or Disabled) when both states set the same single value;
- otherwise a rule for the Enabled state with the policy elements as parameters, plus a rule for the Disabled
  state when that state writes values; the two rules conflict.
A list element (a key with a variable number of values) becomes a parameter of type "list" and a reg-list
action: value names are the data itself, valuePrefix with a number, or given by each item ("name=value") for
explicitValue; a list that is not additive deletes the other values of its key first, and the Disabled rule
leaves the key without values, as Group Policy does. A multiText element is a "list" parameter written as one
MultiString value.
Machine policies write HKLM in the specialize pass; user policies write the default user profile (DU:), so
every account created during installation gets them. Rule ids follow the template namespace and the policy
name ("admx.<namespace>.<policy>"), so a profile keeps its choices across imports of the same templates.
Policies with value lists inside an option or unsafe characters are skipped and counted with the reason.

Template files are untrusted data: documents with a DTD or entities are refused, files and folders have size
limits, and keys, value names and strings with control characters, "$", backquotes, double quotes, typographic
quotes or "]]>" are refused, because they end up inside PowerShell strings and CDATA sections.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from winkickoff.core.catalog import IMPORTED_PREFIX, Action, Catalog, Group, Param, Rule, RuleOrigin, merge
from winkickoff.core.i18n import N_, tr

log = logging.getLogger(__name__)

FORMAT_VERSION = 2  # 2: list and multiText elements (1.1.0-rc.2); imports of format 1 still load
READ_FORMATS = (1, 2)
LEGACY_SKIPS = ("list", "multitext")  # reasons of format 1 for elements that are converted now
META_FILE = "import.json"
DATA_FILE = "policies.json"
SOURCE_CULTURE = "en-US"
MAX_FILES = 3000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_DWORD = 0x7FFFFFFF  # larger values do not fit the signed DWORD that PowerShell writes
MAX_QWORD = 0x7FFFFFFFFFFFFFFF
IMPORT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REF_RE = re.compile(r"^\$\((string|presentation)\.([^)]+)\)$")
_DECLARATION_RE = re.compile(r"^\s*<\?xml[^>]*\?>")
_TYPOGRAPHIC_QUOTES = "".join(chr(c) for c in (0x2018, 0x2019, 0x201A, 0x201B, 0x201C, 0x201D, 0x201E))
_CONTROL = "".join(chr(c) for c in range(32)) + chr(127)
_UNSAFE_NAME = set(_CONTROL + '"`$' + _TYPOGRAPHIC_QUOTES)
_UNSAFE_VALUE = set(_CONTROL + _TYPOGRAPHIC_QUOTES)

# why a policy was not imported; shown translated in the import summary
SKIP_REASONS: dict[str, str] = {
    "valuelist": N_("an option or a check box that writes several values"),
    "unsafe": N_("characters that are not safe in a script"),
    "range": N_("a number outside the range Windows PowerShell writes"),
    "novalue": N_("nothing to write (no value name)"),
    "broken": N_("a template error"),
}
SIDE_TITLES = {"machine": N_("Computer policies (HKLM, written during installation)"),
               "user": N_("User policies (default user profile)")}
NO_CATEGORY = N_("Without a category")
IMPORTED_RISK = N_("Imported from a policy template; WinKickOff has not reviewed this policy. Check its effect in "
                   "a virtual machine before using it on work computers.")
STATE_TITLE = N_("Policy state")
STATE_ENABLED = N_("Enabled")
STATE_DISABLED = N_("Disabled")
TITLE_ENABLED = N_("{0} (Enabled)")
TITLE_DISABLED = N_("{0} (Disabled)")
ON, OFF = N_("On"), N_("Off")
VALUE = N_("Value")
NO_EXPLAIN = N_("The template has no description of this policy.")


class AdmxError(ValueError):
    """A folder or file that cannot be imported."""


# --------------------------------------------------------------------------- XML helpers


def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _kids(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [child for child in element if _local(child.tag) == name] if element is not None else []


def _kid(element: ET.Element | None, name: str) -> ET.Element | None:
    found = _kids(element, name)
    return found[0] if found else None


def read_xml(path: Path) -> ET.Element:
    """Parse one template file; refuse big files and documents with a DTD or entities."""
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise AdmxError(f"{path.name}: {size} bytes, more than {MAX_FILE_BYTES}")
    data = path.read_bytes()
    try:
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = data.decode("utf-16")
        elif data[:3] == b"\xef\xbb\xbf":
            text = data[3:].decode("utf-8")
        elif data[1:2] == b"\x00":
            text = data.decode("utf-16-le")
        else:
            text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdmxError(f"{path.name}: {exc}") from exc
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise AdmxError(f"{path.name}: DTDs and entities are not allowed")
    # the file is decoded here; some templates declare encodings the parser does not know ("unicode")
    text = _DECLARATION_RE.sub("", text, count=1)
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise AdmxError(f"{path.name}: {exc}") from exc


def safe_name(text: str) -> bool:
    """A registry key or value name that can go into a PowerShell string of the generated scripts."""
    return bool(text) and not (set(text) & _UNSAFE_NAME) and len(text) <= 512


def safe_value(text: str) -> bool:
    return not (set(text) & _UNSAFE_VALUE) and "]]>" not in text and len(text) <= 4096


# --------------------------------------------------------------------------- ADML


@dataclass
class _Adml:
    strings: dict[str, str] = field(default_factory=dict)
    presentations: dict[str, ET.Element] = field(default_factory=dict)


class _Languages:
    """ADML files of the chosen cultures, read on first use."""

    def __init__(self, folder: Path, cultures: list[str], problems: list[str]) -> None:
        self.folder = folder
        self.cultures = cultures
        self.problems = problems
        self._cache: dict[tuple[str, str], _Adml] = {}

    def adml(self, culture: str, stem: str) -> _Adml:
        key = (culture, stem.lower())
        if key not in self._cache:
            found = _Adml()
            path = self.folder / culture / f"{stem}.adml"
            if path.is_file():
                try:
                    root = read_xml(path)
                    resources = _kid(root, "resources")
                    for item in _kids(_kid(resources, "stringTable"), "string"):
                        if item.get("id"):
                            found.strings[str(item.get("id"))] = (item.text or "").strip()
                    for item in _kids(_kid(resources, "presentationTable"), "presentation"):
                        if item.get("id"):
                            found.presentations[str(item.get("id"))] = item
                except (OSError, AdmxError) as exc:
                    self.problems.append(f"{culture}/{path.name}: {exc}")
            self._cache[key] = found
        return self._cache[key]

    def texts(self, ref: str | None, stem: str) -> dict[str, str]:
        """$(string.X) of a template in every culture that has it."""
        match = _REF_RE.match(ref or "")
        if not match or match.group(1) != "string":
            return {}
        result: dict[str, str] = {}
        for culture in self.cultures:
            text = self.adml(culture, stem).strings.get(match.group(2))
            if text:
                result[culture] = text
        return result

    def presentation(self, ref: str | None, stem: str) -> dict[str, ET.Element]:
        match = _REF_RE.match(ref or "")
        if not match or match.group(1) != "presentation":
            return {}
        result: dict[str, ET.Element] = {}
        for culture in self.cultures:
            found = self.adml(culture, stem).presentations.get(match.group(2))
            if found is not None:
                result[culture] = found
        return result


def adml_cultures(folder: Path, codes: Iterable[str]) -> list[str]:
    """Subfolders with ADML files whose language is one of codes ("ru" takes ru-RU), en-US first."""
    wanted = {code.split("-")[0].lower() for code in codes} | {"en"}
    found: list[str] = []
    try:
        folders = sorted(p for p in folder.iterdir() if p.is_dir())
    except OSError:
        return []
    for sub in folders:
        if sub.name.split("-")[0].lower() in wanted and any(sub.glob("*.adml")):
            found.append(sub.name)
    found.sort(key=lambda name: (name.lower() != SOURCE_CULTURE.lower(), name.lower()))
    return found


def pick(texts: dict[str, str] | None, language: str) -> str:
    """The text of a culture of the interface language (ru-RU for "ru"), else en-US, else any."""
    if not texts:
        return ""
    code = language.lower()
    same = sorted((c for c in texts if c.split("-")[0].lower() == code), key=lambda c: (c.lower() != f"{code}-{code}", c))
    for culture in same + [SOURCE_CULTURE] + sorted(texts):
        if texts.get(culture):
            return texts[culture]
    return ""


# --------------------------------------------------------------------------- ADMX to policy records


class _Skip(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _number(text: str | None, limit: int) -> int:
    try:
        value = int(str(text).strip())
    except (TypeError, ValueError) as exc:
        raise _Skip("broken") from exc
    if value < 0 or value > limit:
        raise _Skip("range")
    return value


def _value(container: ET.Element | None) -> tuple[str, Any] | None:
    """<decimal>, <longDecimal>, <string> or <delete/> inside a value container: (kind, value); kind "delete"."""
    for child in container if container is not None else []:
        name = _local(child.tag)
        if name == "decimal":
            return "DWord", _number(child.get("value"), MAX_DWORD)
        if name == "longDecimal":
            return "QWord", _number(child.get("value"), MAX_QWORD)
        if name == "string":
            text = child.text or ""
            if not safe_value(text):
                raise _Skip("unsafe")
            return "String", text
        if name == "delete":
            return "delete", None
    return None


def _write(key: str, name: str | None, value: tuple[str, Any]) -> dict[str, Any]:
    if not name:
        raise _Skip("novalue")
    if not safe_name(key) or not safe_name(name):
        raise _Skip("unsafe")
    return {"key": key.strip("\\"), "name": name, "kind": value[0], "value": value[1]}


def _list_writes(element: ET.Element | None, key: str) -> list[dict[str, Any]]:
    if element is None:
        return []
    default_key = element.get("defaultKey") or key
    writes = []
    for item in _kids(element, "item"):
        value = _value(_kid(item, "value"))
        if value is None:
            raise _Skip("broken")
        writes.append(_write(item.get("key") or default_key, item.get("valueName"), value))
    return writes


def _param_name(element_id: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", element_id.lower()).strip("_") or "value"
    if not re.match(r"[a-z_]", base):
        base = "e_" + base
    name, index = base, 2
    while name in taken or name == "state":
        name, index = f"{base}_{index}", index + 1
    taken.add(name)
    return name


def _presentation_parts(presentations: dict[str, ET.Element]) -> tuple[dict[str, dict[str, str]], dict[str, ET.Element]]:
    """Labels of the presentation controls by refId and culture, and the controls of one culture (en-US first)
    for the defaults, which do not depend on the language."""
    labels: dict[str, dict[str, str]] = {}
    controls: dict[str, ET.Element] = {}
    for culture in sorted(presentations, key=lambda c: c.lower() != SOURCE_CULTURE.lower()):
        for control in presentations[culture]:
            ref = control.get("refId")
            if not ref:
                continue
            label = _kid(control, "label")
            text = ((label.text if label is not None else control.text) or "").strip()
            if text:
                labels.setdefault(ref, {})[culture] = text
            controls.setdefault(ref, control)
    return labels, controls


def _list_element(element: ET.Element, element_id: str, key: str, labels: dict[str, dict[str, str]],
                  taken: set[str]) -> dict[str, Any]:
    """A key with a variable number of values; the list box of the presentation has no default."""
    if not safe_name(key):
        raise _Skip("unsafe")
    explicit = element.get("explicitValue") == "true"
    record: dict[str, Any] = {"param": _param_name(element_id, taken), "key": key.strip("\\"), "label": labels.get(element_id, {}),
                              "id": element_id, "element": "list", "type": "list",
                              "kind": "ExpandString" if element.get("expandable") == "true" else "String",
                              "default": [], "required": False, "explicit": explicit,
                              "additive": element.get("additive") == "true"}
    prefix = element.get("valuePrefix")
    if prefix is not None and not explicit:  # names prefix1, prefix2, ...; an empty prefix gives 1, 2, ...
        if prefix and not safe_name(prefix):
            raise _Skip("unsafe")
        record["prefix"] = prefix
    return record


def _element(element: ET.Element, key: str, labels: dict[str, dict[str, str]], controls: dict[str, ET.Element],
             langs: _Languages, stem: str, taken: set[str]) -> dict[str, Any]:
    kind = _local(element.tag)
    element_id = element.get("id") or kind
    elem_key = element.get("key") or key
    if kind == "list":
        return _list_element(element, element_id, elem_key, labels, taken)
    name = element.get("valueName")
    if not name:
        raise _Skip("novalue")
    if not safe_name(elem_key) or not safe_name(name):
        raise _Skip("unsafe")
    control = controls.get(element_id)
    record: dict[str, Any] = {"param": _param_name(element_id, taken), "key": elem_key.strip("\\"), "name": name,
                              "label": labels.get(element_id, {}), "id": element_id}
    if kind in ("decimal", "longDecimal"):
        limit = MAX_DWORD if kind == "decimal" else MAX_QWORD
        low = _number(element.get("minValue") or "0", limit)
        high = min(_number(element.get("maxValue") or "9999", 2**64), limit)  # a larger maximum is cut to what fits
        if high < low:
            raise _Skip("broken")
        default = low
        if control is not None and control.get("defaultValue") not in (None, ""):
            try:
                default = min(max(int(str(control.get("defaultValue"))), low), high)
            except ValueError:
                pass
        stored_as_text = element.get("storeAsText") == "true"
        record.update(type="int", kind="String" if stored_as_text else ("DWord" if kind == "decimal" else "QWord"),
                      min=low, max=high, default=default)
    elif kind == "text":
        default = ""
        if control is not None:
            node = _kid(control, "defaultValue") if _local(control.tag) == "textBox" else _kid(control, "default")
            default = (node.text or "") if node is not None else ""
        if not safe_value(default):
            default = ""
        record.update(type="string", kind="ExpandString" if element.get("expandable") == "true" else "String", default=default,
                      required=element.get("required") == "true")
    elif kind == "multiText":  # one REG_MULTI_SZ value, a line per string
        record.update(element="multiText", type="list", kind="MultiString", default=[], required=element.get("required") == "true")
    elif kind == "boolean":
        if _kid(element, "trueList") is not None or _kid(element, "falseList") is not None:
            raise _Skip("valuelist")
        true = _value(_kid(element, "trueValue")) or ("DWord", 1)
        false = _value(_kid(element, "falseValue")) or ("DWord", 0)
        checked = control is not None and str(control.get("defaultChecked", "")).lower() == "true"
        if "delete" in (true[0], false[0]) or true[0] != false[0]:
            raise _Skip("valuelist")
        if true == ("DWord", 1) and false == ("DWord", 0):
            record.update(type="bool", kind="DWord", default=checked)
        else:
            record.update(type="enum", kind=true[0], values=[[true[1], None], [false[1], None]],
                          default=true[1] if checked else false[1])
    elif kind == "enum":
        values: list[list[Any]] = []
        kinds: set[str] = set()
        for item in _kids(element, "item"):
            if _kid(item, "valueList") is not None:
                raise _Skip("valuelist")
            value = _value(_kid(item, "value"))
            if value is None or value[0] == "delete":
                raise _Skip("valuelist")
            kinds.add(value[0])
            values.append([value[1], langs.texts(item.get("displayName"), stem)])
        if not values or len(kinds) != 1 or len({repr(v[0]) for v in values}) != len(values):
            raise _Skip("broken")
        index = 0
        if control is not None and control.get("defaultItem") not in (None, ""):
            try:
                index = min(max(int(str(control.get("defaultItem"))), 0), len(values) - 1)
            except ValueError:
                pass
        record.update(type="enum", kind=kinds.pop(), values=values, default=values[index][0])
    else:
        raise _Skip("broken")
    return record


def _policy(policy: ET.Element, stem: str, namespace: str, prefixes: dict[str, str], langs: _Languages) -> dict[str, Any]:
    key = policy.get("key") or ""
    if not safe_name(key):
        raise _Skip("unsafe")
    value_name = policy.get("valueName") or ""
    labels, controls = _presentation_parts(langs.presentation(policy.get("presentation"), stem))
    taken: set[str] = set()
    node = _kid(policy, "elements")
    elements = [_element(e, key, labels, controls, langs, stem, taken) for e in (list(node) if node is not None else [])]
    enabled: list[dict[str, Any]] = []
    disabled: list[dict[str, Any]] = []
    if value_name:
        enabled.append(_write(key, value_name, _value(_kid(policy, "enabledValue")) or ("DWord", 1)))
        disabled.append(_write(key, value_name, _value(_kid(policy, "disabledValue")) or ("delete", None)))
    enabled += _list_writes(_kid(policy, "enabledList"), key)
    disabled += _list_writes(_kid(policy, "disabledList"), key)
    if not enabled and not elements:
        raise _Skip("novalue")
    category = _kid(policy, "parentCategory")
    supported = _kid(policy, "supportedOn")
    return {
        "file": f"{stem}.admx",
        "namespace": namespace,
        "name": policy.get("name") or "",
        "class": policy.get("class") or "Machine",
        "category": _qualify(category.get("ref") if category is not None else "", namespace, prefixes),
        "supported": _qualify(supported.get("ref") if supported is not None else "", namespace, prefixes),
        "title": langs.texts(policy.get("displayName"), stem),
        "explain": langs.texts(policy.get("explainText"), stem),
        "enabled": enabled,
        "disabled": disabled,
        "elements": elements,
    }


def _qualify(ref: str | None, namespace: str, prefixes: dict[str, str]) -> str:
    """"prefix:name" or "name" as "namespace:name"."""
    if not ref:
        return ""
    if ":" in ref:
        prefix, name = ref.split(":", 1)
        return f"{prefixes.get(prefix, prefix)}:{name}"
    return f"{namespace}:{ref}"


def read_templates(folder: Path, codes: Iterable[str], *, progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Every policy of the *.admx files in folder, with the texts of the ADML cultures of the languages codes."""
    try:
        files = sorted(p for p in folder.glob("*.admx") if p.is_file())
    except OSError as exc:
        raise AdmxError(f"{folder}: {exc}") from exc
    if not files:
        raise AdmxError(f"{folder}: no *.admx files")
    if len(files) > MAX_FILES:
        raise AdmxError(f"{folder}: {len(files)} templates, more than {MAX_FILES}")
    problems: list[str] = []
    cultures = adml_cultures(folder, codes)
    langs = _Languages(folder, cultures, problems)
    parsed: list[tuple[str, str, dict[str, str], ET.Element]] = []
    categories: dict[str, dict[str, Any]] = {}
    supported: dict[str, dict[str, str]] = {}
    for path in files:
        try:
            root = read_xml(path)
        except (OSError, AdmxError) as exc:
            problems.append(str(exc))
            continue
        spaces = _kid(root, "policyNamespaces")
        target = _kid(spaces, "target")
        if target is None or not target.get("namespace"):
            problems.append(f"{path.name}: no target namespace")
            continue
        namespace = str(target.get("namespace"))
        prefixes = {str(u.get("prefix")): str(u.get("namespace")) for u in _kids(spaces, "using") if u.get("prefix")}
        prefixes[str(target.get("prefix") or "")] = namespace
        for category in _kids(_kid(root, "categories"), "category"):
            parent = _kid(category, "parentCategory")
            categories[f"{namespace}:{category.get('name')}"] = {
                "title": langs.texts(category.get("displayName"), path.stem),
                "parent": _qualify(parent.get("ref") if parent is not None else "", namespace, prefixes),
            }
        for definition in _kids(_kid(_kid(root, "supportedOn"), "definitions"), "definition"):
            supported[f"{namespace}:{definition.get('name')}"] = langs.texts(definition.get("displayName"), path.stem)
        parsed.append((path.stem, namespace, prefixes, root))
    policies: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for index, (stem, namespace, prefixes, root) in enumerate(parsed):
        if progress:
            progress(index + 1, len(parsed))
        for policy in _kids(_kid(root, "policies"), "policy"):
            try:
                record = _policy(policy, stem, namespace, prefixes, langs)
            except _Skip as skip:
                skipped.append({"file": f"{stem}.admx", "policy": policy.get("name") or "", "reason": skip.reason})
                continue
            record["supported"] = supported.get(record["supported"], {})
            policies.append(record)
    used = {p["category"] for p in policies}
    while True:  # keep the ancestors of used categories
        more = {categories[c]["parent"] for c in used if c in categories and categories[c]["parent"]} - used
        if not more:
            break
        used |= more
    return {
        "format": FORMAT_VERSION,
        "cultures": cultures,
        "files": len(parsed),
        "categories": {k: v for k, v in categories.items() if k in used},
        "policies": policies,
        "skipped": skipped,
        "problems": problems,
    }


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
    name = replace.name if replace is not None and replace.renamed else f"{label}, {now:%Y-%m-%d %H:%M}"
    info = ImportInfo(import_id, name, str(folder), now.isoformat(timespec="seconds"), windows, tuple(data.get("cultures", [])),
                      len(data.get("policies", [])), len(data.get("skipped", [])), replace is not None and replace.renamed)
    target = admx_root / import_id
    target.mkdir(parents=True, exist_ok=replace is not None)
    _write_file(target / DATA_FILE, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    _write_file(target / META_FILE, _meta(info, int(data.get("files", 0))))
    log.info("templates imported from %s as %s%s: %d policies, %d skipped", folder, import_id,
             " (updated)" if replace is not None else "", info.policies, info.skipped)
    return info


def rename_import(admx_root: Path, import_id: str, name: str) -> ImportInfo:
    """Give an import a name of the user's choice (the title of its tree)."""
    name = " ".join(name.split())
    if not name or len(name) > MAX_NAME or set(name) & set(_CONTROL):
        raise AdmxError(f"bad name {name!r}")
    info, data = load_import(admx_root, import_id)
    renamed = ImportInfo(info.id, name, info.folder, info.created, info.windows, info.cultures, info.policies, info.skipped, True)
    _write_file(admx_root / import_id / META_FILE, _meta(renamed, int(data.get("files", 0))))
    return renamed


def _info(meta: dict[str, Any]) -> ImportInfo:
    import_id = str(meta.get("id", ""))
    if int(meta.get("format", 0)) not in READ_FORMATS or not IMPORT_ID_RE.match(import_id):
        raise AdmxError(f"unsupported import {import_id!r}")
    return ImportInfo(import_id, str(meta.get("name", import_id)), str(meta.get("folder", "")), str(meta.get("created", "")),
                      str(meta.get("windows", "")), tuple(str(c) for c in meta.get("cultures", [])),
                      int(meta.get("policies", 0)), int(meta.get("skipped", 0)), meta.get("renamed") is True)


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
            info = _info(json.loads(meta_path.read_text(encoding="utf-8")))
            if info.id == folder.name:
                found.append(info)
        except (OSError, ValueError) as exc:
            log.warning("import %s skipped: %s", folder.name, exc)
    return sorted(found, key=lambda i: (i.created, i.id))


def load_import(admx_root: Path, import_id: str) -> tuple[ImportInfo, dict[str, Any]]:
    if not IMPORT_ID_RE.match(import_id):
        raise AdmxError(f"bad import id {import_id!r}")
    folder = admx_root / import_id
    try:
        info = _info(json.loads((folder / META_FILE).read_text(encoding="utf-8")))
        data = json.loads((folder / DATA_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdmxError(f"{import_id}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("policies"), list):
        raise AdmxError(f"{import_id}: no policies")
    return info, data


def delete_import(admx_root: Path, import_id: str) -> None:
    """Remove one saved import (a folder this program created inside its own folder)."""
    if not IMPORT_ID_RE.match(import_id):
        raise AdmxError(f"bad import id {import_id!r}")
    folder = (admx_root / import_id).resolve()
    if folder.parent != admx_root.resolve() or not (folder / META_FILE).is_file():
        raise AdmxError(f"{import_id}: not an import folder")
    shutil.rmtree(folder)


# --------------------------------------------------------------------------- policy records to rules


def _id_part(text: str, keep_dots: bool) -> str:
    parts = text.lower().split(".") if keep_dots else [text.lower()]
    cleaned = [re.sub(r"[^a-z0-9]+", "-", part).strip("-") or "x" for part in parts]
    return ".".join(cleaned)


def _action(write: dict[str, Any], prefix: str, rule_id: str, value: Any = None) -> Action:
    path = prefix + str(write["key"])
    if write["kind"] == "delete":
        return Action("reg-remove", {"path": path, "name": write["name"]}, rule_id)
    return Action("reg", {"path": path, "name": write["name"], "kind": write["kind"],
                          "value": write["value"] if value is None else value}, rule_id)


def _is_list(element: dict[str, Any]) -> bool:
    return element.get("element") == "list"


def _list_action(element: dict[str, Any], prefix: str, rule_id: str, value: Any) -> Action:
    """The values of a list element; an empty literal list (the Disabled state) leaves the key without values."""
    fields: dict[str, Any] = {"path": prefix + str(element["key"]), "kind": element["kind"], "value": value}
    if value == []:
        return Action("reg-list", fields, rule_id)
    if "prefix" in element:
        fields["prefix"] = element["prefix"]
    if element.get("explicit"):
        fields["explicit"] = True
    if element.get("additive"):
        fields["additive"] = True
    return Action("reg-list", fields, rule_id)


def _unique(actions: list[Action]) -> tuple[Action, ...]:
    """Later writes of the same value (or list) replace earlier ones (a policy value repeated by an element)."""
    seen: dict[tuple[str, str | None], Action] = {}
    for action in actions:
        name = action.fields.get("name")
        target = (str(action.fields["path"]).lower(), None if name is None else str(name).lower())
        seen.pop(target, None)
        seen[target] = action
    return tuple(seen.values())


def _param(element: dict[str, Any], language: str, only: bool) -> Param:
    # some templates leave the label empty; the only element of a policy is simply its value
    title = pick(element.get("label"), language) or (tr(VALUE) if only else element.get("id") or element["param"])
    if element["type"] == "list":
        return Param(element["param"], "list", title, list(element["default"]), required=bool(element.get("required")),
                     pairs=bool(element.get("explicit")))
    if element["type"] == "enum":
        # texts None: the two states of a check box with its own values
        values = tuple((value, tr(ON if i == 0 else OFF) if texts is None else pick(texts, language) or str(value))
                       for i, (value, texts) in enumerate(element["values"]))
        return Param(element["param"], "enum", title, element["default"], values=values)
    if element["type"] == "int":
        return Param(element["param"], "int", title, element["default"], min=element.get("min"), max=element.get("max"))
    return Param(element["param"], element["type"], title, element["default"], required=bool(element.get("required", True)))


def _texts(policy: dict[str, Any], language: str) -> tuple[str, str, str]:
    """Title, summary (the first paragraph of the explanation) and the rest of the explanation."""
    title = pick(policy.get("title"), language) or policy["name"]
    explain = pick(policy.get("explain"), language).replace("\r\n", "\n").strip()
    if not explain:
        return title, tr(NO_EXPLAIN), ""
    first, _, rest = explain.partition("\n\n")
    first = first.strip()
    if len(first) > 400:
        return title, first[:397].rstrip() + "...", explain
    return title, first, rest.strip()


def policy_rules(policy: dict[str, Any], rule_id: str, group: str, language: str, source: str) -> list[Rule]:
    """The rule of the Enabled state (or the one rule with a state parameter) and the Disabled rule, if any."""
    machine = policy.get("class") != "User"
    phase, prefix = ("specialize", "HKLM:\\") if machine else ("default-user", "DU:\\")
    title, summary, explain = _texts(policy, language)
    supported = pick(policy.get("supported"), language)
    names = sorted({str(w["name"]).lower() for w in policy["enabled"] + policy["elements"] if w.get("name")})
    tags = tuple(dict.fromkeys(["admx", policy["file"].rsplit(".", 1)[0].lower(), policy["name"].lower(), *names]))
    common = dict(group=group, phase=phase, level="optional", default=False, doc="", summary=summary, effect=explain,
                  tags=tags, risk=tr(IMPORTED_RISK), versions=supported, source=source)
    enabled, disabled, elements = policy["enabled"], policy["disabled"], policy["elements"]
    one_value = (not elements and len(enabled) == 1 and len(disabled) == 1
                 and enabled[0]["kind"] != "delete" and enabled[0]["kind"] == disabled[0]["kind"]
                 and (enabled[0]["key"].lower(), enabled[0]["name"].lower()) == (disabled[0]["key"].lower(), disabled[0]["name"].lower())
                 and enabled[0]["value"] != disabled[0]["value"])
    if one_value:
        state = Param("state", "enum", tr(STATE_TITLE), enabled[0]["value"],
                      values=((enabled[0]["value"], tr(STATE_ENABLED)), (disabled[0]["value"], tr(STATE_DISABLED))))
        action = _action(enabled[0], prefix, rule_id, "{state}")
        return [Rule(id=rule_id, title=title, params={"state": state}, actions=(action,), **common)]
    params = {e["param"]: _param(e, language, len(elements) == 1) for e in elements}
    lists = [e for e in elements if _is_list(e)]
    values = [e for e in elements if not _is_list(e)]
    # lists first: a list that is not additive deletes the other values of its key before they are written
    on_actions = [_list_action(e, prefix, rule_id, "{" + e["param"] + "}") for e in lists]
    on_actions += [_action(w, prefix, rule_id) for w in enabled]
    on_actions += [_action(e, prefix, rule_id, "{" + e["param"] + "}") for e in values]
    writes_off = [w for w in disabled if w["kind"] != "delete"]
    off_id = rule_id + ".off"
    if not writes_off:
        return [Rule(id=rule_id, title=title, params=params, actions=_unique(on_actions), **common)]
    off_actions = [_list_action(e, prefix, off_id, []) for e in lists]
    off_actions += [_action(w, prefix, off_id) for w in disabled]
    off_actions += [_action({**e, "kind": "delete"}, prefix, off_id) for e in values]
    return [
        Rule(id=rule_id, title=tr(TITLE_ENABLED, title), params=params, actions=_unique(on_actions), conflicts=(off_id,), **common),
        Rule(id=off_id, title=tr(TITLE_DISABLED, title), actions=_unique(off_actions), conflicts=(rule_id,), **common),
    ]


def _named_policies(data: dict[str, Any], language: str) -> Iterator[tuple[dict[str, Any], str]]:
    """The policies of an import with the ids of their rules: the namespace and the name, numbered when two policies
    get the same id. Profiles keep these ids, so they fit any import of the same templates."""
    ids: set[str] = set()
    ordered = sorted(data.get("policies", []), key=lambda p: (pick(p.get("title"), language) or p.get("name", "")).lower())
    for policy in ordered:
        base = f"{IMPORTED_PREFIX}{_id_part(policy['namespace'], True)}.{_id_part(policy['name'], False)}"
        rule_id, index = base, 2
        while rule_id in ids:
            rule_id, index = f"{base}-{index}", index + 1
        ids.add(rule_id)
        yield policy, rule_id


def policy_ids(data: dict[str, Any], language: str) -> set[str]:
    """The ids of the policies of an import, as their rules get them (without the "<id>.off" of a Disabled state)."""
    return {rule_id for _, rule_id in _named_policies(data, language)}


def has_policy(ids: set[str], rule_id: str) -> bool:
    """A rule id of a profile belongs to one of these policies: the policy itself or its Disabled state."""
    return rule_id in ids or (rule_id.endswith(".off") and rule_id[:-len(".off")] in ids)


@dataclass
class ImportedPart:
    groups: dict[str, Group] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    origins: dict[str, RuleOrigin] = field(default_factory=dict)
    aliases: dict[str, list[str]] = field(default_factory=dict)  # rules of imports loaded before, shown here too
    shared: int = 0  # policies of this import that are already rules


def catalog_part(info: ImportInfo, data: dict[str, Any], language: str, taken: set[str], order: int = 10000) -> ImportedPart:
    """Groups and rules of one import in the interface language. A policy that is already a rule (taken: rules
    of the imports loaded before) is shown in this tree too, as an alias of that rule: one check mark for both."""
    part = ImportedPart()
    root = f"{IMPORTED_PREFIX}{info.id}"
    categories: dict[str, dict[str, Any]] = data.get("categories", {})
    titles = {key: pick(value.get("title"), language) or key.split(":", 1)[-1] for key, value in categories.items()}
    rank = {key: index for index, key in enumerate(sorted(titles, key=lambda k: (titles[k].lower(), k)))}
    number = {key: index for index, key in enumerate(sorted(categories))}
    part.groups[root] = Group(root, info.name, order, None, "", f"admx:{info.id}")

    def group_for(side: str, category: str) -> str:
        side_id = f"{root}.{side}"
        if side_id not in part.groups:
            part.groups[side_id] = Group(side_id, tr(SIDE_TITLES[side]), 1 if side == "machine" else 2, root, "", f"admx:{info.id}")
        if category not in categories:
            other = f"{side_id}.none"
            part.groups.setdefault(other, Group(other, tr(NO_CATEGORY), 1_000_000, side_id, "", f"admx:{info.id}"))
            return other
        chain: list[str] = []
        current = category
        while current in categories and current not in chain:
            chain.append(current)
            current = categories[current]["parent"]
        parent = side_id
        for key in reversed(chain):
            group_id = f"{side_id}.c{number[key]}"
            part.groups.setdefault(group_id, Group(group_id, titles[key], rank[key], parent, "", f"admx:{info.id}"))
            parent = group_id
        return parent

    for policy, rule_id in _named_policies(data, language):
        side = "user" if policy.get("class") == "User" else "machine"
        if rule_id in taken:
            group = group_for(side, policy.get("category", ""))
            for shown in (rule_id, rule_id + ".off"):
                if shown in taken:
                    part.aliases.setdefault(shown, []).append(group)
            part.shared += 1
            continue
        try:
            rules = policy_rules(policy, rule_id, group_for(side, policy.get("category", "")), language, f"admx:{info.id}")
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("import %s: policy %s skipped: %s", info.id, policy.get("name"), exc)
            continue
        origin = RuleOrigin(info.id, info.name, info.folder, str(policy.get("file", "")), str(policy.get("name", "")))
        for rule in rules:
            part.rules[rule.id] = rule
            part.origins[rule.id] = origin
    counts = tr("{0} policies as {1} rules; {2} skipped", info.policies, len(part.rules) + len(part.aliases), info.skipped)
    if part.shared:
        counts += tr("; {0} of the policies are also in another imported tree loaded earlier, with one check mark for both",
                     part.shared)
    older = sum(1 for item in data.get("skipped", []) if item.get("reason") in LEGACY_SKIPS)
    if older:
        counts += tr("; {0} policies with lists were skipped by an earlier version of WinKickOff, import the templates "
                     "again to get them", older)
    part.groups[root] = Group(root, info.name, order, None, tr("Imported from {0} on {1}: {2}. Languages: {3}.", info.folder,
                              info.created.replace("T", " "), counts, ", ".join(info.cultures) or "-"), f"admx:{info.id}")
    return part


def with_imports(base: Catalog, admx_root: Path, import_ids: Iterable[str], language: str) -> tuple[Catalog, list[str]]:
    """The catalog with the subtrees of the given saved imports; problems are messages for the user."""
    problems: list[str] = []
    groups: dict[str, Group] = {}
    rules: dict[str, Rule] = {}
    origins: dict[str, RuleOrigin] = {}
    aliases: dict[str, list[str]] = {}
    for index, import_id in enumerate(dict.fromkeys(import_ids)):
        try:
            info, data = load_import(admx_root, import_id)
        except AdmxError as exc:
            problems.append(tr("Imported templates {0} were not loaded: {1}", import_id, exc))
            continue
        part = catalog_part(info, data, language, set(base.rules) | set(rules), 10000 + index)
        groups.update(part.groups)
        rules.update(part.rules)
        origins.update(part.origins)
        for rule_id, group_ids in part.aliases.items():
            aliases.setdefault(rule_id, []).extend(group_ids)
    if not rules and not groups:
        return base, problems
    return merge(base, groups, rules, origins, aliases), problems


def skip_summary(data: dict[str, Any]) -> list[tuple[str, int]]:
    """(reason text, count) of the skipped policies, most frequent first."""
    counts: dict[str, int] = {}
    for item in data.get("skipped", []):
        counts[item.get("reason", "broken")] = counts.get(item.get("reason", "broken"), 0) + 1
    return sorted(((tr(SKIP_REASONS.get(reason, SKIP_REASONS["broken"])), count) for reason, count in counts.items()),
                  key=lambda pair: -pair[1])
