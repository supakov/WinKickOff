"""The computer name of the installed Windows (profile fields install.computer_name_mode and install.computer_name).

- "random": no name in the answer file; Windows Setup makes one up (DESKTOP-XXXXXXX), as before 1.3.0-rc.2.
- "fixed": the name itself, written to ComputerName of Microsoft-Windows-Shell-Setup in the specialize pass.
- "template": letters, digits and hyphens with parts computed on each PC during installation: {serial} (the end of the
  BIOS serial number), {mac} (the end of the address of the first physical network adapter) and {random} (random
  letters and digits), each with an optional length, {serial:6}. Setup-System.ps1 computes the name in the specialize
  pass (templates/section-computer-name.ps1); the answer file holds TEMPORARY_NAME, which the script replaces.

A name is a NetBIOS name: at most 15 characters. WinKickOff allows only Latin letters, digits and hyphens (also a DNS
host name), not only digits, and no hyphen at the start or the end.
"""

from __future__ import annotations

import re

from winkickoff.core.i18n import tr

MODES = ("random", "fixed", "template")
MAX_LENGTH = 15
TEMPORARY_NAME = "WINKICKOFF-TMP"  # what Setup writes first in mode "template"; the script of the pass replaces it
PLACEHOLDERS = {"serial": (6, MAX_LENGTH), "mac": (6, 12), "random": (4, MAX_LENGTH)}  # default and largest length
_NAME_CHARS = re.compile(r"^[A-Za-z0-9-]+$")
_PART = re.compile(r"\{([a-z]+)(?::([0-9]{1,2}))?\}")


def name_problem(name: str) -> str | None:
    """Why a fixed computer name cannot be used, or None."""
    if not name:
        return tr("the computer name is empty")
    if len(name) > MAX_LENGTH:
        return tr("the computer name is longer than {0} characters", MAX_LENGTH)
    if not _NAME_CHARS.match(name):
        return tr("the computer name may contain only Latin letters, digits and hyphens")
    if name.isdigit():
        return tr("the computer name cannot consist of digits only")
    if name.startswith("-") or name.endswith("-"):
        return tr("the computer name cannot begin or end with a hyphen")
    return None


def parse_template(template: str) -> list[tuple[str, str | int]]:
    """The parts of a template: ("text", letters) and (placeholder, length). ValueError with the reason (translated)
    when the template cannot be used."""
    parts: list[tuple[str, str | int]] = []
    position = 0
    for match in _PART.finditer(template):
        if match.start() > position:
            parts.append(("text", template[position:match.start()]))
        kind = match.group(1)
        if kind not in PLACEHOLDERS:
            raise ValueError(tr("unknown part {0} of the computer name template; use {1}", match.group(0),
                                ", ".join("{" + name + "}" for name in PLACEHOLDERS)))
        default, largest = PLACEHOLDERS[kind]
        length = int(match.group(2)) if match.group(2) else default
        if not 1 <= length <= largest:
            raise ValueError(tr("the length of {0} must be from 1 to {1}", "{" + kind + "}", largest))
        parts.append((kind, length))
        position = match.end()
    if position < len(template):
        parts.append(("text", template[position:]))
    texts = "".join(str(value) for kind, value in parts if kind == "text")
    if texts and not _NAME_CHARS.match(texts):
        raise ValueError(tr("outside its parts in braces, the computer name template may contain only Latin letters, "
                            "digits and hyphens"))
    if not any(kind != "text" for kind, _ in parts):
        raise ValueError(tr("the computer name template has no part in braces; choose \"This name\" for a fixed name"))
    if not any(character.isalpha() for character in texts):
        raise ValueError(tr("the computer name template needs at least one letter outside its parts in braces, so that "
                            "the name is never only digits"))
    if template.startswith("-") or template.endswith("-"):
        raise ValueError(tr("the computer name cannot begin or end with a hyphen"))
    length = sum(len(str(value)) if kind == "text" else int(value) for kind, value in parts)
    if length > MAX_LENGTH:
        raise ValueError(tr("the computer name template gives up to {0} characters, more than {1}", length, MAX_LENGTH))
    return parts


def template_problem(template: str) -> str | None:
    """Why a computer name template cannot be used, or None."""
    if not template:
        return tr("the computer name template is empty")
    try:
        parse_template(template)
    except ValueError as exc:
        return str(exc)
    return None
