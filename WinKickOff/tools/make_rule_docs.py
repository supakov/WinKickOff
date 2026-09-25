"""Generate the rule lists of the user documentation: docs/user/<lang>/rules.md for ru, uk and en.

Run after changing the catalog or its translations (rules/lang/*.toml):
    cd WinKickOff
    python tools/make_rule_docs.py

The output is deterministic; tests/test_docs.py fails when a list is out of date.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parent / "docs" / "user"
sys.path.insert(0, str(ROOT))

from winkickoff.core.catalog import Catalog, load_catalog  # noqa: E402
from winkickoff.core.i18n import LANGUAGES, CatalogTexts  # noqa: E402

WORDS = {
    "ru": {
        "title": "Список правил",
        "intro": "Все правила каталога WinKickOff {version} по группам, всего {count}. Файл создаётся из каталога "
                 "командой `python tools/make_rule_docs.py`, вручную его не редактируют. В программе у каждого правила "
                 "есть также технические детали, проверка после установки и откат.",
        "levels": {"baseline": "базовое", "recommended": "рекомендуемое", "optional": "необязательное", "risky": "рискованное"},
        "legend": "Уровни: базовое (основа защиты, выключать не рекомендуется), рекомендуемое, необязательное, "
                  "рискованное (может мешать программам, включать осознанно).",
        "level": "Уровень", "office": "«Офис»", "strict": "«Строгий»", "on": "включено", "off": "выключено",
        "effect": "Эффект", "risk": "Риск",
    },
    "uk": {
        "title": "Перелік правил",
        "intro": "Усі правила каталогу WinKickOff {version} за групами, усього {count}. Файл створюється з каталогу "
                 "командою `python tools/make_rule_docs.py`, вручну його не редагують. У програмі кожне правило має також "
                 "технічні деталі, перевірку після встановлення та відкат.",
        "levels": {"baseline": "базове", "recommended": "рекомендоване", "optional": "необов'язкове", "risky": "ризиковане"},
        "legend": "Рівні: базове (основа захисту, вимикати не рекомендується), рекомендоване, необов'язкове, "
                  "ризиковане (може заважати програмам, вмикати свідомо).",
        "level": "Рівень", "office": "«Офіс»", "strict": "«Суворий»", "on": "увімкнено", "off": "вимкнено",
        "effect": "Ефект", "risk": "Ризик",
    },
    "en": {
        "title": "Rule list",
        "intro": "Every rule of the WinKickOff catalog {version} by group, {count} in total. This file is generated from "
                 "the catalog by `python tools/make_rule_docs.py` and is not edited by hand. In the program every rule "
                 "also shows its technical details, the check after installation and the rollback.",
        "levels": {"baseline": "baseline", "recommended": "recommended", "optional": "optional", "risky": "risky"},
        "legend": "Levels: baseline (the core of the protection, disabling is not recommended), recommended, optional, "
                  "risky (may disturb programs, enable deliberately).",
        "level": "Level", "office": "\"Office\"", "strict": "\"Strict\"", "on": "enabled", "off": "disabled",
        "effect": "Effect", "risk": "Risk",
    },
}


def _preset_states(name: str) -> dict[str, bool]:
    data = json.loads((ROOT / "profiles" / name).read_text(encoding="utf-8"))
    return {rule_id: bool(entry.get("enabled")) for rule_id, entry in data.get("rules", {}).items()}


def render(catalog: Catalog, texts: CatalogTexts) -> str:
    w = WORDS[texts.language]
    office, strict = _preset_states("preset-office.json"), _preset_states("preset-strict.json")
    out = [f"# {w['title']}", "", w["intro"].format(version=catalog.version, count=len(catalog.rules)), "", w["legend"], ""]

    def rules_of(group_id: str) -> list[str]:
        lines: list[str] = []
        for rule in catalog.rules_in_group(group_id, recursive=False):
            state = (f"{w['level']}: {w['levels'][rule.level]}. {w['office']}: {w['on'] if office.get(rule.id) else w['off']}; "
                     f"{w['strict']}: {w['on'] if strict.get(rule.id) else w['off']}.")
            lines.append(f"- **{texts.rule(rule, 'title')}** (`{rule.id}`). {state}")
            lines.append(f"  {texts.rule(rule, 'summary')}")
            lines.append(f"  {w['effect']}: {texts.rule(rule, 'effect')}")
            if rule.risk:
                lines.append(f"  {w['risk']}: {texts.rule(rule, 'risk')}")
        return lines

    def section(group_id: str, level: int) -> None:
        group = catalog.groups[group_id]
        out.append(f"{'#' * level} {texts.group(group, 'title')}")
        out.append("")
        summary = texts.group(group, "summary")
        if summary:
            out.extend([summary, ""])
        lines = rules_of(group_id)
        if lines:
            out.extend(lines + [""])
        for child in catalog.children(group_id):
            section(child.id, level + 1)

    for top in catalog.children(None):
        section(top.id, 2)
    return "\n".join(out).rstrip() + "\n"


def expected(catalog: Catalog, language: str) -> str:
    return render(catalog, CatalogTexts.load(ROOT / "rules", language))


def main() -> None:
    catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
    for language in LANGUAGES:
        path = DOCS / language / "rules.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(expected(catalog, language).replace("\n", "\r\n").encode("utf-8"))
        print(f"written {path.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
