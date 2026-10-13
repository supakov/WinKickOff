"""The check of stored policy records (check_templates): known fields, safe names and values, kinds, ranges,
unique parameters, counts; and conform, which brings the records of the parser or of an import saved by an
older version into the shape the check accepts."""

from __future__ import annotations

import logging
import re
from dataclasses import field
from typing import Any

from winkickoff.core import jsonfile
from winkickoff.core.admx.base import (
    FORMAT_VERSION,
    READ_FORMATS,
    MAX_FILES,
    MAX_DWORD,
    MAX_QWORD,
    _CONTROL,
    AdmxError,
    _CULTURE_RE,
    safe_name,
    safe_key,
    safe_value,
)

log = logging.getLogger(__name__)


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
