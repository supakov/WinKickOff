"""Validation of profiles and built XML. Task T07; only the Issue type and account-name rules
are in place now so that the UI and tests can rely on the shape."""

from __future__ import annotations

import re
from dataclasses import dataclass

from winkickoff.core.profile import Profile

RESERVED_ACCOUNT_NAMES = frozenset(
    {"administrator", "guest", "defaultaccount", "wdagutilityaccount", "system", "local service", "network service"}
)
_BAD_NAME_CHARS = re.compile(r'[\\/\[\]:;|=,+*?<>"@]')


@dataclass(frozen=True)
class Issue:
    level: str  # error | warning | info
    target: str  # rule id, profile field or XML element
    message: str
    doc: str = ""


def check_account_name(name: str) -> str | None:
    """Reason why a local account name is invalid, or None."""
    if not name.strip():
        return "имя пустое"
    if len(name) > 20:
        return "длиннее 20 символов"
    if _BAD_NAME_CHARS.search(name):
        return "содержит запрещённые символы"
    if name.lower() in RESERVED_ACCOUNT_NAMES:
        return "зарезервированное имя Windows"
    if name.strip(". ") != name:
        return "не может начинаться или заканчиваться точкой или пробелом"
    return None


def validate_accounts(profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    for index, account in enumerate(profile.accounts):
        target = f"accounts[{index}]"
        reason = check_account_name(account.name)
        if reason:
            issues.append(Issue("error", target, f"Учётная запись '{account.name}': {reason}"))
        if account.name.lower() in seen:
            issues.append(Issue("error", target, f"Учётная запись '{account.name}' повторяется"))
        seen.add(account.name.lower())
        if account.group not in ("Administrators", "Users"):
            issues.append(Issue("error", target, f"Группа '{account.group}' недопустима (Administrators или Users)"))
        if account.password:
            issues.append(Issue("warning", target, f"Пароль '{account.name}' попадёт в XML открытым текстом"))
    if not any(a.group == "Administrators" for a in profile.accounts):
        issues.append(Issue("error", "accounts", "Нужна хотя бы одна учётная запись в группе Administrators"))
    return issues
