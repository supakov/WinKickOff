"""ui/main_window.py with an MCP service (task T22): the MCP menu, the HTTP server started from the window, tools served
by the window through the bridge, busy and modal states, mode and token changes, window rebuilds, the monitor and
create_app with autostart.

Every window is withdrawn before its first update and never shown; the server binds 127.0.0.1 on port 0 only; every
file goes into a temporary folder; launch_elevated and run_audit are mocked. HTTP requests run on a helper thread while
the test pumps the window by hand (Bridge.pump runs from the window's after() timer), as tests/test_ui_smoke.py does
for the audit.
"""

from __future__ import annotations

import quiet_tk  # noqa: F401 - first: every window these tests open stays invisible
import http.client
import json
import logging
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from unittest import mock

try:
    import tkinter as tk
    from tkinter import messagebox, ttk

    _root = tk.Tk()
    _root.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001 - no display or no Tk: the test is skipped
    TK_OK = False

from winkickoff.core import i18n
from winkickoff.core.catalog import load_catalog
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources
from winkickoff.core.settings import TOKEN_RE, Settings
from winkickoff.mcp import ENDPOINT, MODE_EDIT, MODE_FILES, MODE_READ
from winkickoff.mcp.service import McpService

ROOT = Path(__file__).resolve().parents[1]
OFFICE = ROOT / "profiles" / "preset-office.json"
PASSWORD = "Kx9-SecretPassw0rd"  # the password of the test profile: it must never reach a widget of the monitor
RULE = "network.netbios-off"  # off in the Office preset, no dependencies
HTTP_TIMEOUT = 60.0
# A clipboard viewer in its own process, like the clipboard history of Windows: it opens the clipboard with a window
# of its own (a clipboard opened without a window does not lock other processes out), waiting while another viewer
# (the real clipboard history) reads it, says "open", waits for a line on stdin, asks for the text (the owner renders
# it on request) and closes the clipboard.
CLIPBOARD_VIEWER = """
import ctypes, sys, time
from ctypes import wintypes
user32 = ctypes.WinDLL("user32")
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.OpenClipboard.argtypes, user32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
user32.GetClipboardData.argtypes, user32.GetClipboardData.restype = [wintypes.UINT], wintypes.HANDLE
window = user32.CreateWindowExW(0, "STATIC", "viewer", 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)
deadline = time.monotonic() + 10
while not window or not user32.OpenClipboard(window):
    if not window or time.monotonic() > deadline:
        print("busy", flush=True)
        sys.exit(1)
    time.sleep(0.02)
print("open", flush=True)
sys.stdin.readline()
text = user32.GetClipboardData(13)
user32.CloseClipboard()
print("read" if text else "empty", flush=True)
"""


class McpClient:
    """A minimal MCP client over http.client for the tests: one connection per request (the server closes them)."""

    def __init__(self, port: int, token: str) -> None:
        self.port = port
        self.token = token
        self.session = ""
        self._seq = 0

    def post(self, message: dict[str, Any]) -> tuple[int, Any]:
        """The HTTP status and the parsed body (None when empty) of one POST to the endpoint."""
        body = json.dumps(message).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                   "Accept": "application/json", "Content-Length": str(len(body))}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=HTTP_TIMEOUT)
        try:
            connection.request("POST", ENDPOINT, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            session = response.getheader("Mcp-Session-Id")
            if session:
                self.session = session
            return response.status, (json.loads(raw) if raw else None)
        finally:
            connection.close()

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._seq += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self._seq, "method": method}
        if params is not None:
            message["params"] = params
        status, reply = self.post(message)
        if status != 200:
            raise RuntimeError(f"HTTP {status} for {method}")
        return reply

    def initialize(self) -> Any:
        reply = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                            "clientInfo": {"name": "window-test", "version": "1"}})
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return reply

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """The tools/call result: content, structuredContent and isError."""
        reply = self.request("tools/call", {"name": tool, "arguments": arguments or {}})
        if "error" in reply:
            raise RuntimeError(f"JSON-RPC error for {tool}: {reply['error']}")
        return reply["result"]


def widget_texts(widget: Any) -> list[str]:
    """Every text a widget tree shows: labels, variables, entries, combo box values, text boxes, tree rows and headings."""
    texts: list[str] = []
    pending = [widget]
    while pending:
        current = pending.pop()
        pending.extend(current.winfo_children())
        for option in ("text", "values"):
            try:
                texts.append(str(current.cget(option)))
            except tk.TclError:
                pass
        try:
            name = str(current.cget("textvariable"))
            if name:
                texts.append(str(current.getvar(name)))
        except tk.TclError:
            pass
        if isinstance(current, tk.Text):
            texts.append(current.get("1.0", "end"))
        elif isinstance(current, ttk.Entry):  # Combobox and Spinbox are Entry widgets
            texts.append(current.get())
        elif isinstance(current, ttk.Treeview):
            for column in current.tk.splitlist(current.cget("columns")):
                texts.append(str(current.heading(column, "text")))
            for iid in current.get_children(""):
                texts.append(" ".join(str(value) for value in current.item(iid, "values")))
                texts.append(str(current.item(iid, "text")))
    return texts


