"""Test helpers for the hand-written v0.2 answer file over winkickoff.core.actions_parser.

The file lives in the appendices of the documentation: docs/appendices/B-autounattend-v0.2/.

The semantic golden tests compare normalised action tuples: every registry write and removal,
service start type, command, component and app of Setup-System.ps1 v0.2 must be present in the
catalog with the same value. The parser itself lives in the application (the importer uses it).
"""

from __future__ import annotations

from pathlib import Path

from winkickoff.core.actions_parser import Action, catalog_actions, extract_script, parse_script, rule_actions

REPO = Path(__file__).resolve().parents[2]
V02 = REPO / "docs" / "appendices" / "B-autounattend-v0.2" / "autounattend.xml"

__all__ = [
    "REPO",
    "V02",
    "Action",
    "catalog_actions",
    "extract_script",
    "parse_script_actions",
    "parse_script_actions_ordered",
    "parse_v02_actions",
    "rule_actions",
]


def parse_v02_actions(source: Path | str) -> set[Action]:
    """Actions of Setup-System.ps1 embedded in an answer file (a path or the XML text itself)."""
    text = source.read_text(encoding="utf-8") if isinstance(source, Path) else source
    return parse_script(extract_script(text, "Setup-System.ps1")).action_set


def parse_script_actions(script: str) -> set[Action]:
    return parse_script(script).action_set


def parse_script_actions_ordered(script: str) -> list[Action]:
    return parse_script(script).actions
