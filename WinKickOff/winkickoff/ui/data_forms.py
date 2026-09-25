"""Forms of the data nodes of the tree: installation, local accounts, languages and region.

Every change is written into the profile at once and marks it as modified; nothing is written to disk
until the user saves the profile.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from winkickoff.core.profile import Account
from winkickoff.core.render import EDITION_KEYS
from winkickoff.core.resources import find_keyboard, keyboard_item_id
from winkickoff.core.validate import check_account_name

if TYPE_CHECKING:
    from winkickoff.ui.main_window import MainWindow

WRAP = 600
LOCALE_CHOICES = ("uk-UA", "ru-RU", "en-US", "en-GB", "pl-PL", "de-DE")
KEY_MODES = (
    ("generic", "Универсальный ключ выбранной редакции: окон ввода ключа и выбора редакции не будет, "
     "Windows активируется сама по цифровой лицензии этого ПК"),
    ("custom", "Свой ключ продукта (например, из наклейки или договора)"),
    ("ask", "Спросить ключ и редакцию во время установки"),
)


class _Form(ttk.Frame):
    def __init__(self, master: tk.Misc, window: MainWindow, title: str, intro: str) -> None:
        super().__init__(master, padding=(14, 10))
        self.window = window
        self._loading = False
        ttk.Label(self, text=title, style="H1.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(self, text=intro, wraplength=WRAP, justify="left").grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 12))
        self.columnconfigure(1, weight=1)

    def changed(self) -> None:
        if not self._loading:
            self.window.mark_dirty()

    def note(self, row: int, text: str) -> None:
        ttk.Label(self, text=text, wraplength=WRAP, justify="left", style="Note.TLabel").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(2, 10)
        )

    def refresh(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class InstallForm(_Form):
    def __init__(self, master: tk.Misc, window: MainWindow) -> None:
        super().__init__(
            master,
            window,
            "Установка",
            "Редакция Windows, ключ продукта и часовой пояс. Язык интерфейса и языки ввода задаются в узле «Языки и регион».",
        )
        self.edition = tk.StringVar()
        self.mode = tk.StringVar()
        self.key = tk.StringVar()
        self.zone = tk.StringVar()
        ttk.Label(self, text="Редакция Windows").grid(row=2, column=0, sticky="w", padx=(0, 12))
        edition_box = ttk.Combobox(self, textvariable=self.edition, values=list(EDITION_KEYS), state="readonly", width=18)
        edition_box.grid(row=2, column=1, sticky="w")
        edition_box.bind("<<ComboboxSelected>>", lambda _e: self._save())
        self.note(3, "Pro: основная редакция проекта. Enterprise и Education только при наличии соответствующих лицензий; Home не поддерживается (не работают политики).")

        ttk.Label(self, text="Ключ продукта").grid(row=4, column=0, sticky="nw", padx=(0, 12))
        box = ttk.Frame(self)
        box.grid(row=4, column=1, sticky="w")
        for value, text in KEY_MODES:
            ttk.Radiobutton(box, text=text, value=value, variable=self.mode, command=self._save).pack(anchor="w", pady=1)
        self.key_entry = ttk.Entry(box, textvariable=self.key, width=34)
        self.key_entry.pack(anchor="w", padx=(22, 0), pady=(2, 0))
        self.key.trace_add("write", lambda *_: self._save())

        ttk.Label(self, text="Часовой пояс").grid(row=5, column=0, sticky="w", padx=(0, 12), pady=(12, 0))
        self.zone_box = ttk.Combobox(self, textvariable=self.zone, state="readonly", width=48)
        self.zone_box.grid(row=5, column=1, sticky="w", pady=(12, 0))
        self.zone_box.bind("<<ComboboxSelected>>", lambda _e: self._save())
        self.note(6, "Правильный часовой пояс важен для журналов: события при расследовании сопоставляются по времени.")
        self._zones: list[tuple[str, str]] = []

    def refresh(self) -> None:
        self._loading = True
        install = self.window.profile.install
        self.edition.set(str(install.get("edition", "Pro")))
        self.mode.set(str(install.get("product_key_mode", "generic")))
        self.key.set(str(install.get("product_key", "")))
        self._zones = [(str(z["id"]), str(z["title"])) for z in self.window.resources.timezones]
        current = str(install.get("time_zone", ""))
        if current and current not in (z for z, _ in self._zones):
            self._zones.append((current, current))
        self.zone_box.configure(values=[t for _, t in self._zones])
        self.zone.set(next((t for z, t in self._zones if z == current), current))
        self._update_state()
        self._loading = False

    def _update_state(self) -> None:
        self.key_entry.configure(state="normal" if self.mode.get() == "custom" else "disabled")

    def _save(self) -> None:
        self._update_state()
        if self._loading:
            return
        install = self.window.profile.install
        install["edition"] = self.edition.get()
        install["product_key_mode"] = self.mode.get()
        install["product_key"] = self.key.get().strip().upper()
        title = self.zone.get()
        install["time_zone"] = next((z for z, t in self._zones if t == title), title)
        self.changed()


class LanguagesForm(_Form):
    def __init__(self, master: tk.Misc, window: MainWindow) -> None:
        super().__init__(
            master,
            window,
            "Языки и регион",
            "Язык интерфейса Windows берётся из установочного ISO и не меняется. Его всё равно нужно указать: "
            "иначе установщик покажет экран выбора языка. Остальные поля задают форматы и языки ввода.",
        )
        self.vars: dict[str, tk.StringVar] = {}
        rows = (
            ("ui_language", "Язык интерфейса (= язык ISO)"),
            ("user_locale", "Формат дат, чисел, валюты"),
            ("system_locale", "Язык программ без Юникода"),
        )
        for index, (key, title) in enumerate(rows, start=2):
            ttk.Label(self, text=title).grid(row=index, column=0, sticky="w", padx=(0, 12), pady=2)
            var = tk.StringVar()
            ttk.Combobox(self, textvariable=var, values=LOCALE_CHOICES, width=14).grid(row=index, column=1, sticky="w", pady=2)
            var.trace_add("write", lambda *_a, k=key, v=var: self._save_locale(k, v))
            self.vars[key] = var
        self.note(5, "Для украинского ISO: uk-UA. «Язык программ без Юникода» uk-UA даёт кодовую страницу 1251 для старых программ (общая для украинского и русского).")

        ttk.Label(self, text="Языки ввода (порядок переключения)").grid(row=6, column=0, sticky="nw", padx=(0, 12), pady=(8, 0))
        box = ttk.Frame(self)
        box.grid(row=6, column=1, sticky="w", pady=(8, 0))
        self.input_list = tk.Listbox(box, height=6, width=56, activestyle="none", exportselection=False)
        self.input_list.grid(row=0, column=0, rowspan=4, sticky="w")
        for r, (text, cmd) in enumerate((("Вверх", self._up), ("Вниз", self._down), ("Удалить", self._remove))):
            ttk.Button(box, text=text, command=cmd, width=10).grid(row=r, column=1, sticky="w", padx=(6, 0), pady=1)
        add_row = ttk.Frame(box)
        add_row.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.add_var = tk.StringVar()
        self.add_box = ttk.Combobox(add_row, textvariable=self.add_var, state="readonly", width=48)
        self.add_box.pack(side="left")
        ttk.Button(add_row, text="Добавить", command=self._add).pack(side="left", padx=(6, 0))
        self.note(
            7,
            "Первый язык в списке основной. Языки с пометкой «при первом входе» (например, «Русский (Украина)») не имеют "
            "числового кода: на экране входа вместо них стоит базовый язык, а у каждого пользователя они появляются "
            "при первом входе (правило «Список языков ввода пользователя»).",
        )
        ttk.Label(self, text="Страна (регион)").grid(row=8, column=0, sticky="w", padx=(0, 12))
        region = ttk.Frame(self)
        region.grid(row=8, column=1, sticky="w")
        ttk.Label(region, text="задаётся параметрами правила «Регион пользователя»").pack(side="left")
        ttk.Button(region, text="Перейти к правилу", command=lambda: window.select_node("r:default-user.region")).pack(side="left", padx=(8, 0))

    def _entries(self) -> list[dict[str, Any]]:
        return self.window.resources.keyboards

    def _display(self, item: str) -> str:
        entry = find_keyboard(self._entries(), item)
        if entry is None:
            return f"{item} (неизвестный язык)"
        suffix = "  [при первом входе]" if entry.get("transient") else ""
        return f"{entry.get('title', item)}  ({item}){suffix}"

    def refresh(self) -> None:
        self._loading = True
        languages = self.window.profile.languages
        for key, var in self.vars.items():
            var.set(str(languages.get(key, "")))
        self._fill_list()
        self.add_box.configure(values=[f"{e['tag']}: {e['title']}" for e in self._entries()])
        self._loading = False

    def _fill_list(self, select: int | None = None) -> None:
        self.input_list.delete(0, tk.END)
        for item in self.window.profile.languages.get("input", []):
            self.input_list.insert(tk.END, self._display(str(item)))
        if select is not None and 0 <= select < self.input_list.size():
            self.input_list.selection_set(select)

    def _save_locale(self, key: str, var: tk.StringVar) -> None:
        if self._loading:
            return
        self.window.profile.languages[key] = var.get().strip()
        self.changed()

    def _selected(self) -> int | None:
        sel = self.input_list.curselection()
        return int(sel[0]) if sel else None

    def _move(self, delta: int) -> None:
        index = self._selected()
        items: list[str] = self.window.profile.languages["input"]
        if index is None or not 0 <= index + delta < len(items):
            return
        items[index], items[index + delta] = items[index + delta], items[index]
        self._fill_list(index + delta)
        self.changed()

    def _up(self) -> None:
        self._move(-1)

    def _down(self) -> None:
        self._move(1)

    def _remove(self) -> None:
        index = self._selected()
        items: list[str] = self.window.profile.languages["input"]
        if index is None or len(items) <= 1:
            return
        del items[index]
        self._fill_list(min(index, len(items) - 1))
        self.changed()

    def _add(self) -> None:
        choice = self.add_box.current()
        if choice < 0:
            return
        item = keyboard_item_id(self._entries(), self._entries()[choice])
        items: list[str] = self.window.profile.languages["input"]
        if item in items:
            return
        items.append(item)
        self._fill_list(len(items) - 1)
        self.changed()


class AccountsForm(_Form):
    def __init__(self, master: tk.Misc, window: MainWindow) -> None:
        super().__init__(
            master,
            window,
            "Учётные записи",
            "Локальные учётные записи, которые установщик создаёт до первого входа. Стартовые Admin и User по умолчанию "
            "без паролей: пароли и группы назначает отдельный проект после установки. Пароль, если его задать здесь, "
            "попадёт в файл ответов открытым текстом.",
        )
        table = ttk.Frame(self)
        table.grid(row=2, column=0, columnspan=3, sticky="we")
        self.tree = ttk.Treeview(table, columns=("name", "display", "group", "password"), show="headings", height=6, selectmode="browse")
        for column, title, width in (("name", "Имя", 140), ("display", "Отображаемое имя", 180), ("group", "Группа", 130), ("password", "Пароль", 90)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=column == "display")
        self.tree.pack(side="left", fill="x", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected())
        buttons = ttk.Frame(table)
        buttons.pack(side="left", padx=(6, 0), anchor="n")
        for text, cmd in (("Добавить", self._add), ("Удалить", self._remove), ("Вверх", lambda: self._move(-1)), ("Вниз", lambda: self._move(1))):
            ttk.Button(buttons, text=text, command=cmd, width=10).pack(pady=1)

        edit = ttk.LabelFrame(self, text="Выбранная учётная запись", padding=(10, 6))
        edit.grid(row=3, column=0, columnspan=3, sticky="we", pady=(10, 0))
        self.name = tk.StringVar()
        self.display = tk.StringVar()
        self.group = tk.StringVar()
        self.description = tk.StringVar()
        self.password = tk.StringVar()
        fields = (
            ("Имя (для входа)", ttk.Entry(edit, textvariable=self.name, width=24)),
            ("Отображаемое имя", ttk.Entry(edit, textvariable=self.display, width=32)),
            ("Группа", ttk.Combobox(edit, textvariable=self.group, values=("Administrators", "Users"), state="readonly", width=16)),
            ("Описание", ttk.Entry(edit, textvariable=self.description, width=48)),
            ("Пароль (необязательно)", ttk.Entry(edit, textvariable=self.password, width=24, show="*")),
        )
        for row, (title, widget) in enumerate(fields):
            ttk.Label(edit, text=title).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
            widget.grid(row=row, column=1, sticky="w", pady=2)
        ttk.Button(edit, text="Применить", command=self._apply).grid(row=len(fields), column=1, sticky="w", pady=(6, 0))
        self.error = tk.StringVar()
        ttk.Label(edit, textvariable=self.error, style="Error.TLabel", wraplength=WRAP).grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w")

    @property
    def accounts(self) -> list[Account]:
        return self.window.profile.accounts

    def refresh(self, select: int | None = 0) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, account in enumerate(self.accounts):
            self.tree.insert("", "end", iid=str(index), values=(account.name, account.display_name, account.group, "задан" if account.password else "нет"))
        if select is not None and self.accounts:
            select = max(0, min(select, len(self.accounts) - 1))
            self.tree.selection_set(str(select))
        else:
            self._clear_editor()

    def _index(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _clear_editor(self) -> None:
        for var in (self.name, self.display, self.group, self.description, self.password, self.error):
            var.set("")

    def _load_selected(self) -> None:
        index = self._index()
        if index is None:
            return
        account = self.accounts[index]
        self.name.set(account.name)
        self.display.set(account.display_name)
        self.group.set(account.group)
        self.description.set(account.description)
        self.password.set(account.password)
        self.error.set("")

    def _apply(self) -> None:
        index = self._index()
        if index is None:
            return
        name = self.name.get().strip()
        reason = check_account_name(name)
        if reason is None and any(i != index and a.name.lower() == name.lower() for i, a in enumerate(self.accounts)):
            reason = "такое имя уже есть"
        if reason:
            self.error.set(f"Не применено: {reason}.")
            return
        account = self.accounts[index]
        account.name = name
        account.display_name = self.display.get().strip() or name
        account.group = self.group.get() or "Users"
        account.description = self.description.get().strip()
        account.password = self.password.get()
        self.error.set("Пароль будет записан в файл ответов открытым текстом." if account.password else "")
        if not any(a.group == "Administrators" for a in self.accounts):
            self.error.set("Внимание: не осталось ни одной учётной записи в группе Administrators.")
        self.refresh(index)
        self.changed()

    def _add(self) -> None:
        names = {a.name.lower() for a in self.accounts}
        number = 2
        while f"user{number}" in names:
            number += 1
        self.accounts.append(Account(f"User{number}", f"User{number}", "Users", "Standard user"))
        self.refresh(len(self.accounts) - 1)
        self.changed()

    def _remove(self) -> None:
        index = self._index()
        if index is None or len(self.accounts) <= 1:
            self.error.set("Нужна хотя бы одна учётная запись.")
            return
        del self.accounts[index]
        self.refresh(index)
        self.changed()

    def _move(self, delta: int) -> None:
        index = self._index()
        if index is None or not 0 <= index + delta < len(self.accounts):
            return
        self.accounts[index], self.accounts[index + delta] = self.accounts[index + delta], self.accounts[index]
        self.refresh(index + delta)
        self.changed()
