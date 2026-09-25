"""Syntax check of generated scripts through powershell.exe (Windows PowerShell 5.1).

The scripts are only parsed ([System.Management.Automation.Language.Parser]::ParseFile), never run.
Temporary copies are written into a folder inside the application (logs/tmp) and removed afterwards.
Skipped when powershell.exe is absent.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
DONE_MARK = "PSCHECK-DONE"


@dataclass(frozen=True)
class PsCheckResult:
    skipped: bool
    errors: tuple[str, ...] = ()
    failure: str = ""  # the check itself could not run

    @property
    def ok(self) -> bool:
        return not self.skipped and not self.errors and not self.failure


def powershell_path() -> str | None:
    return shutil.which("powershell.exe")


def check_scripts(scripts: dict[str, str], work_dir: Path, timeout: int = 90) -> PsCheckResult:
    exe = powershell_path()
    if exe is None or not scripts:
        return PsCheckResult(skipped=True)
    folder = work_dir / f"pscheck-{uuid.uuid4().hex}"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for name, text in scripts.items():
            (folder / name).write_text(text, encoding="utf-8-sig", newline="\r\n")
        literal = str(folder).replace("'", "''")
        command = (
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
            f"Get-ChildItem -LiteralPath '{literal}' -Filter *.ps1 | ForEach-Object {{"
            "$t=$null;$e=$null;"
            "[void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$t,[ref]$e);"
            "foreach($x in $e){ '{0}|{1}|{2}' -f $_.Name,$x.Extent.StartLineNumber,$x.Message } };"
            f"'{DONE_MARK}'"
        )
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            proc = subprocess.run(
                [exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True,
                timeout=timeout,
                creationflags=flags,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return PsCheckResult(skipped=False, failure=f"powershell.exe не отработал: {exc}")
        out = proc.stdout.decode("utf-8", errors="replace").replace(chr(0xFEFF), "")
        if DONE_MARK not in out:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            return PsCheckResult(skipped=False, failure=f"проверка не завершилась: {err[:300]}")
        errors = []
        for line in out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3 and parts[0].endswith(".ps1"):
                errors.append(f"{parts[0]}, строка {parts[1]}: {parts[2]}")
        return PsCheckResult(skipped=False, errors=tuple(errors))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