@unittest.skipUnless(TK_OK, "Tk is not available")
class McpWindowTestCase(unittest.TestCase):
    """A withdrawn main window with an McpService attached; every file in a temporary folder."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.resources = Resources.load(ROOT / "resources")

    def setUp(self) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name) / "WinKickOff"
        self.paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                              output=base / "output", logs=base / "logs")
        for folder in (self.paths.profiles, self.paths.output, self.paths.logs):
            folder.mkdir(parents=True)
        for target in ("winkickoff.ui.main_window.apply_module.launch_elevated", "winkickoff.ui.main_window.run_audit"):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.settings = Settings(language="en", theme="light", mcp_port=0)
        self.service = McpService()
        self.service.configure(self.paths, self.settings)
        self.win = self.build_window(self.settings)
        self.service.on_save = self.win.save_settings

    def tearDown(self) -> None:
        self.service.stop()
        self.destroy(self.win)
        self._tmp.cleanup()
        i18n.set_language("en")

    # ----------------------------------------------------------------- helpers

    def office_profile(self) -> Profile:
        profile, _ = Profile.load(OFFICE, self.catalog)
        profile.accounts[0].password = PASSWORD
        return profile

    def build_window(self, settings: Settings, *, attached: bool = True) -> Any:
        """A main window on the test paths, withdrawn before its first update; attached=False means service=None."""
        from winkickoff.ui.main_window import MainWindow

        win = MainWindow(self.paths, self.catalog, self.office_profile(), self.resources, settings,
                         service=self.service if attached else None)
        win.withdraw()
        return win

    @staticmethod
    def destroy(win: Any) -> None:
        try:
            win.destroy()
        except tk.TclError:
            pass

    def pump(self, done: Callable[[], bool], timeout: float = 30.0, window: Any = None) -> None:
        """Run the event loop by hand until done() holds; Bridge.pump ticks from the window's after() timer."""
        window = window if window is not None else self.win
        deadline = time.monotonic() + timeout
        while not done() and time.monotonic() < deadline:
            window.update()
            time.sleep(0.01)
        self.assertTrue(done(), f"the window did not reach the expected state in {timeout:g} s")

    def in_thread(self, fn: Callable[[], Any], window: Any = None) -> Any:
        """Run fn (an MCP client) on a helper thread while the test pumps the window; its result, or its exception."""
        box: dict[str, Any] = {}

        def work() -> None:
            try:
                box["result"] = fn()
            except BaseException as exc:  # noqa: BLE001 - raised again on the test thread
                box["error"] = exc

        thread = threading.Thread(target=work, name="mcp-test-client", daemon=True)
        thread.start()
        self.pump(lambda: not thread.is_alive(), timeout=HTTP_TIMEOUT + 10, window=window)
        if "error" in box:
            raise box["error"]
        return box["result"]

    def start(self, mode: str = MODE_READ) -> McpClient:
        """Start the HTTP server from the window in the given mode; an initialized client for it."""
        self.service.set_mode(mode)
        self.win.refresh_mcp_status()
        self.assertTrue(self.win.start_mcp_server())
        client = McpClient(self.service.status().port, self.service.token)
        self.in_thread(client.initialize)
        return client

    def image(self, item: str) -> str:
        """The check box image of a tree item: on, off or partial."""
        shown = str(self.win.tree.item(item, "image")[0])
        return next(name for name, image in self.win.images.items() if str(image) == shown)

    def menu_states(self, win: Any) -> dict[str, str]:
        menu = win.mcp_menu
        states: dict[str, str] = {}
        for index in range(menu.index("end") + 1):
            if menu.type(index) != "separator":
                states[str(menu.entrycget(index, "label"))] = str(menu.entrycget(index, "state"))
        return states

    def set_rules_call(self, client: McpClient, enabled: bool = True) -> dict[str, Any]:
        return self.in_thread(lambda: client.call("set_rules", {"items": [{"id": RULE, "enabled": enabled}]}))


class MenuAndStatusTest(McpWindowTestCase):
    def test_menu_items_are_enabled_with_a_service(self) -> None:
        states = self.menu_states(self.win)
        self.assertGreaterEqual(len(states), 9)
        self.assertEqual(set(states.values()), {"normal"})
        self.assertTrue(self.service.bridge.attached)
        self.assertIsNotNone(self.win.mcp_pump_id)
        self.assertEqual(self.win.mcp_status_var.get(), "MCP: off")  # attached, but the server is not running

    def test_menu_items_are_disabled_without_a_service(self) -> None:
        self.destroy(self.win)  # windows are built one at a time, as the program does
        self.win = self.build_window(Settings(language="en", theme="light"), attached=False)
        states = self.menu_states(self.win)
        self.assertEqual(states.pop("Documentation"), "normal")
        self.assertEqual(set(states.values()), {"disabled"})
        self.assertEqual(self.win.mcp_status_var.get(), "MCP: off")
        self.assertIsNone(self.win.service)
        self.assertIsNone(self.win.mcp_pump_id)
        self.assertFalse(self.service.bridge.attached)
        self.assertFalse(self.win.start_mcp_server())  # inert: nothing starts
        self.assertFalse(self.service.running)

    def test_start_mcp_server_shows_the_port_and_the_mode(self) -> None:
        self.assertTrue(self.win.start_mcp_server())
        self.assertTrue(self.service.running)
        port = self.service.status().port
        self.assertGreater(port, 0)
        text = self.win.mcp_status_var.get()
        self.assertIn(f"127.0.0.1:{port}", text)
        self.assertIn("Read only", text)
        self.assertTrue(self.win.mcp_running_var.get())
        self.assertEqual(self.win.mcp_mode_var.get(), MODE_READ)
        self.assertIn(f"http://127.0.0.1:{port}/mcp", self.win.status_var.get())
        self.win.stop_mcp_server()
        self.assertFalse(self.service.running)
        self.assertEqual(self.win.mcp_status_var.get(), "MCP: off")
        self.assertFalse(self.win.mcp_running_var.get())
        self.assertIn("stopped", self.win.status_var.get())

    def test_the_first_start_generates_and_saves_the_token(self) -> None:
        self.assertEqual(self.settings.mcp_token, "")
        self.assertFalse(self.paths.settings_file.exists())
        self.assertTrue(self.win.start_mcp_server())
        self.assertRegex(self.settings.mcp_token, TOKEN_RE)
        saved = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["mcp_token"], self.settings.mcp_token)
        self.assertEqual(saved["mcp_port"], 0)

    def test_the_menu_check_button_toggles_the_server(self) -> None:
        self.win.mcp_running_var.set(True)
        self.win.toggle_mcp_server()
        self.assertTrue(self.service.running)
        self.win.mcp_running_var.set(False)
        self.win.toggle_mcp_server()
        self.assertFalse(self.service.running)

    def test_autostart_from_the_menu_is_saved(self) -> None:
        self.win.set_mcp_autostart(True)
        self.assertTrue(self.win.mcp_autostart_var.get())
        self.assertTrue(json.loads(self.paths.settings_file.read_text(encoding="utf-8"))["mcp_autostart"])
        self.win.set_mcp_autostart(False)
        self.assertFalse(json.loads(self.paths.settings_file.read_text(encoding="utf-8"))["mcp_autostart"])


