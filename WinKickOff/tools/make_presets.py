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

from winkickoff.core.catalog import Catalog, load_catalog  # noqa: E402
from winkickoff.core.deps import Resolver  # noqa: E402
from winkickoff.core.profile import Profile  # noqa: E402

STAMP = "2026-09-25T00:00:00"


def office(catalog: Catalog) -> Profile:
    profile = Profile.from_catalog(catalog, name="Офис")
    profile.comment = (
        "Соответствует проверенному файлу ответов v0.2: безопасность и обновляемость для рабочих групп без домена. "
        "Стартовые Admin и User без паролей."
    )
    return profile


def strict(catalog: Catalog) -> Profile:
    profile = Profile.from_catalog(catalog, name="Строгий")
    profile.comment = (
        "Офис плюс ограничения, которые могут мешать старым программам: контролируемый доступ к папкам в режиме "
        "блокировки, SmartScreen запрещает запуск программ без репутации, правило ASR по распространённости "
        "блокирует, NetBIOS выключен, движок VBScript удаляется. Перед массовым внедрением проверить на одном ПК."
    )
    resolver = Resolver(catalog)
    profile.set_param("defender.controlled-folder-access", "mode", 1)
    profile.set_param("defender.smartscreen-shell", "level", "Block")
    profile.set_param("asr.prevalence", "mode", 1)
    resolver.enable(profile, "network.netbios-off")
    resolver.enable(profile, "scripts.remove-vbscript")
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


if __name__ == "__main__":
    main()
