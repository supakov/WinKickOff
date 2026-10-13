"""Main window of WinKickOff.

Layout: profile toolbar at the top; rule tree with check boxes and search on the left; description,
parameters or data form of the selected node on the right; messages (checks, build, automatic
changes) at the bottom; status line.

Mouse: a click on the check box toggles a rule or a whole group (dependent rules follow
automatically); a click on the expand indicator only opens the branch; a click on the text selects.
Keyboard: Space toggles, Ctrl+F search, Ctrl+S save, Ctrl+O open, F7 check, F9 build.
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter import font as tkfont
from typing import Any

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.catalog import Catalog, Param, Rule, is_imported
from winkickoff.core import admx as admx_module
from winkickoff.core import linked
from winkickoff.core import package as package_module
from winkickoff.core.deps import Change, Resolver
from winkickoff.core.i18n import SOURCE_LANGUAGE, available_languages, catalog_texts, language, tr
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.render import Renderer
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings
from winkickoff.mcp.service import McpService
from winkickoff.core.themes import Theme, available_themes, resolve_theme
from winkickoff.core.validate import Issue
from winkickoff.ui.checkimages import make_check_images
from winkickoff.ui.data_forms import AccountsForm, InstallForm, LanguagesForm
from winkickoff.ui.mcp_workspace import WindowWorkspace, install_pump
from winkickoff.ui.winmenus import MenuMargins, colorref
from winkickoff.ui.window_admx import AdmxActions
from winkickoff.ui.window_detail import DetailPanel
from winkickoff.ui.window_mcp import McpActions
from winkickoff.ui.window_profiles import ProfileActions
from winkickoff.ui.window_thispc import ThisPcActions
from winkickoff.ui.window_common import (
    WORKFLOW_NODE,
    MODE_TITLES,
    DATA_NODES,
    ISSUE_TITLES,
    UNKNOWN_NODE,
    UNKNOWN_PREFIX,
    UNKNOWN_TITLE,
    VK_F,
    VK_O,
    VK_S,
    rule_of,
    user_docs,
    _profile_name,
)


class MainWindow(DetailPanel, ProfileActions, ThisPcActions, AdmxActions, McpActions, tk.Tk):
    MODE_TITLES = MODE_TITLES

    def __init__(self, paths: AppPaths, catalog: Catalog, profile: Profile, resources: Resources,
                 settings: Settings | None = None, service: McpService | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.service = service  # the MCP service of the process; None makes the window inert for MCP (tests)
        self._modal = 0  # open dialogs (native ones set no Tk grab); the MCP bridge refuses writes meanwhile
        self._files_confirmed = False
        self.mcp_pump_id: str | None = None
        self._draft_text: str | None = None  # the content of the last draft written (core/draft.py)
        self._draft_job: str | None = None
        self.mcp_monitor: Any = None
        self.last_load_warnings: list[str] = []
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
        self._param_boxes: dict[str, tk.Text] = {}  # the text boxes of list parameters, by parameter name
        self._choices: list[tuple[str, Path]] = []
        self._last_output: Path | None = None
        self._issues: list[Issue] = []
        self._current_item = WORKFLOW_NODE
        self._history: list[str] = []  # nodes left by links, messages and clicks (Back)
        # imported policies that share a value with a built-in rule, and those an enabled built-in rule sets now
        self._overlapping = [rid for rid in catalog.rules if is_imported(rid) and catalog.same_values(rid)]
        self._covered: set[str] = set()
        self._future: list[str] = []  # nodes left by Back (Forward)
        self._saved_imports: list[admx_module.ImportInfo] | None = None  # read when an unknown policy is shown
        self._import_ids: dict[str, set[str]] = {}  # policy ids of the saved imports read so far
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
        if service is not None:
            service.attach(WindowWorkspace(self))
            install_pump(self, service.bridge)
        self.refresh_mcp_status()

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
        file_menu.add_command(label=tr("Changes since the last save..."), command=self.show_changes)
        file_menu.add_command(label=tr("Merge a diff profile..."), command=self.merge_diff_dialog)
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
        self.pc_menu.add_command(label=tr("Read the settings of this PC into a new profile..."), command=self.read_this_pc)
        self.pc_menu.add_command(label=tr("Read the settings of this PC as administrator into a new profile..."),
                                 command=lambda: self.read_this_pc(elevated=True))
        self.pc_menu.add_separator()
        self.allow_apply_var = tk.BooleanVar(value=self.settings.allow_apply)
        self.pc_menu.add_checkbutton(label=tr("Allow applying on this PC"), variable=self.allow_apply_var,
                                     command=self.toggle_allow_apply)
        self.tree_menu = tk.Menu(self, tearoff=False)
        self._fill_pc_menu(self.tree_menu)
        self._build_admx_menu(self._top_menu("ADMX"))
        self._build_mcp_menu(self._top_menu("MCP"))
        help_menu = self._top_menu(tr("Help"))
        help_menu.add_command(label=tr("Workflow"), command=lambda: self.select_node(WORKFLOW_NODE))
        help_menu.add_command(label=tr("User documentation"), command=lambda: self.open_doc(user_docs(self.paths.docs_root)))
        help_menu.add_command(label=tr("About"), command=self.about)
        if isinstance(self.menu_bar, tk.Menu):
            self.config(menu=self.menu_bar)

    def _build_admx_menu(self, menu: tk.Menu) -> None:
        """Imported policy templates (core/admx.py) and catalog files (core/package.py): import, show or hide the saved
        imports, export, rename and delete them."""
        menu.add_command(label=tr("Import the templates of this Windows"), command=lambda: self.import_templates(True))
        menu.add_command(label=tr("Import templates from a folder..."), command=lambda: self.import_templates(False))
        menu.add_command(label=tr("Import a catalog file..."), command=lambda: self.import_catalog_file())
        bundled = package_module.bundled_catalogs(self.paths.catalogs)
        shipped = tk.Menu(menu, tearoff=False)
        for catalog in bundled:
            shipped.add_command(label=catalog.label, command=lambda c=catalog: self.import_bundled_catalog(c))
        menu.add_cascade(label=tr("Import a catalog of the program"), menu=shipped, state=tk.NORMAL if bundled else tk.DISABLED)
        menu.add_separator()
        imports = admx_module.list_imports(self.paths.admx)
        self.import_vars: dict[str, tk.BooleanVar] = {}
        for info in imports:
            var = tk.BooleanVar(value=info.id in self.settings.admx)
            self.import_vars[info.id] = var
            menu.add_checkbutton(label=tr("{0} ({1} policies)", info.name, info.policies), variable=var,
                                 command=lambda i=info.id: self.show_templates(i, self.import_vars[i].get()))
        if not imports:
            menu.add_command(label=tr("No imported templates yet"), state=tk.DISABLED)
        menu.add_separator()
        rename = tk.Menu(menu, tearoff=False)
        for info in imports:
            rename.add_command(label=info.name, command=lambda i=info.id, n=info.name: self.rename_templates(i, n))
        menu.add_cascade(label=tr("Rename imported templates"), menu=rename, state=tk.NORMAL if imports else tk.DISABLED)
        export = tk.Menu(menu, tearoff=False)
        for info in imports:
            export.add_command(label=info.name, command=lambda i=info.id, n=info.name: self.export_templates(i, n))
        menu.add_cascade(label=tr("Export imported templates"), menu=export, state=tk.NORMAL if imports else tk.DISABLED)
        delete = tk.Menu(menu, tearoff=False)
        for info in imports:
            delete.add_command(label=info.name, command=lambda i=info.id, n=info.name: self.delete_templates(i, n))
        menu.add_cascade(label=tr("Delete imported templates"), menu=delete, state=tk.NORMAL if imports else tk.DISABLED)

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
        status_bar = ttk.Frame(self)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.mcp_status_var = tk.StringVar(value=tr("MCP: off"))
        mcp_label = ttk.Label(status_bar, textvariable=self.mcp_status_var, anchor=tk.E, padding=(8, 3), style="Note.TLabel")
        mcp_label.pack(side=tk.RIGHT)
        mcp_label.bind("<Double-Button-1>", lambda _e: self.open_mcp_monitor())
        ttk.Label(status_bar, textvariable=self.status_var, anchor=tk.W, padding=(8, 3)).pack(side=tk.LEFT, fill=tk.X, expand=True)

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
        self.tree.tag_configure("linked", foreground=self.color("link"))
        self.tree.tag_configure("unknown", foreground=self.color("warning"))
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-Button-1>", self._on_tree_double)
        self.tree.bind("<space>", self._on_space)
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self._open_groups.add(self.tree.focus()))
        self.tree.bind("<<TreeviewClose>>", lambda _e: self._open_groups.discard(self.tree.focus()))

        self.right = ttk.Frame(horizontal, padding=(3, 2, 8, 0))
        horizontal.add(self.right, weight=3)
        nav = ttk.Frame(self.right)
        nav.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        self.back_button = ttk.Button(nav, text=chr(0x2190) + " " + tr("Back"), command=self.go_back)
        self.back_button.pack(side=tk.LEFT)
        self.forward_button = ttk.Button(nav, text=tr("Forward") + " " + chr(0x2192), command=self.go_forward)
        self.forward_button.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(nav, text=tr("Alt+Left, Alt+Right"), style="Note.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        self.back_button.state(["disabled"])
        self.forward_button.state(["disabled"])
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
        self.detail.tag_configure("changed", foreground=self.color("changed"))
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
        self.bind("<Alt-Left>", lambda _e: (self.go_back(), "break")[1])
        self.bind("<Alt-Right>", lambda _e: (self.go_forward(), "break")[1])
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
        """Build the tree from the catalog. With visible, only those rules (and their groups) are shown, expanded;
        it may also name ids of the profile's unknown choices."""
        self._update_covered()
        self.tree.delete(*self.tree.get_children(""))
        if visible is None:
            self.tree.insert("", tk.END, iid=WORKFLOW_NODE, text="  " + tr("Workflow"), tags=("info",))
            for iid, title in DATA_NODES:
                self.tree.insert("", tk.END, iid=iid, text="  " + tr(title))
        self._insert_groups("", None, visible)
        self._insert_unknown(visible)

    def _insert_unknown(self, visible: set[str] | None) -> None:
        """The last root lists the choices the profile keeps for rules the loaded catalog does not have, such as
        policies of imported templates that are not loaded; it exists only while there are any."""
        entries = [entry for entry in self.profile.unknown_entries() if visible is None or entry[0] in visible]
        if not entries:
            return
        is_open = visible is not None or UNKNOWN_NODE in self._open_groups
        self.tree.insert("", tk.END, iid=UNKNOWN_NODE, text=self._unknown_text(), tags=("unknown",), open=is_open)
        for rule_id, enabled, _params in entries:
            self.tree.insert(UNKNOWN_NODE, tk.END, iid=UNKNOWN_PREFIX + rule_id, text=" " + rule_id,
                             image=self.images["on" if enabled else "off"], tags=() if enabled else ("off",))

    def _unknown_text(self) -> str:
        entries = self.profile.unknown_entries()
        return "  " + tr("{0}   {1} of {2}", tr(UNKNOWN_TITLE), sum(1 for entry in entries if entry[1]), len(entries))

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
                    iid = "r:" + rule.id if rule.group == group.id else f"r:{rule.id}@{group.id}"
                    self.tree.insert(item, tk.END, iid=iid, text=" " + self.rule_title(rule.id), image=self._rule_image(rule), tags=self._rule_tags(rule))

    def _update_covered(self) -> None:
        self._covered = {rid for rid in self._overlapping if linked.covering(self.catalog, self.profile, rid) is not None}

    def _rule_on(self, rule: Rule) -> bool:
        """On in the profile, or an imported policy that an enabled built-in rule sets (core/linked.py)."""
        return self.profile.is_enabled(rule.id) or rule.id in self._covered

    def _rule_image(self, rule: Rule) -> tk.PhotoImage:
        return self.images["on" if self._rule_on(rule) else "off"]

    def _rule_tags(self, rule: Rule) -> tuple[str, ...]:
        tags: list[str] = []
        enabled = self.profile.is_enabled(rule.id)
        if rule.id in self._covered and not enabled:
            tags.append("linked")  # the check mark comes from a built-in rule
        elif not enabled:
            tags.append("off")
        if rule.level == "risky":
            tags.append("risky")
        if enabled != rule.default or self.profile.rules[rule.id].params:
            tags.append("changed")  # differs from the catalog default: state or a parameter
        return tuple(tags)

    def _group_counts(self, group_id: str) -> tuple[int, int]:
        rules = self.catalog.rules_in_group(group_id)
        return sum(1 for r in rules if self._rule_on(r)), len(rules)

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
        self._update_covered()
        for item in self._all_items():
            if item.startswith("r:"):
                rule = self.catalog.rules[rule_of(item)]
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
        if "indicator" not in element:  # the "+" only opens the branch; anything else shows the node
            self._remember(item)
        if "image" in element and item.startswith(("r:", "g:", UNKNOWN_PREFIX)):
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
        if "image" in element and item.startswith(("r:", "g:", UNKNOWN_PREFIX)):
            self.toggle_item(item)
            return "break"
        if item.startswith(("r:", UNKNOWN_PREFIX)) and "indicator" not in element:
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
            rule_id = rule_of(item)
            follow = self._toggle_linked(rule_id)
            if follow is not None:  # the check mark belongs to a built-in rule
                changes, scope = follow, {c.rule_id for c in follow if c.reason == "user"}
            else:
                changes = self.resolver.set_rule(self.profile, rule_id, not self.profile.is_enabled(rule_id))
                scope = {rule_id}
        elif item.startswith("g:"):
            on, total = self._group_counts(item[2:])
            if is_imported(item[2:]) and not any(self.profile.is_enabled(r.id) for r in self.catalog.rules_in_group(item[2:])):
                # thousands of policies, some in pairs that exclude each other: never switch them on all at once
                self.set_status(tr("Imported policies are switched on one by one; the check box of their group only switches them off"))
                return []
            changes = self.resolver.set_group(self.profile, item[2:], on != total and not is_imported(item[2:]))
            scope = {r.id for r in self.catalog.rules_in_group(item[2:])}
        elif item.startswith(UNKNOWN_PREFIX):
            self.set_status(tr("An unknown choice is kept in the profile as it is; it can be changed when its rule is loaded again"))
            return []
        else:
            return []
        changes = changes + self._drop_redundant()
        self._apply_changes(changes, scope)
        if self._current_item == item or item.startswith("r:"):
            self.show_item(item)
        return changes

    def _toggle_linked(self, rule_id: str) -> list[Change] | None:
        """An imported policy linked to a built-in rule: its check mark switches that rule; None when it has its own."""
        found = linked.link(self.catalog, self.profile, rule_id)
        if found is None or self.profile.is_enabled(rule_id):
            return None
        if self.profile.is_enabled(found.rule):  # shown as on because of the built-in rule: switch that rule off
            if not found.equal and not self._dialog(messagebox.askyesno, APP_NAME, tr(
                    "This policy is set by the built-in rule \"{0}\", which also sets other values. Switch the built-in rule off?",
                    self.rule_title(found.rule)), parent=self):
                return []
            return self.resolver.set_rule(self.profile, found.rule, False)
        if found.equal:  # the same setting: the reviewed built-in rule is used instead
            return self.resolver.set_rule(self.profile, found.rule, True)
        return None

    def _drop_redundant(self) -> list[Change]:
        """Switch off imported policies that an enabled built-in rule now writes anyway (no value written twice)."""
        dropped = []
        for rule_id, other in linked.redundant(self.catalog, self.profile):
            self.profile.rules[rule_id].enabled = False
            dropped.append(Change(rule_id, False, "covered by " + other))
        return dropped

    def _reason_text(self, change: Change) -> str:
        reason = change.reason
        for prefix, template in (
            ("requires ", tr("requires \"{}\", which is disabled")),
            ("required by ", tr("needed by \"{}\"")),
            ("conflicts with ", tr("conflicts with \"{}\"")),
            ("covered by ", tr("set by the built-in rule \"{}\"")),
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
        self._cancel_search()
        self._search_job = self.after(150, self.apply_search)

    def _cancel_search(self) -> None:
        """Drop the delayed search: a direct search replaces it, and a closed window must not leave it to Tcl."""
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except tk.TclError:
                pass
            self._search_job = None

    def apply_search(self) -> None:
        self._cancel_search()
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
        words = query.lower().split()  # unknown choices have only their ids to search in
        found |= {rule_id for rule_id, _, _ in self.profile.unknown_entries() if all(w in rule_id.lower() for w in words)}
        self.rebuild_tree(found)
        self.set_status(tr("Rules found: {0}", len(found)) if found else tr("Nothing found"))

    def clear_search(self) -> None:
        self._cancel_search()
        self._suppress_search = True
        self.search_var.set("")
        self._suppress_search = False
        self.apply_search()

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
        item = ""
        if target in self.catalog.rules:
            item = "r:" + target
        elif target.startswith("accounts"):
            item = "data:accounts"
        elif target.startswith("languages"):
            item = "data:languages"
        elif target.startswith("install"):
            item = "data:install"
        if item:
            self._remember(item)
            self.select_node(item)

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
        if self._busy:  # a rebuild would drop the work of the background thread
            self.language_var.set(self.settings.language)
            return
        if code == self.settings.language:
            return
        self.settings.language = code
        self.save_settings()
        self.restart_state = {"profile": self.profile, "dirty": self.dirty, "item": self._current_item}
        self.destroy()

    def change_theme(self, theme_id: str) -> None:
        """Save the choice and rebuild the window in the new colours, like a language change."""
        if self._busy:
            self.theme_var.set(self.settings.theme)
            return
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
        if state.get("issues"):
            self.show_issues(list(state["issues"]))
        if state.get("status"):
            self.set_status(str(state["status"]))

    def show_problems(self, problems: list[str]) -> None:
        """Problems found while the window was prepared (imported templates that were not loaded)."""
        self.show_issues([Issue("warning", "", problem) for problem in problems])
        self.set_status(problems[0])

    def on_close(self) -> None:
        """Unsaved changes go to the draft, which the next start opens again, so closing asks nothing; only when the
        draft cannot be written the question "Save changes?" stays."""
        if self.dirty and not self.write_draft() and not self.confirm_discard():
            return
        self.save_settings()
        self.destroy()

    def destroy(self) -> None:
        margins = getattr(self, "menu_margins", None)
        if margins is not None:
            margins.stop()  # the hook of this window ends with it (a language or theme change builds a new window)
        if self._draft_job is not None:
            try:
                self.after_cancel(self._draft_job)
            except tk.TclError:
                pass
            self._draft_job = None
        if self.mcp_pump_id is not None:
            try:
                self.after_cancel(self.mcp_pump_id)
            except tk.TclError:
                pass
            self.mcp_pump_id = None
        if getattr(self, "_search_job", None) is not None:
            self._cancel_search()  # a search typed just before a restart or close
        self._close_busy_window()  # a window closed during a long operation (tests, a restart)
        if self.service is not None:
            self.service.detach()  # queued calls wait for the next window or time out
        super().destroy()
