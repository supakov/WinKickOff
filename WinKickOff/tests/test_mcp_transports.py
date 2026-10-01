"""mcp/stdio.py, mcp/cli.py and mcp/httpserver.py: the transports and the command line of the MCP server (T22).

Everything runs in memory or on 127.0.0.1 port 0 and writes only into temporary folders. The two subprocess tests
start python -X importtime on this package with an empty stdin and remove the log file the stdio run creates.
Nothing here opens a window, runs PowerShell or touches the settings of this PC.
"""

from __future__ import annotations

import dataclasses
import http.client
import io
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest import mock

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core import i18n
from winkickoff.core.catalog import Catalog, load_catalog
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources
from winkickoff.core.settings import DEFAULT_MCP_PORT, TOKEN_RE, Settings
from winkickoff.mcp import MAX_CONCURRENT, MAX_MESSAGE_BYTES, MAX_SESSIONS, PROTOCOL_VERSION, cli
from winkickoff.mcp.bridge import InlineBridge
from winkickoff.mcp.httpserver import McpHttpServer, serve, start_http
from winkickoff.mcp.protocol import McpServer, Session
from winkickoff.mcp.service import McpService, client_config
from winkickoff.mcp.stdio import open_std_streams, serve_stdio
from winkickoff.mcp.workspace import HeadlessWorkspace

ROOT = Path(__file__).resolve().parents[1]
OFFICE = ROOT / "profiles" / "preset-office.json"
STRICT = ROOT / "profiles" / "preset-strict.json"
TOKEN = "T" * 40
OTHER_TOKEN = "U" * 40
INIT_PARAMS = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "tests", "version": "1"}}


# --------------------------------------------------------------------------- fixtures


@lru_cache(maxsize=None)
def real_catalog() -> Catalog:
    return load_catalog(ROOT / "rules", docs_root=ROOT.parent)


@lru_cache(maxsize=None)
def real_resources() -> Resources:
    return Resources.load(ROOT / "resources")


def make_paths(base: Path) -> AppPaths:
    """Program folder in a temporary folder, data from the repository (as tests/test_ui_smoke.py does)."""
    paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles", output=base / "output",
                     logs=base / "logs")
    for folder in (paths.profiles, paths.output, paths.logs):
        folder.mkdir(parents=True, exist_ok=True)
    return paths


def make_service(paths: AppPaths, transport: str, token: str = TOKEN) -> tuple[McpService, McpServer]:
    """A service on a HeadlessWorkspace with the Office preset and the server it builds for the transport."""
    profile, _ = Profile.load(OFFICE, real_catalog())
    workspace = HeadlessWorkspace(paths, real_catalog(), profile, real_resources(), APP_VERSION)
    service = McpService()
    service.configure(paths, Settings(mcp_token=token))
    service.bridge = InlineBridge(workspace)
    return service, service.build_server(transport, has_window=False)


def request(request_id: object, method: str, params: dict | None = None) -> dict:
    message: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def notification(method: str) -> dict:
    return {"jsonrpc": "2.0", "method": method}


def encode(*messages: dict) -> bytes:
    """Messages as stdio lines."""
    return b"".join(json.dumps(message).encode("utf-8") + b"\n" for message in messages)


