"""core/settings.py: the MCP fields of settings.json (port, access token, autostart) and valid_port (T22)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from winkickoff.core.settings import DEFAULT_MCP_PORT, TOKEN_RE, Settings, valid_port

TOKEN = "a" * 43  # what secrets.token_urlsafe(32) gives in length


class McpSettingsDefaultsTest(unittest.TestCase):
    def test_defaults(self) -> None:
        settings = Settings()
        self.assertEqual(settings.mcp_port, DEFAULT_MCP_PORT)
        self.assertEqual(settings.mcp_port, 47831)
        self.assertEqual(settings.mcp_token, "")
        self.assertIs(settings.mcp_autostart, False)

    def test_a_missing_file_gives_the_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings.load(Path(folder) / "settings.json")
        self.assertEqual((settings.mcp_port, settings.mcp_token, settings.mcp_autostart), (DEFAULT_MCP_PORT, "", False))


class McpSettingsLoadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "settings.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def load(self, **fields: object) -> Settings:
        self.file.write_text(json.dumps(fields), encoding="utf-8")
        return Settings.load(self.file)

    def test_damaged_port_falls_back_to_the_default(self) -> None:
        for value in ("80", True, False, 70000, -1, 1023, 65536, 1.5, None, [47831]):
            with self.subTest(value=value):
                self.assertEqual(self.load(mcp_port=value).mcp_port, DEFAULT_MCP_PORT)

    def test_valid_ports_are_kept(self) -> None:
        for value in (0, 1024, 8080, 47831, 65535):
            with self.subTest(value=value):
                self.assertEqual(self.load(mcp_port=value).mcp_port, value)

    def test_damaged_token_falls_back_to_empty(self) -> None:
        for value in ("short", "x" * 31, "x" * 65, "a" * 40 + " ab", "a" * 40 + "+/=", 12345, None, True, [TOKEN]):
            with self.subTest(value=value):
                self.assertEqual(self.load(mcp_token=value).mcp_token, "")

    def test_valid_tokens_are_kept(self) -> None:
        for value in (TOKEN, "A" * 32, "z" * 64, "aB3_-" * 8):
            with self.subTest(value=value):
                self.assertEqual(self.load(mcp_token=value).mcp_token, value)

    def test_autostart_is_true_only_for_a_json_true(self) -> None:
        for value in ("true", "yes", 1, None, [], {}):
            with self.subTest(value=value):
                self.assertIs(self.load(mcp_autostart=value).mcp_autostart, False)
        self.assertIs(self.load(mcp_autostart=True).mcp_autostart, True)

    def test_missing_fields_give_the_defaults(self) -> None:
        settings = self.load(geometry="1200x800+0+0")
        self.assertEqual((settings.mcp_port, settings.mcp_token, settings.mcp_autostart), (DEFAULT_MCP_PORT, "", False))

    def test_round_trip_keeps_the_fields(self) -> None:
        settings = Settings(mcp_port=0, mcp_token=TOKEN, mcp_autostart=True)
        settings.save(self.file)
        loaded = Settings.load(self.file)
        self.assertEqual((loaded.mcp_port, loaded.mcp_token, loaded.mcp_autostart), (0, TOKEN, True))
        self.assertEqual(loaded, settings)
        data = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual((data["mcp_port"], data["mcp_token"], data["mcp_autostart"]), (0, TOKEN, True))
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ["settings.json"])

    def test_round_trip_of_the_defaults(self) -> None:
        Settings().save(self.file)
        self.assertEqual(Settings.load(self.file), Settings())


class ValidPortTest(unittest.TestCase):
    def test_zero_and_the_registered_and_dynamic_range(self) -> None:
        for value in (0, 1024, 47831, 65535):
            with self.subTest(value=value):
                self.assertTrue(valid_port(value))

    def test_out_of_range_and_wrong_types(self) -> None:
        for value in (-1, 1, 1023, 65536, True, False, "80", "47831", 1.0, 47831.5, None, [0]):
            with self.subTest(value=value):
                self.assertFalse(valid_port(value))

    def test_token_pattern(self) -> None:
        self.assertIsNotNone(TOKEN_RE.match(TOKEN))
        self.assertIsNone(TOKEN_RE.match("short"))
        self.assertIsNone(TOKEN_RE.match(TOKEN + " "))
    def test_token_with_a_trailing_newline_is_refused(self) -> None:
        # "$" of a pattern also matches before a trailing newline with re.match: the settings use fullmatch
        self.assertIsNone(TOKEN_RE.fullmatch(TOKEN + "\n"))
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "settings.json"
            file.write_text(json.dumps({"mcp_token": TOKEN + "\n"}), encoding="utf-8")
            self.assertEqual(Settings.load(file).mcp_token, "")


if __name__ == "__main__":
    unittest.main()
