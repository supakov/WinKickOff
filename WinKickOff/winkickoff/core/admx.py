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

from winkickoff.core import jsonfile
from winkickoff.core.catalog import (IMPORT_KINDS, IMPORTED_PREFIX, Action, Catalog, Group, Param, Rule, RuleOrigin,  # noqa: F401
                                    import_kind, import_rank, merge)
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
_NOT_XML = "".join(chr(c) for c in range(0x80, 0xA0)) + chr(0xFFFE) + chr(0xFFFF)  # C1 controls, non-characters
_UNSAFE_NAME = set(_CONTROL + '"`$' + _TYPOGRAPHIC_QUOTES + _NOT_XML)
_UNSAFE_VALUE = set(_CONTROL + _TYPOGRAPHIC_QUOTES + _NOT_XML)

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
    """Parse one template file; refuse big files and documents with a DTD or entities. Messages name the file only,
    never its folder: they are kept in the records and may travel in an exported catalog file."""
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise AdmxError(f"{path.name}: {size} bytes, more than {MAX_FILE_BYTES}")
        data = path.read_bytes()
    except OSError as exc:
        raise AdmxError(f"{path.name}: {exc.strerror or type(exc).__name__}") from None
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
    return bool(text) and not (set(text) & _UNSAFE_NAME) and "]]>" not in text and len(text) <= 512


def safe_key(text: str) -> bool:
    """A registry key: a safe name whose segments are never empty, "." or ".." (PowerShell resolves ".." even with
    -LiteralPath, so a key "..\\.DEFAULT" of a user policy would leave the default user profile)."""
    if not safe_name(text):
        return False
    segments = re.split(r"[\\/]", text.strip("\\"))
    return all(segment not in ("", ".", "..") for segment in segments)


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
        if _CULTURE_RE.match(sub.name) and sub.name.split("-")[0].lower() in wanted and any(sub.glob("*.adml")):
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
    if not safe_key(key) or not safe_name(name):
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
    if not safe_key(key):
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
    if not safe_key(elem_key) or not safe_name(name):
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
    if not safe_key(key):
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
    data = {
        "format": FORMAT_VERSION,
        "cultures": cultures,
        "files": len(parsed),
        "categories": {k: v for k, v in categories.items() if k in used},
        "policies": policies,
        "skipped": skipped,
        "problems": problems,
    }
    conform(data)  # a policy the record check would refuse is skipped here, so one odd policy never stops an import
    return data


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


# --------------------------------------------------------------------------- checking stored records

# A saved import and a catalog package (core/package.py) are read back without the template parser, so their records
# are checked against what the parser produces: the same safe keys, names and values, the same kinds and ranges, known
# fields only and size limits. The keys of the registry are not limited to the policy branches: the templates of
# Windows themselves write elsewhere too (System\CurrentControlSet, Software\Microsoft).
MAX_POLICIES = 20000
MAX_ELEMENTS = 100
MAX_WRITES = 1000
MAX_OPTIONS = 1000
MAX_TEXT = 65536
MAX_TEXTS = 32
_CULTURE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8}){0,4}$")
MAX_CATEGORY_DEPTH = 32  # categories in a chain of parents; the templates of Windows nest a few levels
_PARAM_RE = re.compile(r"^[a-z_][a-z0-9_]{0,255}$")
_TEXT_CONTROL = set(_CONTROL) - set("\r\n\t")
WRITE_KINDS = ("DWord", "QWord", "String", "delete")
POLICY_CLASSES = ("Machine", "User", "Both")
_DATA_KEYS = {"format", "cultures", "files", "categories", "policies", "skipped", "problems"}
_POLICY_KEYS = {"file", "namespace", "name", "class", "category", "supported", "title", "explain", "enabled", "disabled",
                "elements"}
_ELEMENT_KEYS: dict[str, set[str]] = {  # by element kind; "label" and "id" are common
    "list": {"param", "key", "label", "id", "element", "type", "kind", "default", "required", "explicit", "additive", "prefix"},
    "multiText": {"param", "key", "name", "label", "id", "element", "type", "kind", "default", "required"},
    "int": {"param", "key", "name", "label", "id", "type", "kind", "min", "max", "default"},
    "string": {"param", "key", "name", "label", "id", "type", "kind", "default", "required"},
    "bool": {"param", "key", "name", "label", "id", "type", "kind", "default"},
    "enum": {"param", "key", "name", "label", "id", "type", "kind", "values", "default"},
}


class _Bad(Exception):
    pass


