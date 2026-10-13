"""ADMX and ADML files to policy records: the ADML texts by culture, a policy with its elements as parameters
and writes, read_templates for a folder of templates."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from winkickoff.core.admx.base import (
    FORMAT_VERSION,
    SOURCE_CULTURE,
    MAX_FILES,
    MAX_DWORD,
    MAX_QWORD,
    _REF_RE,
    AdmxError,
    _CULTURE_RE,
    _local,
    _kids,
    _kid,
    read_xml,
    safe_name,
    safe_key,
    safe_value,
)
from winkickoff.core.admx.check import conform


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