class ToolsOverHttpTest(McpWindowTestCase):
    def test_get_status_reports_the_window(self) -> None:
        client = self.start()
        result = self.in_thread(lambda: client.call("get_status"))
        self.assertFalse(result["isError"], result)
        status = result["structuredContent"]
        self.assertEqual((status["mode"], status["transport"], status["has_window"]), (MODE_READ, "http", True))
        self.assertEqual((status["profile"]["name"], status["profile"]["dirty"]), ("Office", False))
        self.assertTrue(status["profile"]["file"].endswith("preset-office.json"))
        self.assertEqual(status["language"], "en")
        requests = self.service.status().requests
        self.assertEqual(requests, 3)  # initialize, notifications/initialized, tools/call
        self.assertIn("requests, last", self.win.mcp_status_var.get())
        self.win.refresh_mcp_status()  # the pump refreshes before the server journals the call: one behind until then
        self.assertIn(f"{requests} requests", self.win.mcp_status_var.get())

    def test_get_profile_redacts_the_password(self) -> None:
        client = self.start()
        result = self.in_thread(lambda: client.call("get_profile"))
        self.assertFalse(result["isError"], result)
        accounts = result["structuredContent"]["accounts"]
        self.assertEqual([a["has_password"] for a in accounts], [True, False])
        self.assertNotIn("password", accounts[0])
        self.assertNotIn(PASSWORD, json.dumps(result))

    def test_set_rules_in_edit_mode_changes_the_profile_the_tree_and_the_title(self) -> None:
        client = self.start(MODE_EDIT)
        self.assertFalse(self.win.profile.is_enabled(RULE))
        self.assertEqual(self.image("r:" + RULE), "off")
        self.assertFalse(self.win.title().endswith("*"))
        result = self.set_rules_call(client)
        self.assertFalse(result["isError"], result)
        self.assertIn(RULE, [c["id"] for c in result["structuredContent"]["changes"]])
        self.assertEqual(result["structuredContent"]["refused"], [])
        self.assertTrue(self.win.profile.is_enabled(RULE))
        self.assertEqual(self.image("r:" + RULE), "on")
        self.assertTrue(self.win.dirty)
        self.assertTrue(self.win.title().endswith("*"))
        self.assertIn("Enabled", self.win.status_var.get())

    def test_set_rules_in_read_mode_is_refused(self) -> None:
        client = self.start()
        result = self.set_rules_call(client)
        self.assertTrue(result["isError"])
        structured = result["structuredContent"]
        self.assertEqual((structured["error"], structured["required"], structured["current"]), ("mode_required", MODE_EDIT, MODE_READ))
        self.assertFalse(self.win.profile.is_enabled(RULE))
        self.assertFalse(self.win.dirty)

    def int_param(self) -> tuple[Any, Any]:
        return next((r, p) for r in self.catalog.rules.values() for p in r.params.values()
                    if p.type == "int" and p.min is not None and p.max is not None and p.max > p.default)

    def test_set_param_changes_the_profile_and_the_parameter_panel(self) -> None:
        rule, param = self.int_param()
        self.win.select_node("r:" + rule.id)
        client = self.start(MODE_EDIT)
        value = param.default + 1
        result = self.in_thread(lambda: client.call("set_param", {"id": rule.id, "name": param.name, "value": value}))
        self.assertFalse(result["isError"], result)
        self.assertEqual(result["structuredContent"]["value"], value)
        self.assertEqual(self.win.profile.param(self.catalog, rule.id, param.name), value)
        self.assertEqual(self.win._param_vars[list(rule.params).index(param.name)].get(), str(value))
        self.assertEqual(str(self.win._param_marks[param.name].cget("text")), "changed")
        self.assertIn("changed", self.win.tree.item("r:" + rule.id, "tags"))
        self.assertTrue(self.win.dirty)
        self.assertIn(f"= {value}", self.win.status_var.get())

    def test_set_param_out_of_range_is_refused(self) -> None:
        rule, param = self.int_param()
        client = self.start(MODE_EDIT)
        result = self.in_thread(lambda: client.call("set_param", {"id": rule.id, "name": param.name, "value": param.max + 1}))
        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["error"], "invalid_arguments")
        self.assertEqual(self.win.profile.param(self.catalog, rule.id, param.name), param.default)
        self.assertFalse(self.win.dirty)

    def test_show_item_selects_the_node(self) -> None:
        client = self.start(MODE_EDIT)
        result = self.in_thread(lambda: client.call("show_item", {"item": "r:defender.pua"}))
        self.assertEqual(result["structuredContent"], {"shown": True})
        self.assertEqual(self.win.tree.selection(), ("r:defender.pua",))
        self.assertEqual(self.win.current_item(), "r:defender.pua")
        self.assertIn(self.catalog.rules["defender.pua"].title, self.win.detail.get("1.0", "end"))
        result = self.in_thread(lambda: client.call("show_item", {"item": "r:no.such-rule"}))
        self.assertEqual(result["structuredContent"], {"shown": False, "reason": "no such item"})
        self.assertEqual(self.win.tree.selection(), ("r:defender.pua",))
        self.assertFalse(self.win.dirty)

    def test_set_group_off_switches_the_whole_group_off(self) -> None:
        group = self.catalog.rules["defender.pua"].group
        client = self.start(MODE_EDIT)
        result = self.in_thread(lambda: client.call("set_group", {"id": group, "action": "off"}))
        self.assertFalse(result["isError"], result)
        self.assertTrue(result["structuredContent"]["changes"])
        rules = self.catalog.rules_in_group(group)
        self.assertFalse(any(self.win.profile.is_enabled(r.id) for r in rules))
        self.assertEqual(self.win._group_counts(group)[0], 0)
        self.assertEqual(self.image("g:" + group), "off")
        self.assertTrue(self.win.dirty)

    def test_load_profile_refuses_when_dirty(self) -> None:
        client = self.start(MODE_EDIT)
        self.set_rules_call(client)
        self.assertTrue(self.win.dirty)
        refused = self.in_thread(lambda: client.call("load_profile", {"name": "strict"}))
        self.assertTrue(refused["isError"])
        self.assertEqual(refused["structuredContent"]["error"], "unsaved_changes")
        self.assertTrue(self.win.dirty)
        self.assertEqual(self.win.profile.name, "Office")
        self.assertTrue(self.win.profile.is_enabled(RULE))
    def test_load_profile_with_force_opens_the_preset(self) -> None:
        client = self.start(MODE_EDIT)
        self.set_rules_call(client)
        self.assertTrue(self.win.dirty)
        loaded = self.in_thread(lambda: client.call("load_profile", {"name": "strict", "force": True}))
        self.assertFalse(loaded["isError"], loaded)
        self.assertTrue(loaded["structuredContent"]["forced"])
        self.assertEqual(self.win.profile.name, "Strict")
        self.assertEqual(self.win.profile.path.name, "preset-strict.json")
        self.assertFalse(self.win.dirty)
        self.assertFalse(self.win.title().endswith("*"))
        self.assertIn("Preset \"Strict\" opened", self.win.status_var.get())

    def test_save_profile_in_files_mode_writes_into_the_profiles_folder(self) -> None:
        client = self.start(MODE_FILES)
        result = self.in_thread(lambda: client.call("save_profile", {"name": "Профіль"}))
        self.assertFalse(result["isError"], result)
        self.assertFalse(result["structuredContent"]["dirty"])
        target = self.paths.profiles / "Профіль.json"
        self.assertTrue(target.is_file())
        self.assertEqual(self.win.profile.name, "Профіль")
        self.assertEqual(self.win.profile.path, target)
        self.assertFalse(self.win.dirty)
        self.assertIn("Profile saved", self.win.status_var.get())
        self.assertIn("Профіль", self.win.profile_box.cget("values"))
        again = self.in_thread(lambda: client.call("save_profile", {"name": "Профіль"}))
        self.assertEqual(again["structuredContent"]["error"], "exists")
        self.assertEqual(sorted(p.name for p in self.paths.profiles.iterdir()), ["Профіль.json"])

    def test_save_profile_in_edit_mode_is_refused(self) -> None:
        client = self.start(MODE_EDIT)
        result = self.in_thread(lambda: client.call("save_profile", {"name": "Профіль"}))
        self.assertEqual(result["structuredContent"]["error"], "mode_required")
        self.assertEqual(list(self.paths.profiles.iterdir()), [])

    def test_write_answer_file_in_files_mode_writes_into_the_output_folder(self) -> None:
        client = self.start(MODE_FILES)
        result = self.in_thread(lambda: client.call("write_answer_file", {"name": "answer-test"}))
        self.assertFalse(result["isError"], result)
        target = self.paths.output / "answer-test.xml"
        self.assertTrue(target.is_file())
        self.assertIn(b"unattend", target.read_bytes())
        self.assertGreater(result["structuredContent"]["rules"], 0)
        self.assertFalse(result["structuredContent"]["powershell_checked"])
        self.assertIn("Built:", self.win.status_var.get())
        rows = [self.win.messages.item(i, "values")[2] for i in self.win.messages.get_children()]
        self.assertTrue(any("Saved:" in r for r in rows), rows)
        self.assertTrue(any("PowerShell" in r for r in rows), rows)
        self.assertEqual(sorted(p.name for p in self.paths.output.iterdir()), ["answer-test.xml"])


