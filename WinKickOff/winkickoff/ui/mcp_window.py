"""The MCP monitor: state and controls of the server, the request journal, the client configuration.

One instance per main window, hidden on close so the filters survive. It refreshes from the journal on an after()
timer; server threads never call into it. No request body, header or token is ever drawn in clear text.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from winkickoff.core.i18n import N_, tr
from winkickoff.mcp import MODES
from winkickoff.mcp.journal import Entry

if TYPE_CHECKING:
    from winkickoff.ui.main_window import MainWindow

REFRESH_MS = 250
COLUMNS = ("time", "transport", "client", "method", "tool", "arguments", "ms", "result")
COLUMN_TITLES = {"time": N_("Time"), "transport": N_("Transport"), "client": N_("Client"), "method": N_("Method"),
                 "tool": N_("Tool"), "arguments": N_("Arguments"), "ms": N_("ms"), "result": N_("Result")}


def masked(token: str) -> str:
    return f"{token[:4]}...{token[-4:]}" if len(token) >= 12 else ("(none)" if not token else "*" * len(token))


class McpMonitor(tk.Toplevel):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.window = window
        self.service = window.service
        self.title(tr("MCP server monitor"))
        self.transient(window)
        self.geometry("980x560")
        self.configure(background=window.color("background") or self.cget("background"))
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self._seen_seq = 0
        self._rows: list[Entry] = []
        self._after_id: str | None = None
        self._build()
        self.refresh_state()
        self._schedule()

    # ----------------------------------------------------------------- layout

    def _build(self) -> None:
        pad = {"padx": 6, "pady": 4}
        top = ttk.Frame(self, padding=(8, 8, 8, 2))
        top.pack(fill=tk.X)
        self.state_var = tk.StringVar()
        ttk.Label(top, textvariable=self.state_var).pack(side=tk.LEFT)
        self.start_button = ttk.Button(top, text=tr("Start"), command=self.toggle)
        self.start_button.pack(side=tk.RIGHT, **pad)

        row = ttk.Frame(self, padding=(8, 2))
        row.pack(fill=tk.X)
        ttk.Label(row, text=tr("Port (0 = any free port):")).pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value=str(self.window.settings.mcp_port))
        self.port_box = ttk.Spinbox(row, textvariable=self.port_var, from_=0, to=65535, width=8, command=self.port_changed)
        self.port_box.pack(side=tk.LEFT, padx=(4, 12))
        self.port_box.bind("<FocusOut>", lambda _e: self.port_changed())
        self.port_box.bind("<Return>", lambda _e: self.port_changed())
        ttk.Label(row, text=tr("Mode:")).pack(side=tk.LEFT)
        self.mode_titles = {mode: tr(title) for mode, title in zip(MODES, self.window.MODE_TITLES)}
        self.mode_var = tk.StringVar(value=self.mode_titles[self.service.mode])
        self.mode_box = ttk.Combobox(row, textvariable=self.mode_var, values=list(self.mode_titles.values()), state="readonly", width=34)
        self.mode_box.pack(side=tk.LEFT, padx=(4, 12))
        self.mode_box.bind("<<ComboboxSelected>>", self.mode_changed)
        self.autostart_var = tk.BooleanVar(value=self.window.settings.mcp_autostart)
        ttk.Checkbutton(row, text=tr("Start with the program (read only)"), variable=self.autostart_var,
                        command=self.autostart_changed).pack(side=tk.LEFT)

        tokens = ttk.Frame(self, padding=(8, 2))
        tokens.pack(fill=tk.X)
        ttk.Label(tokens, text=tr("Access token:")).pack(side=tk.LEFT)
        self.token_var = tk.StringVar()
        ttk.Label(tokens, textvariable=self.token_var, font=self.window.font_mono).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Button(tokens, text=tr("Copy token"), command=self.window.copy_mcp_token).pack(side=tk.LEFT, padx=2)
        ttk.Button(tokens, text=tr("Copy client configuration (stdio)"), command=lambda: self.window.copy_mcp_config("stdio")).pack(side=tk.LEFT, padx=2)
        self.copy_http = ttk.Button(tokens, text=tr("Copy client configuration (HTTP)"), command=lambda: self.window.copy_mcp_config("http"))
        self.copy_http.pack(side=tk.LEFT, padx=2)

        filters = ttk.Frame(self, padding=(8, 2))
        filters.pack(fill=tk.X)
        ttk.Label(filters, text=tr("Filter:")).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.filter_var, width=28).pack(side=tk.LEFT, padx=(4, 10))
        self.filter_var.trace_add("write", lambda *_: self.render())
        self.errors_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filters, text=tr("Errors only"), variable=self.errors_var, command=self.render).pack(side=tk.LEFT)
        self.transport_var = tk.StringVar(value="all")
        box = ttk.Combobox(filters, textvariable=self.transport_var, values=["all", "http", "stdio"], state="readonly", width=8)
        box.pack(side=tk.LEFT, padx=(10, 0))
        box.bind("<<ComboboxSelected>>", lambda _e: self.render())

        table = ttk.Frame(self, padding=(8, 2))
        table.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(table, columns=COLUMNS, show="headings", selectmode="browse")
        widths = {"time": 70, "transport": 60, "client": 120, "method": 110, "tool": 150, "arguments": 240, "ms": 50, "result": 150}
        for column in COLUMNS:
            self.tree.heading(column, text=tr(COLUMN_TITLES[column]))
            self.tree.column(column, width=widths[column], stretch=column in ("arguments", "result"))
        scroll = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.tree.tag_configure("error", foreground=self.window.color("error"))

        buttons = ttk.Frame(self, padding=(8, 2, 8, 8))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text=tr("Copy row"), command=self.copy_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(buttons, text=tr("Copy visible rows"), command=self.copy_rows).pack(side=tk.LEFT, padx=2)
        ttk.Button(buttons, text=tr("Clear"), command=self.clear).pack(side=tk.LEFT, padx=2)
        ttk.Button(buttons, text=tr("Close"), command=self.hide).pack(side=tk.RIGHT, padx=2)
        ttk.Label(self, style="Note.TLabel", padding=(8, 0, 8, 6), wraplength=940, text=tr(
            "stdio servers started by a client run as separate processes and are not shown here; they log into "
            "logs\\mcp-stdio-<pid>.log. Requests are shown with identifiers only: free text appears as <text, N chars>.")).pack(fill=tk.X)

    # ----------------------------------------------------------------- state

    def refresh_state(self) -> None:
        status = self.service.status()
        if status.running:
            self.state_var.set(tr("Running on {0}, mode: {1}, clients seen: {2}", status.url, self.mode_titles[status.mode], status.sessions))
            self.start_button.configure(text=tr("Stop"))
            self.port_box.state(["disabled"])
            self.copy_http.state(["!disabled"])
        else:
            self.state_var.set(tr("Stopped"))
            self.start_button.configure(text=tr("Start"))
            self.port_box.state(["!disabled"])
            self.copy_http.state(["disabled"])
        self.token_var.set(masked(self.service.token))
        self.mode_var.set(self.mode_titles[self.service.mode])
        self.autostart_var.set(self.window.settings.mcp_autostart)
        if not self.service.running:
            self.port_var.set(str(self.window.settings.mcp_port))

    def toggle(self) -> None:
        if self.service.running:
            self.window.stop_mcp_server()
        else:
            self.port_changed()
            self.window.start_mcp_server()
        self.refresh_state()

    def port_changed(self) -> None:
        from winkickoff.core.settings import valid_port

        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            port = -1
        if not valid_port(port):
            self.port_var.set(str(self.window.settings.mcp_port))
            self.window.set_status(tr("The port must be 0 or 1024 to 65535"))
            return
        if port != self.window.settings.mcp_port and not self.service.running:
            self.window.settings.mcp_port = port
            self.window.save_settings()

    def mode_changed(self, _event: object = None) -> None:
        wanted = next((mode for mode, title in self.mode_titles.items() if title == self.mode_var.get()), None)
        if wanted is not None and wanted != self.service.mode:
            self.window.change_mcp_mode(wanted)
        self.refresh_state()

    def autostart_changed(self) -> None:
        self.window.set_mcp_autostart(bool(self.autostart_var.get()))

    # ----------------------------------------------------------------- journal

    def _schedule(self) -> None:
        self._after_id = self.after(REFRESH_MS, self._tick)

    def _tick(self) -> None:
        self._after_id = None
        fresh = self.service.journal.since(self._seen_seq)
        if fresh:
            self._rows.extend(fresh)
            self._seen_seq = fresh[-1].seq
            del self._rows[:-1000]
            for entry in fresh:
                if self._visible(entry):
                    self._insert(entry)
            self.tree.yview_moveto(1.0)
            self.refresh_state()
        self._schedule()

    def _visible(self, entry: Entry) -> bool:
        needle = self.filter_var.get().strip().lower()
        if needle and needle not in f"{entry.method} {entry.tool}".lower():
            return False
        if self.errors_var.get() and entry.ok:
            return False
        transport = self.transport_var.get()
        return transport == "all" or entry.transport == transport

    def _insert(self, entry: Entry) -> None:
        result = "ok" if entry.ok and not entry.note else (entry.note or "error")
        self.tree.insert("", tk.END, iid=str(entry.seq), values=(entry.time, entry.transport, entry.client, entry.method,
                                                                 entry.tool, entry.args, entry.ms, result),
                         tags=() if entry.ok else ("error",))

    def render(self) -> None:
        self.tree.delete(*self.tree.get_children(""))
        for entry in self._rows:
            if self._visible(entry):
                self._insert(entry)

    def _row_text(self, iid: str) -> str:
        return "\t".join(str(v) for v in self.tree.item(iid, "values"))

    def copy_row(self) -> None:
        selection = self.tree.selection()
        if selection:
            self._to_clipboard(self._row_text(selection[0]))

    def copy_rows(self) -> None:
        self._to_clipboard("\n".join(self._row_text(iid) for iid in self.tree.get_children("")))

    def _to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.window.set_status(tr("Copied to the clipboard"))

    def clear(self) -> None:
        self._rows.clear()
        self.render()

    def hide(self) -> None:
        self.withdraw()

    def show(self) -> None:
        self.refresh_state()
        self.deiconify()
        self.lift()

    def destroy(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        super().destroy()
