"""The MCP server in the main window (task T22): the calls of the window workspace, the dialog count, the
MCP menu and the service.

Methods of MainWindow (ui/main_window.py); the attributes they use are made there."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox
from typing import Any

from winkickoff import APP_NAME
from winkickoff.core.deps import Change
from winkickoff.core.i18n import tr
from winkickoff.core.paths import display_path
from winkickoff.core.profile import Profile
from winkickoff.mcp import MODE_READ, MODES
from winkickoff.mcp.workspace import apply_group_action, apply_rule_states, change_param
from winkickoff.core.validate import Issue
from winkickoff.ui.clipboard import copy_secret
from winkickoff.ui.window_common import MODE_TITLES, user_docs

log = logging.getLogger(__name__)


class McpActions:
    """The MCP server in the window: the workspace calls, the dialog count, the MCP menu, the service."""

    # ----------------------------------------------------------------- MCP server (task T22)

    def _dialog(self, show: Any, *args: Any, **kwargs: Any) -> Any:
        """Every message box and file dialog of the window goes through here, so is_busy() knows about them."""
        self._modal += 1
        try:
            return show(*args, **kwargs)
        finally:
            self._modal -= 1

    def is_busy(self) -> bool:
        """A background job, an open dialog or a Tk grab: MCP writes are refused meanwhile, reads go on."""
        try:
            grabbed = self.grab_current() is not None
        except tk.TclError:
            grabbed = False
        return self._busy or self._modal > 0 or grabbed

    def current_item(self) -> str:
        return self._current_item

    def current_issues(self) -> list[Issue]:
        return list(self._issues)

    def apply_rule_states(self, items: list[tuple[str, bool]]) -> tuple[list[Change], list[tuple[str, str]]]:
        """Switch rules as clicks in the tree would, without dialogs: one refresh for the whole list."""
        changes, refused = apply_rule_states(self.catalog, self.profile, self.resolver, items)
        if changes:
            self._apply_changes(changes, {c.rule_id for c in changes if c.reason == "user"})
            self.show_item(self._current_item)
        return changes, refused

    def apply_group_action(self, group_id: str, action: str) -> list[Change]:
        changes = apply_group_action(self.catalog, self.profile, self.resolver, group_id, action)
        if changes:
            self._apply_changes(changes, {r.id for r in self.catalog.rules_in_group(group_id)})
            self.show_item(self._current_item)
        return changes

    def set_param_value(self, rule_id: str, name: str, value: Any) -> Any:
        stored, changed = change_param(self.catalog, self.profile, self.resources, rule_id, name, value)
        if not changed:
            return stored  # the current value: the parameter panel does not mark the profile dirty either
        self.mark_dirty()
        self.refresh_marks()
        rule = self.catalog.rules[rule_id]
        self.set_status(f"{self.rule_title(rule_id)}: {self.param_title(rule, rule.params[name])} = "
                        f"{self._param_display(rule, rule.params[name], stored)}")
        if self._current_item == "r:" + rule_id:
            self.show_item(self._current_item)
        return stored

    def set_profile_info(self, name: str | None, author: str | None, comment: str | None) -> tuple[str, str, str]:
        wanted = (self.profile.name if name is None else name, self.profile.author if author is None else author,
                  self.profile.comment if comment is None else comment)
        if wanted != (self.profile.name, self.profile.author, self.profile.comment):
            self.profile.name, self.profile.author, self.profile.comment = wanted
            self.mark_dirty()
            self.update_title()
            self.set_status(tr("Profile name and notes changed"))
        return wanted

    def _build_mcp_menu(self, menu: tk.Menu) -> None:
        """Start and stop the HTTP server, the mode, the monitor, client configuration, the token, autostart."""
        state = tk.NORMAL if self.service is not None else tk.DISABLED
        self.mcp_running_var = tk.BooleanVar(value=bool(self.service is not None and self.service.running))
        menu.add_checkbutton(label=tr("Server running (HTTP, this computer only)"), variable=self.mcp_running_var,
                             command=self.toggle_mcp_server, state=state)
        menu.add_separator()
        self.mcp_mode_var = tk.StringVar(value=self.service.mode if self.service is not None else MODE_READ)
        for mode, title in zip(MODES, MODE_TITLES):
            menu.add_radiobutton(label=tr(title), value=mode, variable=self.mcp_mode_var,
                                 command=lambda m=mode: self.change_mcp_mode(m), state=state)
        self.mcp_read_pc_var = tk.BooleanVar(value=bool(self.service is not None and self.service.read_pc))
        menu.add_checkbutton(label=tr("Allow reading the settings of this PC"), variable=self.mcp_read_pc_var,
                             command=self.toggle_mcp_read_pc, state=state)
        menu.add_separator()
        menu.add_command(label=tr("Monitor..."), command=self.open_mcp_monitor, state=state)
        menu.add_command(label=tr("Copy client configuration (stdio)"), command=lambda: self.copy_mcp_config("stdio"), state=state)
        menu.add_command(label=tr("Copy client configuration (HTTP)"), command=lambda: self.copy_mcp_config("http"), state=state)
        menu.add_command(label=tr("New access token"), command=self.rotate_mcp_token, state=state)
        menu.add_separator()
        self.mcp_autostart_var = tk.BooleanVar(value=self.settings.mcp_autostart)
        menu.add_checkbutton(label=tr("Start the server with the program (read only)"), variable=self.mcp_autostart_var,
                             command=lambda: self.set_mcp_autostart(bool(self.mcp_autostart_var.get())), state=state)
        menu.add_command(label=tr("Documentation"), command=lambda: self.open_doc(user_docs(self.paths.docs_root).replace("README.md", "mcp.md")))
        self.mcp_menu = menu

    def toggle_mcp_server(self) -> None:
        if self.mcp_running_var.get():
            self.start_mcp_server()
        else:
            self.stop_mcp_server()

    def start_mcp_server(self) -> bool:
        if self.service is None:
            return False
        try:
            port = self.service.start_http(self.settings.mcp_port)
        except OSError as exc:
            log.error("mcp server did not start: %s", exc)
            self.refresh_mcp_status()
            # a foreign listener on the configured port may already have received the token from a configured client
            if self._dialog(messagebox.askyesno, APP_NAME, tr(
                    "The MCP server did not start: port {0} is used by another program. Clients configured for this port may "
                    "already have sent the access token to that program. Choose another port in the monitor.\n\n"
                    "Generate a new access token now?", self.settings.mcp_port), icon=messagebox.WARNING, parent=self):
                self.service.rotate_token()
                self.set_status(tr("New access token generated; the server was stopped"))
                self.refresh_mcp_status()
            return False
        self.set_status(tr("MCP server started on http://127.0.0.1:{0}/mcp, mode: {1}", port, tr(MODE_TITLES[MODES.index(self.service.mode)])))
        self.refresh_mcp_status()
        return True

    def stop_mcp_server(self) -> None:
        if self.service is None:
            return
        self.service.stop()
        self.set_status(tr("MCP server stopped"))
        self.refresh_mcp_status()

    def change_mcp_mode(self, mode: str) -> None:
        if self.service is None:
            return
        if mode == "files" and not self._files_confirmed:
            if not self._dialog(messagebox.askyesno, APP_NAME, tr("Clients will be able to create profiles and answer files inside the program folder. Existing files are never replaced. Continue?"),
                                icon=messagebox.WARNING, default=messagebox.NO, parent=self):
                self.mcp_mode_var.set(self.service.mode)
                return
            self._files_confirmed = True
        self.service.set_mode(mode)
        self.mcp_mode_var.set(mode)
        self.set_status(tr("MCP mode: {0}", tr(MODE_TITLES[MODES.index(mode)])))
        self.refresh_mcp_status()

    def set_mcp_autostart(self, value: bool) -> None:
        self.settings.mcp_autostart = value
        self.save_settings()
        self.mcp_autostart_var.set(value)

    def rotate_mcp_token(self) -> None:
        if self.service is None:
            return
        if not self._dialog(messagebox.askyesno, APP_NAME, tr("Clients configured with the old token stop working. Continue?"), parent=self):
            return
        self.service.rotate_token()
        self.set_status(tr("New access token generated; the server was stopped"))
        self.refresh_mcp_status()

    def copy_mcp_token(self) -> None:
        if self.service is None:
            return
        if copy_secret(self, self.service.ensure_token()):  # kept out of the clipboard history and the cloud clipboard
            self.set_status(tr("Access token copied to the clipboard"))
        else:
            self.set_status(tr("The clipboard is busy, nothing was copied. Try again."))

    def copy_mcp_config(self, kind: str) -> None:
        if self.service is None:
            return
        if kind == "http" and not self.service.running:
            self.set_status(tr("Start the server first: the configuration needs the port"))
            return
        if kind == "http":
            self.service.ensure_token()
            if copy_secret(self, self.service.client_config(kind)):
                self.set_status(tr("Configuration with the access token copied to the clipboard"))
            else:
                self.set_status(tr("The clipboard is busy, nothing was copied. Try again."))
            return
        self.clipboard_clear()
        self.clipboard_append(self.service.client_config(kind))
        self.set_status(tr("Client configuration (stdio) copied to the clipboard"))

    def open_mcp_monitor(self) -> None:
        if self.service is None:
            return
        from winkickoff.ui.mcp_window import McpMonitor

        if self.mcp_monitor is None or not self.mcp_monitor.winfo_exists():
            self.mcp_monitor = McpMonitor(self)
        self.mcp_monitor.show()

    def refresh_mcp_status(self) -> None:
        """The status bar segment, the menu variables and the monitor follow the service."""
        if self.service is None:
            self.mcp_status_var.set(tr("MCP: off"))
            return
        status = self.service.status()
        if status.running:
            self.mcp_status_var.set(tr("MCP: 127.0.0.1:{0}, {1}, {2} requests, last {3}", status.port,
                                       tr(MODE_TITLES[MODES.index(status.mode)]), status.requests, status.last_time or "-"))
        else:
            self.mcp_status_var.set(tr("MCP: off"))
        if hasattr(self, "mcp_running_var"):
            self.mcp_running_var.set(status.running)
            self.mcp_mode_var.set(status.mode)
        if self.mcp_monitor is not None and self.mcp_monitor.winfo_exists():
            self.mcp_monitor.refresh_state()

    def save_settings(self) -> None:
        if self.state() == "normal":
            self.settings.geometry = self.geometry()
        path = self.profile.path
        self.settings.last_profile = display_path(path, self.paths.root) if path is not None else ""
        self.settings.save(self.paths.settings_file)