def _need(condition: bool, where: str, what: str) -> None:
    if not condition:
        raise _Bad(f"{where}: {what}")


def _check_text(value: Any, where: str, limit: int = MAX_TEXT) -> None:
    _need(isinstance(value, str) and len(value) <= limit and not (set(value) & _TEXT_CONTROL), where,
          f"a text of at most {limit} characters without control characters")


def _check_texts(value: Any, where: str) -> None:
    _need(isinstance(value, dict) and len(value) <= MAX_TEXTS, where, "texts by culture")
    for culture, text in value.items():
        _need(bool(_CULTURE_RE.match(culture)), where, f"bad culture {jsonfile.short(culture)}")
        _check_text(text, f"{where}.{culture}")


def _check_int(value: Any, low: int, high: int, where: str) -> None:
    _need(isinstance(value, int) and not isinstance(value, bool) and low <= value <= high, where,
          f"an integer from {low} to {high}")


def _check_flag(value: Any, where: str) -> None:
    _need(isinstance(value, bool), where, "true or false")


def _check_key(value: Any, where: str) -> None:
    _need(isinstance(value, str) and safe_key(value) and value == value.strip("\\"), where,
          "a registry key without unsafe characters")


def _check_name(value: Any, where: str) -> None:
    _need(isinstance(value, str) and safe_name(value), where, "a value name without unsafe characters")


def _check_value(kind: str, value: Any, where: str) -> None:
    if kind == "DWord":
        _check_int(value, 0, MAX_DWORD, where)
    elif kind == "QWord":
        _check_int(value, 0, MAX_QWORD, where)
    elif kind == "delete":
        _need(value is None, where, "null for a deleted value")
    else:
        _need(isinstance(value, str) and safe_value(value), where, "a string without unsafe characters")


def _check_write(write: Any, where: str) -> None:
    _need(isinstance(write, dict) and set(write) == {"key", "name", "kind", "value"}, where,
          "an object with key, name, kind and value")
    _check_key(write["key"], f"{where}.key")
    _check_name(write["name"], f"{where}.name")
    _need(write["kind"] in WRITE_KINDS, f"{where}.kind", f"one of {WRITE_KINDS}")
    _check_value(write["kind"], write["value"], f"{where}.value")


def _check_strings(value: Any, where: str) -> None:
    _need(isinstance(value, list) and len(value) <= MAX_OPTIONS, where, "a list of strings")
    for index, item in enumerate(value):
        _need(isinstance(item, str) and safe_value(item), f"{where}[{index}]", "a string without unsafe characters")


def _check_element(element: Any, where: str, params: set[str]) -> None:
    _need(isinstance(element, dict), where, "an object")
    kind = element.get("element") or element.get("type")
    _need(isinstance(kind, str) and kind in _ELEMENT_KEYS, where, f"unknown element {jsonfile.short(kind)}")
    allowed = _ELEMENT_KEYS[kind]
    required = allowed - {"prefix"}
    _need(required <= set(element) <= allowed, where, f"the fields {sorted(required)}")
    param = element["param"]
    _need(isinstance(param, str) and bool(_PARAM_RE.match(param)) and param != "state" and param not in params,
          f"{where}.param", "a unique parameter name")
    params.add(param)
    _check_key(element["key"], f"{where}.key")
    _check_texts(element["label"], f"{where}.label")
    _check_text(element["id"], f"{where}.id", 512)
    if "name" in allowed:
        _check_name(element["name"], f"{where}.name")
    etype, ekind, default = element["type"], element["kind"], element["default"]
    if kind == "list":
        _need((element["element"], etype) == ("list", "list") and ekind in ("String", "ExpandString"), where, "a list element")
        _check_strings(default, f"{where}.default")
        for flag in ("required", "explicit", "additive"):
            _check_flag(element[flag], f"{where}.{flag}")
        if "prefix" in element:
            prefix = element["prefix"]
            _need(isinstance(prefix, str) and (prefix == "" or safe_name(prefix)) and not element["explicit"],
                  f"{where}.prefix", "a safe prefix, not with explicit names")
    elif kind == "multiText":
        _need((element["element"], etype, ekind) == ("multiText", "list", "MultiString"), where, "a multiText element")
        _check_strings(default, f"{where}.default")
        _check_flag(element["required"], f"{where}.required")
    elif kind == "int":
        _need(ekind in ("DWord", "QWord", "String"), f"{where}.kind", "DWord, QWord or String")
        limit = MAX_DWORD if ekind == "DWord" else MAX_QWORD
        _check_int(element["min"], 0, limit, f"{where}.min")
        _check_int(element["max"], element["min"], limit, f"{where}.max")
        _check_int(default, element["min"], element["max"], f"{where}.default")
    elif kind == "string":
        _need(ekind in ("String", "ExpandString"), f"{where}.kind", "String or ExpandString")
        _need(isinstance(default, str) and safe_value(default), f"{where}.default", "a string without unsafe characters")
        _check_flag(element["required"], f"{where}.required")
    elif kind == "bool":
        _need(ekind == "DWord", f"{where}.kind", "DWord")
        _check_flag(default, f"{where}.default")
    else:  # enum: [value, texts] pairs, texts null for the two states of a check box with its own values
        _need(ekind in ("DWord", "QWord", "String"), f"{where}.kind", "DWord, QWord or String")
        values = element["values"]
        _need(isinstance(values, list) and 0 < len(values) <= MAX_OPTIONS, f"{where}.values", "a list of options")
        seen: set[str] = set()
        for index, option in enumerate(values):
            _need(isinstance(option, list) and len(option) == 2, f"{where}.values[{index}]", "a pair [value, texts]")
            _check_value(ekind, option[0], f"{where}.values[{index}]")
            if option[1] is not None:
                _check_texts(option[1], f"{where}.values[{index}]")
            _need(repr(option[0]) not in seen, f"{where}.values[{index}]", "a value given once")
            seen.add(repr(option[0]))
        _need(repr(default) in seen and not isinstance(default, bool), f"{where}.default", "one of the values")


