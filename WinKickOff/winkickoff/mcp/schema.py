"""A small JSON Schema checker for tool arguments.

Supported keywords: type (a name or a list of names), properties, required, additionalProperties, enum, minimum,
maximum, minLength, maxLength, pattern, items, minItems, maxItems. Nothing else of JSON Schema is needed by the
tools of this server; the schemas are published to clients as they are.
"""

from __future__ import annotations

import re
from typing import Any

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _pattern(pattern: str) -> str:
    """A trailing "$" as ECMA 262 reads it: the end of the string, not before a final newline as Python does."""
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        return pattern[:-1] + r"\Z"
    return pattern


def check(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    """Every violation as "<path>: <reason>"; an empty list means the value fits."""
    problems: list[str] = []
    wanted = schema.get("type")
    if wanted is not None:
        names = wanted if isinstance(wanted, list) else [wanted]
        if not any(_TYPES.get(name, lambda _v: False)(value) for name in names):
            return [f"{path}: expected {' or '.join(names)}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: must be one of {schema['enum']}"]
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{path}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and not re.search(_pattern(schema["pattern"]), value):
            problems.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: less than {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: more than {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{path}: more than {schema['maxItems']} items")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                problems += check(schema["items"], item, f"{path}[{index}]")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                problems.append(f"{path}: missing {name}")
        for name, item in value.items():
            if name in properties:
                problems += check(properties[name], item, f"{path}.{name}")
            elif schema.get("additionalProperties") is False:
                problems.append(f"{path}: unknown property {name}")
    return problems