class BusyStatesTest(McpWindowTestCase):
    def test_reads_work_while_the_window_is_busy_and_writes_are_refused(self) -> None:
        client = self.start(MODE_EDIT)
        self.win._busy = True
        try:
            self.assertTrue(self.win.is_busy())
            read = self.in_thread(lambda: client.call("get_status"))
            self.assertFalse(read["isError"], read)
            write = self.set_rules_call(client)
            self.assertTrue(write["isError"])
            self.assertEqual(write["structuredContent"]["error"], "window_busy")
            self.assertFalse(self.win.profile.is_enabled(RULE))
        finally:
            self.win._busy = False
        self.assertFalse(self.win.is_busy())
        served = self.set_rules_call(client)  # after the background job the write is served
        self.assertFalse(served["isError"], served)
        self.assertTrue(self.win.profile.is_enabled(RULE))

    def test_reads_work_while_a_dialog_is_open(self) -> None:
        client = self.start(MODE_EDIT)
        outcome: dict[str, Any] = {}

        def requests() -> None:
            outcome["read"] = client.call("get_status")
            outcome["write"] = client.call("set_rules", {"items": [{"id": RULE, "enabled": True}]})

        def fake_dialog(*args: Any, **kwargs: Any) -> str:
            """A message box: the window keeps handling timers (Tk ticks under the native message loop)."""
            self.assertTrue(self.win.is_busy())
            thread = threading.Thread(target=requests, name="mcp-test-client", daemon=True)
            thread.start()
            end = time.monotonic() + 0.3
            while time.monotonic() < end or (thread.is_alive() and time.monotonic() < end + HTTP_TIMEOUT):
                self.win.update()
                time.sleep(0.01)
            self.assertFalse(thread.is_alive())
            return "answer"

        self.assertEqual(self.win._dialog(fake_dialog, "title", "text", parent=self.win), "answer")
        self.assertFalse(self.win.is_busy())
        self.assertFalse(outcome["read"]["isError"], outcome["read"])
        self.assertEqual(outcome["write"]["structuredContent"]["error"], "window_busy")
        self.assertFalse(self.win.profile.is_enabled(RULE))

    def test_writes_are_refused_while_a_grab_is_held(self) -> None:
        client = self.start(MODE_EDIT)
        with mock.patch.object(self.win, "grab_current", return_value=self.win):
            self.assertTrue(self.win.is_busy())
            read = self.in_thread(lambda: client.call("get_status"))
            self.assertFalse(read["isError"], read)
            write = self.set_rules_call(client)
            self.assertEqual(write["structuredContent"]["error"], "window_busy")
        self.assertFalse(self.win.is_busy())
        self.assertFalse(self.win.profile.is_enabled(RULE))


class ModeAndTokenTest(McpWindowTestCase):
    ASK = "winkickoff.ui.main_window.messagebox.askyesno"

    def test_change_mode_to_files_asks_once_per_window(self) -> None:
        with mock.patch(self.ASK, return_value=False) as ask:
            self.win.change_mcp_mode(MODE_FILES)
        ask.assert_called_once()
        self.assertEqual(self.service.mode, MODE_READ)
        self.assertEqual(self.win.mcp_mode_var.get(), MODE_READ)
        with mock.patch(self.ASK, return_value=True) as ask:
            self.win.change_mcp_mode(MODE_FILES)
        ask.assert_called_once()
        self.assertEqual(self.service.mode, MODE_FILES)
        self.assertEqual(self.win.mcp_mode_var.get(), MODE_FILES)
        self.assertIn("Change and create files", self.win.status_var.get())
        self.win.change_mcp_mode(MODE_EDIT)
        self.assertEqual(self.service.mode, MODE_EDIT)
        with mock.patch(self.ASK, return_value=False) as ask:
            self.win.change_mcp_mode(MODE_FILES)  # confirmed once in this window: no second question
        ask.assert_not_called()
        self.assertEqual(self.service.mode, MODE_FILES)

    def test_edit_mode_needs_no_confirmation(self) -> None:
        with mock.patch(self.ASK) as ask:
            self.win.change_mcp_mode(MODE_EDIT)
        ask.assert_not_called()
        self.assertEqual(self.service.mode, MODE_EDIT)
        self.assertEqual(self.win.mcp_mode_var.get(), MODE_EDIT)
        self.assertIn("Read and change the open profile", self.win.status_var.get())

    def test_a_mode_change_applies_to_the_next_call(self) -> None:
        client = self.start()
        refused = self.set_rules_call(client)
        self.assertEqual(refused["structuredContent"]["error"], "mode_required")
        self.win.change_mcp_mode(MODE_EDIT)
        self.assertIn("Read and change the open profile", self.win.mcp_status_var.get())
        served = self.set_rules_call(client)
        self.assertFalse(served["isError"], served)
        self.assertTrue(self.win.profile.is_enabled(RULE))
        self.win.change_mcp_mode(MODE_READ)
        refused = self.set_rules_call(client, enabled=False)
        self.assertEqual(refused["structuredContent"]["error"], "mode_required")
        self.assertTrue(self.win.profile.is_enabled(RULE))

    def test_rotate_token_asks_stops_the_server_and_saves_the_settings(self) -> None:
        self.assertTrue(self.win.start_mcp_server())
        old = self.service.token
        with mock.patch(self.ASK, return_value=False) as ask:
            self.win.rotate_mcp_token()
        ask.assert_called_once()
        self.assertEqual(self.service.token, old)
        self.assertTrue(self.service.running)
        with mock.patch(self.ASK, return_value=True) as ask:
            self.win.rotate_mcp_token()
        ask.assert_called_once()
        self.assertFalse(self.service.running)
        new = self.win.settings.mcp_token
        self.assertNotEqual(new, old)
        self.assertRegex(new, TOKEN_RE)
        self.assertEqual(json.loads(self.paths.settings_file.read_text(encoding="utf-8"))["mcp_token"], new)
        self.assertEqual(self.win.mcp_status_var.get(), "MCP: off")
        self.assertFalse(self.win.mcp_running_var.get())
        self.assertIn("New access token", self.win.status_var.get())

    def test_the_old_token_stops_working_after_rotation(self) -> None:
        client = self.start()
        old_token = client.token
        with mock.patch(self.ASK, return_value=True):
            self.win.rotate_mcp_token()
        self.assertTrue(self.win.start_mcp_server())
        port = self.service.status().port
        ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        stale = McpClient(port, old_token)
        self.assertEqual(self.in_thread(lambda: stale.post(ping))[0], 401)
        fresh = McpClient(port, self.service.token)
        status, reply = self.in_thread(lambda: fresh.post(ping))
        self.assertEqual((status, reply["result"]), (200, {}))

    def test_token_survives_window_rebuild(self) -> None:
        from winkickoff.ui.main_window import MainWindow

        self.assertTrue(self.win.start_mcp_server())
        token = self.service.token
        self.assertRegex(token, TOKEN_RE)
        port = self.service.status().port
        self.win.restart_state = {"profile": self.win.profile, "dirty": self.win.dirty, "item": self.win.current_item()}
        self.win.destroy()  # what change_theme does
        self.assertFalse(self.service.bridge.attached)
        self.assertTrue(self.service.running)  # the service outlives the window
        state = self.win.restart_state
        settings2 = Settings.load(self.paths.settings_file)
        self.assertEqual(settings2.mcp_token, token)
        win2 = MainWindow(self.paths, self.catalog, state["profile"], self.resources, settings2, service=self.service)
        win2.withdraw()
        self.win = win2  # tearDown destroys the second window
        self.service.configure(self.paths, settings2, win2.save_settings)
        win2.restore_state(state)
        win2.save_settings()
        self.assertEqual(json.loads(self.paths.settings_file.read_text(encoding="utf-8"))["mcp_token"], token)
        self.assertEqual(self.service.token, token)
        self.assertTrue(self.service.running)
        self.assertTrue(self.service.bridge.attached)
        self.assertIn(f"127.0.0.1:{port}", win2.mcp_status_var.get())
        self.assertTrue(win2.mcp_running_var.get())
        client = McpClient(port, token)
        self.in_thread(client.initialize)
        result = self.in_thread(lambda: client.call("get_status"))  # the second window serves the same server
        self.assertFalse(result["isError"], result)
        self.assertEqual(result["structuredContent"]["profile"]["name"], "Office")