def _check_policy(policy: Any, where: str) -> None:
    _need(isinstance(policy, dict) and set(policy) == _POLICY_KEYS, where, f"an object with the fields {sorted(_POLICY_KEYS)}")
    file = policy["file"]
    _need(isinstance(file, str) and file.lower().endswith(".admx") and len(file) <= 260
          and not (set(file) & set('\\/:*?"<>|' + _CONTROL)), f"{where}.file", "the name of an .admx file")
    for key in ("namespace", "name"):
        _check_text(policy[key], f"{where}.{key}", 512)
        _need(bool(policy[key].strip()), f"{where}.{key}", "not empty")
    _need(policy["class"] in POLICY_CLASSES, f"{where}.class", f"one of {POLICY_CLASSES}")
    _check_text(policy["category"], f"{where}.category", 1024)
    for key in ("supported", "title", "explain"):
        _check_texts(policy[key], f"{where}.{key}")
    for key in ("enabled", "disabled"):
        _need(isinstance(policy[key], list) and len(policy[key]) <= MAX_WRITES, f"{where}.{key}", "a list of writes")
        for index, write in enumerate(policy[key]):
            _check_write(write, f"{where}.{key}[{index}]")
    _need(isinstance(policy["elements"], list) and len(policy["elements"]) <= MAX_ELEMENTS, f"{where}.elements",
          "a list of elements")
    params: set[str] = set()
    for index, element in enumerate(policy["elements"]):
        _check_element(element, f"{where}.elements[{index}]", params)
    _need(bool(policy["enabled"] or policy["elements"]), where, "nothing to write")


