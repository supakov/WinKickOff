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
import sys
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
    audit_rules,
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
from winkickoff.core.i18n import SOURCE_LANGUAGE, N_, available_languages, catalog_texts, language, tr
from winkickoff.core.importer import IMPORTED_NAME, ImportFailed, import_xml
from winkickoff.core.paths import AppPaths, display_path
from winkickoff.core.profile import Profile
from winkickoff.core.pscheck import PsCheckResult, check_scripts
from winkickoff.core.render import BuildResult, Renderer, RenderError, render_action, substitute
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings
from winkickoff.core.themes import Theme, available_themes, resolve_theme
from winkickoff.core.validate import Issue, has_errors, validate_catalog, validate_profile, validate_xml
from winkickoff.core.verify import rollback_steps, verify_steps
from winkickoff.ui.checkimages import make_check_images
from winkickoff.ui.data_forms import AccountsForm, InstallForm, LanguagesForm
from winkickoff.ui.winmenus import MenuMargins, colorref

log = logging.getLogger(__name__)

WORKFLOW_NODE = "info:workflow"
PRESET_NAMES = (N_("Office"), N_("Strict"), N_("Laptop"))  # preset names are English data; shown through tr()
THEME_NAMES = (N_("Light"), N_("Dark"), N_("Latte"), N_("Matrix"))  # names of the bundled themes; shown through tr()
DATA_NODES: tuple[tuple[str, str], ...] = (
    ("data:install", N_("Installation: edition, key, time zone")),
    ("data:accounts", N_("Accounts")),
    ("data:languages", N_("Languages and region")),
)
LEVEL_TITLES = {"baseline": N_("baseline"), "recommended": N_("recommended"), "optional": N_("optional"), "risky": N_("risky")}
PHASE_TITLES = {
    "windowspe": N_("Windows Setup (windowsPE)"),
    "specialize-xml": N_("first boot (command in XML)"),
    "specialize": N_("first boot (machine script Setup-System.ps1)"),
    "default-user": N_("default user profile"),
    "user-first-logon": N_("each user's first sign-in (Setup-User.ps1)"),
    "post-oobe": N_("after initial setup (Post-OOBE.ps1)"),
    "oobe-xml": N_("initial setup (OOBE)"),
}
ISSUE_TITLES = {"error": N_("error"), "warning": N_("warning"), "info": N_("information"), "change": N_("changed")}
VK_S, VK_O, VK_F = 83, 79, 70  # virtual-key codes: shortcuts work with any keyboard layout

WORKFLOW = [
    ("h1", N_("Workflow")),
    ("", N_("WinKickOff builds an autounattend.xml file for automated installation of Windows 11. Put "
            "the file in the root of the Windows installation USB drive; Windows Setup finds it on its "
            "own and does everything selected here.")),
    ("h2", N_("1. Profile")),
    ("", N_("The \"Profile\" field in the top panel. \"Preset: Office\" reproduces the tested v0.2 answer "
            "file; \"Preset: Strict\" adds restrictions that may interfere with older programs. Presets "
            "are never modified: a changed profile is saved under its own name (the \"Save as\" button).")),
    ("h2", N_("2. Rules")),
    ("", N_("The tree on the left contains all installation settings. The checkbox before a name "
            "enables or disables the rule (or the whole group); \"+\" only expands the branch. Rules "
            "that depend on a disabled rule are disabled automatically, and enabling a rule enables "
            "what it needs: the changes are shown in the status bar and in the list below. Search "
            "(Ctrl+F) looks in names, tags and technical details, for example a registry key name.")),
    ("h2", N_("3. Description and parameters")),
    ("", N_("On the right, for the selected rule: what it does technically (registry keys, services, "
            "commands), effect, risks, Windows versions, check and rollback. The rule parameters "
            "(hours, modes, thresholds) are changed there too, below the description.")),
    ("h2", N_("4. Installation data")),
    ("", N_("The \"Installation\", \"Accounts\" and \"Languages and region\" nodes at the top of the tree: "
            "edition and key, time zone, initial accounts, display language (same as the ISO language) "
            "and input languages.")),
    ("h2", N_("5. Saving the profile")),
    ("", N_("\"Save\" (Ctrl+S) writes the profile to the profiles folder next to the program, so the "
            "installation can be repeated on other PCs. The profile is also embedded in every built "
            "file: \"File, Open profile from autounattend.xml\" restores the settings from a finished "
            "autounattend.xml.")),
    ("h2", N_("6. Check and build")),
    ("", N_("\"Check\" (F7) checks the profile and the resulting file. \"Build autounattend.xml\" (F9) "
            "builds the file from enabled rules only, checks Windows Setup limits and PowerShell "
            "syntax, and asks where to save it. Errors and warnings appear in the list below; "
            "double-click one to go to the rule.")),
    ("h2", N_("7. Installation")),
    ("", N_("Copy autounattend.xml to the root of a USB drive with the Windows 11 installation image "
            "and boot the PC from it. Windows Setup asks only for the drive to install to. After "
            "installation, logs are in C:\\ProgramData\\Unattend\\Logs.")),
]