class WindowLifecycleTest(McpWindowTestCase):
    def test_destroy_detaches_the_service_and_update_raises_no_error(self) -> None:
        self.assertTrue(self.service.bridge.attached)
        self.assertIsNotNone(self.win.mcp_pump_id)
        self.win.update()  # the pump timer ticks at least once
        self.win.destroy()
        self.assertFalse(self.service.bridge.attached)
        self.assertIsNone(self.win.mcp_pump_id)
        time.sleep(0.1)  # longer than the pump interval: a timer left behind would fire now
        try:
            self.win.update()
        except tk.TclError as exc:
            self.fail(f"update() after destroy raised {exc}")

    def test_a_call_queued_between_two_windows_is_answered_by_the_second(self) -> None:
        from winkickoff.ui.main_window import MainWindow

        box: dict[str, Any] = {}

        def work() -> None:
            try:
                box["result"] = self.service.bridge.run(lambda ws: ws.snapshot().profile.name, writes=False, timeout=20)
            except BaseException as exc:  # noqa: BLE001 - checked on the test thread
                box["error"] = exc

        thread = threading.Thread(target=work, name="mcp-test-client", daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while self.service.bridge._queue.empty() and time.monotonic() < deadline:  # noqa: SLF001 - queued, not yet pumped
            time.sleep(0.01)
        self.assertFalse(self.service.bridge._queue.empty())  # noqa: SLF001
        self.win.restart_state = {"profile": self.win.profile, "dirty": self.win.dirty, "item": self.win.current_item()}
        self.win.destroy()  # no pump ran: the closure waits in the queue for the next window
        self.assertTrue(thread.is_alive())
        win2 = MainWindow(self.paths, self.catalog, self.office_profile(), self.resources,
                          Settings(language="en", theme="light", mcp_port=0), service=self.service)
        win2.withdraw()
        self.win = win2
        self.pump(lambda: not thread.is_alive(), window=win2)
        self.assertNotIn("error", box)
        self.assertEqual(box["result"], "Office")

    def test_a_write_that_started_before_the_client_timeout_completes_and_is_noted(self) -> None:
        client = self.start(MODE_EDIT)
        original = self.win.apply_rule_states

        def slow(items: list[tuple[str, bool]]) -> Any:
            time.sleep(0.6)  # on the main thread: the window is stuck while the closure runs
            return original(items)

        # WRITE_TIMEOUT: how long the client waits for the window; BRIDGE_TIMEOUT: the extra time a started closure gets
        with mock.patch("winkickoff.mcp.tools.WRITE_TIMEOUT", 0.2), \
             mock.patch("winkickoff.mcp.bridge.BRIDGE_TIMEOUT", 0.1), \
             mock.patch.object(self.win, "apply_rule_states", side_effect=slow):
            result = self.set_rules_call(client)
        self.assertTrue(result["isError"])
        structured = result["structuredContent"]
        self.assertEqual(structured["error"], "window_timeout")
        self.assertIsInstance(structured["pending"], int)
        self.assertIn("may still land", structured["message"])
        self.assertTrue(self.win.profile.is_enabled(RULE))  # the change landed after the client gave up
        self.assertTrue(self.win.dirty)
        self.pump(lambda: any("completed after timeout" in e.note for e in self.service.journal.entries()))
        entry = next(e for e in self.service.journal.entries() if "completed after timeout" in e.note)
        self.assertEqual((entry.method, entry.tool, entry.ok), ("tools/call", "set_rules", False))
        self.assertEqual(entry.note, "window_timeout; completed after timeout")

    def test_stop_fails_the_queued_futures(self) -> None:
        self.assertTrue(self.win.start_mcp_server())  # stop() drains the queue of a running server
        box: dict[str, Any] = {}

        def work() -> None:
            try:
                box["result"] = self.service.bridge.run(lambda ws: ws.snapshot(), writes=False, timeout=20)
            except BaseException as exc:  # noqa: BLE001 - checked on the test thread
                box["error"] = exc

        thread = threading.Thread(target=work, name="mcp-test-client", daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while self.service.bridge._queue.empty() and time.monotonic() < deadline:  # noqa: SLF001 - never pumped
            time.sleep(0.01)
        self.service.stop()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(box.get("error"), RuntimeError)
        self.assertEqual(str(box["error"]), "server stopped")
        self.assertFalse(self.service.running)


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(10)
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            stream.close()


class ClipboardTest(McpWindowTestCase):
    def next_line(self, lines: queue.Queue[str], *, pump: bool, timeout: float = 15.0) -> str:
        """The next line of the viewer; with pump the window handles its messages meanwhile."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                return lines.get(timeout=0.02)
            except queue.Empty:
                if pump:
                    self.win.update()
        self.fail("the clipboard viewer did not answer")

    def clipboard(self) -> str:
        """The system clipboard as Tk sees it after its event loop ran: a Win32 copy takes the ownership from
        Tk, which notices it (WM_DESTROYCLIPBOARD) only on the next update. Right after a copy the clipboard
        service of Windows (and the clipboard history, where it is on) opens the clipboard for a moment, so a read
        refused with "cannot be opened" is repeated for a few seconds."""
        deadline = time.monotonic() + 5
        while True:
            self.win.update()
            try:
                return self.win.clipboard_get()
            except tk.TclError as exc:
                if "cannot be opened" not in str(exc) or time.monotonic() > deadline:
                    raise
            time.sleep(0.05)

    def test_copy_mcp_config_stdio_puts_json_into_the_clipboard(self) -> None:
        self.win.copy_mcp_config("stdio")
        entry = json.loads(self.clipboard())["mcpServers"]["winkickoff"]
        self.assertEqual(entry["args"], ["-m", "winkickoff", "--mcp", "stdio"])  # read mode: no --mode flag
        self.assertTrue(entry["command"].lower().endswith("python.exe"))
        self.assertEqual(entry["env"], {"PYTHONPATH": str(self.paths.root)})
        self.assertIn("stdio", self.win.status_var.get())
        self.service.set_mode(MODE_FILES)
        self.win.copy_mcp_config("stdio")
        args = json.loads(self.clipboard())["mcpServers"]["winkickoff"]["args"]
        self.assertEqual(args[-2:], ["--mode", "edit"])  # files never appears in a snippet
        self.assertNotIn("files", args)

    def test_copy_mcp_config_http_refuses_while_stopped_and_works_while_running(self) -> None:
        self.win.clipboard_clear()
        self.win.clipboard_append("untouched")
        self.win.copy_mcp_config("http")
        self.assertEqual(self.clipboard(), "untouched")
        self.assertIn("Start the server first", self.win.status_var.get())
        self.assertTrue(self.win.start_mcp_server())
        port = self.service.status().port
        self.win.copy_mcp_config("http")
        entry = json.loads(self.clipboard())["mcpServers"]["winkickoff"]
        self.assertEqual(entry, {"type": "http", "url": f"http://127.0.0.1:{port}/mcp",
                                 "headers": {"Authorization": f"Bearer {self.service.token}"}})
        self.assertIn("access token copied", self.win.status_var.get())

    def test_copy_mcp_token_generates_the_token_when_missing(self) -> None:
        self.assertEqual(self.service.token, "")
        self.win.copy_mcp_token()
        token = self.clipboard()
        self.assertRegex(token, TOKEN_RE)
        self.assertEqual(token, self.service.token)
        self.assertEqual(json.loads(self.paths.settings_file.read_text(encoding="utf-8"))["mcp_token"], token)

    @unittest.skipUnless(sys.platform == "win32", "Win32 clipboard formats")
    def test_the_token_is_kept_out_of_the_clipboard_history(self) -> None:
        import ctypes

        from winkickoff.ui.clipboard import EXCLUSION_FORMATS

        user32 = ctypes.windll.user32
        formats = [user32.RegisterClipboardFormatW(name) for name in EXCLUSION_FORMATS]
        self.win.copy_mcp_token()
        self.assertEqual(self.clipboard(), self.service.token)
        for name, fmt in zip(EXCLUSION_FORMATS, formats):
            with self.subTest(format=name):
                self.assertTrue(user32.IsClipboardFormatAvailable(fmt))
        self.win.copy_mcp_config("stdio")  # plain text without the token: Tk's clipboard, no exclusion formats
        self.assertFalse(user32.IsClipboardFormatAvailable(formats[0]))
        self.assertTrue(self.win.start_mcp_server())
        self.win.copy_mcp_config("http")  # holds the token: excluded again
        self.assertIn(self.service.token, self.clipboard())
        self.assertTrue(user32.IsClipboardFormatAvailable(formats[0]))

    @unittest.skipUnless(sys.platform == "win32", "Win32 clipboard")
    def test_a_busy_clipboard_copies_nothing(self) -> None:
        """A plain copy would put the token into the clipboard history: when the clipboard stays busy, nothing is
        copied and the status bar says so."""
        from winkickoff.ui import clipboard

        self.win.clipboard_clear()
        self.win.clipboard_append("untouched")
        with mock.patch.object(clipboard, "_copy_excluded", side_effect=OSError("held")):
            self.assertFalse(clipboard.copy_secret(self.win, "secret-text"))
            self.win.copy_mcp_token()
        self.assertEqual(self.clipboard(), "untouched")
        self.assertIn("clipboard is busy", self.win.status_var.get())

    @unittest.skipUnless(sys.platform == "win32", "Win32 clipboard")
    def test_a_viewer_waiting_for_tk_does_not_block_the_copy(self) -> None:
        """The failure seen on a PC with the clipboard history switched on. After a plain copy Tk owns the clipboard
        with delayed rendering; a viewer (the history service) opens the clipboard and waits until Tk renders the
        text, which happens on this thread. copy_secret must deliver that request while it waits for the clipboard,
        otherwise the viewer keeps it open until copy_secret gives up."""
        import ctypes

        from winkickoff.ui.clipboard import EXCLUSION_FORMATS, copy_secret

        self.win.clipboard_clear()
        self.win.clipboard_append("plain text")  # Tk announces CF_UNICODETEXT and renders it on request
        # the viewer is another process: threads of one process do not lock each other out of the clipboard
        viewer = subprocess.Popen([sys.executable, "-c", CLIPBOARD_VIEWER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, encoding="ascii")
        self.addCleanup(stop_process, viewer)
        lines: queue.Queue[str] = queue.Queue()

        def read_lines() -> None:
            try:
                for line in viewer.stdout:  # type: ignore[union-attr]
                    lines.put(line.strip())
            except (OSError, ValueError):
                pass  # the pipe was closed by the cleanup

        threading.Thread(target=read_lines, name="clipboard-viewer-output", daemon=True).start()
        # While the viewer waits for the clipboard, Tk keeps answering: the real clipboard history of this PC may be
        # reading the text Tk has just published, and it holds the clipboard until Tk renders that text.
        self.assertEqual(self.next_line(lines, pump=True), "open", "another program holds the clipboard")
        viewer.stdin.write("go\n")  # type: ignore[union-attr]
        viewer.stdin.flush()  # type: ignore[union-attr]
        # Tk does not pump any more: copy_secret must deliver the viewer's request itself while it waits
        self.assertTrue(copy_secret(self.win, "secret-value"))
        self.assertEqual(self.next_line(lines, pump=False), "read")
        excluded = ctypes.windll.user32.RegisterClipboardFormatW(EXCLUSION_FORMATS[0])
        self.assertTrue(ctypes.windll.user32.IsClipboardFormatAvailable(excluded))
        self.assertEqual(self.clipboard(), "secret-value")


class ShowItemWindowTest(McpWindowTestCase):
    def test_show_item_clears_an_active_search(self) -> None:
        client = self.start(MODE_EDIT)
        self.win.search_var.set("onedrive")
        self.pump(lambda: not self.win.tree.exists("data:accounts"))  # the filtered tree holds only matching rules
        result = self.in_thread(lambda: client.call("show_item", {"item": "data:accounts"}))
        self.assertEqual(result["structuredContent"], {"shown": True})
        self.assertEqual(self.win.search_var.get(), "")
        self.assertTrue(self.win.tree.exists("data:accounts"))
        self.assertEqual(self.win.current_item(), "data:accounts")
        result = self.in_thread(lambda: client.call("show_item", {"item": "r:no.such.rule"}))
        self.assertEqual(result["structuredContent"], {"shown": False, "reason": "no such item"})


class PortInUseTest(McpWindowTestCase):
    def test_a_taken_port_offers_a_new_token(self) -> None:
        squatter = socket.socket()
        squatter.bind(("127.0.0.1", 0))
        squatter.listen(1)
        self.addCleanup(squatter.close)
        self.settings.mcp_port = squatter.getsockname()[1]
        old = self.service.ensure_token()
        with mock.patch.object(self.win, "_dialog", return_value=True) as dialog:
            self.assertFalse(self.win.start_mcp_server())
        self.assertIs(dialog.call_args.args[0], messagebox.askyesno)
        self.assertIn("access token", dialog.call_args.args[2])
        self.assertNotEqual(self.service.token, old)
        self.assertRegex(self.service.token, TOKEN_RE)
        self.assertFalse(self.service.running)
        rotated = self.service.token
        with mock.patch.object(self.win, "_dialog", return_value=False):
            self.assertFalse(self.win.start_mcp_server())
        self.assertEqual(self.service.token, rotated)


class PumpResilienceTest(McpWindowTestCase):
    def test_the_pump_survives_a_failing_status_refresh(self) -> None:
        client = self.start()
        with mock.patch.object(self.win, "refresh_mcp_status", side_effect=RuntimeError("widget gone")):
            result = self.in_thread(lambda: client.call("get_status"))
            self.assertFalse(result["isError"])
        result = self.in_thread(lambda: client.call("get_status"))
        self.assertFalse(result["isError"])
        self.assertIsNotNone(self.win.mcp_pump_id)


class MonitorTest(McpWindowTestCase):
    def open_monitor(self) -> Any:
        """open_mcp_monitor() without showing anything: the Toplevel is withdrawn before its first update."""
        from winkickoff.ui.mcp_window import McpMonitor

        with mock.patch.object(McpMonitor, "deiconify"), mock.patch.object(McpMonitor, "lift"):
            self.win.open_mcp_monitor()
        monitor = self.win.mcp_monitor
        monitor.withdraw()
        self.win.update()
        return monitor

    def rows(self, monitor: Any) -> list[tuple[str, ...]]:
        return [tuple(str(v) for v in monitor.tree.item(iid, "values")) for iid in monitor.tree.get_children("")]

    def test_monitor_opens_and_shows_a_row_per_request(self) -> None:
        client = self.start()
        monitor = self.open_monitor()
        self.assertTrue(monitor.winfo_exists())
        self.assertIn("Running on http://127.0.0.1:", monitor.state_var.get())
        self.assertEqual(str(monitor.start_button.cget("text")), "Stop")
        self.in_thread(lambda: client.call("get_status"))
        self.in_thread(lambda: client.call("get_profile"))
        self.pump(lambda: {"get_status", "get_profile"} <= {row[4] for row in self.rows(monitor)})
        rows = self.rows(monitor)
        self.assertEqual([row[3] for row in rows], ["initialize", "notifications/initialized", "tools/call", "tools/call"])
        self.assertEqual({row[1] for row in rows}, {"http"})
        self.assertEqual({row[2] for row in rows}, {"window-test 1"})
        self.assertEqual([row[7] for row in rows], ["ok"] * 4)
        self.assertIn("clients seen: 1", monitor.state_var.get())
        with mock.patch("winkickoff.ui.mcp_window.McpMonitor.deiconify"), mock.patch("winkickoff.ui.mcp_window.McpMonitor.lift"):
            self.win.open_mcp_monitor()  # a second call reuses the window
        self.assertIs(self.win.mcp_monitor, monitor)

    def test_monitor_hides_the_token_and_the_password(self) -> None:
        from winkickoff.ui.mcp_window import masked

        client = self.start(MODE_EDIT)
        monitor = self.open_monitor()
        self.in_thread(lambda: client.call("get_profile"))
        self.in_thread(lambda: client.call("set_profile_info", {"name": PASSWORD, "comment": PASSWORD}))  # free text
        self.pump(lambda: "set_profile_info" in {row[4] for row in self.rows(monitor)})
        self.assertEqual(self.win.profile.name, PASSWORD)
        joined = "\n".join(widget_texts(monitor))
        token = self.service.token
        self.assertNotIn(token, joined)
        self.assertNotIn(PASSWORD, joined)
        self.assertIn(masked(token), joined)
        self.assertEqual(masked(token), f"{token[:4]}...{token[-4:]}")
        row = next(row for row in self.rows(monitor) if row[4] == "set_profile_info")
        self.assertEqual(row[5], f"name=<text, {len(PASSWORD)} chars> comment=<text, {len(PASSWORD)} chars>")

    def test_monitor_filters_and_copies_visible_rows(self) -> None:
        client = self.start()
        monitor = self.open_monitor()
        self.in_thread(lambda: client.call("get_status"))
        self.set_rules_call(client)  # read mode: an error row
        self.pump(lambda: "set_rules" in {row[4] for row in self.rows(monitor)})
        total = len(self.rows(monitor))
        self.assertEqual(total, 4)
        monitor.filter_var.set("set_rules")
        self.assertEqual([row[4] for row in self.rows(monitor)], ["set_rules"])
        iid = monitor.tree.get_children("")[0]
        self.assertEqual(self.rows(monitor)[0][7], "mode_required")
        self.assertIn("error", monitor.tree.item(iid, "tags"))
        monitor.filter_var.set("")
        self.assertEqual(len(self.rows(monitor)), total)
        monitor.errors_var.set(True)
        monitor.render()
        self.assertEqual([row[4] for row in self.rows(monitor)], ["set_rules"])
        monitor.errors_var.set(False)
        monitor.transport_var.set("stdio")
        monitor.render()
        self.assertEqual(self.rows(monitor), [])
        monitor.transport_var.set("all")
        monitor.render()
        self.assertEqual(len(self.rows(monitor)), total)
        monitor.copy_rows()
        clip = self.win.clipboard_get()
        lines = clip.split("\n")
        self.assertEqual(len(lines), total)
        self.assertTrue(any("get_status" in line and "\tok" in line for line in lines), lines)
        self.assertNotIn(self.service.token, clip)
        self.assertIn("Copied to the clipboard", self.win.status_var.get())
        monitor.tree.selection_set(iid)
        monitor.copy_row()
        self.assertIn("set_rules", self.win.clipboard_get())
        self.assertNotIn("\n", self.win.clipboard_get())
        monitor.clear()
        self.assertEqual(self.rows(monitor), [])

    def test_monitor_hide_withdraws_and_destroy_cancels_its_timer(self) -> None:
        monitor = self.open_monitor()
        monitor.hide()  # the close box of the window
        self.assertEqual(monitor.state(), "withdrawn")
        self.assertTrue(monitor.winfo_exists())
        self.assertIsNotNone(monitor._after_id)  # noqa: SLF001 - the refresh timer
        monitor.destroy()
        self.assertIsNone(monitor._after_id)  # noqa: SLF001
        self.assertFalse(monitor.winfo_exists())
        time.sleep(0.3)  # longer than the refresh interval: a timer left behind would fire now
        self.win.update()
        reopened = self.open_monitor()
        self.assertIsNot(reopened, monitor)
        self.assertTrue(reopened.winfo_exists())

    def test_monitor_controls_start_the_server_and_change_the_settings(self) -> None:
        monitor = self.open_monitor()
        self.assertEqual(monitor.state_var.get(), "Stopped")
        self.assertIn("disabled", monitor.copy_http.state())
        monitor.toggle()
        self.assertTrue(self.service.running)
        self.assertIn("Running on http://127.0.0.1:", monitor.state_var.get())
        self.assertIn("disabled", monitor.port_box.state())
        self.assertNotIn("disabled", monitor.copy_http.state())
        monitor.mode_var.set(monitor.mode_titles[MODE_EDIT])
        monitor.mode_changed()
        self.assertEqual(self.service.mode, MODE_EDIT)
        self.assertEqual(self.win.mcp_mode_var.get(), MODE_EDIT)
        monitor.autostart_var.set(True)
        monitor.autostart_changed()
        self.assertTrue(self.win.settings.mcp_autostart)
        self.assertTrue(json.loads(self.paths.settings_file.read_text(encoding="utf-8"))["mcp_autostart"])
        monitor.toggle()
        self.assertFalse(self.service.running)
        self.assertEqual(monitor.state_var.get(), "Stopped")
        self.assertNotIn("disabled", monitor.port_box.state())
        monitor.port_var.set("80")  # below 1024: refused, the setting stays
        monitor.port_changed()
        self.assertEqual(self.win.settings.mcp_port, 0)
        self.assertEqual(monitor.port_var.get(), "0")
        self.assertIn("The port must be 0 or 1024 to 65535", self.win.status_var.get())


@unittest.skipUnless(TK_OK, "Tk is not available")
class CreateAppTest(unittest.TestCase):
    """app.create_app on a temporary program folder: the service is configured, autostart honoured."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name) / "WinKickOff"
        self.paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                              output=base / "output", logs=base / "logs")
        for folder in (self.paths.profiles, self.paths.output, self.paths.logs):
            folder.mkdir(parents=True)
        self.windows: list[Any] = []

    def tearDown(self) -> None:
        for win in self.windows:
            try:
                win.destroy()
            except tk.TclError:
                pass
        for handler in list(logging.getLogger().handlers):
            if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename).is_relative_to(self.paths.root):
                logging.getLogger().removeHandler(handler)
                handler.close()
        self._tmp.cleanup()
        i18n.set_language("en")

    def write_settings(self, **extra: Any) -> None:
        """settings.json in the program folder: English and the light theme (create_app follows Windows otherwise)."""
        data = {"language": "en", "theme": "light", "mcp_port": 0, **extra}
        self.paths.settings_file.write_text(json.dumps(data), encoding="utf-8")

    def create(self, service: McpService | None = None) -> Any:
        from winkickoff import app

        with mock.patch.object(app, "app_paths", return_value=self.paths), mock.patch.object(app, "_enable_dpi_awareness"):
            win = app.create_app(withdraw=True, service=service)
        self.windows.append(win)
        return win

    def test_autostart_starts_the_server_in_read_mode(self) -> None:
        self.write_settings(mcp_autostart=True)
        service = McpService()
        try:
            win = self.create(service)
            self.assertTrue(service.running)
            self.assertEqual(service.mode, MODE_READ)
            self.assertIs(service.settings, win.settings)
            self.assertEqual(service.on_save, win.save_settings)
            self.assertTrue(service.bridge.attached)
            self.assertIsNotNone(win.mcp_pump_id)
            port = service.status().port
            self.assertGreater(port, 0)
            self.assertIn(f"127.0.0.1:{port}", win.mcp_status_var.get())
            self.assertIn("Read only", win.mcp_status_var.get())
            self.assertTrue(win.mcp_running_var.get())
            self.assertTrue(win.mcp_autostart_var.get())
            saved = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
            self.assertRegex(saved["mcp_token"], TOKEN_RE)
            self.assertEqual(saved["mcp_token"], service.token)
            service.stop()
            self.assertFalse(service.running)
        finally:
            service.stop()

    def test_without_autostart_the_service_is_attached_but_stopped(self) -> None:
        self.write_settings()
        service = McpService()
        try:
            win = self.create(service)
            self.assertFalse(service.running)
            self.assertTrue(service.bridge.attached)
            self.assertEqual(win.mcp_status_var.get(), "MCP: off")
            self.assertEqual(service.token, "")  # no server, no token
        finally:
            service.stop()

    def test_create_app_without_a_service_has_no_pump_and_shows_mcp_off(self) -> None:
        self.write_settings()
        win = self.create()
        self.assertIsNone(win.service)
        self.assertIsNone(win.mcp_pump_id)
        self.assertEqual(win.mcp_status_var.get(), "MCP: off")
        menu = win.mcp_menu
        states = {str(menu.entrycget(i, "label")): str(menu.entrycget(i, "state"))
                  for i in range(menu.index("end") + 1) if menu.type(i) != "separator"}
        self.assertEqual(states.pop("Documentation"), "normal")
        self.assertEqual(set(states.values()), {"disabled"})


if __name__ == "__main__":
    unittest.main()
