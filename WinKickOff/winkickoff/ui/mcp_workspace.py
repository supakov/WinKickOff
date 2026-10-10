"""The Workspace of the MCP tools implemented on the main window.

Every method runs on the tkinter main thread (called from Bridge.pump through the after() timer the window installs)
and uses the dialog-free methods of MainWindow, so an agent can do exactly what a click does and the user sees
every change as an unsaved change in the tree.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING, Any

from winkickoff.core.deps import Change
from winkickoff.core.i18n import language, tr
from winkickoff.core.profile import Profile
from winkickoff.core.render import BuildResult
from winkickoff.core.validate import Issue, validate_profile
from winkickoff.mcp.bridge import Bridge
from winkickoff.mcp.errors import ToolError
from winkickoff.mcp.workspace import Snapshot, profile_display

if TYPE_CHECKING:
    from winkickoff.ui.main_window import MainWindow

log = logging.getLogger(__name__)
PUMP_INTERVAL_MS = 50


class WindowWorkspace:
    def __init__(self, window: MainWindow) -> None:
        self.window = window

    def snapshot(self) -> Snapshot:
        win = self.window
        return Snapshot(win.catalog, win.profile.copy(), win.resources, win.paths, win.dirty,
                        profile_display(win.profile.path, win.paths.root), win.current_item(), win.current_issues(), language())

    def set_rules(self, items: list[tuple[str, bool]]) -> tuple[list[Change], list[tuple[str, str]]]:
        return self.window.apply_rule_states(items)

    def set_group(self, group_id: str, action: str) -> list[Change]:
        return self.window.apply_group_action(group_id, action)

    def set_param(self, rule_id: str, name: str, value: Any) -> Any:
        return self.window.set_param_value(rule_id, name, value)

    def set_profile_info(self, name: str | None, author: str | None, comment: str | None) -> tuple[str, str, str]:
        return self.window.set_profile_info(name, author, comment)

    def load_profile(self, path: Path, force: bool) -> list[str]:
        win = self.window
        if win.dirty and not force:
            raise ToolError("unsaved_changes", "the open profile has unsaved changes; save it in the window or pass force")
        if not win.load_profile_file(path, confirm=False):
            raise ToolError("load_failed", "the profile could not be opened", {"name": path.stem})
        return list(win.last_load_warnings)

    def open_profile(self, profile: Profile, issues: list[Issue], force: bool) -> None:
        win = self.window
        if win.dirty and not force:
            raise ToolError("unsaved_changes", "the open profile has unsaved changes; save it in the window or pass force")
        win.adopt_profile(profile, issues)
        win.set_status(tr("An MCP client read the settings of this PC into a new profile: check it and save it under a name"))

    def show_item(self, item: str) -> bool:
        win = self.window
        if not win.can_show(item):
            return False
        win.select_node(item)  # clears an active search when the item is filtered out, as links in the panel do
        return True

    def save_profile_to(self, path: Path) -> None:
        self.window.save_profile_to(path)

    def write_answer_file_to(self, path: Path) -> tuple[BuildResult, list[Issue]]:
        return self.window.write_answer_file_to(path)

    def current_issues(self) -> list[Issue]:
        return self.window.current_issues()

    def is_dirty(self) -> bool:
        return self.window.dirty

    def error_count(self) -> int:
        win = self.window
        return sum(1 for i in validate_profile(win.profile, win.catalog, win.resources.keyboards) if i.level == "error")

    def is_busy(self) -> bool:
        return self.window.is_busy()


def install_pump(window: MainWindow, bridge: Bridge) -> None:
    """Drain the bridge every 50 ms on the main thread; the window stores the after id and cancels it in destroy()."""

    seen = [-1]

    def tick() -> None:
        try:
            bridge.pump()
        except Exception:  # noqa: BLE001 - a closure failure belongs to its future; the pump must go on
            pass
        try:
            count = window.service.journal.count if window.service is not None else 0
            if count != seen[0]:  # the journal grew (the server thread appends after the closure returned)
                seen[0] = count
                window.refresh_mcp_status()
        except Exception:  # noqa: BLE001 - a widget in an odd state must not stop the pump
            log.debug("mcp status refresh failed", exc_info=True)
        finally:
            try:
                window.mcp_pump_id = window.after(PUMP_INTERVAL_MS, tick)
            except tk.TclError:
                pass  # the window is gone

    window.mcp_pump_id = window.after(PUMP_INTERVAL_MS, tick)
