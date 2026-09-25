"""Validation of profiles and of built answer files.

Profile checks catch what the user can get wrong in the editor; XML checks repeat the hard limits
of Windows Setup (a violation aborts the install with 0x80220005) and mirror tools/Validate-Unattend.ps1.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from winkickoff.core.catalog import Catalog, CatalogError, heading_anchors, load_catalog
from winkickoff.core.i18n import catalog_texts, tr
from winkickoff.core.profile import Profile
from winkickoff.core.render import EDITION_KEYS
from winkickoff.core.resources import find_keyboard
from winkickoff.core.verify import rollback_steps, verify_steps

RESERVED_ACCOUNT_NAMES = frozenset(
    {"administrator", "guest", "defaultaccount", "wdagutilityaccount", "system", "local service", "network service"}
)
_BAD_NAME_CHARS = re.compile(r'[\\/\[\]:;|=,+*?<>"@]')
_KEY_RE = re.compile(r"^[A-Z0-9]{5}(-[A-Z0-9]{5}){4}$")
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{4})?(-[A-Z]{2})?$")
_INPUT_LOCALE_ITEM = re.compile(r"^([0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}|[a-z]{2,3}(-[A-Za-z]{2,4})?(-[A-Z]{2})?)$")
U = "{urn:schemas-microsoft-com:unattend}"
EXT = "{urn:workgroup-unattend}"
MAX_PATH = 259
DEVICE_ENCRYPTION_RULE = "encryption.prevent-auto-bitlocker"


@dataclass(frozen=True)
class Issue:
    level: str  # error | warning | info
    target: str  # rule id, profile field (install.x, languages.x, accounts[i]) or "xml"
    message: str
    doc: str = ""


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)


# --------------------------------------------------------------------------- profile


def check_account_name(name: str) -> str | None:
    """Reason why a local account name is invalid, or None."""
    if not name.strip():
        return tr("имя пустое")
    if len(name) > 20:
        return tr("длиннее 20 символов")
    if _BAD_NAME_CHARS.search(name):
        return tr("содержит запрещённые символы")
    if name.lower() in RESERVED_ACCOUNT_NAMES:
        return tr("зарезервированное имя Windows")
    if name.strip(". ") != name:
        return tr("не может начинаться или заканчиваться точкой или пробелом")
    return None


def validate_accounts(profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    for index, account in enumerate(profile.accounts):
        target = f"accounts[{index}]"
        reason = check_account_name(account.name)
        if reason:
            issues.append(Issue("error", target, tr("Учётная запись '{0}': {1}", account.name, reason)))
        if account.name.lower() in seen:
            issues.append(Issue("error", target, tr("Учётная запись '{0}' повторяется", account.name)))
        seen.add(account.name.lower())
        if account.group not in ("Administrators", "Users"):
            issues.append(Issue("error", target, tr("Группа '{0}' недопустима (Administrators или Users)", account.group)))
        if account.password:
            issues.append(Issue("warning", target, tr("Пароль '{0}' попадёт в XML открытым текстом; храните файл как секрет", account.name)))
    if not any(a.group == "Administrators" for a in profile.accounts):
        issues.append(Issue("error", "accounts", tr("Нужна хотя бы одна учётная запись в группе Administrators")))
    return issues


def _check_param(rule: Any, param: Any, value: Any) -> str | None:
    title = catalog_texts().param(rule, param)
    if param.type == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            return tr("'{0}' должно быть целым числом", title)
        if param.min is not None and value < param.min or param.max is not None and value > param.max:
            return tr("'{0}' вне диапазона {1}..{2}", title, param.min, param.max)
    elif param.type == "enum":
        if value not in {v for v, _ in param.values}:
            return tr("'{0}': недопустимое значение {1!r}", title, value)
    elif param.type == "bool":
        if not isinstance(value, bool):
            return tr("'{0}' должно быть да или нет", title)
    elif param.type == "string" and not str(value).strip():
        return tr("'{0}' не может быть пустым", title)
    return None


def validate_profile(profile: Profile, catalog: Catalog, keyboards: list[dict[str, Any]] | None = None) -> list[Issue]:
    issues = validate_accounts(profile)

    edition = profile.install.get("edition")
    mode = profile.install.get("product_key_mode")
    if mode not in ("generic", "custom", "ask"):
        issues.append(Issue("error", "install.product_key_mode", tr("Неизвестный режим ключа '{0}'", mode)))
    if mode == "generic" and edition not in EDITION_KEYS:
        issues.append(Issue("error", "install.edition", tr("Для редакции '{0}' нет универсального ключа", edition)))
    if mode == "custom" and not _KEY_RE.match(str(profile.install.get("product_key", "")).strip().upper()):
        issues.append(Issue("error", "install.product_key", tr("Ключ продукта должен иметь вид XXXXX-XXXXX-XXXXX-XXXXX-XXXXX")))
    if not str(profile.install.get("time_zone", "")).strip():
        issues.append(Issue("error", "install.time_zone", tr("Часовой пояс не задан")))

    for key, title in (("ui_language", tr("Язык интерфейса")), ("system_locale", tr("Язык программ без Юникода")), ("user_locale", tr("Формат дат и чисел"))):
        value = str(profile.languages.get(key, ""))
        if not _LOCALE_RE.match(value):
            issues.append(Issue("error", f"languages.{key}", tr("{0}: '{1}' не похоже на тег языка вида uk-UA", title, value)))
    inputs = [str(i) for i in (profile.languages.get("input") or [])]
    if not inputs:
        issues.append(Issue("error", "languages.input", tr("Нужен хотя бы один язык ввода")))
    if len(set(inputs)) != len(inputs):
        issues.append(Issue("warning", "languages.input", tr("Языки ввода повторяются")))
    if keyboards is not None:
        for item in inputs:
            if find_keyboard(keyboards, item) is None:
                issues.append(Issue("error", "languages.input", tr("Неизвестный язык ввода '{0}'", item)))

    for rule in catalog.rules.values():
        title = catalog_texts().rule(rule, "title")
        enabled = profile.is_enabled(rule.id)
        for pname, param in rule.params.items():
            problem = _check_param(rule, param, profile.param(catalog, rule.id, pname))
            if problem:
                issues.append(Issue("error", rule.id, tr("«{0}»: {1}", title, problem), rule.doc))
        if enabled:
            for req in rule.requires:
                if not profile.is_enabled(req):
                    issues.append(Issue("error", rule.id, tr("«{0}» включено, но требует выключенное «{1}»", title, catalog_texts().rule(catalog.rules[req], "title")), rule.doc))
            for other in rule.conflicts:
                if profile.is_enabled(other):
                    issues.append(Issue("error", rule.id, tr("«{0}» конфликтует с включённым «{1}»", title, catalog_texts().rule(catalog.rules[other], "title")), rule.doc))
            if rule.level == "risky":
                issues.append(Issue("warning", rule.id, tr("Включено рискованное правило «{0}»: {1}", title, catalog_texts().rule(rule, "risk") or catalog_texts().rule(rule, "effect")), rule.doc))
        elif rule.level == "baseline":
            issues.append(Issue("warning", rule.id, tr("Выключено базовое правило «{0}»", title), rule.doc))
    encryption = catalog.rules.get(DEVICE_ENCRYPTION_RULE)
    if encryption is not None and not profile.is_enabled(encryption.id):
        issues.append(Issue("warning", encryption.id, tr(
            "Автоматическое шифрование устройства разрешено: Windows может зашифровать системный диск сама, а с "
            "локальными учётными записями ключ восстановления никуда не сохраняется. Сразу после установки проверьте "
            "Get-BitLockerVolume C: и сохраните ключ (manage-bde -protectors -get C:) отдельно от компьютера, иначе "
            "при сбое TPM или замене платы данные будут потеряны."), encryption.doc))
    if profile.unknown:
        issues.append(Issue("info", "profile", tr("В профиле есть правила, которых нет в каталоге: ") + ", ".join(sorted(profile.unknown))))
    return issues


# --------------------------------------------------------------------------- xml


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


# --------------------------------------------------------------------------- catalog


def validate_catalog(rules_dir: Path, docs_root: Path | None) -> tuple[Catalog | None, list[Issue]]:
    """Reload the catalog from disk (command «Проверить каталог»). Loader defects are errors; gaps in
    the descriptions are warnings: every rule must say how to check it and how to undo it, either
    in its own text or through steps derived from its actions (core/verify.py)."""
    try:
        catalog = load_catalog(rules_dir, docs_root=docs_root)
    except CatalogError as exc:
        return None, [Issue("error", exc.rule_id or "catalog", tr("Каталог не загружается: {0}", exc))]
    issues: list[Issue] = []
    anchors: dict[Path, set[str]] = {}
    for rule in catalog.rules.values():
        params = {name: param.default for name, param in rule.params.items()}
        if not rule.verify and not verify_steps(rule, params):
            issues.append(Issue("warning", rule.id, tr("«{0}»: нет текста проверки, и по действиям его не вывести", rule.title), rule.doc))
        if not rule.rollback and not rollback_steps(rule, params):
            issues.append(Issue("warning", rule.id, tr("«{0}»: нет текста отката, и по действиям его не вывести", rule.title), rule.doc))
        if rule.level == "risky" and not rule.risk:
            issues.append(Issue("warning", rule.id, tr("«{0}»: рискованное правило без описания риска", rule.title), rule.doc))
        if docs_root is not None and "#" in rule.doc:
            file_part, anchor = rule.doc.split("#", 1)
            path = docs_root / file_part
            if path not in anchors:
                anchors[path] = heading_anchors(path.read_text(encoding="utf-8"))
            if anchor not in anchors[path]:
                issues.append(Issue("warning", rule.id, tr("«{0}»: в {1} нет заголовка для ссылки #{2}", rule.title, file_part, anchor), rule.doc))
    for group_id in catalog.groups:
        if not catalog.rules_in_group(group_id):
            issues.append(Issue("info", "catalog", tr("Группа {0} без правил", group_id)))
    return catalog, issues


def validate_xml(text: str) -> list[Issue]:
    issues: list[Issue] = []
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        root = ET.fromstring(text.encode("utf-8"), parser=parser)
    except ET.ParseError as exc:
        return [Issue("error", "xml", tr("XML не разбирается: {0}", exc))]
    if root.tag != f"{U}unattend":
        issues.append(Issue("error", "xml", tr("Корневой элемент не unattend в пространстве имён Microsoft")))

    for component in root.iter(f"{U}component"):
        name = component.get("name", "?")
        if any(node.tag is ET.Comment for node in component.iter()):
            issues.append(Issue("error", "xml", tr("Комментарий внутри компонента {0}: установщик отвергнет файл", name)))

    for sync in root.iter(f"{U}RunSynchronous"):
        orders = [_text(cmd.find(f"{U}Order")) for cmd in sync.findall(f"{U}RunSynchronousCommand")]
        if len(set(orders)) != len(orders):
            issues.append(Issue("error", "xml", tr("Повторяющиеся значения Order в RunSynchronous")))
    for cmd in root.iter(f"{U}RunSynchronousCommand"):
        path = _text(cmd.find(f"{U}Path"))
        description = _text(cmd.find(f"{U}Description"))
        if not path:
            issues.append(Issue("error", "xml", tr("Пустой Path в RunSynchronousCommand")))
        elif len(path) > MAX_PATH:
            issues.append(Issue("error", "xml", tr("Команда длиннее {0} символов ({1}): {2}...", MAX_PATH, len(path), path[:60])))
        if len(description) > MAX_PATH:
            issues.append(Issue("error", "xml", tr("Description длиннее {0} символов", MAX_PATH)))

    for settings in root.findall(f"{U}settings"):
        if settings.get("pass") != "oobeSystem":
            continue
        for component in settings.findall(f"{U}component"):
            arch = component.get("processorArchitecture", "?")
            if component.get("name") == "Microsoft-Windows-International-Core":
                for field in ("InputLocale", "SystemLocale", "UILanguage", "UserLocale"):
                    if not _text(component.find(f"{U}{field}")):
                        issues.append(Issue("error", "xml", tr("International-Core ({0}): не задан {1}; установщик покажет экран языка", arch, field)))
                for item in _text(component.find(f"{U}InputLocale")).split(";"):
                    if item and not _INPUT_LOCALE_ITEM.match(item):
                        issues.append(Issue("error", "xml", tr("InputLocale ({0}): неверный элемент '{1}'", arch, item)))
            if component.get("name") == "Microsoft-Windows-Shell-Setup":
                groups = [_text(g) for g in component.iter(f"{U}Group")]
                if groups and "Administrators" not in groups:
                    issues.append(Issue("error", "xml", tr("LocalAccounts ({0}): нет учётной записи в группе Administrators", arch)))

    extensions = root.find(f"{EXT}Extensions")
    files = extensions.findall(f"{EXT}File") if extensions is not None else []
    commands = " ".join(_text(c.find(f"{U}Path")) for c in root.iter(f"{U}RunSynchronousCommand"))
    if "Extensions.ExtractScript" in commands and not files:
        issues.append(Issue("error", "xml", tr("Команда извлечения скриптов есть, а встроенных скриптов нет")))
    names = {f.get("path", "").rsplit("\\", 1)[-1] for f in files}
    if "Setup-System.ps1" in commands and "Setup-System.ps1" not in names:
        issues.append(Issue("error", "xml", tr("Команда запуска Setup-System.ps1 есть, а самого скрипта нет")))
    for f in files:
        body = (f.text or "").strip()
        name = f.get("path", "?").rsplit("\\", 1)[-1]
        if not body:
            issues.append(Issue("error", "xml", tr("Скрипт {0} пуст", name)))
        elif not re.search(r"(?m)^\s*exit 0\s*$", body):
            issues.append(Issue("error", "xml", tr("Скрипт {0} не заканчивается 'exit 0'", name)))
    return issues
