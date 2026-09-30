"""Forms of the data nodes of the tree: installation, local accounts, languages and region.

Every change is written into the profile at once and marks it as modified; nothing is written to disk
until the user saves the profile.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from winkickoff.core.i18n import N_, language, tr
from winkickoff.core.profile import Account
from winkickoff.core.render import EDITION_KEYS
from winkickoff.core.resources import find_keyboard, keyboard_item_id
from winkickoff.core.validate import check_account_name

if TYPE_CHECKING:
    from winkickoff.ui.main_window import MainWindow

WRAP = 600
LOCALE_CHOICES = ("uk-UA", "ru-RU", "en-US", "en-GB", "pl-PL", "de-DE")
KEY_MODES = (
    ("generic", N_("Generic key for the selected edition: no product key or edition selection screens, "
                   "Windows activates on its own using this PC's digital license")),
    ("custom", N_("Your own product key (for example, from a sticker or contract)")),
    ("ask", N_("Ask for the key and edition during installation")),
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
            tr("Installation"),
            tr("Windows edition, product key and time zone. The display language and input languages are set in the \"Languages and region\" node."),
        )
        self.edition = tk.StringVar()
        self.mode = tk.StringVar()
        self.key = tk.StringVar()
        self.zone = tk.StringVar()
        ttk.Label(self, text=tr("Windows edition")).grid(row=2, column=0, sticky="w", padx=(0, 12))
        edition_box = ttk.Combobox(self, textvariable=self.edition, values=list(EDITION_KEYS), state="readonly", width=18)
        edition_box.grid(row=2, column=1, sticky="w")
        edition_box.bind("<<ComboboxSelected>>", lambda _e: self._save())
        self.note(3, tr("Pro: the main edition of the project. Enterprise and Education only with the corresponding licenses; Home is not supported (policies do not work)."))

        ttk.Label(self, text=tr("Product key")).grid(row=4, column=0, sticky="nw", padx=(0, 12))
        box = ttk.Frame(self)
        box.grid(row=4, column=1, sticky="w")
        for value, text in KEY_MODES:
            ttk.Radiobutton(box, text=tr(text), value=value, variable=self.mode, command=self._save).pack(anchor="w", pady=1)
        self.key_entry = ttk.Entry(box, textvariable=self.key, width=34)
        self.key_entry.pack(anchor="w", padx=(22, 0), pady=(2, 0))
        self.key.trace_add("write", lambda *_: self._save())

        ttk.Label(self, text=tr("Time zone")).grid(row=5, column=0, sticky="w", padx=(0, 12), pady=(12, 0))
        self.zone_box = ttk.Combobox(self, textvariable=self.zone, state="readonly", width=48)
        self.zone_box.grid(row=5, column=1, sticky="w", pady=(12, 0))
        self.zone_box.bind("<<ComboboxSelected>>", lambda _e: self._save())
        self.note(6, tr("The correct time zone matters for logs: during an investigation, events are matched by time."))
        self._zones: list[tuple[str, str]] = []

    def refresh(self) -> None:
        self._loading = True
        install = self.window.profile.install
        self.edition.set(str(install.get("edition", "Pro")))
        self.mode.set(str(install.get("product_key_mode", "generic")))
        self.key.set(str(install.get("product_key", "")))
        title_key = "title" if language() == "ru" else f"title_{language()}"
        self._zones = [(str(z["id"]), str(z.get(title_key) or z["title"])) for z in self.window.resources.timezones]
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
            tr("Languages and region"),
            tr("The Windows display language comes from the installation ISO and does not change. It "
               "still has to be specified; otherwise Windows Setup shows the language selection screen. "
               "The other fields set formats and input languages."),
        )
        self.vars: dict[str, tk.StringVar] = {}
        rows = (
            ("ui_language", tr("Display language (= ISO language)")),
            ("user_locale", tr("Date, number and currency format")),
            ("system_locale", tr("Language for non-Unicode programs")),
        )
        for index, (key, title) in enumerate(rows, start=2):
            ttk.Label(self, text=title).grid(row=index, column=0, sticky="w", padx=(0, 12), pady=2)
            var = tk.StringVar()
            ttk.Combobox(self, textvariable=var, values=LOCALE_CHOICES, width=14).grid(row=index, column=1, sticky="w", pady=2)
            var.trace_add("write", lambda *_a, k=key, v=var: self._save_locale(k, v))
            self.vars[key] = var
        self.note(5, tr("For a Ukrainian ISO: uk-UA. Setting \"Language for non-Unicode programs\" to uk-UA gives legacy programs code page 1251 (shared by Ukrainian and Russian)."))

        ttk.Label(self, text=tr("Input languages (switching order)")).grid(row=6, column=0, sticky="nw", padx=(0, 12), pady=(8, 0))
        box = ttk.Frame(self)
        box.grid(row=6, column=1, sticky="w", pady=(8, 0))
        self.input_list = tk.Listbox(box, height=6, width=56, activestyle="none", exportselection=False)
        self.input_list.grid(row=0, column=0, rowspan=4, sticky="w")
        for r, (text, cmd) in enumerate(((tr("Move up"), self._up), (tr("Move down"), self._down), (tr("Remove"), self._remove))):
            ttk.Button(box, text=text, command=cmd, width=10).grid(row=r, column=1, sticky="w", padx=(6, 0), pady=1)
        add_row = ttk.Frame(box)
        add_row.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.add_var = tk.StringVar()
        self.add_box = ttk.Combobox(add_row, textvariable=self.add_var, state="readonly", width=48)
        self.add_box.pack(side="left")
        ttk.Button(add_row, text=tr("Add"), command=self._add).pack(side="left", padx=(6, 0))
        self.note(
            7,
            tr("The first language in the list is the default. Languages marked \"at first sign-in\" (for "
               "example, \"Russian (Ukraine)\") have no numeric code: the sign-in screen shows the base "
               "language instead, and each user gets them at first sign-in (rule \"User input language "
               "list\")."),
        )
        ttk.Label(self, text=tr("Country or region")).grid(row=8, column=0, sticky="w", padx=(0, 12))
        region = ttk.Frame(self)
        region.grid(row=8, column=1, sticky="w")
        ttk.Label(region, text=tr("set by the parameters of the \"User region\" rule")).pack(side="left")
        ttk.Button(region, text=tr("Go to rule"), command=lambda: window.select_node("r:default-user.region")).pack(side="left", padx=(8, 0))

    def _entries(self) -> list[dict[str, Any]]:
        return self.window.resources.keyboards

    def _display(self, item: str) -> str:
        entry = find_keyboard(self._entries(), item)
        if entry is None:
            return tr("{0} (unknown language)", item)
        suffix = tr("  [at first sign-in]") if entry.get("transient") else ""
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
            tr("Accounts"),
            tr("Local accounts that Windows Setup creates before the first sign-in. The initial Admin and "
               "User accounts have no passwords by default: passwords and groups are assigned by a "
               "separate project after installation. A password set here is written to the answer file in "
               "plain text."),
        )
        table = ttk.Frame(self)
        table.grid(row=2, column=0, columnspan=3, sticky="we")
        self.tree = ttk.Treeview(table, columns=("name", "display", "group", "password"), show="headings", height=6, selectmode="browse")
        for column, title, width in (("name", tr("Name"), 140), ("display", tr("Display name"), 180), ("group", tr("Group"), 130), ("password", tr("Password"), 90)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, stretch=column == "display")
        self.tree.pack(side="left", fill="x", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected())
        buttons = ttk.Frame(table)
        buttons.pack(side="left", padx=(6, 0), anchor="n")
        for text, cmd in ((tr("Add"), self._add), (tr("Remove"), self._remove), (tr("Move up"), lambda: self._move(-1)), (tr("Move down"), lambda: self._move(1))):
            ttk.Button(buttons, text=text, command=cmd, width=10).pack(pady=1)

        edit = ttk.LabelFrame(self, text=tr("Selected account"), padding=(10, 6))
        edit.grid(row=3, column=0, columnspan=3, sticky="we", pady=(10, 0))
        self.name = tk.StringVar()
        self.display = tk.StringVar()
        self.group = tk.StringVar()
        self.description = tk.StringVar()
        self.password = tk.StringVar()
        fields = (
            (tr("Name (for sign-in)"), ttk.Entry(edit, textvariable=self.name, width=24)),
            (tr("Display name"), ttk.Entry(edit, textvariable=self.display, width=32)),
            (tr("Group"), ttk.Combobox(edit, textvariable=self.group, values=("Administrators", "Users"), state="readonly", width=16)),
            (tr("Description"), ttk.Entry(edit, textvariable=self.description, width=48)),
            (tr("Password (optional)"), ttk.Entry(edit, textvariable=self.password, width=24, show="*")),
        )
        for row, (title, widget) in enumerate(fields):
            ttk.Label(edit, text=title).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
            widget.grid(row=row, column=1, sticky="w", pady=2)
        ttk.Button(edit, text=tr("Apply"), command=self._apply).grid(row=len(fields), column=1, sticky="w", pady=(6, 0))
        self.error = tk.StringVar()
        ttk.Label(edit, textvariable=self.error, style="Error.TLabel", wraplength=WRAP).grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w")

    @property
    def accounts(self) -> list[Account]:
        return self.window.profile.accounts

    def refresh(self, select: int | None = 0) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, account in enumerate(self.accounts):
            self.tree.insert("", "end", iid=str(index), values=(account.name, account.display_name, account.group, tr("set") if account.password else tr("not set")))
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
            reason = tr("this name already exists")
        if reason:
            self.error.set(tr("Not applied: {0}.", reason))
            return
        account = self.accounts[index]
        account.name = name
        account.display_name = self.display.get().strip() or name
        account.group = self.group.get() or "Users"
        account.description = self.description.get().strip()
        account.password = self.password.get()
        self.error.set(tr("The password will be written to the answer file in plain text.") if account.password else "")
        if not any(a.group == "Administrators" for a in self.accounts):
            self.error.set(tr("Warning: no accounts are left in the Administrators group."))
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
            self.error.set(tr("At least one account is required."))
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
