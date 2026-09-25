"""Optional syntax check of generated scripts through powershell.exe (Windows PowerShell 5.1).
Task T08. Never runs the scripts, only parses them; skipped when powershell.exe is absent."""

from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class PsCheckResult:
    skipped: bool
    errors: tuple[str, ...] = ()


def powershell_available() -> bool:
    return shutil.which("powershell.exe") is not None


def check_scripts(scripts: dict[str, str]) -> PsCheckResult:  # pragma: no cover - placeholder until T08
    if not powershell_available():
        return PsCheckResult(skipped=True)
    raise NotImplementedError("check_scripts is implemented in task T08")
