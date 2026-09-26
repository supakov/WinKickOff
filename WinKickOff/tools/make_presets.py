"""Regenerate the preset profiles in profiles/ from the rules catalog.

Run after changing the catalog (defaults, new rules):
    cd WinKickOff
    python tools/make_presets.py

Presets are deterministic (fixed timestamps), contain no passwords and are versioned in git.
tests/test_presets.py fails when a preset no longer matches the catalog.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from winkickoff.core.catalog import Catalog, load_catalog  # noqa: E402
from winkickoff.core.deps import Resolver  # noqa: E402
from winkickoff.core.profile import Profile  # noqa: E402

import memstechtips as memstechtips_map  # noqa: E402

STAMP = "2026-09-25T00:00:00"


def office(catalog: Catalog) -> Profile:
    profile = Profile.from_catalog(catalog, name="Офис")
    profile.comment = (
        "Безопасность и обновляемость для рабочих групп без домена; равен значениям каталога по умолчанию. "
        "Основа: проверенный файл ответов v0.2 с изменениями 26.09.2026: политики браузеров, OneDrive не "
        "устанавливается, UAC администратора как в Windows (без запроса для диспетчера задач), без правила ASR "
        "для USB и без обновлений других продуктов Microsoft. Стартовые Admin и User без паролей."
    )
    return profile


def strict(catalog: Catalog) -> Profile:
    profile = Profile.from_catalog(catalog, name="Строгий")
    profile.comment = (
        "Офис плюс ограничения, которые могут мешать старым программам: контролируемый доступ к папкам в режиме "
        "блокировки, SmartScreen запрещает запуск программ без репутации, правило ASR по распространённости "
        "блокирует, неподписанные программы с USB не запускаются, UAC всегда спрашивает администратора, "
        "обновления других продуктов Microsoft включены, NetBIOS выключен, движок VBScript удаляется. "
        "Перед массовым внедрением проверить на одном ПК."
    )
    resolver = Resolver(catalog)
    profile.set_param("defender.controlled-folder-access", "mode", 1)
    profile.set_param("defender.smartscreen-shell", "level", "Block")
    profile.set_param("asr.prevalence", "mode", 1)
    for rule_id in ("asr.usb-untrusted", "uac.admin-always-notify", "update.other-microsoft-products",
                    "network.netbios-off", "scripts.remove-vbscript"):
        resolver.enable(profile, rule_id)
    return profile


def laptop(catalog: Catalog) -> Profile:
    profile = Profile.from_catalog(catalog, name="Ноутбук")
    profile.comment = (
        "Офис для ноутбуков: экран блокируется через 10 минут бездействия, автоматическое шифрование устройства "
        "разрешено. Сразу после установки сохраните ключ восстановления BitLocker отдельно от ноутбука."
    )
    profile.set_param("accounts.inactivity-lock", "seconds", 600)
    Resolver(catalog).disable(profile, "encryption.prevent-auto-bitlocker")
    return profile


def memstechtips(catalog: Catalog) -> Profile:
    profile, _ = memstechtips_map.load(catalog)
    profile.comment = (
        "Перенос оригинального файла ответов UnattendedWinstall (memstechtips, приложение A): включены правила, "
        "действия которых есть в оригинале и не противоречат ему. Ключ продукта спрашивается при установке. "
        "Базовые правила WinKickOff, которых нет в оригинале или которые ему противоречат, выключены: проверьте "
        "предупреждения перед применением. Что добавлено сверх оригинала, что не перенесено и почему: "
        "docs/technical/memstechtips-profile.md."
    )
    return profile


def memstechtips_report(catalog: Catalog) -> str:
    profile, facts = memstechtips_map.load(catalog)
    return memstechtips_map.report(catalog, profile, facts)


def write(profile: Profile, catalog: Catalog, path: Path) -> None:
    profile.created = STAMP
    profile.modified = STAMP
    text = json.dumps(profile.to_dict(catalog), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\r\n")
    print(f"written {path.relative_to(ROOT)}")


def main() -> None:
    catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
    write(office(catalog), catalog, ROOT / "profiles" / "preset-office.json")
    write(strict(catalog), catalog, ROOT / "profiles" / "preset-strict.json")
    write(laptop(catalog), catalog, ROOT / "profiles" / "preset-laptop.json")
    write(memstechtips(catalog), catalog, ROOT / "profiles" / "preset-memstechtips.json")
    memstechtips_map.REPORT.write_text(memstechtips_report(catalog), encoding="utf-8", newline="\r\n")
    print(f"written {memstechtips_map.REPORT.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