def check_templates(data: Any, *, policies: bool = True) -> None:
    """Raise AdmxError when the records of a saved import or a package are not what the template parser writes.
    policies=False leaves out the check of each policy, for records that conform() has just checked one by one."""
    check_each = policies
    try:
        _need(isinstance(data, dict) and "policies" in data and set(data) <= _DATA_KEYS, "templates",
              f"an object with the fields {sorted(_DATA_KEYS)}")
        _check_int(data.get("format", FORMAT_VERSION), min(READ_FORMATS), max(READ_FORMATS), "templates.format")
        cultures = data.get("cultures", [])
        _need(isinstance(cultures, list) and len(cultures) <= MAX_TEXTS
              and all(isinstance(c, str) and _CULTURE_RE.match(c) for c in cultures), "templates.cultures", "culture names")
        _check_int(data.get("files", 0), 0, MAX_FILES, "templates.files")
        categories = data.get("categories", {})
        _need(isinstance(categories, dict) and len(categories) <= MAX_POLICIES, "templates.categories", "an object")
        for key, category in categories.items():
            where = f"category {jsonfile.short(key)}"
            _check_text(key, where, 1024)
            _need(isinstance(category, dict) and set(category) == {"title", "parent"}, where, "title and parent")
            _check_texts(category["title"], f"{where}.title")
            _check_text(category["parent"], f"{where}.parent", 1024)
        for key in categories:
            _need(_chain_fits(categories, key), f"category {jsonfile.short(key)}",
                  f"a chain of parent categories of at most {MAX_CATEGORY_DEPTH} levels, without a cycle")
        policies = data["policies"]
        _need(isinstance(policies, list) and len(policies) <= MAX_POLICIES, "templates.policies",
              f"a list of at most {MAX_POLICIES} policies")
        for index, policy in enumerate(data["policies"] if check_each else ()):
            _check_policy(policy, _policy_where(index, policy))
        skipped = data.get("skipped", [])
        _need(isinstance(skipped, list) and len(skipped) <= MAX_POLICIES, "templates.skipped", "a list")
        for index, item in enumerate(skipped):
            _need(isinstance(item, dict) and set(item) == {"file", "policy", "reason"}, f"skipped[{index}]",
                  "file, policy and reason")
            for key in ("file", "policy", "reason"):
                _check_text(item[key], f"skipped[{index}].{key}", 512)
        problems = data.get("problems", [])
        _need(isinstance(problems, list) and len(problems) <= MAX_POLICIES, "templates.problems", "a list")
        for index, problem in enumerate(problems):
            _check_text(problem, f"problems[{index}]", 4096)
    except _Bad as exc:
        raise AdmxError(str(exc)) from None
    except (TypeError, KeyError, AttributeError, ValueError, RecursionError) as exc:  # a shape no check above foresaw
        raise AdmxError(f"templates: a record of an unexpected shape ({type(exc).__name__})") from None


def _policy_where(index: int, policy: Any) -> str:
    name = policy.get("name") if isinstance(policy, dict) else None
    return f"policy {index}" + (f" ({name[:80]})" if isinstance(name, str) else "")


def _chain_fits(categories: dict[str, Any], key: str) -> bool:
    """The chain of parents of one category is at most MAX_CATEGORY_DEPTH long and has no cycle."""
    seen: set[str] = set()
    current = key
    while current in categories:
        if current in seen or len(seen) >= MAX_CATEGORY_DEPTH:
            return False
        seen.add(current)
        parent = categories[current].get("parent") if isinstance(categories[current], dict) else ""
        current = parent if isinstance(parent, str) else ""
    return True


# a quote, a drive or two slashes, anything up to the closing quote of the same kind: one pass, never backtracking
_QUOTED_PATH = re.compile(r"'((?:[A-Za-z]:|[\\/]{2})[^']*)'|\"((?:[A-Za-z]:|[\\/]{2})[^\"]*)\"")


def without_paths(text: str) -> str:
    """A message with the quoted paths of this computer reduced to their file names ('C:\\...\\a.adml' to 'a.adml'):
    the problems of an import made by an older version may carry them, and an exported catalog file travels."""
    def file_name(match: re.Match[str]) -> str:
        quote = "'" if match.group(1) is not None else '"'
        path = match.group(1) if match.group(1) is not None else match.group(2)
        return quote + re.split(r"[\\/]+", path.rstrip("\\/"))[-1] + quote

    return _QUOTED_PATH.sub(file_name, text)