def user_docs(docs_root: Path | None = None) -> str:
    """The user documentation in the interface language (docs/user/<code>/README.md), English when a language
    has no documentation."""
    wanted = f"docs/user/{language()}/README.md"
    if docs_root is not None and not (docs_root / wanted).exists():
        return f"docs/user/{SOURCE_LANGUAGE}/README.md"
    return wanted


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
        self.images = make_check_images(self, self.theme.colors)
        self.style.configure("Treeview", rowheight=self.images["on"].height() + 8)
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._bind_keys()
        self.rebuild_tree()
        self.refresh_profile_choices()
        self.update_title()
        self.select_node(WORKFLOW_NODE)
        self._windows_frame()
        self.set_status(tr("Rule catalog {0}: {1} rules in {2} groups. Profile: {3}.", catalog.version, len(catalog.rules), len(catalog.groups), tr(profile.name)))

    # ----------------------------------------------------------------- style and layout

    def _setup_style(self) -> None:
        """ttk styles, fonts and colours of the theme (resources/themes, settings.theme; "" follows Windows)."""
        self.theme: Theme = resolve_theme(self.settings.theme, self.paths.resources)
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("vista" if self.theme.base == "native" else self.theme.base)
        except tk.TclError:
            pass
        if self.theme.font:
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkTooltipFont"):
                try:
                    tkfont.nametofont(name).configure(family=self.theme.font)
                except tk.TclError:
                    pass
            self.option_add("*Menu.font", "TkMenuFont")  # on Windows menus take the system font, not TkMenuFont
        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        size = int(base.actual("size")) or 9
        self.font_h1 = tkfont.Font(self, family=family, size=size + 4, weight="bold")
        self.font_h2 = tkfont.Font(self, family=family, size=size + 1, weight="bold")
        self.font_text = tkfont.Font(self, family=family, size=size + 1)
        self.font_mono = tkfont.Font(self, family="Consolas", size=size)
        self._apply_theme_colors()
        self.style.configure("H1.TLabel", font=self.font_h1)
        self.style.configure("Note.TLabel", foreground=self.color("muted"))
        self.style.configure("Error.TLabel", foreground=self.color("error"))
        self.style.configure("Changed.TLabel", foreground=self.color("changed"), font=(family, size, "bold"))

    def color(self, key: str) -> str:
        return self.theme.color(key)

    def _apply_theme_colors(self) -> None:
        """Colours of every widget style; a native theme with no window colours keeps the Windows look."""
        c = self.theme.colors
        bg, fg, field, field_fg = c["background"], c["foreground"], c["field"], c["field_foreground"]
        if not bg:
            return
        select, select_fg, border = c["select"] or field, c["select_foreground"] or fg, c["border"] or bg
        button, button_fg, active = c["button"] or bg, c["button_foreground"] or fg, c["button_active"] or select
        s = self.style
        self.configure(background=bg)
        s.configure(".", background=bg, foreground=fg, fieldbackground=field, bordercolor=border, lightcolor=bg,
                    darkcolor=bg, troughcolor=bg, selectbackground=select, selectforeground=select_fg,
                    insertcolor=field_fg, arrowcolor=fg, focuscolor=select)
        s.map(".", foreground=[("disabled", c["disabled"])], background=[("active", active)])
        for name in ("TFrame", "TLabel", "TLabelframe", "TPanedwindow", "TCheckbutton", "TRadiobutton"):
            s.configure(name, background=bg, foreground=fg)
        s.configure("TLabelframe.Label", background=bg, foreground=fg)
        s.map("TCheckbutton", background=[("active", bg)], indicatorbackground=[("selected", select), ("!selected", field)])
        s.map("TRadiobutton", background=[("active", bg)], indicatorbackground=[("selected", select), ("!selected", field)])
        s.configure("TButton", background=button, foreground=button_fg, bordercolor=border)
        s.map("TButton", background=[("pressed", select), ("active", active)], foreground=[("disabled", c["disabled"])])
        for name in ("TEntry", "TCombobox", "TSpinbox"):
            s.configure(name, fieldbackground=field, foreground=field_fg, background=button, insertcolor=field_fg, arrowcolor=fg)
        s.map("TCombobox", fieldbackground=[("readonly", field)], foreground=[("readonly", field_fg)],
              selectbackground=[("readonly", field)], selectforeground=[("readonly", field_fg)])
        s.configure("Treeview", background=field, fieldbackground=field, foreground=field_fg, bordercolor=border)
        s.map("Treeview", background=[("selected", select)], foreground=[("selected", select_fg)])
        s.configure("Treeview.Heading", background=c["heading"] or button, foreground=fg, bordercolor=border)
        s.map("Treeview.Heading", background=[("active", active)])
        s.configure("TScrollbar", background=button, troughcolor=bg, arrowcolor=fg, bordercolor=border)
        s.map("TScrollbar", background=[("active", active)])
        for option, value in (("*TCombobox*Listbox.background", field), ("*TCombobox*Listbox.foreground", field_fg),
                              ("*TCombobox*Listbox.selectBackground", select), ("*TCombobox*Listbox.selectForeground", select_fg),
                              ("*Menu.background", bg), ("*Menu.foreground", fg), ("*Menu.activeBackground", select),
                              ("*Menu.activeForeground", select_fg), ("*Listbox.background", field),
                              ("*Listbox.foreground", field_fg), ("*Listbox.selectBackground", select),
                              ("*Listbox.selectForeground", select_fg), ("*Toplevel.background", bg)):
            self.option_add(option, value)

    def _style_text(self, widget: tk.Text) -> None:
        c = self.theme.colors
        if c["field"]:
            widget.configure(background=c["field"], foreground=c["field_foreground"] or c["foreground"],
                             insertbackground=c["field_foreground"] or c["foreground"],
                             selectbackground=c["select"] or c["field"], selectforeground=c["select_foreground"] or c["foreground"])

    def _windows_frame(self) -> None:
        """The window frame and the menu frames in the theme colours. Every call affects only this program while it
        runs: DwmSetWindowAttribute on this window (dark mode; on Windows 11 also the colours of the title bar, its
        text and the border) and the preferred app mode of this process, which makes Windows draw the borders of
        drop-down menus dark (uxtheme ordinals 135 SetPreferredAppMode and 136 FlushMenuThemes, undocumented but
        stable since Windows 10 1903). Nothing is written to the system."""
        if sys.platform != "win32":
            return
        dark, c = self.theme.dark, self.theme.colors
        try:
            import ctypes

            if sys.getwindowsversion().build >= 18362:
                uxtheme = ctypes.windll.uxtheme
                uxtheme[135](2 if dark else 0)  # ForceDark or Default
                uxtheme[136]()
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())

            def put(attribute: int, value: int) -> bool:
                data = ctypes.c_int(value)
                return ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data)) == 0

            if dark and not put(20, 1):  # DWMWA_USE_IMMERSIVE_DARK_MODE; 19 on builds before 20H1
                put(19, 1)
            if self.theme.base != "native":
                # DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR: Windows 11, ignored by older builds
                for attribute, color in ((34, c["border"]), (35, c["title_bar"] or c["background"]),
                                         (36, c["title_text"] or c["foreground"])):
                    if color:
                        put(attribute, colorref(color))
        except (AttributeError, OSError, ValueError):
            pass

    def _top_menu(self, label: str) -> tk.Menu:
        """A menu of the menu bar. Windows draws its own menu bar in system colours only, so a coloured theme gets a
        row of menu buttons instead; their drop-down menus are drawn by Tk in the theme colours either way."""
        used = self._access_keys
        starts = [i for i, ch in enumerate(label) if ch.isalpha() and (i == 0 or not label[i - 1].isalpha())]
        order = starts + [i for i in range(len(label)) if i not in starts]  # first letters of words first
        underline = next((i for i in order if label[i].isalpha() and label[i].lower() not in used), -1)
        if underline >= 0:
            used.add(label[underline].lower())  # Alt + this letter opens the menu
        if isinstance(self.menu_bar, tk.Menu):
            menu = tk.Menu(self.menu_bar, tearoff=False)
            self.menu_bar.add_cascade(label=label, menu=menu, **({"underline": underline} if underline >= 0 else {}))
            return menu
        c = self.theme.colors
        button = tk.Menubutton(self.menu_bar, text=label, relief=tk.FLAT, borderwidth=0,
                               highlightthickness=0, padx=8, pady=3, indicatoron=False,
                               background=c["background"], foreground=c["foreground"],
                               activebackground=c["select"] or c["button_active"] or c["background"],
                               activeforeground=c["select_foreground"] or c["foreground"],
                               disabledforeground=c["disabled"])
        button.pack(side=tk.LEFT)
        menu = tk.Menu(button, tearoff=False)  # Tk requires the menu of a menu button to be its child
        button.configure(menu=menu)
        self._no_underline = button.cget("underline")  # Tk's "none": -1 in Tk 8.6, an empty string in Tk 9
        self.menu_buttons.append(button)
        self._menu_underlines.append(underline)
        return menu

    def _on_alt_key(self, event: tk.Event) -> str | None:  # type: ignore[type-arg]
        """Alt + the underlined letter opens that menu; the Latin letter is also found by its key code, so it works
        whichever keyboard layout is active."""
        chars = {event.char.lower()} if event.char else set()
        if 0x41 <= event.keycode <= 0x5A:
            chars.add(chr(event.keycode).lower())
        for button, underline in zip(self.menu_buttons, self._menu_underlines):
            if underline >= 0 and button.cget("text")[underline].lower() in chars:
                return self._post_menu(button)
        return None

    def _post_menu(self, button: tk.Menubutton) -> str:
        self._show_access_keys(False)
        self.tk.call("tk::MbPost", str(button))  # the same calls as Tk's own keyboard traversal
        self.tk.call("tk::MenuFirstEntry", button.cget("menu"))
        return "break"

    def _show_access_keys(self, show: bool) -> None:
        """Underline the access letters of the menu buttons while Alt is held, as Windows does in its menu bar."""
        for button, underline in zip(self.menu_buttons, self._menu_underlines):
            button.configure(underline=underline if show and underline >= 0 else self._no_underline)

    def _build_menu(self) -> None:
        self._access_keys: set[str] = set()
        self.menu_buttons: list[tk.Menubutton] = []
        self._menu_underlines: list[int] = []
        if self.theme.base == "native" or not self.color("background"):
            self.menu_bar: tk.Menu | tk.Frame = tk.Menu(self, tearoff=False)
            self.menu_margins = MenuMargins("")
        else:
            self.menu_bar = tk.Frame(self, background=self.color("background"))
            self.menu_bar.pack(side=tk.TOP, fill=tk.X)
            self.menu_margins = MenuMargins(self.color("background"))
            for key in ("Alt_L", "Alt_R"):
                self.bind(f"<KeyPress-{key}>", lambda _e: self._show_access_keys(True), add="+")
                self.bind(f"<KeyRelease-{key}>", lambda _e: self._show_access_keys(False), add="+")
            self.bind("<FocusOut>", lambda _e: self._show_access_keys(False), add="+")
            # on Windows Tk binds Alt + letter and F10 only inside a focused menu button, so the window does it
            self.bind("<Alt-KeyPress>", self._on_alt_key, add="+")
            self.bind("<KeyPress-F10>", lambda e: self._post_menu(self.menu_buttons[0]) if self.menu_buttons else None, add="+")
        file_menu = self._top_menu(tr("File"))
        presets = tk.Menu(file_menu, tearoff=False)
        for path in sorted((self.paths.data / "profiles").glob("preset-*.json")):
            presets.add_command(label=tr(_profile_name(path)), command=lambda p=path: self.load_profile_file(p))
        file_menu.add_cascade(label=tr("New profile from preset"), menu=presets)
        file_menu.add_command(label=tr("Open profile..."), accelerator="Ctrl+O", command=self.open_profile_dialog)
        file_menu.add_command(label=tr("Open profile from autounattend.xml..."), command=self.import_from_xml)
        file_menu.add_command(label=tr("Compare with profile..."), command=self.compare_with_file)
        self.recent_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(label=tr("Recent"), menu=self.recent_menu)
        self._rebuild_recent_menu()
        file_menu.add_separator()
        file_menu.add_command(label=tr("Save profile"), accelerator="Ctrl+S", command=self.save_profile)
        file_menu.add_command(label=tr("Save profile as..."), command=self.save_profile_as)
        file_menu.add_separator()
        file_menu.add_command(label=tr("Exit"), command=self.on_close)
        build_menu = self._top_menu(tr("Build"))
        build_menu.add_command(label=tr("Check"), accelerator="F7", command=self.check)
        build_menu.add_command(label=tr("Build autounattend.xml..."), accelerator="F9", command=self.build)
        build_menu.add_command(label=tr("Open output folder"), command=self.open_output_folder)
        build_menu.add_separator()
        build_menu.add_command(label=tr("Check rule catalog"), command=self.check_catalog)
        view_menu = self._top_menu(tr("Language"))
        # "" follows the Windows language; the others are every translation file found (native names, never translated)
        self.language_var = tk.StringVar(value=self.settings.language)
        view_menu.add_radiobutton(label=tr("As in Windows"), value="", variable=self.language_var, command=lambda: self.change_language(""))
        view_menu.add_separator()
        for code, name in available_languages(self.paths.resources, self.paths.rules).items():
            view_menu.add_radiobutton(label=name, value=code, variable=self.language_var, command=lambda c=code: self.change_language(c))
        theme_menu = self._top_menu(tr("Theme"))
        self.theme_var = tk.StringVar(value=self.settings.theme)
        theme_menu.add_radiobutton(label=tr("As in Windows"), value="", variable=self.theme_var, command=lambda: self.change_theme(""))
        theme_menu.add_separator()
        for theme_id, theme in available_themes(self.paths.resources).items():
            theme_menu.add_radiobutton(label=tr(theme.name), value=theme_id, variable=self.theme_var,
                                       command=lambda t=theme_id: self.change_theme(t))
        self.pc_menu = self._top_menu(tr("This PC"))
        self._fill_pc_menu(self.pc_menu)
        self.pc_menu.add_separator()
        self.allow_apply_var = tk.BooleanVar(value=self.settings.allow_apply)
        self.pc_menu.add_checkbutton(label=tr("Allow applying on this PC"), variable=self.allow_apply_var,
                                     command=self.toggle_allow_apply)
        self.tree_menu = tk.Menu(self, tearoff=False)
        self._fill_pc_menu(self.tree_menu)
        help_menu = self._top_menu(tr("Help"))
        help_menu.add_command(label=tr("Workflow"), command=lambda: self.select_node(WORKFLOW_NODE))
        help_menu.add_command(label=tr("User documentation"), command=lambda: self.open_doc(user_docs(self.paths.docs_root)))
        help_menu.add_command(label=tr("About"), command=self.about)
        if isinstance(self.menu_bar, tk.Menu):
            self.config(menu=self.menu_bar)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6, 8, 4))
        bar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(bar, text=tr("Profile:")).pack(side=tk.LEFT)
        self.profile_var = tk.StringVar()
        self.profile_box = ttk.Combobox(bar, textvariable=self.profile_var, state="readonly", width=34)
        self.profile_box.pack(side=tk.LEFT, padx=(4, 6))
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_selected)
        for text, command in ((tr("Open..."), self.open_profile_dialog), (tr("Save"), self.save_profile), (tr("Save as..."), self.save_profile_as)):
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        self.check_button = ttk.Button(bar, text=tr("Check (F7)"), command=self.check)
        self.check_button.pack(side=tk.LEFT, padx=2)
        self.build_button = ttk.Button(bar, text=tr("Build autounattend.xml (F9)"), command=self.build)
        self.build_button.pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text=tr("Output folder"), command=self.open_output_folder).pack(side=tk.LEFT, padx=2)

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
        ttk.Label(search_row, text=tr("Search:")).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(search_row, text=tr("Clear"), command=self.clear_search).pack(side=tk.LEFT)
        self.search_var.trace_add("write", lambda *_: self._schedule_search())

        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.tree.tag_configure("off", foreground=self.color("disabled"))
        self.tree.tag_configure("changed", foreground=self.color("changed"))
        self.tree.tag_configure("risky", foreground=self.color("risky"))
        self.tree.tag_configure("info", foreground=self.color("changed"))
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
        self._style_text(self.detail)
        detail_scroll = ttk.Scrollbar(self.text_frame, orient=tk.VERTICAL, command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.detail.tag_configure("h1", font=self.font_h1, spacing3=4)
        self.detail.tag_configure("h2", font=self.font_h2, spacing1=10, spacing3=2)
        self.detail.tag_configure("mono", font=self.font_mono, lmargin1=12, lmargin2=12)
        self.detail.tag_configure("muted", foreground=self.color("muted"))
        self.detail.tag_configure("risk", foreground=self.color("risky"))
        self.detail.tag_configure("link", foreground=self.color("link"), underline=True)
        self.detail.tag_bind("link", "<Enter>", lambda _e: self.detail.configure(cursor="hand2"))
        self.detail.tag_bind("link", "<Leave>", lambda _e: self.detail.configure(cursor=""))
        self._link_tags: list[str] = []
        self.params_frame = ttk.LabelFrame(self.detail_view, padding=(10, 6))
        self.detail_view.pack(fill=tk.BOTH, expand=True)

        messages = ttk.Frame(vertical, padding=(8, 2, 8, 2))
        vertical.add(messages, weight=1)
        ttk.Label(messages, text=tr("Messages: check, build, automatic changes (double-click to go to the rule)")).pack(anchor=tk.W)
        box = ttk.Frame(messages)
        box.pack(fill=tk.BOTH, expand=True)
        self.messages = ttk.Treeview(box, columns=("level", "target", "message"), show="headings", height=5)
        for column, title, width, stretch in (("level", tr("Type"), 110, False), ("target", tr("Location"), 230, False), ("message", tr("Message"), 700, True)):
            self.messages.heading(column, text=title)
            self.messages.column(column, width=width, stretch=stretch)
        messages_scroll = ttk.Scrollbar(box, orient=tk.VERTICAL, command=self.messages.yview)
        self.messages.configure(yscrollcommand=messages_scroll.set)
        self.messages.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        messages_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.messages.tag_configure("error", foreground=self.color("error"))
        self.messages.tag_configure("warning", foreground=self.color("warning"))
        self.messages.tag_configure("change", foreground=self.color("changed"))
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
            self.tree.insert("", tk.END, iid=WORKFLOW_NODE, text="  " + tr("Workflow"), tags=("info",))
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
        return " " + tr("{0}   {1} of {2}", self.group_title(group_id), on, total)

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
            ("requires ", tr("requires \"{}\", which is disabled")),
            ("required by ", tr("needed by \"{}\"")),
            ("conflicts with ", tr("conflicts with \"{}\"")),
        ):
            if reason.startswith(prefix):
                other = reason[len(prefix):]
                title = self.rule_title(other) if other in self.catalog.rules else other
                return template.format(title)
        return tr("by your action")

    def _apply_changes(self, changes: list[Change], scope: set[str] | None = None) -> None:
        """Show the result of a toggle. scope: rules the user acted on (a rule or a whole group);
        everything else in changes happened automatically because of dependencies."""
        if not changes:
            self.set_status(tr("No changes"))
            return
        self.mark_dirty()
        self.refresh_marks()
        scope = scope if scope is not None else {c.rule_id for c in changes if c.reason == "user"}
        direct = [c for c in changes if c.rule_id in scope]
        cascade = [c for c in changes if c.rule_id not in scope]
        action = tr("Enabled") if (direct or changes)[0].enabled else tr("Disabled")
        text = tr("{0} rules: {1}", action, len(direct))
        if cascade:
            text += tr("; {0} more changed automatically outside the selection (list below)", len(cascade))
            rows = [
                Issue("change", c.rule_id, tr("{0} \"{1}\": {2}", tr("Enabled") if c.enabled else tr("Disabled"), self.rule_title(c.rule_id), self._reason_text(c)))
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
        if language() != SOURCE_LANGUAGE:  # the index is English; also search the translated titles, summaries and tags
            needle = query.lower()
            texts = catalog_texts()
            found |= {r.id for r in self.catalog.rules.values()
                      if needle in " ".join([self.rule_text(r, "title"), self.rule_text(r, "summary"), *texts.tags(r)]).lower()}
        self.rebuild_tree(found)
        self.set_status(tr("Rules found: {0}", len(found)) if found else tr("Nothing found"))

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
            ("muted", tr("{0}   |   level: {1}   |   {2}   |   {3}", tr("Enabled") if enabled else tr("Disabled"),
                         tr(LEVEL_TITLES.get(rule.level, rule.level)), tr(PHASE_TITLES.get(rule.phase, rule.phase)), rule.id)),
            ("", self.rule_text(rule, "summary")),
            ("h2", tr("What it does technically")),
        ]
        parts += [("mono", self._action_text(action, params)) for action in rule.actions]
        parts += [("h2", tr("Effect")), ("", self.rule_text(rule, "effect"))]
        if rule.risk:
            parts += [("h2", tr("Risks and side effects")), ("risk", self.rule_text(rule, "risk"))]
        if rule.versions:
            parts += [("h2", tr("Windows versions")), ("", self.rule_text(rule, "versions"))]
        parts.append(("h2", tr("Dependencies")))
        for caption, ids, optional in (
            (tr("Requires"), list(rule.requires), False),
            (tr("Disabled along with it"), self.resolver.dependents(rule.id), False),
            (tr("Conflicts with"), list(rule.conflicts), True),
        ):
            if not ids and optional:
                continue
            parts.append(("", f"{caption}: {tr("nothing")}" if not ids else f"{caption}:"))
            parts += [(f"link:r:{other}", "    " + self._rule_link_text(other)) for other in ids]
        parts.append(("h2", tr("Check after installation")))
        if rule.verify:
            parts.append(("mono", self.rule_text(rule, "verify")))
        else:
            parts.append(("muted", tr("Generated from the rule's actions:")))
            parts += [("mono", step) for step in verify_steps(rule, params)]
        parts.append(("h2", tr("Rollback")))
        if rule.rollback:
            parts.append(("", self.rule_text(rule, "rollback")))
        else:
            parts.append(("muted", tr("Generated from the rule's actions:")))
            parts += [("mono", step) for step in rollback_steps(rule, params)]
        parts += [("h2", tr("More details")), (f"link:doc:{rule.doc}", tr("Reference entry: ") + rule.doc)]
        return parts

    def _rule_link_text(self, rule_id: str) -> str:
        state = tr("enabled") if self.profile.is_enabled(rule_id) else tr("disabled")
        return f"{self.rule_title(rule_id)} ({state})"

    def _group_parts(self, group_id: str) -> list[tuple[str, str]]:
        group = self.catalog.groups[group_id]
        on, total = self._group_counts(group_id)
        summary = catalog_texts().group(group, "summary")
        parts: list[tuple[str, str]] = [("h1", self.group_title(group_id)), ("muted", tr("Rules: {0}, enabled: {1}", total, on))]
        if summary:
            parts.append(("", summary))
        parts.append(("h2", tr("Rules in this group")))
        for rule in self.catalog.rules_in_group(group_id):
            mark = "[x]" if self.profile.is_enabled(rule.id) else "[ ]"
            parts.append((f"link:r:{rule.id}", f"{mark} {self.rule_title(rule.id)}"))
        return parts

    def _action_text(self, action: Action, params: dict[str, Any]) -> str:
        f = action.fields
        if action.type == "xml-oobe":
            value = substitute(f["value"], params)
            return tr("XML, initial setup: <{0}>{1}</{2}>", f['element'], value, f['element'])
        if action.type in ("xml-pe-command", "xml-specialize-command"):
            return tr("XML, command: {0}", f['command'])
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
            self.set_status(tr("Reference entry not found: {0}", path))
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            self.set_status(tr("Opened reference entry: {0}", path.name) + (tr(", section \"{0}\"", doc.split('#', 1)[1]) if "#" in doc else ""))
        except OSError as exc:
            self.set_status(tr("Could not open the reference entry: {0}", exc))

    def _clear_params(self) -> None:
        for widget in self.params_frame.winfo_children():
            widget.destroy()
        self._param_vars = []
        self._param_marks = {}
        self.params_frame.pack_forget()

    def _build_group_buttons(self, group_id: str) -> None:
        self._clear_params()
        self.params_frame.configure(text=tr("Whole group"))
        self.params_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.text_frame, pady=(6, 4))
        for text, command in (
            (tr("Enable all"), lambda: self._group_action(group_id, True)),
            (tr("Disable all"), lambda: self._group_action(group_id, False)),
            (tr("Catalog defaults"), lambda: self._group_reset(group_id)),
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
        self.params_frame.configure(text=tr("Rule parameters"))
        self.params_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.text_frame, pady=(6, 4))
        for row, param in enumerate(rule.params.values()):
            ttk.Label(self.params_frame, text=self.param_title(rule, param)).grid(row=row, column=0, sticky=tk.W, padx=(0, 12), pady=2)
            self._param_widget(rule, param).grid(row=row, column=1, sticky=tk.W, pady=2)
            hint = tr("default: {0}", self._param_display(rule, param, param.default))
            if param.type == "int" and (param.min is not None or param.max is not None):
                hint += tr(", range {0}..{1}", param.min, param.max)
            ttk.Label(self.params_frame, text=hint, style="Note.TLabel").grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
            mark = ttk.Label(self.params_frame, style="Changed.TLabel")
            mark.grid(row=row, column=3, sticky=tk.W, padx=(10, 0))
            self._param_marks[param.name] = mark
            self._update_param_mark(rule, param)
        ttk.Button(self.params_frame, text=tr("Restore defaults"), command=lambda: self._reset_params(rule)).grid(
            row=len(rule.params), column=1, sticky=tk.W, pady=(6, 0)
        )

    def _param_display(self, rule: Rule, param: Param, value: Any) -> str:
        if param.type == "enum":
            return next((title for v, title in self.param_options(rule, param) if v == value), str(value))
        if param.type == "bool":
            return tr("yes") if value else tr("no")
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
            mark.configure(text=tr("changed") if param.name in self.profile.rules[rule.id].params else "")

    def _set_param_text(self, rule: Rule, param: Param, raw: str) -> None:
        try:
            value = int(raw)
        except ValueError:
            self.set_status(tr("\"{0}\": an integer is required", self.param_title(rule, param)))
            return
        if param.min is not None and value < param.min or param.max is not None and value > param.max:
            self.set_status(tr("\"{0}\": allowed range is {1} to {2}", self.param_title(rule, param), param.min, param.max))
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
        self.set_status(f"{self.rule_title(rule.id)}: {self.param_title(rule, param)} = {self._param_display(rule, param, value)}")
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
            choices.append((tr("Preset: {0}", tr(_profile_name(path))), path))
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
        return tr("{0} (not saved)", tr(self.profile.name))

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
        answer = messagebox.askyesnocancel(APP_NAME, tr("Profile \"{0}\" has been changed. Save changes?", tr(self.profile.name)), parent=self)
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
            messagebox.showerror(APP_NAME, tr("Could not open the profile:\n{0}\n\n{1}", path, exc), parent=self)
            return False
        self.set_profile(profile, dirty=False, warnings=warnings)
        if not self._is_preset(path):
            self.remember_file(path)
        kind = tr("Preset") if self._is_preset(path) else tr("Profile")
        self.set_status(tr("{0} \"{1}\" opened", kind, profile.name) + (tr(" (changes are saved under a new name)") if self._is_preset(path) else ""))
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
            self.recent_menu.add_command(label=tr("(empty)"), state=tk.DISABLED)
            return
        for index, item in enumerate(self.settings.recent, start=1):
            self.recent_menu.add_command(label=f"{index}. {item}", command=lambda i=item: self.open_recent(i))

    def open_recent(self, item: str) -> bool:
        path = Settings.resolve(item, self.paths.root)
        if not path.exists():
            messagebox.showerror(APP_NAME, tr("File not found and removed from the recent list:\n{0}", path), parent=self)
            self.settings.forget(path, self.paths.root)
            self.settings.save(self.paths.settings_file)
            self._rebuild_recent_menu()
            return False
        if path.suffix.lower() == ".xml":
            return self.confirm_discard() and self.import_file(path)
        return self.load_profile_file(path)

    def open_profile_dialog(self) -> None:
        name = filedialog.askopenfilename(parent=self, title=tr("Open profile"), initialdir=str(self.paths.profiles),
                                          filetypes=[(tr("WinKickOff profile"), "*.json"), (tr("All files"), "*.*")])
        if name:
            self.load_profile_file(Path(name))

    def save_profile(self) -> bool:
        if self.profile.path is None or self._is_preset(self.profile.path):
            return self.save_profile_as()
        try:
            self.profile.save(self.profile.path, self.catalog)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Could not save the profile:\n{0}", exc), parent=self)
            return False
        self.dirty = False
        self.update_title()
        self.remember_file(self.profile.path)
        self.set_status(tr("Profile saved: {0}", self.profile.path))
        return True

    def save_profile_as(self) -> bool:
        suggested = re.sub(r'[\\/:*?"<>|]', "_", self.profile.name) or "profile"
        if self._is_preset(self.profile.path):
            suggested += tr(" (mine)")
        name = filedialog.asksaveasfilename(parent=self, title=tr("Save profile as"), initialdir=str(self.paths.profiles),
                                            initialfile=f"{suggested}.json", defaultextension=".json",
                                            filetypes=[(tr("WinKickOff profile"), "*.json")])
        if not name:
            return False
        path = Path(name)
        if path.name.startswith("preset-"):
            messagebox.showerror(APP_NAME, tr("The names preset-*.json are reserved for presets. Choose a different name."), parent=self)
            return False
        self.profile.name = path.stem
        try:
            self.profile.save(path, self.catalog)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Could not save the profile:\n{0}", exc), parent=self)
            return False
        self.dirty = False
        self.refresh_profile_choices()
        self.update_title()
        self.remember_file(path)
        self.set_status(tr("Profile saved: {0}", path))
        return True

    # ----------------------------------------------------------------- comparison

    def compare_with_file(self) -> None:
        name = filedialog.askopenfilename(parent=self, title=tr("Compare with profile"), initialdir=str(self.paths.profiles),
                                          filetypes=[(tr("WinKickOff profile"), "*.json"), (tr("All files"), "*.*")])
        if name:
            self.show_comparison(Path(name))

    def comparison_rows(self, other: Profile) -> list[tuple[str, str, str, str, str]]:
        """(tree node, kind, item, value here, value there) for every difference from other."""

        def state(value: Any) -> str:
            return "" if value is None else tr("enabled") if value else tr("disabled")

        install_titles = {"edition": tr("Edition"), "product_key_mode": tr("Key mode"), "product_key": tr("Product key"),
                          "time_zone": tr("Time zone")}
        language_titles = {"ui_language": tr("Display language"), "system_locale": tr("Language for non-Unicode programs"),
                           "user_locale": tr("Date and number format"), "input": tr("Input languages")}

        def text(value: Any) -> str:
            return ", ".join(str(v) for v in value) if isinstance(value, list) else "" if value is None else str(value)

        rows: list[tuple[str, str, str, str, str]] = []
        for d in self.profile.diff(other, self.catalog):
            if d.kind == "rule":
                title = self.rule_title(d.key) if d.key in self.catalog.rules else d.key
                rows.append(("r:" + d.key, tr("rule"), title, state(d.before), state(d.after)))
            elif d.kind == "param":
                rule_id, _, name = d.key.rpartition(".")
                rule = self.catalog.rules.get(rule_id)
                if rule is not None and name in rule.params:
                    param = rule.params[name]
                    rows.append(("r:" + rule_id, tr("parameter"), f"{self.rule_title(rule_id)}: {self.param_title(rule, param)}",
                                 self._param_display(rule, param, d.before), self._param_display(rule, param, d.after)))
                else:
                    rows.append(("", tr("parameter"), d.key, text(d.before), text(d.after)))
            elif d.kind == "install":
                rows.append(("data:install", tr("installation"), install_titles.get(d.key, d.key), text(d.before), text(d.after)))
            elif d.kind == "languages":
                rows.append(("data:languages", tr("languages"), language_titles.get(d.key, d.key), text(d.before), text(d.after)))
            else:
                rows.append(("data:accounts", tr("accounts"), tr("account list"), text(d.before), text(d.after)))
        return rows

    def show_comparison(self, path: Path) -> tk.Toplevel | None:
        try:
            other, _warnings = Profile.load(path, self.catalog)
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_NAME, tr("Could not open the profile:\n{0}\n\n{1}", path, exc), parent=self)
            return None
        rows = self.comparison_rows(other)
        window = tk.Toplevel(self)
        window.title(tr("Comparison: \"{0}\" and \"{1}\"", tr(self.profile.name), tr(other.name)))
        window.geometry("980x520")
        caption = tr("Differences: {0}. Double-click to go to the rule or data.", len(rows)) if rows else tr("The profiles are identical.")
        ttk.Label(window, text=caption, padding=(10, 8)).pack(anchor=tk.W)
        box = ttk.Frame(window, padding=(10, 0, 10, 0))
        box.pack(fill=tk.BOTH, expand=True)
        table = ttk.Treeview(box, columns=("kind", "item", "mine", "theirs"), show="headings")
        for column, title, width in (("kind", tr("Item"), 110), ("item", tr("Location"), 420),
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
        ttk.Button(window, text=tr("Close"), command=window.destroy).pack(anchor=tk.E, padx=10, pady=8)
        window.comparison_rows = rows  # type: ignore[attr-defined]
        return window

    def import_from_xml(self) -> None:
        if not self.confirm_discard():
            return
        name = filedialog.askopenfilename(parent=self, title=tr("Open profile from autounattend.xml"),
                                          filetypes=[(tr("Answer file"), "*.xml"), (tr("All files"), "*.*")])
        if name:
            self.import_file(Path(name))

    def import_file(self, path: Path) -> bool:
        """A WinKickOff build gives back its embedded profile; any other answer file of the same
        family (the hand-written v0.2) is imported by its actions, with a list of what is uncertain."""
        try:
            text = path.read_text(encoding="utf-8")
            profile, warnings = import_xml(text, self.catalog, self.resources.keyboards)
        except (OSError, UnicodeDecodeError, ImportFailed) as exc:
            messagebox.showerror(APP_NAME, tr("Could not restore the profile:\n{0}", exc), parent=self)
            return False
        by_actions = profile.name == IMPORTED_NAME
        if by_actions:
            profile.name = tr("Import {0}", path.stem)
        self.set_profile(profile, dirty=True, warnings=warnings)
        self.remember_file(path)
        how = tr("from the file's actions (uncertain items in the list below)") if by_actions else tr("from the embedded profile")
        self.set_status(tr("Profile \"{0}\" restored {1}; save it to use it again", profile.name, how))
        return True

    # ----------------------------------------------------------------- check and build

    def run_checks(self, *, with_powershell: bool) -> tuple[BuildResult | None, list[Issue]]:
        issues = validate_profile(self.profile, self.catalog, self.resources.keyboards)
        if has_errors(issues):
            return None, issues
        try:
            result = self.renderer.build(self.profile, app_version=APP_VERSION)
        except RenderError as exc:
            return None, issues + [Issue("error", "build", tr("Cannot build: {0}", exc))]
        issues += validate_xml(result.xml)
        if with_powershell and not has_errors(issues):
            issues += self._ps_issues(check_scripts(result.scripts, self.paths.logs / "tmp"))
        return result, issues

    @staticmethod
    def _ps_issues(ps: PsCheckResult) -> list[Issue]:
        if ps.skipped:
            return [Issue("info", "powershell", tr("PowerShell syntax check skipped: powershell.exe not found"))]
        if ps.failure:
            return [Issue("warning", "powershell", tr("PowerShell syntax check could not be run: {0}", ps.failure))]
        if ps.errors:
            return [Issue("error", "powershell", e) for e in ps.errors]
        return [Issue("info", "powershell", tr("Script syntax (Windows PowerShell 5.1): no errors"))]

    def check(self) -> list[Issue]:
        result, issues = self.run_checks(with_powershell=False)
        if result is not None:
            issues.append(Issue("info", "build", tr("The file can be built: {0} rules, scripts: {1}", len(result.rule_ids), ', '.join(result.scripts) or tr("no scripts"))))
        self.show_issues(issues)
        errors = sum(1 for i in issues if i.level == "error")
        warnings = sum(1 for i in issues if i.level == "warning")
        self.set_status(tr("Check: {0} errors, {1} warnings", errors, warnings) + (tr("; ready to build (F9)") if not errors else ""))
        return issues

    def check_catalog(self) -> list[Issue]:
        """Re-read the rule files from disk and report defects (useful while editing the TOML)."""
        catalog, issues = validate_catalog(self.paths.rules, self.paths.docs_root)
        if catalog is not None:
            issues.append(Issue("info", "catalog", tr("Catalog {0} is readable: {1} rules, {2} groups. Changes to catalog files take effect after the program is restarted.", catalog.version, len(catalog.rules), len(catalog.groups))))
        self.show_issues(issues)
        errors = sum(1 for i in issues if i.level == "error")
        warnings = sum(1 for i in issues if i.level == "warning")
        self.set_status(tr("Catalog check: {0} errors, {1} warnings", errors, warnings))
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
        self.set_busy(True, tr("Checking PowerShell syntax..."))
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(100, poll)
                return
            self.set_busy(False)
            if "error" in outcome:
                extra = [Issue("warning", "powershell", tr("PowerShell syntax check could not be run: {0}", outcome['error']))]
            else:
                extra = self._ps_issues(outcome["ps"])
            self._finish_build(result, issues + extra)

        self.after(100, poll)

    def _finish_build(self, result: BuildResult | None, issues: list[Issue]) -> None:
        self.show_issues(issues)
        if result is None or has_errors(issues):
            count = sum(1 for i in issues if i.level == "error")
            self.set_status(tr("Build stopped: {0} errors", count))
            messagebox.showerror(APP_NAME, tr("Build stopped: {0} errors. See the list at the bottom of the window; double-click an item to go to the error.", count), parent=self)
            return
        initial_dir = self._last_output.parent if self._last_output else self.paths.output
        name = filedialog.asksaveasfilename(parent=self, title=tr("Save answer file"), initialdir=str(initial_dir),
                                            initialfile="autounattend.xml", defaultextension=".xml",
                                            filetypes=[(tr("Windows answer file"), "*.xml")])
        if not name:
            self.set_status(tr("Build complete but not saved"))
            return
        path = Path(name)
        try:
            self.write_build(result, path)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Could not write the file:\n{0}", exc), parent=self)
            return
        note = "" if path.name.lower() == "autounattend.xml" else tr("\n\nWarning: Windows Setup looks only for a file named autounattend.xml.")
        self.show_issues(issues + [Issue("info", "build", tr("Saved: {0} ({1} rules)", path, len(result.rule_ids)))])
        self.set_status(tr("Built: {0}", path))
        if messagebox.askyesno(
            APP_NAME,
            tr("File saved:\n{0}\n\nRules enabled: {1}.\nCopy it to the root of a USB drive with the Windows 11 installation image and boot the PC from it.{2}\n\nOpen the folder containing the file?", path, len(result.rule_ids), note),
            parent=self,
        ):
            self._open_folder(path.parent)

    # ----------------------------------------------------------------- this PC (task T15)

    def _fill_pc_menu(self, menu: tk.Menu) -> None:
        # Always available: the first apply or return asks for permission (toggle_allow_apply) instead of a
        # greyed-out item whose switch is hard to find.
        menu.add_command(label=tr("Check the selection on this PC"), command=self.audit_selected)
        menu.add_command(label=tr("Save an apply script for the selection..."), command=self.save_apply_scripts)
        menu.add_command(label=tr("Apply the selection now..."), command=self.apply_now)
        menu.add_command(label=tr("Return the selection to Windows defaults now..."), command=self.revert_now)

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
                "Allow applying rules to this computer?\n\nThe apply script changes the registry, services "
                "and Windows components. Test it on a test computer or a virtual machine first. App "
                "removal and PowerShell steps cannot be rolled back automatically. Applying always starts "
                "through a User Account Control prompt."),
                icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            self.allow_apply_var.set(False)
            wanted = False
        self.settings.allow_apply = wanted
        self.settings.save(self.paths.settings_file)

    def _ensure_apply_allowed(self) -> bool:
        """Changes to this PC need the permission of "This PC, Allow applying on this PC"; ask for it once."""
        if self.settings.allow_apply:
            return True
        self.allow_apply_var.set(True)
        self.toggle_allow_apply()
        return self.settings.allow_apply

    def _apply_items(self) -> list[str]:
        items = [i for i in self.tree.selection() if i.startswith("r:") or i.startswith("g:")]
        if not items:
            messagebox.showinfo(APP_NAME, tr("Select a rule or a group in the tree."), parent=self)
        return items

    def _plan_issues(self, plan: ApplyPlan) -> list[Issue]:
        issues = [Issue("info", rule.id, tr("not applied: {0}", tr(reason))) for rule, reason in plan.excluded]
        for planned in plan.rules:
            notes = []
            if planned.requirement:
                notes.append(tr("needed by a selected rule"))
            if planned.irreversible:
                notes.append(tr("not rolled back automatically"))
            if planned.reboot:
                notes.append(tr("restart needed"))
            level = "warning" if planned.irreversible else "info"
            issues.append(Issue(level, planned.rule.id, tr("will be applied") + (": " + "; ".join(notes) if notes else "")))
        for returning in plan.reverts:
            notes = [tr("disabled in the profile")]
            if returning.dependent:
                notes.append(tr("depends on a selected rule"))
            if returning.skipped:
                notes.append(tr("not returned automatically: {0}", ", ".join(sorted({a.type for a in returning.skipped}))))
            if returning.reboot:
                notes.append(tr("restart needed"))
            level = "warning" if returning.skipped else "info"
            issues.append(Issue(level, returning.rule.id, tr("will be returned to Windows defaults") + ": " + "; ".join(notes)))
        return issues

    def _nothing_to_apply(self, plan: ApplyPlan) -> None:
        """Say plainly why nothing happens, instead of a line in the status bar only."""
        reasons = [f"{self.rule_title(rule.id)}: {tr(reason)}" for rule, reason in plan.excluded[:8]]
        more = tr("\n... and {0} more", len(plan.excluded) - 8) if len(plan.excluded) > 8 else ""
        messagebox.showinfo(APP_NAME, tr("There is nothing in the selection to apply to this computer.") + "\n\n"
                            + "\n".join(reasons) + more, parent=self)
        self.set_status(tr("The selection has no rules that can be applied to a running system"))

    def audit_selected(self) -> None:
        """Read-only check on this PC: which of the selected rules already take effect."""
        if self._busy:
            return
        items = self._apply_items()
        if not items:
            return
        rule_ids, skipped = audit_rules(self.catalog, items)
        excluded = [Issue("info", rule.id, tr("not checked: {0}", tr(reason))) for rule, reason in skipped]
        if not rule_ids:
            self.show_issues(excluded)
            self.set_status(tr("The selection has no rules that can be checked on a running system"))
            return
        script = render_audit(rule_ids, self.profile, self.catalog, self.paths.templates, APP_VERSION)
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["text"] = run_audit(script, self.paths.logs / "tmp")
            except Exception as exc:  # noqa: BLE001 - shown to the user
                outcome["error"] = exc

        thread = threading.Thread(target=work, name="audit", daemon=True)
        self.set_busy(True, tr("Checking this PC (read-only)..."))
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                self.after(150, poll)
                return
            self.set_busy(False)
            if "error" in outcome:
                self.show_issues([Issue("error", "audit", tr("The check failed: {0}", outcome["error"]))] + excluded)
                self.set_status(tr("The check on this PC failed"))
                return
            self.show_audit(outcome["text"], excluded)

        self.after(150, poll)

    def show_audit(self, report_text: str, excluded: list[Issue]) -> None:
        meta, results = parse_audit_report(report_text)
        issues: list[Issue] = []
        counts = {"applied": 0, "not-applied": 0, "partial": 0, "unknown": 0}
        for rule_id, result in results.items():
            counts[result.status] = counts.get(result.status, 0) + 1
            details = [f"{c['check']}: {c['current'] or tr("no value")} ({tr("expected")} {c['expected']})"
                       for c in result.checks if c["status"] == "differs"][:3]
            level = "info" if result.status in ("applied", "unknown") else "warning"
            issues.append(Issue(level, rule_id, status_title(result.status) + (": " + "; ".join(details) if details else "")))
        self.show_issues(issues + excluded)
        note = "" if str(meta.get("admin")).lower() == "true" else tr(" Without administrator rights some checks are unavailable.")
        self.set_status(tr("Check on this PC: in effect {0}, not in effect {1}, partly {2}, not checked {3}.",
                           counts["applied"], counts["not-applied"], counts["partial"], counts["unknown"]) + note)

    def _write_apply_folder(self, folder: Path, plan: ApplyPlan) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        apply_path = folder / "Apply.ps1"
        write_script(apply_path, render_apply(plan, self.profile, self.catalog, self.paths.templates, APP_VERSION))
        write_script(folder / "Undo-Apply.ps1", render_undo(self.paths.templates, self.profile, APP_VERSION))
        lines = [tr("WinKickOff {0} apply scripts, profile \"{1}\".", APP_VERSION, tr(self.profile.name)), "",
                 tr("1. Test on a test computer or a virtual machine first."),
                 tr("2. Run Apply.ps1 as administrator: powershell -ExecutionPolicy Bypass -File Apply.ps1"),
                 tr("3. The log and the backup of the previous values appear next to the script (apply-*.log, backup-*.json)."),
                 tr("4. Rollback: Undo-Apply.ps1 as administrator. Removed apps and PowerShell steps are not rolled back."),
                 tr("5. Restart the computer after applying."), "", tr("Rules:")]
        for planned in plan.rules:
            flags = (tr(" (not rolled back)") if planned.irreversible else "") + (tr(" (restart needed)") if planned.reboot else "")
            lines.append(f"- {planned.rule.id}: {self.rule_title(planned.rule.id)}{flags}")
        if plan.reverts:
            lines += ["", tr("Off in the profile, returning to the Windows defaults:")]
            for returning in plan.reverts:
                lines.append(f"- {returning.rule.id}: {self.rule_title(returning.rule.id)}" + (tr(" (partly)") if returning.skipped else ""))
        if plan.excluded:
            lines += ["", tr("Not applied:")]
            lines += [f"- {rule.id}: {tr(reason)}" for rule, reason in plan.excluded]
        (folder / "README.txt").write_bytes(("\n".join(lines) + "\n").replace("\n", "\r\n").encode("utf-8-sig"))
        return apply_path

    def save_apply_scripts(self) -> Path | None:
        items = self._apply_items()
        if not items:
            return None
        plan = plan_apply(self.catalog, self.profile, items)
        self.show_issues(self._plan_issues(plan))
        if plan.empty:
            self._nothing_to_apply(plan)
            return None
        name = filedialog.askdirectory(parent=self, title=tr("Folder for the apply scripts"), initialdir=str(self.paths.output))
        if not name:
            return None
        folder = Path(name) / time.strftime("apply-%Y%m%d-%H%M%S")
        try:
            self._write_apply_folder(folder, plan)
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("The scripts were not written:\n{0}", exc), parent=self)
            return None
        self.set_status(tr("Apply scripts saved: {0} (rules: {1})", folder, len(plan.rules) + len(plan.reverts)))
        return folder

    def apply_now(self) -> bool:
        """Apply the selection to this PC: confirmation, scripts in logs/, launch through UAC."""
        items = self._apply_items()
        if not items or not self._ensure_apply_allowed():
            return False
        plan = plan_apply(self.catalog, self.profile, items)
        self.show_issues(self._plan_issues(plan))
        if plan.empty:
            self._nothing_to_apply(plan)
            return False
        irreversible = [self.rule_title(p.rule.id) for p in plan.rules if p.irreversible]
        text = tr("Apply the selected rules ({1}) to computer {0}?", os.environ.get("COMPUTERNAME", "?"), len(plan.rules) + len(plan.reverts))
        if plan.reverts:
            text += "\n\n" + tr("On in the profile and applied: {0}. Off in the profile and returned to the Windows defaults: {1}.",
                                len(plan.rules), len(plan.reverts))
        if irreversible:
            text += "\n\n" + tr("Not rolled back automatically: {0}.", "; ".join(irreversible[:8]) + ("..." if len(irreversible) > 8 else ""))
        if any(p.reboot for p in plan.rules) or any(p.reboot for p in plan.reverts):
            text += "\n\n" + tr("A restart is needed after applying.")
        text += "\n\n" + tr("Windows will ask to confirm administrator rights. The previous values are saved for rollback (Undo-Apply.ps1).")
        if not messagebox.askyesno(APP_NAME, text, icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            return False
        folder = self.paths.logs / time.strftime("apply-%Y%m%d-%H%M%S")
        try:
            script = self._write_apply_folder(folder, plan)
            apply_module.launch_elevated(script)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror(APP_NAME, tr("Applying was not started:\n{0}", exc), parent=self)
            return False
        self.set_status(tr("The apply script was started; log and backup: {0}", folder))
        return True

    def _revert_issues(self, plan: RevertPlan) -> list[Issue]:
        issues = [Issue("info", rule.id, tr("not returned: {0}", tr(reason))) for rule, reason in plan.excluded]
        for planned in plan.rules:
            notes = []
            if planned.dependent:
                notes.append(tr("depends on a selected rule"))
            if planned.skipped:
                notes.append(tr("not returned automatically: {0}", ", ".join(sorted({a.type for a in planned.skipped}))))
            if planned.reboot:
                notes.append(tr("restart needed"))
            level = "warning" if planned.skipped else "info"
            issues.append(Issue(level, planned.rule.id, tr("will be returned to Windows defaults") + (": " + "; ".join(notes) if notes else "")))
        return issues

    def _write_revert_folder(self, folder: Path, plan: RevertPlan) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        script_path = folder / "Apply.ps1"
        write_script(script_path, render_revert(plan, self.profile, self.paths.templates, APP_VERSION))
        write_script(folder / "Undo-Apply.ps1", render_undo(self.paths.templates, self.profile, APP_VERSION))
        lines = [tr("Return to Windows defaults, WinKickOff {0}.", APP_VERSION), "",
                 tr("1. Test on a test computer or a virtual machine first."),
                 tr("2. Run Apply.ps1 as administrator: powershell -ExecutionPolicy Bypass -File Apply.ps1"),
                 tr("3. The log and the backup of the previous values appear next to the script (apply-*.log, backup-*.json)."),
                 tr("4. To undo the return: Undo-Apply.ps1 as administrator."),
                 tr("5. Restart the computer after applying."), "", tr("Rules:")]
        for planned in plan.rules:
            flags = tr(" (partly)") if planned.skipped else ""
            lines.append(f"- {planned.rule.id}: {self.rule_title(planned.rule.id)}{flags}")
        if plan.excluded:
            lines += ["", tr("Not returned:")]
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
            self.set_status(tr("The selection has no rules that can be returned to Windows defaults on a running system"))
            return False
        partial = [self.rule_title(p.rule.id) for p in plan.rules if p.skipped]
        text = tr("Return the selected rules ({1}) on computer {0} to Windows defaults?",
                  os.environ.get("COMPUTERNAME", "?"), len(plan.rules))
        dependents = [self.rule_title(p.rule.id) for p in plan.rules if p.dependent]
        if dependents:
            text += "\n\n" + tr("Together with them: {0}.", "; ".join(dependents[:8]) + ("..." if len(dependents) > 8 else ""))
        if partial:
            text += "\n\n" + tr("Not returned completely (apps, scripts, values with an unknown default): {0}.",
                                "; ".join(partial[:8]) + ("..." if len(partial) > 8 else ""))
        text += "\n\n" + tr("Windows will ask to confirm administrator rights. The previous values are saved for rollback (Undo-Apply.ps1).")
        if not messagebox.askyesno(APP_NAME, text, icon=messagebox.WARNING, default=messagebox.NO, parent=self):
            return False
        folder = self.paths.logs / time.strftime("revert-%Y%m%d-%H%M%S")
        try:
            script = self._write_revert_folder(folder, plan)
            apply_module.launch_elevated(script)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror(APP_NAME, tr("The return was not started:\n{0}", exc), parent=self)
            return False
        self.set_status(tr("The return-to-defaults script is running; log and backup: {0}", folder))
        return True

    def open_output_folder(self) -> None:
        self._open_folder(self._last_output.parent if self._last_output else self.paths.output)

    def _open_folder(self, folder: Path) -> None:
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("Could not open the folder:\n{0}", exc), parent=self)

    # ----------------------------------------------------------------- misc

    def about(self) -> None:
        self.select_node(WORKFLOW_NODE)
        self._write_detail(
            [
                ("h1", f"{APP_NAME} {APP_VERSION}"),
                ("", tr("Rule catalog: version {0}, {1} rules.", self.catalog.version, len(self.catalog.rules))),
                ("", tr("Program folder: {0}", self.paths.root)),
                ("", tr("Profiles: {0}", self.paths.profiles)),
                ("", tr("Default location for built files: {0}", self.paths.output)),
                ("", tr("Program settings: {0}", self.paths.settings_file)),
                ("", tr("Runtime templates: {0}", self.paths.templates)),
                ("h2", tr("Documentation")),
                ("link:doc:" + user_docs(self.paths.docs_root), tr("User documentation: ") + user_docs(self.paths.docs_root)),
                ("link:doc:docs/technical/reference/README.md", tr("Technical parameter reference (in English): docs/technical/reference/README.md")),
                ("muted", tr("Editor specification and plan: docs/technical/editor/ in the project repository.")),
            ]
        )

    def change_language(self, code: str) -> None:
        """Save the choice and rebuild the window in the new language; the open profile, its unsaved
        changes and the selected node survive (app.run creates the new window from restart_state)."""
        if code == self.settings.language:
            return
        self.settings.language = code
        self.save_settings()
        self.restart_state = {"profile": self.profile, "dirty": self.dirty, "item": self._current_item}
        self.destroy()

    def change_theme(self, theme_id: str) -> None:
        """Save the choice and rebuild the window in the new colours, like a language change."""
        if theme_id == self.settings.theme:
            return
        self.settings.theme = theme_id
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

    def destroy(self) -> None:
        margins = getattr(self, "menu_margins", None)
        if margins is not None:
            margins.stop()  # the hook of this window ends with it (a language or theme change builds a new window)
        super().destroy()

    def save_settings(self) -> None:
        if self.state() == "normal":
            self.settings.geometry = self.geometry()
        path = self.profile.path
        self.settings.last_profile = display_path(path, self.paths.root) if path is not None else ""
        self.settings.save(self.paths.settings_file)