def detach_file_handlers() -> None:
    """Remove the rotating file handler that setup_logging installed, so the next test gets a fresh one."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()


# --------------------------------------------------------------------------- stdio


class StdioTransportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = make_paths(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def replies(self, raw: bytes) -> list[dict]:
        """One JSON object per line; every line ends with a single newline and holds no carriage return."""
        if not raw:
            return []
        self.assertTrue(raw.endswith(b"\n"), raw[-20:])
        lines = raw[:-1].split(b"\n")
        for line in lines:
            self.assertNotIn(b"\r", line)
            self.assertTrue(line.startswith(b"{"), line[:40])
        return [json.loads(line) for line in lines]

    def run_session(self, data: bytes) -> tuple[int, list[dict], bytes]:
        _, server = make_service(self.paths, "stdio")
        writer = io.BytesIO()
        code = serve_stdio(io.BytesIO(data), writer, server, Session("stdio", "stdio"))
        return code, self.replies(writer.getvalue()), writer.getvalue()

    def test_full_session_writes_one_json_object_per_line(self) -> None:
        data = encode(request(1, "initialize", INIT_PARAMS), request(2, "tools/list"),
                      notification("notifications/initialized"), request(3, "tools/call", {"name": "get_status"}),
                      request(4, "ping"))
        code, replies, raw = self.run_session(data)
        self.assertEqual(code, 0)
        self.assertEqual(raw.count(b"\n"), 4, "four requests, one notification: four lines")
        self.assertEqual([reply["id"] for reply in replies], [1, 2, 3, 4])
        self.assertEqual(replies[0]["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "winkickoff")
        self.assertIn("get_status", {tool["name"] for tool in replies[1]["result"]["tools"]})
        self.assertFalse(replies[2]["result"]["isError"])
        status = replies[2]["result"]["structuredContent"]
        self.assertEqual(status["transport"], "stdio")
        self.assertEqual(status["mode"], "read")
        self.assertFalse(status["has_window"])
        self.assertEqual(status["profile"]["name"], "Office")
        self.assertEqual(replies[3]["result"], {})

    def test_tools_list_before_initialized_notification_succeeds(self) -> None:
        _, replies, _ = self.run_session(encode(request(1, "initialize", INIT_PARAMS), request(2, "tools/list")))
        self.assertIn("result", replies[1])
        self.assertNotIn("error", replies[1])

    def test_notification_alone_writes_nothing(self) -> None:
        code, replies, raw = self.run_session(encode(notification("notifications/initialized")))
        self.assertEqual(code, 0)
        self.assertEqual(replies, [])
        self.assertEqual(raw, b"")

    def test_client_response_message_writes_nothing(self) -> None:
        _, _, raw = self.run_session(encode({"jsonrpc": "2.0", "id": 7, "result": {}}))
        self.assertEqual(raw, b"")

    def test_invalid_utf8_gives_parse_error_with_null_id_and_loop_continues(self) -> None:
        _, replies, _ = self.run_session(b"\xff\xfe{}\n" + encode(request(5, "ping")))
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertIsNone(replies[0]["id"])
        self.assertEqual(replies[1], {"jsonrpc": "2.0", "id": 5, "result": {}})

    def test_invalid_json_gives_parse_error_with_null_id_and_loop_continues(self) -> None:
        _, replies, _ = self.run_session(b"{not json\n" + encode(request(6, "ping")))
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertIsNone(replies[0]["id"])
        self.assertEqual(replies[1]["id"], 6)

    def test_over_long_line_gives_one_parse_error_and_never_answers_its_tail(self) -> None:
        tail = json.dumps(request("tail", "ping")).encode("utf-8")
        line = b"x" * (MAX_MESSAGE_BYTES + 10 - len(tail)) + tail
        self.assertEqual(len(line), MAX_MESSAGE_BYTES + 10)
        _, replies, _ = self.run_session(line + b"\n" + encode(request("after", "ping")))
        self.assertEqual(len(replies), 2, replies)
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertIsNone(replies[0]["id"])
        self.assertIn(str(MAX_MESSAGE_BYTES), replies[0]["error"]["message"])
        self.assertEqual(replies[1], {"jsonrpc": "2.0", "id": "after", "result": {}})
        self.assertNotIn("tail", [reply["id"] for reply in replies])

    def test_over_long_line_at_eof_without_newline_gives_one_parse_error(self) -> None:
        _, replies, _ = self.run_session(b"y" * (MAX_MESSAGE_BYTES + 10))
        self.assertEqual([reply["error"]["code"] for reply in replies], [-32700])

    def test_blank_lines_are_skipped(self) -> None:
        _, replies, _ = self.run_session(b"\n   \n\r\n" + encode(request(8, "ping")) + b"\n\t\n")
        self.assertEqual([reply["id"] for reply in replies], [8])

    def test_line_with_carriage_return_is_parsed(self) -> None:
        _, replies, _ = self.run_session(json.dumps(request(9, "ping")).encode("utf-8") + b"\r\n")
        self.assertEqual(replies[0]["result"], {})

    def test_immediate_eof_returns_zero_and_writes_nothing(self) -> None:
        code, _, raw = self.run_session(b"")
        self.assertEqual(code, 0)
        self.assertEqual(raw, b"")

    def test_broken_pipe_on_write_ends_the_loop_with_zero(self) -> None:
        _, server = make_service(self.paths, "stdio")
        writer = mock.Mock()
        writer.write.side_effect = BrokenPipeError()
        code = serve_stdio(io.BytesIO(encode(request(1, "ping"), request(2, "ping"))), writer, server, Session("stdio", "stdio"))
        self.assertEqual(code, 0)
        self.assertEqual(writer.write.call_count, 1)

    def test_open_std_streams_returns_none_without_streams_and_descriptors(self) -> None:
        with mock.patch("sys.stdin", None), mock.patch("winkickoff.mcp.stdio.os.fstat", side_effect=OSError(9, "bad fd")):
            self.assertIsNone(open_std_streams())

    def test_open_std_streams_falls_back_to_descriptors_zero_and_one(self) -> None:
        reader, writer = io.BytesIO(), io.BytesIO()
        with mock.patch("sys.stdin", None), mock.patch("winkickoff.mcp.stdio.os.fstat", return_value=None), \
                mock.patch("winkickoff.mcp.stdio.os.fdopen", side_effect=[reader, writer]) as fdopen:
            self.assertEqual(open_std_streams(), (reader, writer))
        self.assertEqual([call.args[0] for call in fdopen.call_args_list], [0, 1])

    def test_open_std_streams_returns_the_buffers_of_text_streams(self) -> None:
        stdin, stdout = io.TextIOWrapper(io.BytesIO(b"")), io.TextIOWrapper(io.BytesIO())
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout):
            streams = open_std_streams()
        self.assertIsNotNone(streams)
        self.assertIs(streams[0], stdin.buffer)
        self.assertIs(streams[1], stdout.buffer)
        if hasattr(sys.stdin, "buffer") and hasattr(sys.stdout, "buffer"):  # the real streams of this process
            real = open_std_streams()
            self.assertIsNotNone(real)
            self.assertIs(real[0], sys.stdin.buffer)
            self.assertIs(real[1], sys.stdout.buffer)


# --------------------------------------------------------------------------- command line


class CliArgumentsTest(unittest.TestCase):
    def parse(self, argv: list[str]):
        with mock.patch("sys.stderr", io.StringIO()):  # argparse writes its message there
            return cli.parse_args(argv)

    def assert_exit_2(self, argv: list[str]) -> None:
        with self.assertRaises(SystemExit) as caught:
            self.parse(argv)
        self.assertEqual(caught.exception.code, 2, argv)

    def test_parse_args_every_flag(self) -> None:
        args, extras = cli.parse_args(["--mcp", "http", "--port", "0", "--token", TOKEN, "--mode", "files", "--profile", "office",
                                       "--language", "uk", "--mcp-config", "http", "--version"])
        self.assertEqual(args.mcp, "http")
        self.assertEqual(args.port, 0)
        self.assertEqual(args.token, TOKEN)
        self.assertEqual(args.mode, "files")
        self.assertEqual(args.profile, "office")
        self.assertEqual(args.language, "uk")
        self.assertEqual(args.mcp_config, "http")
        self.assertTrue(args.version)
        self.assertEqual(extras, [])

    def test_help_exits_zero_without_the_window_path(self) -> None:
        from winkickoff.__main__ import main

        with mock.patch("sys.stdout", io.StringIO()) as out, mock.patch.dict(sys.modules, {"winkickoff.app": None}):
            self.assertEqual(main(["--help"]), 0)  # the window module (and its error box) is never imported
        self.assertIn("--mcp", out.getvalue())

    def test_defaults_mode_read_and_nothing_else(self) -> None:
        args, extras = cli.parse_args(["--mcp", "stdio"])
        self.assertEqual(args.mode, "read")
        self.assertIsNone(args.port)
        self.assertIsNone(args.token)
        self.assertIsNone(args.profile)
        self.assertIsNone(args.language)
        self.assertIsNone(args.mcp_config)
        self.assertFalse(args.version)
        self.assertEqual(extras, [])

    def test_mcp_and_mode_accept_only_their_choices(self) -> None:
        self.assert_exit_2(["--mcp", "tcp"])
        self.assert_exit_2(["--mode", "admin"])
        self.assert_exit_2(["--mcp-config", "sse"])

    def test_port_out_of_range_exits_2(self) -> None:
        for value in ("80", "1023", "65536", "-1", "abc", "1.5"):
            self.assert_exit_2(["--port", value])

    def test_port_boundaries_are_accepted(self) -> None:
        for value in (0, 1024, 65535):
            self.assertEqual(cli.parse_args(["--port", str(value)])[0].port, value)

    def test_token_of_wrong_shape_exits_2(self) -> None:
        for value in ("short", "A" * 31, "A" * 65, "A" * 30 + "!!", "A" * 20 + " " + "B" * 20, "A" * 39 + "."):
            self.assert_exit_2(["--token", value])

    def test_token_of_right_shape_is_accepted(self) -> None:
        for value in ("a" * 32, "Z" * 64, "abc_DEF-123" * 4):
            self.assertEqual(cli.parse_args(["--token", value])[0].token, value)

    def test_extras_are_allowed_on_the_window_path(self) -> None:
        args, extras = cli.parse_args(["C:\\somewhere\\profile.json", "--mode", "edit"])
        self.assertEqual(extras, ["C:\\somewhere\\profile.json"])
        self.assertEqual(args.mode, "edit")
        self.assertIsNone(args.mcp)

    def test_extras_are_refused_with_the_headless_flags(self) -> None:
        self.assert_exit_2(["--mcp", "stdio", "C:\\somewhere\\profile.json"])
        self.assert_exit_2(["--mcp-config", "stdio", "extra"])
        self.assert_exit_2(["--mcp=http", "--what"])

    def test_abbreviated_flags_are_not_accepted(self) -> None:
        args, extras = cli.parse_args(["--vers"])
        self.assertFalse(args.version)
        self.assertEqual(extras, ["--vers"])

    def test_is_headless(self) -> None:
        for argv in (["--mcp", "stdio"], ["--mcp=http"], ["--mcp-config", "stdio"], ["--mcp-config=http"], ["--version"],
                     ["profile.json", "--version"]):
            self.assertTrue(cli.is_headless(argv), argv)
        for argv in ([], ["profile.json"], ["--mode", "edit"], ["--port", "0"], ["--token", TOKEN], ["--mcpx"]):
            self.assertFalse(cli.is_headless(argv), argv)

    def test_emit_without_stdout_returns_false_and_logs(self) -> None:
        with mock.patch("sys.stdout", None), self.assertLogs("winkickoff.mcp.cli", level="ERROR") as logs:
            self.assertFalse(cli.emit("hello"))
        self.assertIn("no console", logs.output[0])

    def test_emit_writes_one_line_per_call(self) -> None:
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            self.assertTrue(cli.emit("hello"))
            self.assertTrue(cli.emit("two\n"))
        self.assertEqual(out.getvalue(), "hello\ntwo\n")

    def test_housekeep_logs_removes_stale_mcp_logs_and_keeps_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            stale, fresh, rolled, main = (logs / "mcp-stdio-1.log", logs / "mcp-stdio-2.log", logs / "mcp-http-3.log.1",
                                          logs / "winkickoff.log")
            for path in (stale, fresh, rolled, main):
                path.write_text("x", encoding="utf-8")
            old = time.time() - 8 * 86400
            for path in (stale, rolled, main):
                os.utime(path, (old, old))
            cli.housekeep_logs(logs)
            self.assertFalse(stale.exists(), "a stale headless log is removed")
            self.assertFalse(rolled.exists(), "a stale rollover is removed")
            self.assertTrue(fresh.exists(), "a fresh headless log stays")
            self.assertTrue(main.exists(), "winkickoff.log is never touched")

    def test_housekeep_logs_keeps_a_log_just_under_the_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp-stdio-4.log"
            path.write_text("x", encoding="utf-8")
            recent = time.time() - (cli.LOG_KEEP_DAYS * 86400 - 3600)
            os.utime(path, (recent, recent))
            cli.housekeep_logs(Path(tmp))
            self.assertTrue(path.exists())

    def test_housekeep_logs_tolerates_a_missing_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cli.housekeep_logs(Path(tmp) / "absent")

    def test_main_defaults_to_a_stdio_server(self) -> None:
        with mock.patch.object(cli, "run_headless", return_value=0) as run:
            self.assertEqual(cli.main([]), 0)
            self.assertEqual(run.call_args.args[0].mcp, "stdio")
            self.assertEqual(cli.main(["--mode", "edit"]), 0)
            self.assertEqual(run.call_args.args[0].mcp, "stdio")
            self.assertEqual(run.call_args.args[0].mode, "edit")

    def test_main_passes_explicit_headless_flags_through(self) -> None:
        with mock.patch.object(cli, "run_headless", return_value=0) as run:
            self.assertEqual(cli.main(["--version"]), 0)
            self.assertTrue(run.call_args.args[0].version)
            self.assertIsNone(run.call_args.args[0].mcp)

    def test_main_returns_2_for_a_bad_argument(self) -> None:
        with mock.patch("sys.stderr", io.StringIO()), mock.patch.object(cli, "run_headless") as run:
            self.assertEqual(cli.main(["--port", "80"]), 2)
            self.assertEqual(cli.main(["--mcp", "stdio", "extra"]), 2)
        run.assert_not_called()


class CliHeadlessTest(unittest.TestCase):
    """run_headless in this process: the paths point into a temporary folder, the streams are BytesIO objects."""

    SESSION = encode(request(1, "initialize", INIT_PARAMS), notification("notifications/initialized"),
                     request(2, "tools/call", {"name": "get_status"}))

    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.paths = make_paths(self.tmp)
        root = logging.getLogger()
        self.addCleanup(root.setLevel, root.level)
        self.addCleanup(logging.captureWarnings, False)
        self.addCleanup(detach_file_handlers)  # before the temporary folder goes: the handler holds the file open
        detach_file_handlers()
        self.enterContext(mock.patch("winkickoff.core.paths.app_paths", return_value=self.paths))
        self.save = self.enterContext(mock.patch.object(Settings, "save", autospec=True,
                                                        side_effect=AssertionError("a headless process never writes settings")))
        self.stdout = io.StringIO()
        self.enterContext(mock.patch("sys.stdout", self.stdout))

    def headless(self, argv: list[str], stdin: bytes = b"") -> tuple[int, bytes]:
        """run_headless with in-memory standard streams; any import of tkinter or of winkickoff.app fails."""
        args, _ = cli.parse_args(argv)
        writer = io.BytesIO()
        with mock.patch("winkickoff.mcp.stdio.open_std_streams", return_value=(io.BytesIO(stdin), writer)), \
                mock.patch.dict(sys.modules, {"tkinter": None, "_tkinter": None, "winkickoff.app": None}):
            code = cli.run_headless(args)
        return code, writer.getvalue()

    @staticmethod
    def status_of(raw: bytes) -> dict:
        replies = [json.loads(line) for line in raw.splitlines()]
        return replies[1]["result"]["structuredContent"]

    def log_names(self) -> list[str]:
        return sorted(path.name for path in self.paths.logs.iterdir())

    def own_log(self) -> Path:
        return self.paths.logs / f"mcp-stdio-{os.getpid()}.log"

    # ----------------------------------------------------------------- --version and --mcp-config

    def test_version_prints_name_and_version_and_logs_nothing(self) -> None:
        code, _ = self.headless(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(self.stdout.getvalue(), f"{APP_NAME} {APP_VERSION}\n")
        self.assertEqual(self.log_names(), [])

    def test_version_without_a_console_exits_3(self) -> None:
        with mock.patch("sys.stdout", None), self.assertLogs("winkickoff.mcp.cli", level="ERROR"):
            code, _ = self.headless(["--version"])
        self.assertEqual(code, 3)

    def test_mcp_config_stdio_is_json_whose_command_is_python_exe(self) -> None:
        with mock.patch("sys.executable", "C:\\Tools\\Python\\pythonw.exe"):
            code, _ = self.headless(["--mcp-config", "stdio"])
        self.assertEqual(code, 0)
        entry = json.loads(self.stdout.getvalue())["mcpServers"]["winkickoff"]
        self.assertEqual(entry["command"], "C:\\Tools\\Python\\python.exe")
        self.assertEqual(entry["args"], ["-m", "winkickoff", "--mcp", "stdio"])
        self.assertEqual(entry["env"], {"PYTHONPATH": str(self.paths.root)})
        self.assertEqual(self.log_names(), [])

    def test_mcp_config_stdio_carries_the_mode_but_never_files(self) -> None:
        self.headless(["--mcp-config", "stdio", "--mode", "edit"])
        entry = json.loads(self.stdout.getvalue())["mcpServers"]["winkickoff"]
        self.assertEqual(entry["args"][-2:], ["--mode", "edit"])
        text = client_config("stdio", paths=self.paths, port=0, token="", mode="files")
        self.assertNotIn("files", json.loads(text)["mcpServers"]["winkickoff"]["args"])

    def test_mcp_config_http_uses_loopback_url_and_token(self) -> None:
        code, _ = self.headless(["--mcp-config", "http", "--token", TOKEN, "--port", "1234"])
        self.assertEqual(code, 0)
        entry = json.loads(self.stdout.getvalue())["mcpServers"]["winkickoff"]
        self.assertEqual(entry, {"type": "http", "url": "http://127.0.0.1:1234/mcp", "headers": {"Authorization": f"Bearer {TOKEN}"}})

    def test_mcp_config_http_defaults_to_the_settings_port(self) -> None:
        self.headless(["--mcp-config", "http"])
        entry = json.loads(self.stdout.getvalue())["mcpServers"]["winkickoff"]
        self.assertEqual(entry["url"], f"http://127.0.0.1:{DEFAULT_MCP_PORT}/mcp")

    # ----------------------------------------------------------------- --mcp stdio

    def test_stdio_session_logs_into_its_own_file_only(self) -> None:
        code, raw = self.headless(["--mcp", "stdio", "--language", "en"], self.SESSION)
        self.assertEqual(code, 0)
        status = self.status_of(raw)
        self.assertEqual(status["transport"], "stdio")
        self.assertEqual(status["mode"], "read")
        self.assertEqual(status["language"], "en")
        self.assertEqual(status["profile"]["name"], "Office")
        self.assertEqual(self.log_names(), [self.own_log().name])
        self.assertIn("mcp stdio server started", self.own_log().read_text(encoding="utf-8"))
        self.assertFalse((self.paths.logs / "winkickoff.log").exists())
        self.assertFalse(self.paths.settings_file.exists())
        self.save.assert_not_called()
        self.assertEqual(self.stdout.getvalue(), "", "nothing but protocol lines on stdout")

    def test_stdio_mode_flag_reaches_the_server(self) -> None:
        _, raw = self.headless(["--mcp", "stdio", "--mode", "edit", "--language", "en"], self.SESSION)
        self.assertEqual(self.status_of(raw)["mode"], "edit")

    def test_stdio_catalog_error_exits_2_without_tkinter(self) -> None:
        broken = AppPaths(root=self.tmp, data=self.tmp / "data", docs_root=ROOT.parent, profiles=self.paths.profiles,
                          output=self.paths.output, logs=self.paths.logs)
        broken.rules.mkdir(parents=True)
        (broken.rules / "groups.toml").write_text("[broken\n", encoding="utf-8")
        with mock.patch("winkickoff.core.paths.app_paths", return_value=broken):
            code, raw = self.headless(["--mcp", "stdio", "--language", "en"], self.SESSION)
        self.assertEqual(code, 2)
        self.assertEqual(raw, b"")
        self.assertEqual(self.log_names(), [self.own_log().name])
        text = self.own_log().read_text(encoding="utf-8")
        self.assertIn("start-up failed", text)
        self.assertIn("catalog", text)

    def test_stdio_profile_by_preset_id(self) -> None:
        code, raw = self.headless(["--mcp", "stdio", "--language", "en", "--profile", "strict"], self.SESSION)
        self.assertEqual(code, 0)
        self.assertEqual(self.status_of(raw)["profile"]["name"], "Strict")

    def test_stdio_profile_by_saved_name(self) -> None:
        profile, _ = Profile.load(OFFICE, real_catalog())
        profile.name = "Kasa"
        profile.save(self.paths.profiles / "Kasa.json", real_catalog())
        code, raw = self.headless(["--mcp", "stdio", "--language", "en", "--profile", "Kasa"], self.SESSION)
        self.assertEqual(code, 0)
        status = self.status_of(raw)
        self.assertEqual(status["profile"]["name"], "Kasa")
        self.assertEqual(Path(status["profile"]["file"]), Path("profiles") / "Kasa.json")

    def test_stdio_profile_by_absolute_path(self) -> None:
        code, raw = self.headless(["--mcp", "stdio", "--language", "en", "--profile", str(STRICT)], self.SESSION)
        self.assertEqual(code, 0)
        self.assertEqual(self.status_of(raw)["profile"]["name"], "Strict")

    def test_stdio_refused_profile_name_exits_2(self) -> None:
        for name in ("..", "a/b", "preset-office"):
            with self.subTest(name=name):
                code, raw = self.headless(["--mcp", "stdio", "--language", "en", "--profile", name], self.SESSION)
                self.assertEqual(code, 2)
                self.assertEqual(raw, b"")
        self.assertIn("profile name refused", self.own_log().read_text(encoding="utf-8"))

    def test_stdio_missing_profile_exits_2(self) -> None:
        code, raw = self.headless(["--mcp", "stdio", "--language", "en", "--profile", "nothere"], self.SESSION)
        self.assertEqual(code, 2)
        self.assertEqual(raw, b"")

    def test_stdio_without_standard_streams_exits_3(self) -> None:
        args, _ = cli.parse_args(["--mcp", "stdio", "--language", "en"])
        with mock.patch("winkickoff.mcp.stdio.open_std_streams", return_value=None):
            self.assertEqual(cli.run_headless(args), 3)
        self.assertIn("no standard streams", self.own_log().read_text(encoding="utf-8"))

    # ----------------------------------------------------------------- --mcp http

    def test_http_without_token_exits_2_before_binding(self) -> None:
        args, _ = cli.parse_args(["--mcp", "http", "--language", "en"])
        with mock.patch("winkickoff.mcp.httpserver.start_http", side_effect=AssertionError("bind attempted")):
            self.assertEqual(cli.run_headless(args), 2)
        self.assertIn("no access token", self.stdout.getvalue())
        self.save.assert_not_called()

    def test_http_bind_failure_exits_2(self) -> None:
        args, _ = cli.parse_args(["--mcp", "http", "--language", "en", "--token", TOKEN, "--port", "0"])
        with mock.patch("winkickoff.mcp.httpserver.start_http", side_effect=OSError("taken")):
            self.assertEqual(cli.run_headless(args), 2)
        self.assertIn("not available", self.stdout.getvalue())

    def test_http_serves_on_loopback_until_interrupted(self) -> None:
        args, _ = cli.parse_args(["--mcp", "http", "--language", "en", "--token", TOKEN, "--port", "0"])
        seen: list[McpHttpServer] = []

        def interrupted(httpd: McpHttpServer) -> None:
            seen.append(httpd)
            raise KeyboardInterrupt

        with mock.patch("winkickoff.mcp.httpserver.serve", side_effect=interrupted):
            self.assertEqual(cli.run_headless(args), 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].server_address[0], "127.0.0.1")
        self.assertEqual(seen[0].token, TOKEN)
        self.assertIn(f"http://127.0.0.1:{seen[0].port}/mcp", self.stdout.getvalue())
        with self.assertRaises(OSError):  # server_close ran: the listening socket is closed
            seen[0].socket.getsockname()


class HeadlessSubprocessTest(unittest.TestCase):
    """python -X importtime -m winkickoff: the headless paths never load tkinter (T22, section 3.6)."""

    def run_python(self, *argv: str) -> tuple[int, int, bytes, str]:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen([sys.executable, "-X", "importtime", "-m", "winkickoff", *argv], cwd=str(ROOT), env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = proc.communicate(input=b"", timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        return proc.pid, proc.returncode, out, err.decode("utf-8", "replace")

    @staticmethod
    def imported(trace: str) -> list[str]:
        """Module names of the importtime trace ("import time: self | cumulative | name")."""
        return [line.rsplit("|", 1)[-1].strip() for line in trace.splitlines() if line.startswith("import time:")]

    def assert_no_tkinter(self, names: list[str]) -> None:
        self.assertIn("winkickoff.mcp.cli", names, "the trace is present and the headless path ran")
        offenders = [name for name in names if name in ("tkinter", "_tkinter") or name.startswith("tkinter.")]
        self.assertEqual(offenders, [])

    def test_version_subprocess_never_imports_tkinter(self) -> None:
        _, code, out, err = self.run_python("--version")
        self.assertEqual(code, 0, err[-2000:])
        self.assertEqual(out.decode("utf-8").strip(), f"{APP_NAME} {APP_VERSION}")
        self.assert_no_tkinter(self.imported(err))

    def test_stdio_subprocess_never_imports_tkinter_and_logs_into_its_own_file(self) -> None:
        pid, code, out, err = self.run_python("--mcp", "stdio", "--profile", str(OFFICE))
        log = ROOT / "logs" / f"mcp-stdio-{pid}.log"
        self.addCleanup(lambda: log.unlink(missing_ok=True))
        self.assertEqual(code, 0, err[-2000:])
        self.assertEqual(out, b"", "an empty stdin gives an empty stdout")
        self.assert_no_tkinter(self.imported(err))
        self.assertTrue(log.is_file(), "the headless process logs into logs/mcp-stdio-<pid>.log")
        self.assertIn("mcp stdio server started", log.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- HTTP


@dataclasses.dataclass
class Reply:
    status: int
    headers: http.client.HTTPMessage
    body: bytes

    def json(self) -> dict:
        return json.loads(self.body.decode("utf-8"))


RESET_RETRIES = 5


class HttpClientCase(unittest.TestCase):
    """http.client against a server on 127.0.0.1 (allowed in tests/); self.port names the server.

    An answer the server sends before it read the request body (401, 403, 406, 415, 503 and so on) closes the socket
    with unread bytes; Windows turns that close into a reset and the client may lose the answer (WinError 10053 or
    10054). Such a reset is retried a few times, so the tests check the status codes, not that race.
    """

    port: int

    def exchange(self, conn: http.client.HTTPConnection, send) -> Reply:
        send()
        response = conn.getresponse()
        return Reply(response.status, response.headers, response.read())

    def retrying(self, port: int | None, send) -> Reply:
        """send(conn) on a fresh connection, repeated when the answer was lost to a reset."""
        for attempt in range(RESET_RETRIES):
            conn = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=5)
            try:
                return self.exchange(conn, lambda: send(conn))
            except ConnectionError:
                if attempt == RESET_RETRIES - 1:
                    raise
                time.sleep(0.05)
            finally:
                conn.close()
        raise AssertionError("unreachable")

    def send(self, method: str = "POST", path: str = "/mcp", *, body: bytes | None = None, headers: dict | None = None,
             token: str | None = TOKEN, session: str | None = None, port: int | None = None) -> Reply:
        sent: dict[str, str] = {}
        if token is not None:
            sent["Authorization"] = f"Bearer {token}"
        if body is not None:
            sent["Content-Type"] = "application/json"
        if session is not None:
            sent["Mcp-Session-Id"] = session
        sent.update(headers or {})
        return self.retrying(port, lambda conn: conn.request(method, path, body=body, headers=sent))

    def send_headers_only(self, headers: dict, port: int | None = None) -> Reply:
        """A POST with exactly these headers besides Host and Authorization: no Content-Length unless given."""

        def send(conn: http.client.HTTPConnection) -> None:
            conn.putrequest("POST", "/mcp")
            conn.putheader("Authorization", f"Bearer {TOKEN}")
            for name, value in headers.items():
                conn.putheader(name, value)
            conn.endheaders()

        return self.retrying(port, send)

    def post(self, message: dict, **kw) -> Reply:
        return self.send(body=json.dumps(message).encode("utf-8"), **kw)

    def initialize(self, **kw) -> tuple[Reply, str]:
        reply = self.post(request(1, "initialize", INIT_PARAMS), **kw)
        return reply, reply.headers.get("Mcp-Session-Id") or ""


class HttpTransportTest(HttpClientCase):
    """One server for the class: every test makes its own sessions."""

    @classmethod
    def setUpClass(cls) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = make_paths(Path(cls.tmp.name))
        cls.service, cls.server = make_service(cls.paths, "http")
        cls.httpd = start_http(0, TOKEN, cls.server)
        cls.thread = threading.Thread(target=serve, args=(cls.httpd,), name="test-mcp-http", daemon=True)
        cls.thread.start()
        if not cls.httpd.serving.wait(5):
            raise RuntimeError("the serving thread did not start")
        cls.port = cls.httpd.port

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(5)
        cls.tmp.cleanup()

    # ----------------------------------------------------------------- the happy path

    def test_initialize_returns_json_a_session_and_close_headers(self) -> None:
        reply, session = self.initialize()
        self.assertEqual(reply.status, 200)
        self.assertTrue(reply.headers.get("Content-Type", "").startswith("application/json"))
        self.assertTrue(session)
        self.assertEqual(reply.headers.get("Connection"), "close")
        self.assertEqual(reply.headers.get("Cache-Control"), "no-store")
        self.assertEqual(int(reply.headers.get("Content-Length")), len(reply.body))
        self.assertEqual(reply.json()["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(reply.json()["id"], 1)

    def test_server_header_is_the_program_name_without_a_version(self) -> None:
        reply, _ = self.initialize()
        server = reply.headers.get("Server", "")
        self.assertEqual(server.strip(), "WinKickOff")
        self.assertNotIn("Python", server)
        self.assertNotIn("/", server)

    def test_tools_list_on_a_new_session_before_initialized_succeeds(self) -> None:
        _, session = self.initialize()
        reply = self.post(request(2, "tools/list"), session=session)
        self.assertEqual(reply.status, 200)
        self.assertIn("get_status", {tool["name"] for tool in reply.json()["result"]["tools"]})

    def test_initialized_notification_gets_202_with_an_empty_body(self) -> None:
        _, session = self.initialize()
        reply = self.post(notification("notifications/initialized"), session=session)
        self.assertEqual(reply.status, 202)
        self.assertEqual(reply.body, b"")
        self.assertEqual(reply.headers.get("Content-Length"), "0")
        self.assertIsNone(reply.headers.get("Content-Type"))
        self.assertEqual(reply.headers.get("Connection"), "close")

    def test_tools_call_get_status_reports_the_http_transport(self) -> None:
        _, session = self.initialize()
        reply = self.post(request(3, "tools/call", {"name": "get_status"}), session=session)
        self.assertEqual(reply.status, 200)
        result = reply.json()["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["transport"], "http")
        self.assertEqual(result["structuredContent"]["mode"], "read")
        self.assertFalse(result["structuredContent"]["has_window"])
        self.assertEqual(result["structuredContent"]["profile"]["name"], "Office")

    def test_ping_without_a_session_id_is_answered(self) -> None:
        reply = self.post(request(4, "ping"))
        self.assertEqual(reply.status, 200)
        self.assertEqual(reply.json(), {"jsonrpc": "2.0", "id": 4, "result": {}})
        self.assertIsNone(reply.headers.get("Mcp-Session-Id"))

    # ----------------------------------------------------------------- token, origin, host

    def test_missing_token_gives_401_with_an_empty_body_and_no_challenge(self) -> None:
        reply = self.post(request(4, "ping"), token=None)
        self.assertEqual(reply.status, 401)
        self.assertEqual(reply.body, b"")
        self.assertIsNone(reply.headers.get("WWW-Authenticate"))
        self.assertEqual(reply.headers.get("Connection"), "close")

    def test_wrong_token_or_scheme_gives_401(self) -> None:
        self.assertEqual(self.post(request(4, "ping"), token=OTHER_TOKEN).status, 401)
        self.assertEqual(self.post(request(4, "ping"), token=TOKEN[:-1]).status, 401)
        self.assertEqual(self.post(request(4, "ping"), token=None, headers={"Authorization": f"Basic {TOKEN}"}).status, 401)
        self.assertEqual(self.post(request(4, "ping"), token="").status, 401)

    def test_foreign_origin_gives_403(self) -> None:
        self.assertEqual(self.post(request(4, "ping"), headers={"Origin": "http://evil.example"}).status, 403)
        self.assertEqual(self.post(request(4, "ping"), headers={"Origin": f"http://evil.example:{self.port}"}).status, 403)
        self.assertEqual(self.post(request(4, "ping"), headers={"Origin": f"https://127.0.0.1:{self.port}"}).status, 403)

    def test_null_origin_gives_403(self) -> None:
        reply = self.post(request(4, "ping"), headers={"Origin": "null"})
        self.assertEqual(reply.status, 403)
        self.assertEqual(reply.body, b"")

    def test_loopback_origins_are_accepted(self) -> None:
        self.assertEqual(self.post(request(4, "ping"), headers={"Origin": f"http://127.0.0.1:{self.port}"}).status, 200)
        self.assertEqual(self.post(request(4, "ping"), headers={"Origin": f"http://localhost:{self.port}"}).status, 200)
        self.assertEqual(self.post(request(4, "ping"), headers={"Origin": f"HTTP://127.0.0.1:{self.port}"}).status, 200)

    def test_foreign_host_gives_421(self) -> None:
        self.assertEqual(self.post(request(4, "ping"), headers={"Host": f"evil.example:{self.port}"}).status, 421)
        self.assertEqual(self.post(request(4, "ping"), headers={"Host": "127.0.0.1"}).status, 421)
        self.assertEqual(self.post(request(4, "ping"), headers={"Host": f"127.0.0.1:{self.port + 1}"}).status, 421)

    def test_localhost_host_is_accepted(self) -> None:
        self.assertEqual(self.post(request(4, "ping"), headers={"Host": f"localhost:{self.port}"}).status, 200)
        self.assertEqual(self.post(request(4, "ping"), headers={"Host": f"LOCALHOST:{self.port}"}).status, 200)

    def test_host_is_checked_before_the_token(self) -> None:
        reply = self.post(request(4, "ping"), token=None, headers={"Host": f"evil.example:{self.port}"})
        self.assertEqual(reply.status, 421)

    # ----------------------------------------------------------------- methods and paths

    def test_get_head_options_put_and_patch_give_405_with_allow(self) -> None:
        for method in ("GET", "HEAD", "OPTIONS", "PUT", "PATCH"):
            with self.subTest(method=method):
                reply = self.send(method)
                self.assertEqual(reply.status, 405)
                self.assertEqual(reply.headers.get("Allow"), "POST, DELETE")
                self.assertEqual(reply.body, b"")

    def test_get_without_a_token_is_401_not_405(self) -> None:
        self.assertEqual(self.send("GET", token=None).status, 401)

    def test_unknown_paths_give_404_with_an_empty_body(self) -> None:
        for path in ("/other", "/.well-known/oauth-protected-resource", "/mcp/", "/", "/mcp?x=1"):
            with self.subTest(path=path):
                reply = self.post(request(4, "ping"), path=path)
                self.assertEqual(reply.status, 404)
                self.assertEqual(reply.body, b"")

    # ----------------------------------------------------------------- bodies

    def test_array_body_gives_400_invalid_request(self) -> None:
        reply = self.send(body=b"[]")
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.json()["error"]["code"], -32600)
        self.assertIsNone(reply.json()["id"])

    def test_bad_json_gives_400_parse_error(self) -> None:
        reply = self.send(body=b"{")
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.json()["error"]["code"], -32700)

    def test_two_megabyte_body_is_received_in_full_and_gets_413(self) -> None:
        reply = self.send(body=b"x" * 2_000_000)
        self.assertEqual(reply.status, 413)
        self.assertEqual(reply.body, b"")

    def test_body_just_over_the_limit_gets_413_and_at_the_limit_is_parsed(self) -> None:
        self.assertEqual(self.send(body=b"{" + b" " * MAX_MESSAGE_BYTES).status, 413)
        padded = json.dumps(request(4, "ping")).encode("utf-8")
        padded = padded + b" " * (MAX_MESSAGE_BYTES - len(padded))
        self.assertEqual(self.send(body=padded).status, 200)

    def test_chunked_transfer_gives_411(self) -> None:
        reply = self.send_headers_only({"Transfer-Encoding": "chunked", "Content-Type": "application/json"})
        self.assertEqual(reply.status, 411)

    def test_missing_content_length_gives_411(self) -> None:
        reply = self.send_headers_only({"Content-Type": "application/json"})
        self.assertEqual(reply.status, 411)

    def test_non_numeric_content_length_gives_400(self) -> None:
        reply = self.send_headers_only({"Content-Type": "application/json", "Content-Length": "many"})
        self.assertEqual(reply.status, 400)

    def test_signed_or_odd_content_length_gives_400(self) -> None:
        for value in ("-5", "-1", "+5", "5_0", "0x10"):  # trailing spaces are stripped by every header parser
            with self.subTest(value=value):
                reply = self.send_headers_only({"Content-Type": "application/json", "Content-Length": value})
                self.assertEqual(reply.status, 400)

    def test_a_malformed_notification_gets_400_without_a_body(self) -> None:
        _, session = self.initialize()
        body = b'{"jsonrpc":"2.0","method":"notifications/cancelled","params":null}'
        reply = self.send(body=body, session=session)
        self.assertEqual((reply.status, reply.body), (400, b""))
        body = b'{"jsonrpc":"2.0","method":"notifications/cancelled","params":{}}'
        self.assertEqual(self.send(body=body, session=session).status, 202)

    def test_text_plain_gives_415(self) -> None:
        reply = self.send(body=b"{}", headers={"Content-Type": "text/plain"})
        self.assertEqual(reply.status, 415)

    def test_accept_text_html_gives_406_and_json_or_any_is_accepted(self) -> None:
        self.assertEqual(self.post(request(4, "ping"), headers={"Accept": "text/html"}).status, 406)
        self.assertEqual(self.post(request(4, "ping"), headers={"Accept": "application/json"}).status, 200)
        self.assertEqual(self.post(request(4, "ping"), headers={"Accept": "application/json, text/event-stream"}).status, 200)
        self.assertEqual(self.post(request(4, "ping"), headers={"Accept": "*/*"}).status, 200)

    def test_protocol_version_header(self) -> None:
        reply = self.post(request(4, "ping"), headers={"MCP-Protocol-Version": "1.0"})
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.body, b"")
        for version in ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"):
            with self.subTest(version=version):
                self.assertEqual(self.post(request(4, "ping"), headers={"MCP-Protocol-Version": version}).status, 200)
        self.assertEqual(self.post(request(4, "ping")).status, 200, "absent is accepted")

    # ----------------------------------------------------------------- sessions

    def test_request_without_a_session_gives_400(self) -> None:
        reply = self.post(request(2, "tools/list"))
        self.assertEqual(reply.status, 400)
        self.assertEqual(reply.json()["error"]["code"], -32600)
        self.assertIn("Mcp-Session-Id", reply.json()["error"]["message"])
        self.assertEqual(reply.json()["id"], 2)

    def test_notification_without_a_session_gives_400(self) -> None:
        self.assertEqual(self.post(notification("notifications/initialized")).status, 400)

    def test_unknown_session_gives_404(self) -> None:
        reply = self.post(request(2, "tools/list"), session="nope")
        self.assertEqual(reply.status, 404)
        self.assertEqual(reply.body, b"")
        self.assertEqual(self.post(request(4, "ping"), session="nope").status, 404, "a ping with a session id must match one")

    def test_delete_ends_the_session_then_404(self) -> None:
        _, session = self.initialize()
        self.assertEqual(self.post(request(2, "tools/list"), session=session).status, 200)
        reply = self.send("DELETE", session=session)
        self.assertEqual(reply.status, 204)
        self.assertEqual(reply.body, b"")
        self.assertEqual(self.send("DELETE", session=session).status, 404)
        self.assertEqual(self.post(request(2, "tools/list"), session=session).status, 404)
        self.assertEqual(self.send("DELETE").status, 404, "DELETE without a session id")
        self.assertEqual(self.send("DELETE", session=session, token=None).status, 401)

    def test_seventeenth_initialize_evicts_the_oldest_session(self) -> None:
        _, first = self.initialize()
        self.assertEqual(self.post(request(2, "tools/list"), session=first).status, 200)
        sessions = [self.initialize()[1] for _ in range(MAX_SESSIONS)]
        self.assertEqual(self.post(request(2, "tools/list"), session=first).status, 404)
        self.assertEqual(self.post(request(2, "tools/list"), session=sessions[-1]).status, 200)
        self.assertLessEqual(len(self.httpd.sessions), MAX_SESSIONS)
        self.assertNotIn(first, self.httpd.sessions)

    def test_every_response_carries_connection_close_and_no_store(self) -> None:
        _, session = self.initialize()
        replies = [self.initialize()[0], self.post(notification("notifications/initialized"), session=session),
                   self.post(request(4, "ping"), token=None), self.post(request(4, "ping"), path="/other"),
                   self.send("GET"), self.post(request(2, "tools/list"), session="nope"), self.send(body=b"[]")]
        for reply in replies:
            with self.subTest(status=reply.status):
                self.assertEqual(reply.headers.get("Connection"), "close")
                self.assertEqual(reply.headers.get("Cache-Control"), "no-store")
                self.assertEqual(int(reply.headers.get("Content-Length")), len(reply.body))


class HttpLifecycleTest(HttpClientCase):
    """Servers started and stopped inside one test: capacity, eviction, shutdown, binding, the service, the journal."""

    def setUp(self) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        self.paths = make_paths(Path(self.enterContext(tempfile.TemporaryDirectory())))

    def start(self, token: str = TOKEN) -> tuple[McpHttpServer, McpServer]:
        _, server = make_service(self.paths, "http", token)
        httpd = start_http(0, token, server)
        thread = threading.Thread(target=serve, args=(httpd,), name="test-mcp-http", daemon=True)
        thread.start()
        self.assertTrue(httpd.serving.wait(5))
        self.addCleanup(self.stop, httpd, thread)
        self.port = httpd.port
        return httpd, server

    @staticmethod
    def stop(httpd: McpHttpServer, thread: threading.Thread) -> None:
        if httpd.serving.is_set():
            httpd.shutdown()
        httpd.server_close()
        thread.join(5)

    def test_connections_beyond_the_cap_are_closed_unanswered(self) -> None:
        from winkickoff.mcp.httpserver import MAX_CONNECTIONS

        httpd, _ = self.start()
        held = [httpd.connections.acquire(blocking=False) for _ in range(MAX_CONNECTIONS)]
        self.assertTrue(all(held))
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
                sock.sendall(b"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n")
                try:
                    data = sock.recv(100)
                except ConnectionError:
                    data = b""
            self.assertEqual(data, b"")
        finally:
            for _ in held:
                httpd.connections.release()
        self.assertEqual(self.initialize()[0].status, 200)

    def test_stop_marks_the_server_closed(self) -> None:
        service, _ = make_service(self.paths, "http")
        service.start_http(0)
        server = service.server
        self.assertIsNotNone(server)
        self.assertFalse(server.closed)  # type: ignore[union-attr]
        service.stop()
        self.assertTrue(server.closed)  # type: ignore[union-attr]
        session = Session(id="late", transport="http")
        response = server.handle(request(1, "initialize", INIT_PARAMS), session)  # type: ignore[union-attr]
        self.assertEqual(response["error"]["code"], -32600)

    def test_503_with_retry_after_when_every_slot_is_busy(self) -> None:
        httpd, server = self.start()
        gate = threading.Event()
        spec = server.tools.specs["get_status"]
        server.tools.specs["get_status"] = dataclasses.replace(spec, handler=lambda ctx, args: gate.wait(10) and {"blocked": True})
        self.addCleanup(server.tools.specs.__setitem__, "get_status", spec)
        self.addCleanup(gate.set)
        _, session = self.initialize()
        statuses: list[int] = []

        def worker() -> None:
            statuses.append(self.post(request(9, "tools/call", {"name": "get_status"}), session=session).status)

        workers = [threading.Thread(target=worker, daemon=True) for _ in range(MAX_CONCURRENT)]
        for thread in workers:
            thread.start()
        deadline = time.monotonic() + 5
        while httpd.slots._value > 0 and time.monotonic() < deadline:  # noqa: SLF001 - the free slots of the semaphore
            time.sleep(0.02)
        self.assertEqual(httpd.slots._value, 0, "all slots are taken by the blocked calls")
        reply = self.post(request(10, "ping"), session=session)
        self.assertEqual(reply.status, 503)
        self.assertEqual(reply.headers.get("Retry-After"), "1")
        self.assertEqual(reply.body, b"")
        gate.set()
        for thread in workers:
            thread.join(15)
        self.assertEqual(statuses, [200] * MAX_CONCURRENT)
        self.assertEqual(self.post(request(11, "ping")).status, 200, "the slots are free again")

    def test_shutdown_returns_within_three_seconds_with_an_idle_client(self) -> None:
        httpd, _ = self.start()
        idle = socket.create_connection(("127.0.0.1", httpd.port), timeout=5)
        self.addCleanup(idle.close)
        time.sleep(0.2)  # the listener accepts and a handler thread waits for the request line
        started = time.monotonic()
        httpd.shutdown()
        httpd.server_close()
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertFalse(httpd.serving.is_set())

    def test_service_stop_with_a_thread_never_started_returns_at_once(self) -> None:
        service, server = make_service(self.paths, "http")
        service.httpd = start_http(0, TOKEN, server)
        service.thread = threading.Thread(target=lambda: None)
        self.assertFalse(service.running)
        started = time.monotonic()
        service.stop()
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIsNone(service.httpd)
        self.assertIsNone(service.thread)
        service.stop()  # a second stop is a no-op

    def test_second_start_http_on_the_same_port_raises(self) -> None:
        _, server = make_service(self.paths, "http")
        httpd = start_http(0, TOKEN, server)
        self.addCleanup(httpd.server_close)
        with self.assertRaises(OSError):
            start_http(httpd.port, TOKEN, server)

    @unittest.skipUnless(sys.platform == "win32", "SO_EXCLUSIVEADDRUSE is a Windows option")
    def test_exclusive_bind_refuses_a_reuseaddr_socket_on_the_port(self) -> None:
        _, server = make_service(self.paths, "http")
        httpd = start_http(0, TOKEN, server)
        self.addCleanup(httpd.server_close)
        other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(other.close)
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with self.assertRaises(OSError):
            other.bind(("127.0.0.1", httpd.port))

    def test_service_start_generates_a_token_saves_once_and_reports_status(self) -> None:
        profile, _ = Profile.load(OFFICE, real_catalog())
        service = McpService()
        settings = Settings()
        saves = mock.Mock()
        service.configure(self.paths, settings, saves)
        service.bridge = InlineBridge(HeadlessWorkspace(self.paths, real_catalog(), profile, real_resources(), APP_VERSION))
        self.addCleanup(service.stop)
        idle = service.status()
        self.assertEqual((idle.running, idle.port, idle.mode, idle.requests, idle.last_time, idle.sessions, idle.url),
                         (False, DEFAULT_MCP_PORT, "read", 0, "", 0, ""))
        port = service.start_http(0, has_window=False)
        self.assertTrue(TOKEN_RE.match(settings.mcp_token))
        saves.assert_called_once_with()
        self.assertTrue(service.running)
        self.assertEqual(service.start_http(0), port, "a second start returns the running port")
        saves.assert_called_once_with()
        status = service.status()
        self.assertEqual((status.running, status.port, status.mode, status.sessions, status.url),
                         (True, port, "read", 0, f"http://127.0.0.1:{port}/mcp"))
        self.port = port
        reply, _ = self.initialize(token=settings.mcp_token)
        self.assertEqual(reply.status, 200)
        self.assertEqual(self.initialize(token=TOKEN)[0].status, 401, "only the generated token opens the server")
        status = service.status()
        self.assertEqual((status.sessions, status.requests), (1, 1))
        self.assertRegex(status.last_time, r"^\d\d:\d\d:\d\d$")
        config = json.loads(service.client_config("http"))["mcpServers"]["winkickoff"]
        self.assertEqual(config["url"], status.url)
        self.assertIn("127.0.0.1", config["url"])
        self.assertEqual(config["headers"]["Authorization"], f"Bearer {settings.mcp_token}")

    def test_rotate_token_stops_the_server_and_changes_the_token(self) -> None:
        profile, _ = Profile.load(OFFICE, real_catalog())
        service = McpService()
        settings = Settings(mcp_token=TOKEN)
        saves = mock.Mock()
        service.configure(self.paths, settings, saves)
        service.bridge = InlineBridge(HeadlessWorkspace(self.paths, real_catalog(), profile, real_resources(), APP_VERSION))
        self.addCleanup(service.stop)
        port = service.start_http(0, has_window=False)
        saves.assert_not_called()
        new = service.rotate_token()
        self.assertNotEqual(new, TOKEN)
        self.assertTrue(TOKEN_RE.match(new))
        self.assertEqual(settings.mcp_token, new)
        saves.assert_called_once_with()
        self.assertFalse(service.running)
        self.assertEqual(service.status().url, "")
        with self.assertRaises((ConnectionError, OSError)):
            self.post(request(4, "ping"), port=port, token=new)

    def test_service_needs_configuration_before_starting(self) -> None:
        with self.assertRaises(RuntimeError):
            McpService().start_http(0)
        with self.assertRaises(RuntimeError):
            McpService().rotate_token()

    def test_journal_holds_one_entry_per_handled_request_and_no_token(self) -> None:
        _, server = self.start()
        _, session = self.initialize()
        self.assertEqual(self.post(notification("notifications/initialized"), session=session).status, 202)
        self.assertEqual(self.post(request(3, "tools/call", {"name": "get_status"}), session=session).status, 200)
        self.assertEqual(self.post(request(4, "ping")).status, 200)
        self.assertEqual(self.post(request(4, "ping"), token=None).status, 401)
        self.assertEqual(self.send("GET").status, 405)
        self.assertEqual(self.post(request(2, "tools/list"), session="nope").status, 404)
        entries = server.journal.entries()
        self.assertEqual([entry.method for entry in entries], ["initialize", "notifications/initialized", "tools/call", "ping"])
        self.assertEqual([entry.seq for entry in entries], [1, 2, 3, 4])
        self.assertEqual(entries[2].tool, "get_status")
        self.assertEqual(entries[0].client, "tests 1")
        self.assertEqual({entry.transport for entry in entries}, {"http"})
        self.assertTrue(all(entry.ok for entry in entries))
        for entry in entries:
            self.assertNotIn(TOKEN, str(entry))
            self.assertNotIn("Bearer", str(entry))


if __name__ == "__main__":
    unittest.main()