def _clean_text(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    text = "".join(" " if ch in _TEXT_CONTROL else ch for ch in text) if set(text) & _TEXT_CONTROL else text
    return text[:limit]


def _clean_texts(value: Any) -> dict[str, str]:
    """Texts by culture as the check expects them: culture names only, no control characters, cut to MAX_TEXT."""
    if not isinstance(value, dict):
        return {}
    out = {culture: _clean_text(text, MAX_TEXT) for culture, text in value.items()
           if isinstance(culture, str) and _CULTURE_RE.match(culture) and isinstance(text, str)}
    return dict(list(out.items())[:MAX_TEXTS])


def _clean_policy_texts(policy: dict[str, Any]) -> None:
    for key in ("supported", "title", "explain"):
        if key in policy:
            policy[key] = _clean_texts(policy[key])
    for element in policy.get("elements", []) if isinstance(policy.get("elements"), list) else []:
        if not isinstance(element, dict):
            continue
        if "label" in element:
            element["label"] = _clean_texts(element["label"])
        if isinstance(element.get("id"), str):
            element["id"] = _clean_text(element["id"], 512)
        for option in element.get("values", []) if isinstance(element.get("values"), list) else []:
            if isinstance(option, list) and len(option) == 2 and option[1] is not None:
                option[1] = _clean_texts(option[1])


def conform(data: Any) -> int:
    """Bring the records of the template parser, or of an import saved by an older version, into the shape that
    check_templates accepts, in place: texts lose control characters and cultures that are not culture names, a chain
    of categories that is too deep or a cycle is cut, paths in problems become file names, and every policy the check
    would refuse becomes a skipped policy (reason "unsafe" or "broken") instead of refusing the whole import. Returns
    the number of policies moved to skipped. A catalog file is never conformed: it is refused as it is."""
    if not isinstance(data, dict) or not isinstance(data.get("policies"), list):
        raise AdmxError("templates: no list of policies")
    for key in [k for k in data if k not in _DATA_KEYS]:
        del data[key]
    fmt = data.get("format", FORMAT_VERSION)
    data["format"] = fmt if isinstance(fmt, int) and not isinstance(fmt, bool) and fmt in READ_FORMATS else FORMAT_VERSION
    cultures = data.get("cultures", [])
    data["cultures"] = ([c for c in cultures if isinstance(c, str) and _CULTURE_RE.match(c)][:MAX_TEXTS]
                        if isinstance(cultures, list) else [])
    files = data.get("files", 0)
    data["files"] = files if isinstance(files, int) and not isinstance(files, bool) and 0 <= files <= MAX_FILES else 0
    categories: dict[str, dict[str, Any]] = {}
    raw_categories = data.get("categories", {})
    for key, category in (raw_categories.items() if isinstance(raw_categories, dict) else ()):
        if not (isinstance(key, str) and key == _clean_text(key, 1024) and isinstance(category, dict)):
            continue
        parent = category.get("parent", "")
        categories[key] = {"title": _clean_texts(category.get("title")),
                           "parent": parent if isinstance(parent, str) and parent == _clean_text(parent, 1024) else ""}
        if len(categories) >= MAX_POLICIES:
            break
    for key in categories:  # one pass is enough: cutting a parent only shortens the chains of later categories
        if not _chain_fits(categories, key):
            categories[key]["parent"] = ""
    data["categories"] = categories
    skipped = [{field: _clean_text(item.get(field, ""), 512) for field in ("file", "policy", "reason")}
               for item in (data.get("skipped") if isinstance(data.get("skipped"), list) else []) if isinstance(item, dict)]
    kept: list[dict[str, Any]] = []
    for index, policy in enumerate(data["policies"]):
        if isinstance(policy, dict):
            _clean_policy_texts(policy)
        try:
            _need(len(kept) < MAX_POLICIES, "templates.policies", f"at most {MAX_POLICIES} policies")
            _check_policy(policy, _policy_where(index, policy))
        except (_Bad, TypeError, KeyError, AttributeError, ValueError) as exc:
            reason = "unsafe" if "unsafe" in str(exc) else "broken"
            name = policy.get("name") if isinstance(policy, dict) else ""
            file = policy.get("file") if isinstance(policy, dict) else ""
            skipped.append({"file": _clean_text(file, 512), "policy": _clean_text(name, 512), "reason": reason})
            log.info("policy %s skipped: %s", _clean_text(name, 80), str(exc)[:200])
            continue
        kept.append(policy)
    moved = len(data["policies"]) - len(kept)
    data["policies"] = kept
    data["skipped"] = skipped[:MAX_POLICIES]
    problems = data.get("problems", [])
    data["problems"] = [_clean_text(without_paths(str(problem)[:4096]), 4096)
                        for problem in (problems if isinstance(problems, list) else [])[:MAX_POLICIES]]
    return moved


# --------------------------------------------------------------------------- policy records to rules


def _id_part(text: str, keep_dots: bool) -> str:
    parts = text.lower().split(".") if keep_dots else [text.lower()]
    cleaned = [re.sub(r"[^a-z0-9]+", "-", part).strip("-") or "x" for part in parts]
    return ".".join(cleaned)


def _action(write: dict[str, Any], prefix: str, rule_id: str, value: Any = None) -> Action:
    path = prefix + str(write["key"])
    if write["kind"] == "delete":
        return Action("reg-remove", {"path": path, "name": write["name"]}, rule_id)
    if value is None and isinstance(write["value"], str):  # a fixed text of the template: "{id}" in it is text, never a
        return Action("reg", {"path": path, "name": write["name"], "kind": write["kind"], "value": write["value"],  # parameter
                              "literal": True}, rule_id)
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


def _rule_ids(policies: list[dict[str, Any]]) -> list[str]:
    """The rule id of every policy (by position): the namespace and the name. Two policies with the same id are
    numbered (base, base-2, ...) in the order of their English titles, then of their position, so the ids never
    depend on the interface language; an id is never the "<id>.off" of another policy's Disabled state. Linear in the number of
    policies. Profiles keep these ids, so they fit any import of the same templates."""
    # 1.2 numbered by the title in the interface language; the English title keeps the ids of English users and never
    # changes with the language (no template of Windows has two policies with one id, so their ids are the same anyway)
    titles = [(pick(p.get("title"), "en") or str(p.get("name", ""))).lower() for p in policies]
    order = sorted(range(len(policies)), key=lambda i: (titles[i], i))
    reserved: set[str] = set()
    counters: dict[str, int] = {}
    ids = [""] * len(policies)
    for i in order:
        base = f"{IMPORTED_PREFIX}{_id_part(policies[i]['namespace'], True)}.{_id_part(policies[i]['name'], False)}"
        index = counters.get(base, 1)
        rule_id = base if index == 1 else f"{base}-{index}"
        while rule_id in reserved or rule_id + ".off" in reserved:
            index += 1
            rule_id = f"{base}-{index}"
        counters[base] = index
        reserved.update((rule_id, rule_id + ".off"))
        ids[i] = rule_id
    return ids


def _named_policies(data: dict[str, Any], language: str) -> Iterator[tuple[dict[str, Any], str]]:
    """The policies of an import with the ids of their rules (_rule_ids), in the order of their titles in the
    interface language (the order of the tree)."""
    policies = data.get("policies", [])
    ids = _rule_ids(policies)
    titles = [(pick(p.get("title"), language) or p.get("name", "")).lower() for p in policies]
    for i in sorted(range(len(policies)), key=lambda i: (titles[i], ids[i])):
        yield policies[i], ids[i]


def policy_ids(data: dict[str, Any], language: str = "en") -> set[str]:
    """The ids of the policies of an import, as their rules get them (without the "<id>.off" of a Disabled state)."""
    return set(_rule_ids(data.get("policies", [])))


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
    made: dict[tuple[str, str], str] = {}  # (side, category) -> group id, so a chain is walked once per category

    def group_for(side: str, category: str) -> str:
        if (side, category) in made:
            return made[(side, category)]
        side_id = f"{root}.{side}"
        if side_id not in part.groups:
            part.groups[side_id] = Group(side_id, tr(SIDE_TITLES[side]), 1 if side == "machine" else 2, root, "", f"admx:{info.id}")
        if category not in categories:
            other = f"{side_id}.none"
            part.groups.setdefault(other, Group(other, tr(NO_CATEGORY), 1_000_000, side_id, "", f"admx:{info.id}"))
            made[(side, category)] = other
            return other
        chain: list[str] = []
        seen: set[str] = set()
        current = category
        while current in categories and current not in seen and len(chain) < MAX_CATEGORY_DEPTH:
            chain.append(current)
            seen.add(current)
            current = categories[current]["parent"]
        parent = side_id
        for key in reversed(chain):
            group_id = f"{side_id}.c{number[key]}"
            part.groups.setdefault(group_id, Group(group_id, titles[key], rank[key], parent, "", f"admx:{info.id}"))
            parent = group_id
        made[(side, category)] = parent
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
        if any(rule.id in taken for rule in rules):  # its Disabled rule would replace a rule of another import
            log.warning("import %s: policy %s skipped: its rule id is taken by another import", info.id, policy.get("name"))
            continue
        origin = RuleOrigin(info.id, info.name, info.folder, str(policy.get("file", "")), str(policy.get("name", "")))
        for rule in rules:
            part.rules[rule.id] = rule
            part.origins[rule.id] = origin
    # counted from the records: a policy that an older version kept and this one skips (conform) is among the skipped
    counts = tr("{0} policies as {1} rules; {2} skipped", len(data.get("policies", [])), len(part.rules) + len(part.aliases),
                len(data.get("skipped", [])))
    if part.shared:
        counts += tr("; {0} of the policies come from another imported tree of a more trusted source or shown higher, "
                     "with one check mark for both",
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
    shown = list(dict.fromkeys(import_ids))  # the order of the trees
    for import_id in trust_order(shown):  # the order in which they take the policies they share
        try:
            info, data = load_import(admx_root, import_id)
            part = catalog_part(info, data, language, set(base.rules) | set(rules), 10000 + shown.index(import_id))
        except Exception as exc:  # noqa: BLE001 - a broken import is reported, the program starts without it
            problems.append(tr("Imported templates {0} were not loaded: {1}", import_id, str(exc)[:500]))
            continue
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
