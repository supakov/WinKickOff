"""Main window: rule tree with check marks and search on the left, description and parameters
on the right, status line at the bottom. Skeleton for tasks T09-T11."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.catalog import Catalog, Rule
from winkickoff.core.deps import Change, Resolver
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.render import render_action

log = logging.getLogger(__name__)

MARK_ON = "☑"  # ballot box with check
MARK_OFF = "☐"  # ballot box
MARK_PART = "◧"  # square with left half black (group partially enabled)
DATA_NODES: tuple[tuple[str, str], ...] = (
    ("data:install", "Установка (редакция, ключ, часовой пояс)"),
    ("data:accounts", "Учётные записи"),
    ("data:languages", "Языки и регион"),
)
LEVEL_TITLES = {"baseline": "базовое", "recommended": "рекомендуемое", "optional": "необязательное", "risky": "рискованное"}
PHASE_TITLES = {
    "windowspe": "установщик (windowsPE)",
    "specialize-xml": "specialize (команда XML)",
    "specialize": "specialize (скрипт машины)",
    "default-user": "профиль пользователя по умолчанию",
    "user-first-logon": "первый вход каждого пользователя",
    "post-oobe": "после первичной настройки",
    "oobe-xml": "первичная настройка (OOBE)",
}


class MainWindow(tk.Tk):
    def __init__(self, paths: AppPaths, catalog: Catalog, profile: Profile) -> None:
        super().__init__()
        self.paths = paths
        self.catalog = catalog
        self.profile = profile
        self.resolver = Resolver(catalog)
        self.dirty = False
        self._search_job: str | None = None
        self._last_changes: list[Change] = []
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1180x720")
        self.minsize(900, 560)
        try:
            ttk.Style(self).theme_use("vista")
        except tk.TclError:
            pass
        self._build_menu()
        self._build_body()
        self._bind_keys()
        self.rebuild_tree()
        self._set_status("Каталог правил загружен: " + f"{len(catalog.rules)} правил, {len(catalog.groups)} групп")

    # ----------------------------------------------------------------- layout

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Новый профиль (пресет «Офис»)", command=self.new_profile)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.on_close)
        menubar.add_cascade(label="Файл", menu=file_menu)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="О программе", command=self.about)
        menubar.add_cascade(label="Справка", menu=help_menu)
        self.config(menu=menubar)

    def _build_body(self) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned, padding=(6, 6, 3, 0))
        paned.add(left, weight=2)
        search_row = ttk.Frame(left)
        search_row.pack(fill=tk.X)
        ttk.Label(search_row, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        ttk.Button(search_row, text="×", width=3, command=self.clear_search).pack(side=tk.LEFT)
        self.search_var.trace_add("write", lambda *_: self._schedule_search())

        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.tree.tag_configure("changed", foreground="#1f4e79")
        self.tree.tag_configure("off", foreground="#7a7a7a")
        self.tree.tag_configure("risky", foreground="#a33")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<space>", self._on_space)

        right = ttk.Frame(paned, padding=(3, 6, 6, 0))
        paned.add(right, weight=3)
        self.detail = tk.Text(right, wrap=tk.WORD, font=("Segoe UI", 10), state=tk.DISABLED, padx=8, pady=6)
        detail_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.detail.tag_configure("h1", font=("Segoe UI", 13, "bold"))
        self.detail.tag_configure("h2", font=("Segoe UI", 10, "bold"), spacing1=8)
        self.detail.tag_configure("mono", font=("Consolas", 9))
        self.detail.tag_configure("muted", foreground="#666")
        self.detail.tag_configure("risk", foreground="#a33")

        self.status_var = tk.StringVar()
        status = ttk.Label(self, textvariable=self.status_var, anchor=tk.W, padding=(8, 3))
        status.pack(fill=tk.X, side=tk.BOTTOM)

    def _bind_keys(self) -> None:
        self.bind("<Control-f>", lambda _e: self.search_entry.focus_set())
        self.bind("<Escape>", lambda _e: self.clear_search())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ----------------------------------------------------------------- tree

    def rebuild_tree(self, visible_rules: set[str] | None = None) -> None:
        """Build the tree from the catalog; when visible_rules is given, show only those rules and
        the groups that lead to them, fully expanded."""
        self.tree.delete(*self.tree.get_children(""))
        for node_id, title in DATA_NODES:
            if visible_rules is None:
                self.tree.insert("", tk.END, iid=node_id, text="   " + title)
        self._insert_groups("", None, visible_rules)

    def _insert_groups(self, parent_item: str, parent_group: str | None, visible: set[str] | None) -> None:
        for group in self.catalog.children(parent_group):
            rules = [r for r in self.catalog.rules_in_group(group.id) if visible is None or r.id in visible]
            if visible is not None and not rules:
                continue
            item = self.tree.insert(parent_item, tk.END, iid="g:" + group.id, text=self._group_text(group.id), open=visible is not None)
            self._insert_groups(item, group.id, visible)
            for rule in self.catalog.rules_in_group(group.id, recursive=False):
                if visible is not None and rule.id not in visible:
                    continue
                self.tree.insert(item, tk.END, iid="r:" + rule.id, text=self._rule_text(rule), tags=self._rule_tags(rule))

    def _rule_text(self, rule: Rule) -> str:
        mark = MARK_ON if self.profile.is_enabled(rule.id) else MARK_OFF
        return f"{mark} {rule.title}"

    def _rule_tags(self, rule: Rule) -> tuple[str, ...]:
        tags: list[str] = []
        if not self.profile.is_enabled(rule.id):
            tags.append("off")
        if rule.level == "risky":
            tags.append("risky")
        if self.profile.is_enabled(rule.id) != rule.default:
            tags.append("changed")
        return tuple(tags)

    def _group_text(self, group_id: str) -> str:
        rules = self.catalog.rules_in_group(group_id)
        on = sum(1 for r in rules if self.profile.is_enabled(r.id))
        mark = MARK_ON if on == len(rules) and rules else MARK_OFF if on == 0 else MARK_PART
        return f"{mark} {self.catalog.groups[group_id].title}  ({on}/{len(rules)})"

    def refresh_marks(self, rule_ids: set[str] | None = None) -> None:
        """Update the text of rule nodes (all, or the given ids) and of every group node."""
        for item in self._all_items():
            if item.startswith("r:"):
                rule_id = item[2:]
                if rule_ids is None or rule_id in rule_ids:
                    rule = self.catalog.rules[rule_id]
                    self.tree.item(item, text=self._rule_text(rule), tags=self._rule_tags(rule))
            elif item.startswith("g:"):
                self.tree.item(item, text=self._group_text(item[2:]))

    def _all_items(self, parent: str = "") -> list[str]:
        items: list[str] = []
        for child in self.tree.get_children(parent):
            items.append(child)
            items.extend(self._all_items(child))
        return items

    # ----------------------------------------------------------------- events

    def _on_tree_click(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        item = self.tree.identify_row(event.y)
        if not item:
            return
        # a click on the mark (left part of the text) toggles; a click elsewhere only selects
        bbox = self.tree.bbox(item, "#0")
        if bbox and event.x - bbox[0] <= 34:
            self.toggle_item(item)

    def _on_space(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        selection = self.tree.selection()
        if selection:
            self.toggle_item(selection[0])
        return "break"

    def _on_tree_select(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        selection = self.tree.selection()
        if selection:
            self.show_item(selection[0])

    def toggle_item(self, item: str) -> None:
        if item.startswith("r:"):
            rule_id = item[2:]
            changes = self.resolver.set_rule(self.profile, rule_id, not self.profile.is_enabled(rule_id))
        elif item.startswith("g:"):
            group_id = item[2:]
            rules = self.catalog.rules_in_group(group_id)
            all_on = all(self.profile.is_enabled(r.id) for r in rules)
            changes = self.resolver.set_group(self.profile, group_id, not all_on)
        else:
            return
        self._apply_changes(changes)
        self.show_item(item)

    def _apply_changes(self, changes: list[Change]) -> None:
        if not changes:
            self._set_status("Без изменений")
            return
        self.dirty = True
        self._last_changes = changes
        self.refresh_marks({c.rule_id for c in changes})
        direct = [c for c in changes if c.reason == "user"]
        cascade = [c for c in changes if c.reason != "user"]
        parts = []
        if direct:
            parts.append(("Включено: " if direct[0].enabled else "Выключено: ") + f"{len(direct)}")
        if cascade:
            names = ", ".join(self.catalog.rules[c.rule_id].title for c in cascade[:4])
            more = f" и ещё {len(cascade) - 4}" if len(cascade) > 4 else ""
            parts.append(f"вслед за этим изменено ещё {len(cascade)}: {names}{more}")
        self._set_status("; ".join(parts))
        self.title(f"{APP_NAME} {APP_VERSION} *")

    # ----------------------------------------------------------------- search

    def _schedule_search(self) -> None:
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(150, self.apply_search)

    def apply_search(self) -> None:
        self._search_job = None
        query = self.search_var.get().strip()
        if not query:
            self.rebuild_tree()
            return
        found = set(self.catalog.search(query))
        self.rebuild_tree(found)
        self._set_status(f"Найдено правил: {len(found)}")

    def clear_search(self) -> None:
        self.search_var.set("")

    # ----------------------------------------------------------------- description

    def show_item(self, item: str) -> None:
        if item.startswith("r:"):
            self._show_rule(self.catalog.rules[item[2:]])
        elif item.startswith("g:"):
            group = self.catalog.groups[item[2:]]
            rules = self.catalog.rules_in_group(group.id)
            on = sum(1 for r in rules if self.profile.is_enabled(r.id))
            self._write_detail([("h1", group.title), ("muted", f"Правил: {len(rules)}, включено: {on}"), ("", group.summary or "")])
        else:
            self._write_detail([("h1", dict(DATA_NODES)[item]), ("muted", "Форма редактирования появится в задаче T10.")])

    def _show_rule(self, rule: Rule) -> None:
        params = self.profile.params_for(self.catalog, rule.id)
        state = "включено" if self.profile.is_enabled(rule.id) else "выключено"
        parts: list[tuple[str, str]] = [
            ("h1", rule.title),
            ("muted", f"{rule.id}   |   {state}   |   уровень: {LEVEL_TITLES.get(rule.level, rule.level)}   |   фаза: {PHASE_TITLES.get(rule.phase, rule.phase)}"),
            ("", rule.summary),
            ("h2", "Что делает технически"),
        ]
        for action in rule.actions:
            parts.append(("mono", self._action_line(action, params)))
        if rule.params:
            parts.append(("h2", "Параметры"))
            for param in rule.params.values():
                parts.append(("", f"{param.title}: {params[param.name]}   (по умолчанию {param.default})"))
        parts.append(("h2", "Эффект"))
        parts.append(("", rule.effect))
        if rule.risk:
            parts.append(("h2", "Риск и побочные действия"))
            parts.append(("risk", rule.risk))
        if rule.versions:
            parts.append(("h2", "Версии Windows"))
            parts.append(("", rule.versions))
        parts.append(("h2", "Зависимости"))
        parts.append(("", "Требует: " + (", ".join(rule.requires) or "ничего")))
        parts.append(("", "Требуется для: " + (", ".join(self.resolver.dependents(rule.id)) or "ничего")))
        if rule.conflicts:
            parts.append(("", "Конфликтует с: " + ", ".join(rule.conflicts)))
        if rule.verify:
            parts.append(("h2", "Проверка"))
            parts.append(("mono", rule.verify))
        if rule.rollback:
            parts.append(("h2", "Откат"))
            parts.append(("", rule.rollback))
        parts.append(("h2", "Подробнее"))
        parts.append(("muted", rule.doc))
        self._write_detail(parts)

    def _action_line(self, action, params: dict) -> str:  # type: ignore[no-untyped-def]
        if action.type.startswith("xml-"):
            f = action.fields
            if action.type == "xml-oobe":
                return f"OOBE: <{f['element']}>{f['value']}</{f['element']}>"
            return f"{action.type}: {f['command']}"
        try:
            return render_action(action, params)
        except Exception as exc:  # noqa: BLE001 - the panel must never break on a bad action
            return f"{action.type}: {exc}"

    def _write_detail(self, parts: list[tuple[str, str]]) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        for tag, text in parts:
            self.detail.insert(tk.END, text + "\n", tag or ())
        self.detail.configure(state=tk.DISABLED)

    # ----------------------------------------------------------------- commands

    def new_profile(self) -> None:
        self.profile = Profile.from_catalog(self.catalog, name="Офис")
        self.dirty = False
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.rebuild_tree()
        self._set_status("Новый профиль из значений каталога по умолчанию")

    def about(self) -> None:
        self._write_detail(
            [
                ("h1", f"{APP_NAME} {APP_VERSION}"),
                ("", f"Каталог правил: версия {self.catalog.version}, {len(self.catalog.rules)} правил."),
                ("", f"Папка приложения: {self.paths.root}"),
                ("muted", "Документация: draft/install-editor/ и docs/reference/ в репозитории проекта."),
            ]
        )

    def on_close(self) -> None:
        self.destroy()

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
