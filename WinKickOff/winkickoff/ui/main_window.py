"""Main window of WinKickOff.

Layout: profile toolbar at the top; rule tree with check boxes and search on the left; description,
parameters or data form of the selected node on the right; messages (checks, build, automatic
changes) at the bottom; status line.

Mouse: a click on the check box toggles a rule or a whole group (dependent rules follow
automatically); a click on the expand indicator only opens the branch; a click on the text selects.
Keyboard: Space toggles, Ctrl+F search, Ctrl+S save, Ctrl+O open, F7 check, F9 build.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.catalog import Action, Catalog, Group, Param, Rule
from winkickoff.core.apply import (
    ApplyPlan,
    RevertPlan,
    parse_audit_report,
    plan_apply,
    plan_revert,
    render_apply,
    render_audit,
    render_revert,
    render_undo,
    run_audit,
    status_title,
    write_script,
)
from winkickoff.core import apply as apply_module
from winkickoff.core.deps import Change, Resolver
from winkickoff.core.i18n import LANGUAGE_NAMES, N_, catalog_texts, language, tr
from winkickoff.core.importer import IMPORTED_NAME, ImportFailed, import_xml
from winkickoff.core.paths import AppPaths, display_path
from winkickoff.core.profile import Profile
from winkickoff.core.pscheck import PsCheckResult, check_scripts
from winkickoff.core.render import BuildResult, Renderer, RenderError, render_action, substitute
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings
from winkickoff.core.validate import Issue, has_errors, validate_catalog, validate_profile, validate_xml
from winkickoff.core.verify import rollback_steps, verify_steps
from winkickoff.ui.checkimages import make_check_images
from winkickoff.ui.data_forms import AccountsForm, InstallForm, LanguagesForm

log = logging.getLogger(__name__)

WORKFLOW_NODE = "info:workflow"
PRESET_NAMES = (N_("Офис"), N_("Строгий"), N_("Ноутбук"))  # preset names are Russian data; shown through tr()
DATA_NODES: tuple[tuple[str, str], ...] = (
    ("data:install", N_("Установка: редакция, ключ, часовой пояс")),
    ("data:accounts", N_("Учётные записи")),
    ("data:languages", N_("Языки и регион")),
)
LEVEL_TITLES = {"baseline": N_("базовое"), "recommended": N_("рекомендуемое"), "optional": N_("необязательное"), "risky": N_("рискованное")}
PHASE_TITLES = {
    "windowspe": N_("установщик (windowsPE)"),
    "specialize-xml": N_("первая загрузка (команда в XML)"),
    "specialize": N_("первая загрузка (скрипт машины Setup-System.ps1)"),
    "default-user": N_("профиль пользователя по умолчанию"),
    "user-first-logon": N_("первый вход каждого пользователя (Setup-User.ps1)"),
    "post-oobe": N_("после первичной настройки (Post-OOBE.ps1)"),
    "oobe-xml": N_("первичная настройка (OOBE)"),
}
ISSUE_TITLES = {"error": N_("ошибка"), "warning": N_("предупреждение"), "info": N_("сведения"), "change": N_("изменено")}
VK_S, VK_O, VK_F = 83, 79, 70  # virtual-key codes: shortcuts work with any keyboard layout

WORKFLOW = [
    ("h1", N_("Порядок работы")),
    ("", N_("WinKickOff собирает файл autounattend.xml для автоматической установки Windows 11. Файл кладётся в корень "
         "флешки с установкой Windows; установщик сам находит его и выполняет всё, что выбрано здесь.")),
    ("h2", N_("1. Профиль")),
    ("", N_("Поле «Профиль» на панели сверху. «Пресет: Офис» повторяет проверенный файл ответов v0.2; «Пресет: Строгий» "
         "добавляет ограничения, которые могут мешать старым программам. Пресеты не меняются: изменённый профиль "
         "сохраняется под своим именем (кнопка «Сохранить как»).")),
    ("h2", N_("2. Правила")),
    ("", N_("Дерево слева содержит все настройки установки. Квадрат перед названием включает или выключает правило "
         "(или всю группу); «+» только раскрывает ветку. Правила, которые зависят от выключенного, выключаются "
         "автоматически, а включение правила включает то, что ему нужно: что изменилось, видно в строке состояния "
         "и в списке внизу. Поиск (Ctrl+F) ищет по названию, тегам и техническим деталям, например по имени ключа реестра.")),
    ("h2", N_("3. Описание и параметры")),
    ("", N_("Справа для выбранного правила: что оно делает технически (ключи реестра, службы, команды), эффект, риски, "
         "версии Windows, проверка и откат. Параметры правила (часы, режимы, пороги) меняются там же, под описанием.")),
    ("h2", N_("4. Данные установки")),
    ("", N_("Узлы «Установка», «Учётные записи», «Языки и регион» в начале дерева: редакция и ключ, часовой пояс, "
         "стартовые учётные записи, язык интерфейса (равен языку ISO) и языки ввода.")),
    ("h2", N_("5. Сохранение профиля")),
    ("", N_("«Сохранить» (Ctrl+S) записывает профиль в папку profiles рядом с программой, чтобы повторять установку на "
         "других ПК. Профиль также встраивается в каждый собранный файл: «Файл, Открыть профиль из autounattend.xml» "
         "восстанавливает настройки из готового autounattend.xml.")),
    ("h2", N_("6. Проверка и сборка")),
    ("", N_("«Проверить» (F7) проверяет профиль и файл, который получится. «Собрать autounattend.xml» (F9) собирает файл "
         "только из включённых правил, проверяет ограничения установщика Windows и синтаксис PowerShell и предлагает, "
         "куда сохранить. Ошибки и предупреждения появляются в списке внизу; двойной щелчок ведёт к правилу.")),
    ("h2", N_("7. Установка")),
    ("", N_("Скопируйте autounattend.xml в корень флешки с установочным образом Windows 11 и загрузите ПК с неё. "
         "Установщик спросит только диск для установки. После установки логи лежат в C:\\ProgramData\\Unattend\\Logs.")),
]


def user_docs() -> str:
    """The user documentation in the interface language (docs/user/<ru|uk|en>/README.md)."""
    return f"docs/user/{language()}/README.md"


def _profile_name(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return str(data.get("name") or path.stem)
    except (OSError, ValueError):
        return path.stem


class MainWindow(tk.Tk):
    def __init__(self, paths: AppPaths, catalog: Catalog, profile: Profile, resources: Resources,
                 settings: Settings | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.settings = settings if settings is not None else Settings.load(paths.settings_file)
        self.restart_state: dict[str, Any] | None = None
        self._busy = False
        self.catalog = catalog
        self.profile = profile
        self.resources = resources
        self.resolver = Resolver(catalog)
        self.renderer = Renderer(catalog, paths.templates, resources.keyboards)
        self.dirty = False
        self._search_job: str | None = None
        self._suppress_search = False
        self._open_groups: set[str] = set()
        self._param_vars: list[tk.Variable] = []
        self._param_marks: dict[str, ttk.Label] = {}
        self._choices: list[tuple[str, Path]] = []
        self._last_output: Path | None = None
        self._issues: list[Issue] = []
        self._current_item = WORKFLOW_NODE
        self.forms: dict[str, InstallForm | AccountsForm | LanguagesForm] = {}

        self.geometry(self.settings.geometry or "1260x800")
        self.minsize(980, 620)
        self._setup_style()
        self.images = make_check_images(self)
        self.style.configure("Treeview", rowheight=self.images["on"].height() + 8)
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._bind_keys()
        self.rebuild_tree()
        self.refresh_profile_choices()
        self.update_title()
        self.select_node(WORKFLOW_NODE)
        self.set_status(tr("Каталог правил {0}: {1} правил в {2} группах. Профиль: {3}.", catalog.version, len(catalog.rules), len(catalog.groups), tr(profile.name)))

    # ----------------------------------------------------------------- style and layout

    def _setup_style(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("vista")
        except tk.TclError:
            pass
        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        size = int(base.actual("size")) or 9
        self.font_h1 = tkfont.Font(self, family=family, size=size + 4, weight="bold")
        self.font_h2 = tkfont.Font(self, family=family, size=size + 1, weight="bold")
        self.font_text = tkfont.Font(self, family=family, size=size + 1)
        self.font_mono = tkfont.Font(self, family="Consolas", size=size)
        self.style.configure("H1.TLabel", font=self.font_h1)
        self.style.configure("Note.TLabel", foreground="#555555")
        self.style.configure("Error.TLabel", foreground="#b00020")
        self.style.configure("Changed.TLabel", foreground="#1f4e79", font=(family, size, "bold"))

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        presets = tk.Menu(file_menu, tearoff=False)
        for path in sorted((self.paths.data / "profiles").glob("preset-*.json")):
            presets.add_command(label=tr(_profile_name(path)), command=lambda p=path: self.load_profile_file(p))
        file_menu.add_cascade(label=tr("Новый профиль из пресета"), menu=presets)
        file_menu.add_command(label=tr("Открыть профиль..."), accelerator="Ctrl+O", command=self.open_profile_dialog)
        file_menu.add_command(label=tr("Открыть профиль из autounattend.xml..."), command=self.import_from_xml)
        file_menu.add_command(label=tr("Сравнить с профилем..."), command=self.compare_with_file)
        self.recent_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(label=tr("Недавние"), menu=self.recent_menu)
        self._rebuild_recent_menu()
        file_menu.add_separator()
        file_menu.add_command(label=tr("Сохранить профиль"), accelerator="Ctrl+S", command=self.save_profile)
        file_menu.add_command(label=tr("Сохранить профиль как..."), command=self.save_profile_as)
        file_menu.add_separator()
        file_menu.add_command(label=tr("Выход"), command=self.on_close)
        menubar.add_cascade(label=tr("Файл"), menu=file_menu)
        build_menu = tk.Menu(menubar, tearoff=False)
        build_menu.add_command(label=tr("Проверить"), accelerator="F7", command=self.check)
        build_menu.add_command(label=tr("Собрать autounattend.xml..."), accelerator="F9", command=self.build)
        build_menu.add_command(label=tr("Открыть папку результата"), command=self.open_output_folder)
        build_menu.add_separator()
        build_menu.add_command(label=tr("Проверить каталог правил"), command=self.check_catalog)
        menubar.add_cascade(label=tr("Сборка"), menu=build_menu)
        view_menu = tk.Menu(menubar, tearoff=False)
        self.language_var = tk.StringVar(value=language())
        for code, name in LANGUAGE_NAMES.items():  # native names, never translated
            view_menu.add_radiobutton(label=name, value=code, variable=self.language_var, command=lambda c=code: self.change_language(c))
        menubar.add_cascade(label=tr("Язык"), menu=view_menu)
        self.pc_menu = tk.Menu(menubar, tearoff=False)
        self._fill_pc_menu(self.pc_menu)
        self.pc_menu.add_separator()
        self.allow_apply_var = tk.BooleanVar(value=self.settings.allow_apply)
        self.pc_menu.add_checkbutton(label=tr("Разрешить применение на этом ПК"), variable=self.allow_apply_var,
                                     command=self.toggle_allow_apply)
        menubar.add_cascade(label=tr("Этот ПК"), menu=self.pc_menu)
        self.tree_menu = tk.Menu(self, tearoff=False)
        self._fill_pc_menu(self.tree_menu)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label=tr("Порядок работы"), command=lambda: self.select_node(WORKFLOW_NODE))
        help_menu.add_command(label=tr("Документация пользователя"), command=lambda: self.open_doc(user_docs()))
        help_menu.add_command(label=tr("О программе"), command=self.about)
        menubar.add_cascade(label=tr("Справка"), menu=help_menu)
        self.config(menu=menubar)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6, 8, 4))
        bar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(bar, text=tr("Профиль:")).pack(side=tk.LEFT)
        self.profile_var = tk.StringVar()
        self.profile_box = ttk.Combobox(bar, textvariable=self.profile_var, state="readonly", width=34)
        self.profile_box.pack(side=tk.LEFT, padx=(4, 6))
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_selected)
        for text, command in ((tr("Открыть..."), self.open_profile_dialog), (tr("Сохранить"), self.save_profile), (tr("Сохранить как..."), self.save_profile_as)):
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        self.check_button = ttk.Button(bar, text=tr("Проверить (F7)"), command=self.check)
        self.check_button.pack(side=tk.LEFT, padx=2)
        self.build_button = ttk.Button(bar, text=tr("Собрать autounattend.xml (F9)"), command=self.build)
        self.build_button.pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text=tr("Папка результата"), command=self.open_output_folder).pack(side=tk.LEFT, padx=2)

    def _build_body(self) -> None:
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, anchor=tk.W, padding=(8, 3)).pack(side=tk.BOTTOM, fill=tk.X)

        vertical = ttk.PanedWindow(self, orient=tk.VERTICAL)
        vertical.pack(fill=tk.BOTH, expand=True)
        horizontal = ttk.PanedWindow(vertical, orient=tk.HORIZONTAL)
        vertical.add(horizontal, weight=5)

        left = ttk.Frame(horizontal, padding=(8, 2, 3, 0))
        horizontal.add(left, weight=2)
        search_row = ttk.Frame(left)
        search_row.pack(fill=tk.X)
        ttk.Label(search_row, text=tr("Поиск:")).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(search_row, text=tr("Сбросить"), command=self.clear_search).pack(side=tk.LEFT)
        self.search_var.trace_add("write", lambda *_: self._schedule_search())

        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.tree.tag_configure("off", foreground="#7a7a7a")
        self.tree.tag_configure("changed", foreground="#1f4e79")
        self.tree.tag_configure("risky", foreground="#a33333")
        self.tree.tag_configure("info", foreground="#1f4e79")
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-Button-1>", self._on_tree_double)
        self.tree.bind("<space>", self._on_space)
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self._open_groups.add(self.tree.focus()))
        self.tree.bind("<<TreeviewClose>>", lambda _e: self._open_groups.discard(self.tree.focus()))

        self.right = ttk.Frame(horizontal, padding=(3, 2, 8, 0))
        horizontal.add(self.right, weight=3)
        self.detail_view = ttk.Frame(self.right)
        self.text_frame = ttk.Frame(self.detail_view)
        self.text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.detail = tk.Text(self.text_frame, wrap=tk.WORD, font=self.font_text, state=tk.DISABLED, padx=10, pady=8, height=12, relief=tk.FLAT)
        detail_scroll = ttk.Scrollbar(self.text_frame, orient=tk.VERTICAL, command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.detail.tag_configure("h1", font=self.font_h1, spacing3=4)
        self.detail.tag_configure("h2", font=self.font_h2, spacing1=10, spacing3=2)
        self.detail.tag_configure("mono", font=self.font_mono, lmargin1=12, lmargin2=12)
        self.detail.tag_configure("muted", foreground="#666666")
        self.detail.tag_configure("risk", foreground="#a33333")
        self.detail.tag_configure("link", foreground="#1a5fb4", underline=True)
        self.detail.tag_bind("link", "<Enter>", lambda _e: self.detail.configure(cursor="hand2"))
        self.detail.tag_bind("link", "<Leave>", lambda _e: self.detail.configure(cursor=""))
        self._link_tags: list[str] = []
        self.params_frame = ttk.LabelFrame(self.detail_view, padding=(10, 6))
        self.detail_view.pack(fill=tk.BOTH, expand=True)

        messages = ttk.Frame(vertical, padding=(8, 2, 8, 2))
        vertical.add(messages, weight=1)
        ttk.Label(messages, text=tr("Сообщения: проверка, сборка, автоматические изменения (двойной щелчок ведёт к правилу)")).pack(anchor=tk.W)
        box = ttk.Frame(messages)
        box.pack(fill=tk.BOTH, expand=True)
        self.messages = ttk.Treeview(box, columns=("level", "target", "message"), show="headings", height=5)
        for column, title, width, stretch in (("level", tr("Вид"), 110, False), ("target", tr("Где"), 230, False), ("message", tr("Сообщение"), 700, True)):
            self.messages.heading(column, text=title)
            self.messages.column(column, width=width, stretch=stretch)
        messages_scroll = ttk.Scrollbar(box, orient=tk.VERTICAL, command=self.messages.yview)
        self.messages.configure(yscrollcommand=messages_scroll.set)
        self.messages.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        messages_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.messages.tag_configure("error", foreground="#b00020")
        self.messages.tag_configure("warning", foreground="#8a5a00")
        self.messages.tag_configure("change", foreground="#1f4e79")
        self.messages.bind("<Double-Button-1>", self._on_message_double)

    def _bind_keys(self) -> None:
        self.bind("<F7>", lambda _e: None if self._busy else self.check())
        self.bind("<F9>", lambda _e: self.build())
        self.bind("<Control-KeyPress>", self._on_ctrl_key)
        self.bind("<Escape>", lambda _e: self.clear_search())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _on_ctrl_key(self, event: tk.Event) -> str | None:  # type: ignore[type-arg]
        if event.keycode == VK_S:
            self.save_profile()
        elif event.keycode == VK_O:
            self.open_profile_dialog()
        elif event.keycode == VK_F:
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)
        else:
            return None
        return "break"

    # ----------------------------------------------------------------- title, status, dirty

    def update_title(self) -> None:
        self.title(f"{APP_NAME} {APP_VERSION}: {tr(self.profile.name)}{' *' if self.dirty else ''}")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def mark_dirty(self) -> None:
        if not self.dirty:
            self.dirty = True
            self.update_title()

    # ----------------------------------------------------------------- tree

    def rebuild_tree(self, visible: set[str] | None = None) -> None:
        """Build the tree from the catalog. With visible, only those rules (and their groups) are shown, expanded."""
        self.tree.delete(*self.tree.get_children(""))
        if visible is None:
            self.tree.insert("", tk.END, iid=WORKFLOW_NODE, text="  " + tr("Порядок работы"), tags=("info",))
            for iid, title in DATA_NODES:
                self.tree.insert("", tk.END, iid=iid, text="  " + tr(title))
        self._insert_groups("", None, visible)

    def _insert_groups(self, parent_item: str, parent_group: str | None, visible: set[str] | None) -> None:
        for group in self.catalog.children(parent_group):
            rules = self.catalog.rules_in_group(group.id)
            if visible is not None and not any(r.id in visible for r in rules):
                continue
            item = "g:" + group.id
            is_open = visible is not None or item in self._open_groups
            self.tree.insert(parent_item, tk.END, iid=item, text=self._group_text(group.id), image=self._group_image(group.id), open=is_open)
            self._insert_groups(item, group.id, visible)
            for rule in self.catalog.rules_in_group(group.id, recursive=False):
                if visible is None or rule.id in visible:
                    self.tree.insert(item, tk.END, iid="r:" + rule.id, text=" " + self.rule_title(rule.id), image=self._rule_image(rule), tags=self._rule_tags(rule))

    def _rule_image(self, rule: Rule) -> tk.PhotoImage:
        return self.images["on" if self.profile.is_enabled(rule.id) else "off"]

    def _rule_tags(self, rule: Rule) -> tuple[str, ...]:
        tags: list[str] = []
        enabled = self.profile.is_enabled(rule.id)
        if not enabled:
            tags.append("off")
        if rule.level == "risky":
            tags.append("risky")
        if enabled != rule.default or self.profile.rules[rule.id].params:
            tags.append("changed")  # differs from the catalog default: state or a parameter
        return tuple(tags)

    def _group_counts(self, group_id: str) -> tuple[int, int]:
        rules = self.catalog.rules_in_group(group_id)
        return sum(1 for r in rules if self.profile.is_enabled(r.id)), len(rules)

    def _group_image(self, group_id: str) -> tk.PhotoImage:
        on, total = self._group_counts(group_id)
        return self.images["on" if on == total and total else "off" if on == 0 else "partial"]

    def _group_text(self, group_id: str) -> str:
        on, total = self._group_counts(group_id)
        return " " + tr("{0}   {1} из {2}", self.group_title(group_id), on, total)

    # ----------------------------------------------------------------- texts in the interface language

    def rule_title(self, rule_id: str) -> str:
        return catalog_texts().rule(self.catalog.rules[rule_id], "title")

    def rule_text(self, rule: Rule, name: str) -> str:
        return catalog_texts().rule(rule, name)

    def group_title(self, group_id: str) -> str:
        return catalog_texts().group(self.catalog.groups[group_id], "title")

    def param_title(self, rule: Rule, param: Param) -> str:
        return catalog_texts().param(rule, param)

    def param_options(self, rule: Rule, param: Param) -> list[tuple[Any, str]]:
        return [(value, catalog_texts().option(rule, param, value, title)) for value, title in param.values]

    def _all_items(self, parent: str = "") -> list[str]:
        items: list[str] = []
        for child in self.tree.get_children(parent):
            items.append(child)
            items.extend(self._all_items(child))
        return items

    def refresh_marks(self) -> None:
        for item in self._all_items():
            if item.startswith("r:"):
                rule = self.catalog.rules[item[2:]]
                self.tree.item(item, image=self._rule_image(rule), tags=self._rule_tags(rule))
            elif item.startswith("g:"):
                self.tree.item(item, text=self._group_text(item[2:]), image=self._group_image(item[2:]))

    def select_node(self, iid: str) -> None:
        if not self.tree.exists(iid):
            self.clear_search()
            if not self.tree.exists(iid):
                return
        parent = self.tree.parent(iid)
        while parent:
            self.tree.item(parent, open=True)
            self._open_groups.add(parent)
            parent = self.tree.parent(parent)
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self.show_item(iid)

    # ----------------------------------------------------------------- tree events

    def _on_tree_click(self, event: tk.Event) -> str | None:  # type: ignore[type-arg]
        item = self.tree.identify_row(event.y)
        if not item:
            return None
        element = str(self.tree.identify_element(event.x, event.y))
        if "image" in element and (item.startswith("r:") or item.startswith("g:")):
            self.tree.selection_set(item)
            self.tree.focus(item)
            self.toggle_item(item)
            return "break"
        return None  # the indicator opens the branch, the text selects: default behaviour

    def _on_tree_double(self, event: tk.Event) -> str | None:  # type: ignore[type-arg]
        """The second click of a quick double click arrives here instead of <Button-1>:
        on a check box it toggles again (every click counts), on a rule's text it toggles once,
        on a group's text or indicator the default (open or close) applies."""
        item = self.tree.identify_row(event.y)
        element = str(self.tree.identify_element(event.x, event.y))
        if "image" in element and (item.startswith("r:") or item.startswith("g:")):
            self.toggle_item(item)
            return "break"
        if item.startswith("r:") and "indicator" not in element:
            self.toggle_item(item)
            return "break"
        return None

    def _on_space(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        selection = self.tree.selection()
        if selection:
            self.toggle_item(selection[0])
        return "break"

    def _on_tree_select(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        selection = self.tree.selection()
        if selection:
            self.show_item(selection[0])

    # ----------------------------------------------------------------- toggling

    def toggle_item(self, item: str) -> list[Change]:
        if item.startswith("r:"):
            rule_id = item[2:]
            changes = self.resolver.set_rule(self.profile, rule_id, not self.profile.is_enabled(rule_id))
            scope = {rule_id}
        elif item.startswith("g:"):
            on, total = self._group_counts(item[2:])
            changes = self.resolver.set_group(self.profile, item[2:], on != total)
            scope = {r.id for r in self.catalog.rules_in_group(item[2:])}
        else:
            return []
        self._apply_changes(changes, scope)
        if self._current_item == item or item.startswith("r:"):
            self.show_item(item)
        return changes

    def _reason_text(self, change: Change) -> str:
        reason = change.reason
        for prefix, template in (
            ("requires ", tr("требует «{}», которое выключено")),
            ("required by ", tr("нужно для «{}»")),
            ("conflicts with ", tr("конфликтует с «{}»")),
        ):
            if reason.startswith(prefix):
                other = reason[len(prefix):]
                title = self.rule_title(other) if other in self.catalog.rules else other
                return template.format(title)
        return tr("по вашему действию")

    def _apply_changes(self, changes: list[Change], scope: set[str] | None = None) -> None:
        """Show the result of a toggle. scope: rules the user acted on (a rule or a whole group);
        everything else in changes happened automatically because of dependencies."""
        if not changes:
            self.set_status(tr("Без изменений"))
            return
        self.mark_dirty()
        self.refresh_marks()
        scope = scope if scope is not None else {c.rule_id for c in changes if c.reason == "user"}
        direct = [c for c in changes if c.rule_id in scope]
        cascade = [c for c in changes if c.rule_id not in scope]
        action = tr("Включено") if (direct or changes)[0].enabled else tr("Выключено")
        text = tr("{0} правил: {1}", action, len(direct))
        if cascade:
            text += tr("; автоматически изменено ещё {0} за пределами выбранного (список внизу)", len(cascade))
            rows = [
                Issue("change", c.rule_id, tr("{0} «{1}»: {2}", tr("Включено") if c.enabled else tr("Выключено"), self.rule_title(c.rule_id), self._reason_text(c)))
                for c in cascade
            ]
            self.show_issues(rows)
        self.set_status(text)

    # ----------------------------------------------------------------- search

    def _schedule_search(self) -> None:
        if self._suppress_search:
            return
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(150, self.apply_search)

    def apply_search(self) -> None:
        self._search_job = None
        query = self.search_var.get().strip()
        if not query:
            self.rebuild_tree()
            if self.tree.exists(self._current_item):
                self.tree.selection_set(self._current_item)
                self.tree.see(self._current_item)
            return
        found = set(self.catalog.search(query))
        if language() != "ru":  # the index is Russian; also search the translated titles and summaries
            needle = query.lower()
            found |= {r.id for r in self.catalog.rules.values()
                      if needle in (self.rule_text(r, "title") + " " + self.rule_text(r, "summary")).lower()}
        self.rebuild_tree(found)
        self.set_status(tr("Найдено правил: {0}", len(found)) if found else tr("Ничего не найдено"))

    def clear_search(self) -> None:
        if self._search_job is not None:
            self.after_cancel(self._search_job)
            self._search_job = None
        self._suppress_search = True
        self.search_var.set("")
        self._suppress_search = False
        self.apply_search()

    # ----------------------------------------------------------------- right panel

    def _show_panel(self, form_key: str | None) -> None:
        for key, form in self.forms.items():
            if key != form_key:
                form.pack_forget()
        if form_key is None:
            if not self.detail_view.winfo_ismapped():
                self.detail_view.pack(fill=tk.BOTH, expand=True)
            return
        self.detail_view.pack_forget()
        if form_key not in self.forms:
            factory = {"data:install": InstallForm, "data:accounts": AccountsForm, "data:languages": LanguagesForm}[form_key]
            self.forms[form_key] = factory(self.right, self)
        form = self.forms[form_key]
        form.refresh()
        form.pack(fill=tk.BOTH, expand=True)

    def show_item(self, item: str) -> None:
        self._current_item = item
        if item.startswith("data:"):
            self._show_panel(item)
            return
        self._show_panel(None)
        if item.startswith("r:"):
            rule = self.catalog.rules[item[2:]]
            self._write_detail(self._rule_parts(rule))
            self._build_params(rule)
        elif item.startswith("g:"):
            self._write_detail(self._group_parts(item[2:]))
            self._build_group_buttons(item[2:])
        else:
            self._write_detail([(tag, tr(text)) for tag, text in WORKFLOW])
            self._clear_params()

    def _rule_parts(self, rule: Rule) -> list[tuple[str, str]]:
        params = self.profile.params_for(self.catalog, rule.id)
        enabled = self.profile.is_enabled(rule.id)
        parts: list[tuple[str, str]] = [
            ("h1", self.rule_title(rule.id)),
            ("muted", tr("{0}   |   уровень: {1}   |   {2}   |   {3}", tr("Включено") if enabled else tr("Выключено"),
                         tr(LEVEL_TITLES.get(rule.level, rule.level)), tr(PHASE_TITLES.get(rule.phase, rule.phase)), rule.id)),
            ("", self.rule_text(rule, "summary")),
            ("h2", tr("Что делает технически")),
        ]
        parts += [("mono", self._action_text(action, params)) for action in rule.actions]
        parts += [("h2", tr("Эффект")), ("", self.rule_text(rule, "effect"))]
        if rule.risk:
            parts += [("h2", tr("Риск и побочные действия")), ("risk", self.rule_text(rule, "risk"))]
        if rule.versions:
            parts += [("h2", tr("Версии Windows")), ("", self.rule_text(rule, "versions"))]
        parts.append(("h2", tr("Зависимости")))
        for caption, ids, optional in (
            (tr("Требует"), list(rule.requires), False),
            (tr("Выключится вместе с ним"), self.resolver.dependents(rule.id), False),
            (tr("Конфликтует с"), list(rule.conflicts), True),
        ):
            if not ids and optional:
                continue
            parts.append(("", f"{caption}: {tr('ничего')}" if not ids else f"{caption}:"))
            parts += [(f"link:r:{other}", "    " + self._rule_link_text(other)) for other in ids]
        parts.append(("h2", tr("Проверка после установки")))
        if rule.verify:
            parts.append(("mono", self.rule_text(rule, "verify")))
        else:
            parts.append(("muted", tr("Сформировано по действиям правила:")))
            parts += [("mono", step) for step in verify_steps(rule, params)]
        parts.append(("h2", tr("Откат")))
        if rule.rollback:
            parts.append(("", self.rule_text(rule, "rollback")))
        else:
            parts.append(("muted", tr("Сформировано по действиям правила:")))
            parts += [("mono", step) for step in rollback_steps(rule, params)]
        parts += [("h2", tr("Подробнее")), (f"link:doc:{rule.doc}", tr("Карточка справочника: ") + rule.doc)]
        return parts

    def _rule_link_text(self, rule_id: str) -> str:
        state = tr("включено") if self.profile.is_enabled(rule_id) else tr("выключено")
        return f"{self.rule_title(rule_id)} ({state})"

    def _group_parts(self, group_id: str) -> list[tuple[str, str]]:
        group = self.catalog.groups[group_id]
        on, total = self._group_counts(group_id)
        summary = catalog_texts().group(group, "summary")
        parts: list[tuple[str, str]] = [("h1", self.group_title(group_id)), ("muted", tr("Правил: {0}, включено: {1}", total, on))]
        if summary:
            parts.append(("", summary))
        parts.append(("h2", tr("Правила группы")))
        for rule in self.catalog.rules_in_group(group_id):
            mark = "[x]" if self.profile.is_enabled(rule.id) else "[ ]"
            parts.append((f"link:r:{rule.id}", f"{mark} {self.rule_title(rule.id)}"))
        return parts

    def _action_text(self, action: Action, params: dict[str, Any]) -> str:
        f = action.fields
        if action.type == "xml-oobe":
            value = substitute(f["value"], params)
            return tr("XML, первичная настройка: <{0}>{1}</{2}>", f['element'], value, f['element'])
        if action.type in ("xml-pe-command", "xml-specialize-command"):
            return tr("XML, команда: {0}", f['command'])
        try:
            return render_action(action, params)
        except (RenderError, KeyError) as exc:
            return f"{action.type}: {exc}"

    def _write_detail(self, parts: list[tuple[str, str]]) -> None:
        """Parts are (tag, line). A tag "link:<target>" makes the line clickable: the target is a tree
        node ("r:<rule>", "g:<group>") or "doc:<path#anchor>" (a card of the reference)."""
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        for name in self._link_tags:
            self.detail.tag_delete(name)
        self._link_tags = []
        for tag, text in parts:
            if tag.startswith("link:"):
                name = f"link{len(self._link_tags)}"
                self._link_tags.append(name)
                self.detail.insert(tk.END, text, ("link", name))
                self.detail.insert(tk.END, "\n")
                self.detail.tag_bind(name, "<Button-1>", lambda _e, target=tag[5:]: self.follow_link(target))
            else:
                self.detail.insert(tk.END, text + "\n", tag or ())
        self.detail.configure(state=tk.DISABLED)
        self.detail.yview_moveto(0)

    def follow_link(self, target: str) -> None:
        if target.startswith("doc:"):
            self.open_doc(target[4:])
        else:
            self.select_node(target)

    def open_doc(self, doc: str) -> None:
        """Open a card of the reference in the program Windows associates with .md files."""
        path = self.paths.docs_root / doc.split("#", 1)[0]
        if not path.exists():
            self.set_status(tr("Карточка справочника не найдена: {0}", path))
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            self.set_status(tr("Открыта карточка справочника: {0}", path.name) + (tr(", раздел «{0}»", doc.split('#', 1)[1]) if "#" in doc else ""))
        except OSError as exc:
            self.set_status(tr("Карточка не открылась: {0}", exc))

    def _clear_params(self) -> None:
        for widget in self.params_frame.winfo_children():
            widget.destroy()
        self._param_vars = []
        self._param_marks = {}
        self.params_frame.pack_forget()

    def _build_group_buttons(self, group_id: str) -> None:
        self._clear_params()
        self.params_frame.configure(text=tr("Вся группа"))
        self.params_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.text_frame, pady=(6, 4))
        for text, command in (
            (tr("Включить все"), lambda: self._group_action(group_id, True)),
            (tr("Выключить все"), lambda: self._group_action(group_id, False)),
            (tr("Как в каталоге по умолчанию"), lambda: self._group_reset(group_id)),
        ):
            ttk.Button(self.params_frame, text=text, command=command).pack(side=tk.LEFT, padx=(0, 6))

    def _group_action(self, group_id: str, enabled: bool) -> None:
        scope = {r.id for r in self.catalog.rules_in_group(group_id)}
        self._apply_changes(self.resolver.set_group(self.profile, group_id, enabled), scope)
        self.show_item("g:" + group_id)

    def _group_reset(self, group_id: str) -> None:
        scope = {r.id for r in self.catalog.rules_in_group(group_id)}
        self._apply_changes(self.resolver.reset_group(self.profile, group_id), scope)
        self.show_item("g:" + group_id)

    def _build_params(self, rule: Rule) -> None:
        self._clear_params()
        if not rule.params:
            return
        self.params_frame.configure(text=tr("Параметры правила"))
        self.params_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.text_frame, pady=(6, 4))
        for row, param in enumerate(rule.params.values()):
            ttk.Label(self.params_frame, text=self.param_title(rule, param)).grid(row=row, column=0, sticky=tk.W, padx=(0, 12), pady=2)
            self._param_widget(rule, param).grid(row=row, column=1, sticky=tk.W, pady=2)
            hint = tr("по умолчанию: {0}", self._param_display(rule, param, param.default))
            if param.type == "int" and (param.min is not None or param.max is not None):
                hint += tr(", диапазон {0}..{1}", param.min, param.max)
            ttk.Label(self.params_frame, text=hint, style="Note.TLabel").grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
            mark = ttk.Label(self.params_frame, style="Changed.TLabel")
            mark.grid(row=row, column=3, sticky=tk.W, padx=(10, 0))
            self._param_marks[param.name] = mark
            self._update_param_mark(rule, param)
        ttk.Button(self.params_frame, text=tr("Вернуть значения по умолчанию"), command=lambda: self._reset_params(rule)).grid(
            row=len(rule.params), column=1, sticky=tk.W, pady=(6, 0)
        )

    def _param_display(self, rule: Rule, param: Param, value: Any) -> str:
        if param.type == "enum":
            return next((title for v, title in self.param_options(rule, param) if v == value), str(value))
        if param.type == "bool":
            return tr("да") if value else tr("нет")
        return str(value)

    def _param_widget(self, rule: Rule, param: Param) -> tk.Widget:
        value = self.profile.param(self.catalog, rule.id, param.name)
        if param.type == "enum":
            options = self.param_options(rule, param)
            var = tk.StringVar(value=self._param_display(rule, param, value))
            box = ttk.Combobox(self.params_frame, textvariable=var, values=[t for _, t in options], state="readonly", width=46)
            box.bind("<<ComboboxSelected>>", lambda _e: self._set_param(rule, param, next(v for v, t in options if t == var.get())))
            widget: tk.Widget = box
        elif param.type == "bool":
            var = tk.BooleanVar(value=bool(value))
            widget = ttk.Checkbutton(self.params_frame, variable=var, command=lambda: self._set_param(rule, param, bool(var.get())))
        elif param.type == "int":
            var = tk.StringVar(value=str(value))
            widget = ttk.Spinbox(self.params_frame, textvariable=var, from_=param.min if param.min is not None else 0,
                                 to=param.max if param.max is not None else 10**9, width=12)
            var.trace_add("write", lambda *_: self._set_param_text(rule, param, var.get()))
        else:
            var = tk.StringVar(value=str(value))
            widget = ttk.Entry(self.params_frame, textvariable=var, width=24)
            var.trace_add("write", lambda *_: self._set_param(rule, param, var.get().strip()))
        self._param_vars.append(var)
        return widget

    def _update_param_mark(self, rule: Rule, param: Param) -> None:
        """A parameter that differs from the catalog default is marked next to its hint."""
        mark = self._param_marks.get(param.name)
        if mark is not None:
            mark.configure(text=tr("изменено") if param.name in self.profile.rules[rule.id].params else "")

    def _set_param_text(self, rule: Rule, param: Param, raw: str) -> None:
        try:
            value = int(raw)
        except ValueError:
            self.set_status(tr("«{0}»: нужно целое число", self.param_title(rule, param)))
            return
        if param.min is not None and value < param.min or param.max is not None and value > param.max:
            self.set_status(tr("«{0}»: допустимо от {1} до {2}", self.param_title(rule, param), param.min, param.max))
            return
        self._set_param(rule, param, value)

    def _set_param(self, rule: Rule, param: Param, value: Any) -> None:
        state = self.profile.rules[rule.id]
        current = self.profile.param(self.catalog, rule.id, param.name)
        if value == current:
            return
        if value == param.default:
            state.params.pop(param.name, None)
        else:
            state.params[param.name] = value
        self.mark_dirty()
        self.set_status(f"«{self.rule_title(rule.id)}»: {self.param_title(rule, param)} = {self._param_display(rule, param, value)}")
        self._update_param_mark(rule, param)
        self.refresh_marks()
        self._write_detail(self._rule_parts(rule))

    def _reset_params(self, rule: Rule) -> None:
        if self.profile.rules[rule.id].params:
            self.profile.rules[rule.id].params.clear()
            self.mark_dirty()
            self.refresh_marks()
        self.show_item("r:" + rule.id)

    # ----------------------------------------------------------------- messages

    def show_issues(self, issues: list[Issue]) -> None:
        self.messages.delete(*self.messages.get_children())
        order = {"error": 0, "warning": 1, "change": 2, "info": 3}
        for index, issue in enumerate(sorted(issues, key=lambda i: order.get(i.level, 9))):
            target = self.rule_title(issue.target) if issue.target in self.catalog.rules else issue.target
            self.messages.insert("", tk.END, iid=f"m{index}", values=(tr(ISSUE_TITLES.get(issue.level, issue.level)), target, issue.message),
                                 tags=(issue.level,))
        self._issues = sorted(issues, key=lambda i: order.get(i.level, 9))

    def _on_message_double(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        selection = self.messages.selection()
        if not selection:
            return
        issue = self._issues[int(selection[0][1:])]
        target = issue.target
        if target in self.catalog.rules:
            self.select_node("r:" + target)
        elif target.startswith("accounts"):
            self.select_node("data:accounts")
        elif target.startswith("languages"):
            self.select_node("data:languages")
        elif target.startswith("install"):
            self.select_node("data:install")

    # ----------------------------------------------------------------- profiles

    def refresh_profile_choices(self) -> None:
        choices: list[tuple[str, Path]] = []
        for path in sorted((self.paths.data / "profiles").glob("preset-*.json")):
            choices.append((tr("Пресет: {0}", tr(_profile_name(path))), path))
        for path in sorted(self.paths.profiles.glob("*.json")):
            if not path.name.startswith("preset-"):
                choices.append((path.stem, path))
        self._choices = choices
        labels = [label for label, _ in choices]
        current = self._current_label()
        if current not in labels:
            labels.append(current)
        self.profile_box.configure(values=labels)
        self.profile_var.set(current)

    def _current_label(self) -> str:
        if self.profile.path is not None:
            for label, path in self._choices:
                if path.resolve() == self.profile.path.resolve():
                    return label
            return self.profile.path.stem
        return tr("{0} (не сохранён)", tr(self.profile.name))

    def _is_preset(self, path: Path | None) -> bool:
        return path is not None and path.name.startswith("preset-")

    def _on_profile_selected(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        label = self.profile_var.get()
        path = next((p for text, p in self._choices if text == label), None)
        if path is None or (self.profile.path is not None and path.resolve() == self.profile.path.resolve()):
            return
        if not self.load_profile_file(path):
            self.profile_var.set(self._current_label())

    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(APP_NAME, tr("Профиль «{0}» изменён. Сохранить изменения?", tr(self.profile.name)), parent=self)
        if answer is None:
            return False
        if answer:
            return self.save_profile()
        return True

    def set_profile(self, profile: Profile, *, dirty: bool, warnings: list[str] | None = None) -> None:
        self.profile = profile
        self.dirty = dirty
        if self.search_var.get().strip():
            self.apply_search()
        else:
            self.rebuild_tree()
        for form in self.forms.values():
            form.refresh()
        self.refresh_profile_choices()
        self.update_title()
        current = self._current_item if self.tree.exists(self._current_item) else WORKFLOW_NODE
        self.select_node(current)
        self.show_issues([Issue("info", "profile", w) for w in (warnings or [])])

    def load_profile_file(self, path: Path) -> bool:
        if not self.confirm_discard():
            return False
        try:
            profile, warnings = Profile.load(path, self.catalog)
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_NAME, tr("Профиль не открыт:\n{0}\n\n{1}", path, exc), parent=self)
            return False
        self.set_profile(profile, dirty=False, warnings=warnings)
        if not self._is_preset(path):
            self.remember_file(path)
        kind = tr("Пресет") if self._is_preset(path) else tr("Профиль")
        self.set_status(tr("{0} «{1}» открыт", kind, profile.name) + (tr(" (изменения сохраняются под новым именем)") if self._is_preset(path) else ""))
        return True

    def remember_file(self, path: Path | None) -> None:
        if path is None:
            return
        self.settings.add_recent(path, self.paths.root)
        self.settings.save(self.paths.settings_file)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.delete(0, tk.END)
        if not self.settings.recent:
            self.recent_menu.add_command(label=tr("(пусто)"), state=tk.DISABLED)
            return
        for index, item in enumerate(self.settings.recent, start=1):
            self.recent_menu.add_command(label=f"{index}. {item}", command=lambda i=item: self.open_recent(i))

    def open_recent(self, item: str) -> bool:
        path = Settings.resolve(item, self.paths.root)
        if not path.exists():
            messagebox.showerror(APP_NAME, tr("Файл не найден и убран из списка недавних:\n{0}", path), parent=self)
            self.settings.forget(path, self.paths.root)
            self.settings.save(self.paths.settings_file)
            self._rebuild_recent_menu()
            return False
        if path.suffix.lower() == ".xml":
            return self.confirm_discard() and self.import_file(path)
        return self.load_profile_file(path)

    def open_profile_dialog(self) -> None:
        name = filedialog.askopenfilename(parent=self, title=tr("Открыть профиль"), initialdir=str(self.paths.profiles),
                                          filetypes=[(tr("Профиль WinKickOff"), "*.json"), (tr("Все файлы"), "*.*")])
        if name:
            self.load_profile_file(Path(name))

    def save_profile(self) -> bool:
        if self.profile.path is None or self._is_preset(self.profile.path):
            return self.save_profile_as()
        try:
            self.profile.save(self.profile.path, self.catalog)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Профиль не сохранён:\n{0}", exc), parent=self)
            return False
        self.dirty = False
        self.update_title()
        self.remember_file(self.profile.path)
        self.set_status(tr("Профиль сохранён: {0}", self.profile.path))
        return True

    def save_profile_as(self) -> bool:
        suggested = re.sub(r'[\\/:*?"<>|]', "_", self.profile.name) or "profile"
        if self._is_preset(self.profile.path):
            suggested += tr(" (мой)")
        name = filedialog.asksaveasfilename(parent=self, title=tr("Сохранить профиль как"), initialdir=str(self.paths.profiles),
                                            initialfile=f"{suggested}.json", defaultextension=".json",
                                            filetypes=[(tr("Профиль WinKickOff"), "*.json")])
        if not name:
            return False
        path = Path(name)
        if path.name.startswith("preset-"):
            messagebox.showerror(APP_NAME, tr("Имена preset-*.json зарезервированы для пресетов. Выберите другое имя."), parent=self)
            return False
        self.profile.name = path.stem
        try:
            self.profile.save(path, self.catalog)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Профиль не сохранён:\n{0}", exc), parent=self)
            return False
        self.dirty = False
        self.refresh_profile_choices()
        self.update_title()
        self.remember_file(path)
        self.set_status(tr("Профиль сохранён: {0}", path))
        return True

    # ----------------------------------------------------------------- comparison

    def compare_with_file(self) -> None:
        name = filedialog.askopenfilename(parent=self, title=tr("Сравнить с профилем"), initialdir=str(self.paths.profiles),
                                          filetypes=[(tr("Профиль WinKickOff"), "*.json"), (tr("Все файлы"), "*.*")])
        if name:
            self.show_comparison(Path(name))

    def comparison_rows(self, other: Profile) -> list[tuple[str, str, str, str, str]]:
        """(tree node, kind, item, value here, value there) for every difference from other."""

        def state(value: Any) -> str:
            return "" if value is None else tr("включено") if value else tr("выключено")

        install_titles = {"edition": tr("Редакция"), "product_key_mode": tr("Режим ключа"), "product_key": tr("Ключ продукта"),
                          "time_zone": tr("Часовой пояс")}
        language_titles = {"ui_language": tr("Язык интерфейса"), "system_locale": tr("Язык программ без Юникода"),
                           "user_locale": tr("Формат дат и чисел"), "input": tr("Языки ввода")}

        def text(value: Any) -> str:
            return ", ".join(str(v) for v in value) if isinstance(value, list) else "" if value is None else str(value)

        rows: list[tuple[str, str, str, str, str]] = []
        for d in self.profile.diff(other, self.catalog):
            if d.kind == "rule":
                title = self.rule_title(d.key) if d.key in self.catalog.rules else d.key
                rows.append(("r:" + d.key, tr("правило"), title, state(d.before), state(d.after)))
            elif d.kind == "param":
                rule_id, _, name = d.key.rpartition(".")
                rule = self.catalog.rules.get(rule_id)
                if rule is not None and name in rule.params:
                    param = rule.params[name]
                    rows.append(("r:" + rule_id, tr("параметр"), f"{self.rule_title(rule_id)}: {self.param_title(rule, param)}",
                                 self._param_display(rule, param, d.before), self._param_display(rule, param, d.after)))
                else:
                    rows.append(("", tr("параметр"), d.key, text(d.before), text(d.after)))
            elif d.kind == "install":
                rows.append(("data:install", tr("установка"), install_titles.get(d.key, d.key), text(d.before), text(d.after)))
            elif d.kind == "languages":
                rows.append(("data:languages", tr("языки"), language_titles.get(d.key, d.key), text(d.before), text(d.after)))
            else:
                rows.append(("data:accounts", tr("учётные записи"), tr("список учётных записей"), text(d.before), text(d.after)))
        return rows

    def show_comparison(self, path: Path) -> tk.Toplevel | None:
        try:
            other, _warnings = Profile.load(path, self.catalog)
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_NAME, tr("Профиль не открыт:\n{0}\n\n{1}", path, exc), parent=self)
            return None
        rows = self.comparison_rows(other)
        window = tk.Toplevel(self)
        window.title(tr("Сравнение: «{0}» и «{1}»", tr(self.profile.name), tr(other.name)))
        window.geometry("980x520")
        caption = tr("Различий: {0}. Двойной щелчок ведёт к правилу или данным.", len(rows)) if rows else tr("Профили совпадают.")
        ttk.Label(window, text=caption, padding=(10, 8)).pack(anchor=tk.W)
        box = ttk.Frame(window, padding=(10, 0, 10, 0))
        box.pack(fill=tk.BOTH, expand=True)
        table = ttk.Treeview(box, columns=("kind", "item", "mine", "theirs"), show="headings")
        for column, title, width in (("kind", tr("Что"), 110), ("item", tr("Где"), 420),
                                     ("mine", tr(self.profile.name), 200), ("theirs", tr(other.name), 200)):
            table.heading(column, text=title)
            table.column(column, width=width, stretch=column == "item")
        scroll = ttk.Scrollbar(box, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.LEFT, fill=tk.Y)
        targets: dict[str, str] = {}
        for index, (target, kind, item, mine, theirs) in enumerate(rows):
            iid = f"d{index}"
            targets[iid] = target
            table.insert("", tk.END, iid=iid, values=(kind, item, mine, theirs))

        def go(_event: tk.Event) -> None:  # type: ignore[type-arg]
            selection = table.selection()
            if selection and targets.get(selection[0]):
                self.select_node(targets[selection[0]])

        table.bind("<Double-Button-1>", go)
        ttk.Button(window, text=tr("Закрыть"), command=window.destroy).pack(anchor=tk.E, padx=10, pady=8)
        window.comparison_rows = rows  # type: ignore[attr-defined]
        return window

    def import_from_xml(self) -> None:
        if not self.confirm_discard():
            return
        name = filedialog.askopenfilename(parent=self, title=tr("Открыть профиль из autounattend.xml"),
                                          filetypes=[(tr("Файл ответов"), "*.xml"), (tr("Все файлы"), "*.*")])
        if name:
            self.import_file(Path(name))

    def import_file(self, path: Path) -> bool:
        """A WinKickOff build gives back its embedded profile; any other answer file of the same
        family (the hand-written v0.2) is imported by its actions, with a list of what is uncertain."""
        try:
            text = path.read_text(encoding="utf-8")
            profile, warnings = import_xml(text, self.catalog, self.resources.keyboards)
        except (OSError, UnicodeDecodeError, ImportFailed) as exc:
            messagebox.showerror(APP_NAME, tr("Профиль не восстановлен:\n{0}", exc), parent=self)
            return False
        by_actions = profile.name == IMPORTED_NAME
        if by_actions:
            profile.name = tr("Импорт {0}", path.stem)
        self.set_profile(profile, dirty=True, warnings=warnings)
        self.remember_file(path)
        how = tr("по действиям файла (сомнения в списке внизу)") if by_actions else tr("из встроенного профиля")
        self.set_status(tr("Профиль «{0}» восстановлен {1}; сохраните его, чтобы использовать повторно", profile.name, how))
        return True

    # ----------------------------------------------------------------- check and build

    def run_checks(self, *, with_powershell: bool) -> tuple[BuildResult | None, list[Issue]]:
        issues = validate_profile(self.profile, self.catalog, self.resources.keyboards)
        if has_errors(issues):
            return None, issues
        try:
            result = self.renderer.build(self.profile, app_version=APP_VERSION)
        except RenderError as exc:
            return None, issues + [Issue("error", "build", tr("Сборка невозможна: {0}", exc))]
        issues += validate_xml(result.xml)
        if with_powershell and not has_errors(issues):
            issues += self._ps_issues(check_scripts(result.scripts, self.paths.logs / "tmp"))
        return result, issues

    @staticmethod
    def _ps_issues(ps: PsCheckResult) -> list[Issue]:
        if ps.skipped:
            return [Issue("info", "powershell", tr("Проверка синтаксиса PowerShell пропущена: powershell.exe не найден"))]
        if ps.failure:
            return [Issue("warning", "powershell", tr("Проверка синтаксиса PowerShell не выполнена: {0}", ps.failure))]
        if ps.errors:
            return [Issue("error", "powershell", e) for e in ps.errors]
        return [Issue("info", "powershell", tr("Синтаксис скриптов по Windows PowerShell 5.1: ошибок нет"))]

    def check(self) -> list[Issue]:
        result, issues = self.run_checks(with_powershell=False)
        if result is not None:
            issues.append(Issue("info", "build", tr("Файл соберётся: {0} правил, скрипты: {1}", len(result.rule_ids), ', '.join(result.scripts) or tr('нет скриптов'))))
        self.show_issues(issues)
        errors = sum(1 for i in issues if i.level == "error")
        warnings = sum(1 for i in issues if i.level == "warning")
        self.set_status(tr("Проверка: ошибок {0}, предупреждений {1}", errors, warnings) + (tr("; можно собирать (F9)") if not errors else ""))
        return issues

    def check_catalog(self) -> list[Issue]:
        """Re-read the rule files from disk and report defects (useful while editing the TOML)."""
        catalog, issues = validate_catalog(self.paths.rules, self.paths.docs_root)
        if catalog is not None:
            issues.append(Issue("info", "catalog", tr("Каталог {0} читается: {1} правил, {2} групп. Изменения файлов каталога вступают в силу после перезапуска программы.", catalog.version, len(catalog.rules), len(catalog.groups))))
        self.show_issues(issues)
        errors = sum(1 for i in issues if i.level == "error")
        warnings = sum(1 for i in issues if i.level == "warning")
        self.set_status(tr("Проверка каталога: ошибок {0}, предупреждений {1}", errors, warnings))
        return issues

    def write_build(self, result: BuildResult, path: Path) -> None:
        path.write_bytes(result.xml.encode("utf-8"))
        self._last_output = path

    def set_busy(self, busy: bool, text: str = "") -> None:
        """While a background check runs, Check and Build are unavailable (buttons and F7, F9)."""
        self._busy = busy
        state = ["disabled"] if busy else ["!disabled"]
        self.check_button.state(state)
        self.build_button.state(state)
        self.configure(cursor="watch" if busy else "")
        if text:
            self.set_status(text)

    def build(self) -> None:
        """Validate and assemble at once; the PowerShell syntax check (up to a few seconds) runs in a
        background thread so the window stays responsive; then the file is saved."""
        if self._busy:
            return
        result, issues = self.run_checks(with_powershell=False)
        if result is None or has_errors(issues):
            self._finish_build(result, issues)
            return
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["ps"] = check_scripts(result.scripts, self.paths.logs / "tmp")
            except Exception as exc:  # noqa: BLE001 - reported to the user, never lost in the thread
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="pscheck", daemon=True)
        self.set_busy(True, tr("Проверка синтаксиса PowerShell..."))
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(100, poll)
                return
            self.set_busy(False)
            if "error" in outcome:
                extra = [Issue("warning", "powershell", tr("Проверка синтаксиса PowerShell не выполнена: {0}", outcome['error']))]
            else:
                extra = self._ps_issues(outcome["ps"])
            self._finish_build(result, issues + extra)

        self.after(100, poll)

    def _finish_build(self, result: BuildResult | None, issues: list[Issue]) -> None:
        self.show_issues(issues)
        if result is None or has_errors(issues):
            count = sum(1 for i in issues if i.level == "error")
            self.set_status(tr("Сборка остановлена: ошибок {0}", count))
            messagebox.showerror(APP_NAME, tr("Сборка остановлена: ошибок {0}. Список внизу окна, двойной щелчок ведёт к месту ошибки.", count), parent=self)
            return
        initial_dir = self._last_output.parent if self._last_output else self.paths.output
        name = filedialog.asksaveasfilename(parent=self, title=tr("Сохранить файл ответов"), initialdir=str(initial_dir),
                                            initialfile="autounattend.xml", defaultextension=".xml",
                                            filetypes=[(tr("Файл ответов Windows"), "*.xml")])
        if not name:
            self.set_status(tr("Сборка готова, но не сохранена"))
            return
        path = Path(name)
        try:
            self.write_build(result, path)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Файл не записан:\n{0}", exc), parent=self)
            return
        note = "" if path.name.lower() == "autounattend.xml" else tr("\n\nВнимание: установщик ищет файл только с именем autounattend.xml.")
        self.show_issues(issues + [Issue("info", "build", tr("Сохранено: {0} ({1} правил)", path, len(result.rule_ids)))])
        self.set_status(tr("Собрано: {0}", path))
        if messagebox.askyesno(
            APP_NAME,
            tr("Файл сохранён:\n{0}\n\nВключено правил: {1}.\nСкопируйте его в корень флешки с установочным образом Windows 11 и загрузите ПК с неё.{2}\n\nОткрыть папку с файлом?", path, len(result.rule_ids), note),
            parent=self,
        ):
            self._open_folder(path.parent)

    # ----------------------------------------------------------------- this PC (task T15)

    def _fill_pc_menu(self, menu: tk.Menu) -> None:
        # Always available: the first apply or return asks for permission (toggle_allow_apply) instead of a
        # greyed-out item whose switch is hard to find.
        menu.add_command(label=tr("Проверить выбранное на этом ПК"), command=self.audit_selected)
        menu.add_command(label=tr("Сохранить скрипт применения выбранного..."), command=self.save_apply_scripts)
        menu.add_command(label=tr("Применить выбранное сейчас..."), command=self.apply_now)
        menu.add_command(label=tr("Вернуть выбранное к умолчаниям Windows сейчас..."), command=self.revert_now)

    def _on_tree_right_click(self, event: tk.Event) -> str | None:  # type: ignore[type-arg]
        item = self.tree.identify_row(event.y)
        if not (item.startswith("r:") or item.startswith("g:")):
            return None
        self.tree.selection_set(item)
        self.tree.focus(item)
        self.tree_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def toggle_allow_apply(self) -> None:
        wanted = bool(self.allow_apply_var.get())
        if wanted and not messagebox.askyesno(APP_NAME, tr(
                "Разрешить применение правил к этому компьютеру?\n\n"
                "Скрипт применения меняет реестр, службы и компоненты Windows. Сначала проверьте его на тестовом "
                "компьютере или виртуальной машине. Удаление приложений и шаги на PowerShell нельзя откатить "
                "автоматически. Применение всегда запускается через запрос контроля учётных записей."),
                icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            self.allow_apply_var.set(False)
            wanted = False
        self.settings.allow_apply = wanted
        self.settings.save(self.paths.settings_file)

    def _ensure_apply_allowed(self) -> bool:
        """Changes to this PC need the permission of «Этот ПК, Разрешить применение»; ask for it once."""
        if self.settings.allow_apply:
            return True
        self.allow_apply_var.set(True)
        self.toggle_allow_apply()
        return self.settings.allow_apply

    def _apply_items(self) -> list[str]:
        items = [i for i in self.tree.selection() if i.startswith("r:") or i.startswith("g:")]
        if not items:
            messagebox.showinfo(APP_NAME, tr("Выберите в дереве правило или группу."), parent=self)
        return items

    def _plan_issues(self, plan: ApplyPlan) -> list[Issue]:
        issues = [Issue("info", rule.id, tr("не применяется: {0}", tr(reason))) for rule, reason in plan.excluded]
        for planned in plan.rules:
            notes = []
            if planned.requirement:
                notes.append(tr("нужно для выбранного правила"))
            if planned.irreversible:
                notes.append(tr("автоматически не откатывается"))
            if planned.reboot:
                notes.append(tr("нужна перезагрузка"))
            level = "warning" if planned.irreversible else "info"
            issues.append(Issue(level, planned.rule.id, tr("будет применено") + (": " + "; ".join(notes) if notes else "")))
        return issues

    def audit_selected(self) -> None:
        """Read-only check on this PC: which of the selected rules already take effect."""
        if self._busy:
            return
        items = self._apply_items()
        if not items:
            return
        plan = plan_apply(self.catalog, self.profile, items)
        excluded = [Issue("info", rule.id, tr("не проверяется: {0}", tr(reason))) for rule, reason in plan.excluded]
        if not plan.rules:
            self.show_issues(excluded)
            self.set_status(tr("Среди выбранного нет правил, которые можно проверить на работающей системе"))
            return
        script = render_audit(plan.rule_ids, self.profile, self.catalog, self.paths.templates, APP_VERSION)
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["text"] = run_audit(script, self.paths.logs / "tmp")
            except Exception as exc:  # noqa: BLE001 - shown to the user
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="audit", daemon=True)
        self.set_busy(True, tr("Проверка на этом ПК (только чтение)..."))
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(150, poll)
                return
            self.set_busy(False)
            if "error" in outcome:
                self.show_issues([Issue("error", "audit", tr("Проверка не выполнена: {0}", outcome["error"]))] + excluded)
                self.set_status(tr("Проверка на этом ПК не выполнена"))
                return
            self.show_audit(outcome["text"], excluded)

        self.after(150, poll)

    def show_audit(self, report_text: str, excluded: list[Issue]) -> None:
        meta, results = parse_audit_report(report_text)
        issues: list[Issue] = []
        counts = {"applied": 0, "not-applied": 0, "partial": 0, "unknown": 0}
        for rule_id, result in results.items():
            counts[result.status] = counts.get(result.status, 0) + 1
            details = [f"{c['check']}: {c['current'] or tr('нет значения')} ({tr('нужно')} {c['expected']})"
                       for c in result.checks if c["status"] == "differs"][:3]
            level = "info" if result.status in ("applied", "unknown") else "warning"
            issues.append(Issue(level, rule_id, status_title(result.status) + (": " + "; ".join(details) if details else "")))
        self.show_issues(issues + excluded)
        note = "" if str(meta.get("admin")).lower() == "true" else tr(" Без прав администратора часть проверок недоступна.")
        self.set_status(tr("Проверка на этом ПК: действует {0}, не действует {1}, частично {2}, не проверяется {3}.",
                           counts["applied"], counts["not-applied"], counts["partial"], counts["unknown"]) + note)

    def _write_apply_folder(self, folder: Path, plan: ApplyPlan) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        apply_path = folder / "Apply.ps1"
        write_script(apply_path, render_apply(plan, self.profile, self.catalog, self.paths.templates, APP_VERSION))
        write_script(folder / "Undo-Apply.ps1", render_undo(self.paths.templates, self.profile, APP_VERSION))
        lines = [tr("Скрипты применения WinKickOff {0}, профиль «{1}».", APP_VERSION, tr(self.profile.name)), "",
                 tr("1. Сначала проверьте на тестовом компьютере или виртуальной машине."),
                 tr("2. Запустите Apply.ps1 от имени администратора: powershell -ExecutionPolicy Bypass -File Apply.ps1"),
                 tr("3. Журнал и резервная копия прежних значений появятся рядом со скриптом (apply-*.log, backup-*.json)."),
                 tr("4. Откат: Undo-Apply.ps1 от имени администратора. Удалённые приложения и шаги на PowerShell не откатываются."),
                 tr("5. После применения перезагрузите компьютер."), "", tr("Правила:")]
        for planned in plan.rules:
            flags = (tr(" (не откатывается)") if planned.irreversible else "") + (tr(" (нужна перезагрузка)") if planned.reboot else "")
            lines.append(f"- {planned.rule.id}: {self.rule_title(planned.rule.id)}{flags}")
        if plan.excluded:
            lines += ["", tr("Не применяются:")]
            lines += [f"- {rule.id}: {tr(reason)}" for rule, reason in plan.excluded]
        (folder / "README.txt").write_bytes(("\n".join(lines) + "\n").replace("\n", "\r\n").encode("utf-8-sig"))
        return apply_path

    def save_apply_scripts(self) -> Path | None:
        items = self._apply_items()
        if not items:
            return None
        plan = plan_apply(self.catalog, self.profile, items)
        self.show_issues(self._plan_issues(plan))
        if not plan.rules:
            self.set_status(tr("Среди выбранного нет правил, которые можно применить к работающей системе"))
            return None
        name = filedialog.askdirectory(parent=self, title=tr("Папка для скриптов применения"), initialdir=str(self.paths.output))
        if not name:
            return None
        folder = Path(name) / time.strftime("apply-%Y%m%d-%H%M%S")
        try:
            self._write_apply_folder(folder, plan)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Скрипты не записаны:\n{0}", exc), parent=self)
            return None
        self.set_status(tr("Скрипты применения сохранены: {0} (правил: {1})", folder, len(plan.rules)))
        return folder

    def apply_now(self) -> bool:
        """Apply the selection to this PC: confirmation, scripts in logs/, launch through UAC."""
        items = self._apply_items()
        if not items or not self._ensure_apply_allowed():
            return False
        plan = plan_apply(self.catalog, self.profile, items)
        self.show_issues(self._plan_issues(plan))
        if not plan.rules:
            self.set_status(tr("Среди выбранного нет правил, которые можно применить к работающей системе"))
            return False
        irreversible = [self.rule_title(p.rule.id) for p in plan.rules if p.irreversible]
        text = tr("Применить выбранные правила ({1}) к компьютеру {0}?", os.environ.get("COMPUTERNAME", "?"), len(plan.rules))
        if irreversible:
            text += "\n\n" + tr("Автоматически не откатываются: {0}.", "; ".join(irreversible[:8]) + ("..." if len(irreversible) > 8 else ""))
        if any(p.reboot for p in plan.rules):
            text += "\n\n" + tr("После применения нужна перезагрузка.")
        text += "\n\n" + tr("Windows запросит подтверждение прав администратора. Прежние значения сохраняются для отката (Undo-Apply.ps1).")
        if not messagebox.askyesno(APP_NAME, text, icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            return False
        folder = self.paths.logs / time.strftime("apply-%Y%m%d-%H%M%S")
        try:
            script = self._write_apply_folder(folder, plan)
            apply_module.launch_elevated(script)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror(APP_NAME, tr("Применение не запущено:\n{0}", exc), parent=self)
            return False
        self.set_status(tr("Скрипт применения запущен; журнал и резервная копия: {0}", folder))
        return True

    def _revert_issues(self, plan: RevertPlan) -> list[Issue]:
        issues = [Issue("info", rule.id, tr("не возвращается: {0}", tr(reason))) for rule, reason in plan.excluded]
        for planned in plan.rules:
            notes = []
            if planned.dependent:
                notes.append(tr("зависит от выбранного правила"))
            if planned.skipped:
                notes.append(tr("не возвращается автоматически: {0}", ", ".join(sorted({a.type for a in planned.skipped}))))
            if planned.reboot:
                notes.append(tr("нужна перезагрузка"))
            level = "warning" if planned.skipped else "info"
            issues.append(Issue(level, planned.rule.id, tr("будет возвращено к умолчаниям Windows") + (": " + "; ".join(notes) if notes else "")))
        return issues

    def _write_revert_folder(self, folder: Path, plan: RevertPlan) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        script_path = folder / "Apply.ps1"
        write_script(script_path, render_revert(plan, self.profile, self.paths.templates, APP_VERSION))
        write_script(folder / "Undo-Apply.ps1", render_undo(self.paths.templates, self.profile, APP_VERSION))
        lines = [tr("Возврат к значениям Windows по умолчанию, WinKickOff {0}.", APP_VERSION), "",
                 tr("1. Сначала проверьте на тестовом компьютере или виртуальной машине."),
                 tr("2. Запустите Apply.ps1 от имени администратора: powershell -ExecutionPolicy Bypass -File Apply.ps1"),
                 tr("3. Журнал и резервная копия прежних значений появятся рядом со скриптом (apply-*.log, backup-*.json)."),
                 tr("4. Отмена возврата: Undo-Apply.ps1 от имени администратора."),
                 tr("5. После применения перезагрузите компьютер."), "", tr("Правила:")]
        for planned in plan.rules:
            flags = tr(" (частично)") if planned.skipped else ""
            lines.append(f"- {planned.rule.id}: {self.rule_title(planned.rule.id)}{flags}")
        if plan.excluded:
            lines += ["", tr("Не возвращаются:")]
            lines += [f"- {rule.id}: {tr(reason)}" for rule, reason in plan.excluded]
        (folder / "README.txt").write_bytes(("\n".join(lines) + "\n").replace("\n", "\r\n").encode("utf-8-sig"))
        return script_path

    def revert_now(self) -> bool:
        """Return the selected rules on this PC to the values of a clean Windows, through UAC, with a backup."""
        items = self._apply_items()
        if not items or not self._ensure_apply_allowed():
            return False
        plan = plan_revert(self.catalog, items)
        self.show_issues(self._revert_issues(plan))
        if not plan.rules:
            self.set_status(tr("Среди выбранного нет правил, которые можно вернуть к умолчаниям Windows на работающей системе"))
            return False
        partial = [self.rule_title(p.rule.id) for p in plan.rules if p.skipped]
        text = tr("Вернуть выбранные правила ({1}) на компьютере {0} к значениям Windows по умолчанию?",
                  os.environ.get("COMPUTERNAME", "?"), len(plan.rules))
        dependents = [self.rule_title(p.rule.id) for p in plan.rules if p.dependent]
        if dependents:
            text += "\n\n" + tr("Вместе с ними: {0}.", "; ".join(dependents[:8]) + ("..." if len(dependents) > 8 else ""))
        if partial:
            text += "\n\n" + tr("Возвращаются не полностью (приложения, скрипты, значения с неизвестным умолчанием): {0}.",
                                "; ".join(partial[:8]) + ("..." if len(partial) > 8 else ""))
        text += "\n\n" + tr("Windows запросит подтверждение прав администратора. Прежние значения сохраняются для отката (Undo-Apply.ps1).")
        if not messagebox.askyesno(APP_NAME, text, icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            return False
        folder = self.paths.logs / time.strftime("revert-%Y%m%d-%H%M%S")
        try:
            script = self._write_revert_folder(folder, plan)
            apply_module.launch_elevated(script)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror(APP_NAME, tr("Возврат не запущен:\n{0}", exc), parent=self)
            return False
        self.set_status(tr("Скрипт возврата к умолчаниям запущен; журнал и резервная копия: {0}", folder))
        return True

    def open_output_folder(self) -> None:
        self._open_folder(self._last_output.parent if self._last_output else self.paths.output)

    def _open_folder(self, folder: Path) -> None:
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Папка не открыта:\n{0}", exc), parent=self)

    # ----------------------------------------------------------------- misc

    def about(self) -> None:
        self.select_node(WORKFLOW_NODE)
        self._write_detail(
            [
                ("h1", f"{APP_NAME} {APP_VERSION}"),
                ("", tr("Каталог правил: версия {0}, {1} правил.", self.catalog.version, len(self.catalog.rules))),
                ("", tr("Папка программы: {0}", self.paths.root)),
                ("", tr("Профили: {0}", self.paths.profiles)),
                ("", tr("Собранные файлы по умолчанию: {0}", self.paths.output)),
                ("", tr("Настройки программы: {0}", self.paths.settings_file)),
                ("", tr("Шаблоны рантайма: {0}", self.paths.templates)),
                ("h2", tr("Документация")),
                ("link:doc:" + user_docs(), tr("Документация пользователя: ") + user_docs()),
                ("link:doc:docs/technical/reference/README.md", tr("Технический справочник параметров (на английском): docs/technical/reference/README.md")),
                ("muted", tr("Постановка и план редактора: docs/technical/editor/ в репозитории проекта.")),
            ]
        )

    def change_language(self, code: str) -> None:
        """Save the choice and rebuild the window in the new language; the open profile, its unsaved
        changes and the selected node survive (app.run creates the new window from restart_state)."""
        if code == language():
            return
        self.settings.language = code
        self.save_settings()
        self.restart_state = {"profile": self.profile, "dirty": self.dirty, "item": self._current_item}
        self.destroy()

    def restore_state(self, state: dict[str, Any]) -> None:
        self.dirty = bool(state.get("dirty"))
        self.update_title()
        item = str(state.get("item") or WORKFLOW_NODE)
        self.select_node(item if self.tree.exists(item) else WORKFLOW_NODE)

    def on_close(self) -> None:
        if self.confirm_discard():
            self.save_settings()
            self.destroy()

    def save_settings(self) -> None:
        if self.state() == "normal":
            self.settings.geometry = self.geometry()
        path = self.profile.path
        self.settings.last_profile = display_path(path, self.paths.root) if path is not None else ""
        self.settings.save(self.paths.settings_file)
