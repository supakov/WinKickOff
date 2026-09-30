"""mcp/: JSON-RPC parsing, the schema checker, redaction, the journal and McpServer.handle in memory (T22).

Everything runs in memory on the real catalog and the Office preset through a HeadlessWorkspace behind an InlineBridge:
no window, no socket, no PowerShell; the only folder written is a temporary one (and nothing is written into it here).
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from winkickoff.core import i18n
from winkickoff.core.catalog import load_catalog
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Difference, Profile
from winkickoff.core.render import EDITION_KEYS
from winkickoff.core.resources import Resources
from winkickoff.mcp import SUPPORTED_VERSIONS, jsonrpc, redact, schema
from winkickoff.mcp.bridge import InlineBridge
from winkickoff.mcp.errors import RedactionError, ToolError
from winkickoff.mcp.journal import Journal, render_args
from winkickoff.mcp.protocol import INSTRUCTIONS, McpServer, Session, accepted_header_version
from winkickoff.mcp.resources import ResourceRegistry
from winkickoff.mcp.tools import ID_PATTERN, ToolRegistry
from winkickoff.mcp.workspace import HeadlessWorkspace, check_and_build

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "ru", "uk")
TOOL_NAMES = {"get_status", "list_groups", "list_rules", "get_rule", "get_profile", "list_profiles", "diff_profile",
              "check_profile", "preview_build", "get_messages", "set_rules", "set_group", "set_param", "set_profile_info",
              "load_profile", "show_item", "save_profile", "write_answer_file"}
# invisible and control characters, built from code points (rule 9 of AGENTS.md: no escapes in the source)
LINE_SEP = chr(0x2028)
ZERO_WIDTH = chr(0x200B)
RLO = chr(0x202E)  # right-to-left override
ISOLATE = chr(0x2066)  # left-to-right isolate
BOM = chr(0xFEFF)
ACUTE = chr(0x0301)  # combining acute accent
SOLIDUS = chr(0x0338)  # combining long solidus overlay


def paths_in(folder: Path) -> AppPaths:
    paths = AppPaths(root=folder, data=ROOT, docs_root=ROOT.parent, profiles=folder / "profiles",
                     output=folder / "output", logs=folder / "logs")
    for sub in (paths.profiles, paths.output, paths.logs):
        sub.mkdir(parents=True, exist_ok=True)
    return paths


# --------------------------------------------------------------------------- jsonrpc


class ParseMessageTest(unittest.TestCase):
    def refused(self, raw: object, code: int) -> jsonrpc.JsonRpcError:
        with self.assertRaises(jsonrpc.JsonRpcError) as cm:
            jsonrpc.parse_message(raw if isinstance(raw, (bytes, str)) else json.dumps(raw))
        self.assertEqual(cm.exception.code, code)
        return cm.exception

    def test_bad_json_is_a_parse_error(self) -> None:
        self.refused("{not json", jsonrpc.PARSE_ERROR)

    def test_bad_utf8_is_a_parse_error(self) -> None:
        self.refused(b'{"jsonrpc":"2.0","method":"\xff"}', jsonrpc.PARSE_ERROR)

    def test_array_is_refused(self) -> None:
        self.refused([{"jsonrpc": "2.0", "id": 1, "method": "ping"}], jsonrpc.INVALID_REQUEST)

    def test_non_object_is_refused(self) -> None:
        for raw in ("42", '"text"', "true"):
            with self.subTest(raw=raw):
                self.refused(raw, jsonrpc.INVALID_REQUEST)

    def test_null_id_is_refused(self) -> None:
        self.refused({"jsonrpc": "2.0", "id": None, "method": "ping"}, jsonrpc.INVALID_REQUEST)

    def test_boolean_id_is_refused(self) -> None:
        self.refused({"jsonrpc": "2.0", "id": True, "method": "ping"}, jsonrpc.INVALID_REQUEST)

    def test_float_id_is_refused(self) -> None:
        self.refused({"jsonrpc": "2.0", "id": 1.5, "method": "ping"}, jsonrpc.INVALID_REQUEST)

    def test_missing_jsonrpc_is_refused(self) -> None:
        error = self.refused({"id": 1, "method": "ping"}, jsonrpc.INVALID_REQUEST)
        self.assertEqual(error.request_id, 1)

    def test_wrong_jsonrpc_is_refused(self) -> None:
        for value in ("1.0", 2.0, "2.0 "):
            with self.subTest(value=value):
                self.refused({"jsonrpc": value, "id": 1, "method": "ping"}, jsonrpc.INVALID_REQUEST)

    def test_non_string_method_is_refused(self) -> None:
        error = self.refused({"jsonrpc": "2.0", "id": "a", "method": 5}, jsonrpc.INVALID_REQUEST)
        self.assertEqual(error.request_id, "a")

    def test_params_not_an_object_is_invalid_params(self) -> None:
        for params in ([1], "x", 3, None):
            with self.subTest(params=params):
                error = self.refused({"jsonrpc": "2.0", "id": 7, "method": "ping", "params": params}, jsonrpc.INVALID_PARAMS)
                self.assertEqual(error.request_id, 7)

    def test_neither_method_nor_result_is_refused(self) -> None:
        self.refused({"jsonrpc": "2.0", "id": 1}, jsonrpc.INVALID_REQUEST)

    def test_request_notification_and_responses_parse(self) -> None:
        request = jsonrpc.parse_message('{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}')
        self.assertTrue(jsonrpc.is_request(request) and not jsonrpc.is_notification(request))
        notification = jsonrpc.parse_message(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
        self.assertTrue(jsonrpc.is_notification(notification) and not jsonrpc.is_request(notification))
        result = jsonrpc.parse_message('{"jsonrpc":"2.0","id":"x","result":{}}')
        self.assertFalse(jsonrpc.is_request(result) or jsonrpc.is_notification(result))
        error = jsonrpc.parse_message('{"jsonrpc":"2.0","id":2,"error":{"code":-1,"message":"m"}}')
        self.assertEqual(error["error"]["code"], -1)

    def test_string_and_integer_ids_are_valid(self) -> None:
        self.assertTrue(jsonrpc.valid_id("abc") and jsonrpc.valid_id(0) and jsonrpc.valid_id(-3))
        self.assertFalse(jsonrpc.valid_id(None) or jsonrpc.valid_id(True) or jsonrpc.valid_id(1.0) or jsonrpc.valid_id([1]))

    def test_error_response_carries_data_only_when_given(self) -> None:
        self.assertEqual(jsonrpc.error_response(1, -32600, "m"), {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "m"}})
        self.assertEqual(jsonrpc.error_response(None, -32700, "m", {"a": 1})["error"]["data"], {"a": 1})
        self.assertEqual(jsonrpc.JsonRpcError(-32601, "nf", request_id=4).response()["id"], 4)


class DumpsTest(unittest.TestCase):
    def test_one_compact_utf8_line(self) -> None:
        out = jsonrpc.dumps({"a": [1, 2], "b": {"c": "я"}})
        self.assertIsInstance(out, bytes)
        self.assertEqual(out, '{"a":[1,2],"b":{"c":"я"}}'.encode("utf-8"))

    def test_line_separator_stays_a_character_and_never_a_newline(self) -> None:
        out = jsonrpc.dumps({"t": "a" + LINE_SEP + "b"})
        self.assertNotIn(b"\n", out)
        self.assertNotIn(b"\r", out)
        self.assertEqual(json.loads(out.decode("utf-8"))["t"], "a" + LINE_SEP + "b")

    def test_newline_inside_a_string_is_escaped(self) -> None:
        out = jsonrpc.dumps({"t": "a\nb\r\nc"})
        self.assertNotIn(b"\n", out)
        self.assertNotIn(b"\r", out)
        self.assertEqual(out, b'{"t":"a\\nb\\r\\nc"}')


# --------------------------------------------------------------------------- schema


class SchemaCheckTest(unittest.TestCase):
    def test_every_type_name(self) -> None:
        good = {"object": {}, "array": [], "string": "s", "integer": 3, "number": 1.5, "boolean": False, "null": None}
        for name, value in good.items():
            with self.subTest(name=name):
                self.assertEqual(schema.check({"type": name}, value), [])
        self.assertEqual(schema.check({"type": "string"}, 1), ["$: expected string"])
        self.assertEqual(schema.check({"type": "object"}, []), ["$: expected object"])
        self.assertEqual(schema.check({"type": "array"}, {}), ["$: expected array"])
        self.assertEqual(schema.check({"type": "null"}, 0), ["$: expected null"])

    def test_integer_and_number_refuse_booleans(self) -> None:
        self.assertEqual(schema.check({"type": "integer"}, True), ["$: expected integer"])
        self.assertEqual(schema.check({"type": "number"}, False), ["$: expected number"])
        self.assertEqual(schema.check({"type": "integer"}, 1.0), ["$: expected integer"])
        self.assertEqual(schema.check({"type": "number"}, 2), [])

    def test_type_as_a_list(self) -> None:
        typed = {"type": ["string", "integer"]}
        self.assertEqual(schema.check(typed, "a"), [])
        self.assertEqual(schema.check(typed, 5), [])
        self.assertEqual(schema.check(typed, True), ["$: expected string or integer"])
        self.assertEqual(schema.check(typed, None), ["$: expected string or integer"])

    def test_no_type_accepts_anything(self) -> None:
        self.assertEqual(schema.check({}, {"a": [None]}), [])

    def test_enum(self) -> None:
        self.assertEqual(schema.check({"type": "string", "enum": ["on", "off"]}, "on"), [])
        self.assertEqual(schema.check({"type": "string", "enum": ["on", "off"]}, "up"), ["$: must be one of ['on', 'off']"])

    def test_pattern(self) -> None:
        self.assertEqual(schema.check({"type": "string", "pattern": "^[a-z]+$"}, "abc"), [])
        self.assertEqual(schema.check({"type": "string", "pattern": "^[a-z]+$"}, "ab1"), ["$: does not match ^[a-z]+$"])

    def test_min_and_max_length(self) -> None:
        self.assertEqual(schema.check({"type": "string", "minLength": 1, "maxLength": 3}, "ab"), [])
        self.assertEqual(schema.check({"type": "string", "minLength": 1}, ""), ["$: shorter than 1 characters"])
        self.assertEqual(schema.check({"type": "string", "maxLength": 3}, "abcd"), ["$: longer than 3 characters"])

    def test_minimum_and_maximum(self) -> None:
        self.assertEqual(schema.check({"type": "integer", "minimum": 1, "maximum": 500}, 1), [])
        self.assertEqual(schema.check({"type": "integer", "minimum": 1, "maximum": 500}, 500), [])
        self.assertEqual(schema.check({"type": "integer", "minimum": 1}, 0), ["$: less than 1"])
        self.assertEqual(schema.check({"type": "integer", "maximum": 500}, 501), ["$: more than 500"])
        self.assertEqual(schema.check({"type": "number", "minimum": 0.5}, 0.25), ["$: less than 0.5"])

    def test_min_and_max_items(self) -> None:
        self.assertEqual(schema.check({"type": "array", "minItems": 1, "maxItems": 2}, [1]), [])
        self.assertEqual(schema.check({"type": "array", "minItems": 1}, []), ["$: fewer than 1 items"])
        self.assertEqual(schema.check({"type": "array", "maxItems": 2}, [1, 2, 3]), ["$: more than 2 items"])

    def test_items_with_a_scalar_schema(self) -> None:
        self.assertEqual(schema.check({"type": "array", "items": {"type": "string"}}, ["a", "b"]), [])
        self.assertEqual(schema.check({"type": "array", "items": {"type": "string"}}, ["a", 1]), ["$[1]: expected string"])

    def test_nested_items_with_object_schemas(self) -> None:
        nested = {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "properties": {"id": {"type": "string"}, "on": {"type": "boolean"}},
                                             "required": ["id", "on"]}}
        self.assertEqual(schema.check(nested, [{"id": "a", "on": True}]), [])
        self.assertEqual(schema.check(nested, [{"id": "a"}]), ["$[0]: missing on"])
        self.assertEqual(schema.check(nested, [{"id": "a", "on": 1}]), ["$[0].on: expected boolean"])
        self.assertEqual(schema.check(nested, [{"id": "a", "on": True, "x": 1}]), ["$[0]: unknown property x"])
        self.assertEqual(schema.check(nested, ["a"]), ["$[0]: expected object"])

    def test_required_and_additional_properties_false(self) -> None:
        obj = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "integer"}}, "required": ["a"]}
        self.assertEqual(schema.check(obj, {"a": 1}), [])
        self.assertEqual(schema.check(obj, {}), ["$: missing a"])
        self.assertEqual(schema.check(obj, {"a": 1, "b": 2}), ["$: unknown property b"])
        self.assertEqual(schema.check({"type": "object", "properties": {"a": {}}}, {"b": 2}), [])  # additional allowed

    def test_several_problems_are_all_reported(self) -> None:
        obj = {"type": "object", "properties": {"a": {"type": "string", "minLength": 2}, "b": {"type": "integer", "maximum": 1}},
               "required": ["c"]}
        self.assertEqual(schema.check(obj, {"a": "x", "b": 5}), ["$: missing c", "$.a: shorter than 2 characters", "$.b: more than 1"])


class RegistrySchemaTest(unittest.TestCase):
    """The exact schemas of set_rules and set_param.value as the registry publishes them."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.specs = ToolRegistry(paths_in(Path(cls.tmp.name)), LANGUAGES).specs

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_set_rules_schema(self) -> None:
        item = {"type": "object", "additionalProperties": False,
                "properties": {"id": {"type": "string", "pattern": ID_PATTERN, "maxLength": 200}, "enabled": {"type": "boolean"}},
                "required": ["id", "enabled"]}
        self.assertEqual(self.specs["set_rules"].input_schema,
                         {"type": "object", "additionalProperties": False,
                          "properties": {"items": {"type": "array", "minItems": 1, "maxItems": 200, "items": item}},
                          "required": ["items"]})

    def test_set_rules_arguments(self) -> None:
        rules = self.specs["set_rules"].input_schema
        self.assertEqual(schema.check(rules, {"items": [{"id": "apps.remove.onedrive", "enabled": False}]}), [])
        self.assertEqual(schema.check(rules, {}), ["$: missing items"])
        self.assertEqual(schema.check(rules, {"items": []}), ["$.items: fewer than 1 items"])
        self.assertEqual(schema.check(rules, {"items": [{"id": "a", "enabled": "yes"}]}), ["$.items[0].enabled: expected boolean"])
        self.assertEqual(schema.check(rules, {"items": [{"id": "bad id!", "enabled": True}]}), [f"$.items[0].id: does not match {ID_PATTERN}"])
        self.assertEqual(schema.check(rules, {"items": [{"id": "a", "enabled": True, "x": 1}]}), ["$.items[0]: unknown property x"])
        self.assertEqual(schema.check(rules, {"items": [{"id": "a", "enabled": True}] * 201}), ["$.items: more than 200 items"])
        self.assertEqual(schema.check(rules, {"items": [{"id": "a", "enabled": True}], "force": True}), ["$: unknown property force"])

    def test_set_param_value_schema(self) -> None:
        self.assertEqual(self.specs["set_param"].input_schema["properties"]["value"],
                         {"type": ["string", "integer", "boolean", "array"], "maxLength": 4000,
                          "items": {"type": "string", "maxLength": 4000}, "maxItems": 200})
        self.assertEqual(self.specs["set_param"].input_schema["required"], ["id", "name", "value"])

    def test_set_param_value_arguments(self) -> None:
        value = self.specs["set_param"].input_schema["properties"]["value"]
        for good in ("text", 5, True, ["a", "b"], [], 5000, "x" * 4000):
            with self.subTest(value=good):
                self.assertEqual(schema.check(value, good), [])  # maxLength is ignored for an integer
        self.assertEqual(schema.check(value, {"a": 1}), ["$: expected string or integer or boolean or array"])
        self.assertEqual(schema.check(value, None), ["$: expected string or integer or boolean or array"])
        self.assertEqual(schema.check(value, 1.5), ["$: expected string or integer or boolean or array"])
        self.assertEqual(schema.check(value, "x" * 4001), ["$: longer than 4000 characters"])
        self.assertEqual(schema.check(value, [1]), ["$[0]: expected string"])
        self.assertEqual(schema.check(value, ["x"] * 201), ["$: more than 200 items"])

    def test_list_rules_limit_refuses_a_boolean(self) -> None:
        self.assertEqual(schema.check(self.specs["list_rules"].input_schema, {"limit": True}), ["$.limit: expected integer"])
        self.assertEqual(schema.check(self.specs["list_rules"].input_schema, {"limit": 500, "offset": 0}), [])
        self.assertEqual(schema.check(self.specs["list_rules"].input_schema, {"limit": 501}), ["$.limit: more than 500"])


# --------------------------------------------------------------------------- redact


class CleanTextTest(unittest.TestCase):
    def test_control_characters_are_stripped_and_whitespace_kept(self) -> None:
        self.assertEqual(redact.clean_text("a\x00b\x07c\x1bd\x7fe"), "abcde")
        self.assertEqual(redact.clean_text("a\tb\nc"), "a\tb\nc")
        self.assertEqual(redact.clean_text("a\r\nb\rc"), "a\nb\nc")

    def test_bidi_and_invisible_characters_are_stripped(self) -> None:
        self.assertEqual(redact.clean_text("a" + RLO + "b" + ISOLATE + "c" + ZERO_WIDTH + "d" + BOM), "abcd")

    def test_none_and_non_text(self) -> None:
        self.assertEqual(redact.clean_text(None), "")
        self.assertEqual(redact.clean_text(12), "12")

    def test_truncation_marks_the_cut(self) -> None:
        self.assertEqual(redact.clean_text("abcdefgh", limit=4), "abcd [truncated]")
        self.assertEqual(redact.clean_text("abc  fgh", limit=5), "abc [truncated]")
        self.assertEqual(redact.clean_text("abcd", limit=4), "abcd")
        self.assertEqual(redact.clean_text("x" * (redact.OTHER + 1)).count(" [truncated]"), 1)

    def test_clean_json_reaches_every_string(self) -> None:
        cleaned = redact.clean_json({"a": ["x" + ZERO_WIDTH, {"b": "y\x00"}], 3: 4})
        self.assertEqual(cleaned, {"a": ["x", {"b": "y"}], "3": 4})


class RedactProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)

    @classmethod
    def tearDownClass(cls) -> None:
        i18n.set_language("en")

    def secret_profile(self) -> Profile:
        profile = Profile.from_catalog(self.catalog)
        profile.accounts[0].password = "Secret1"
        profile.install["product_key"] = "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"
        profile.comment = "a note\x00"
        profile.author = "Ann"
        return profile

    def test_password_becomes_has_password(self) -> None:
        data = redact.redact_profile(self.secret_profile().to_dict(self.catalog))
        self.assertEqual([a["has_password"] for a in data["accounts"]], [True, False])
        self.assertTrue(all("password" not in a for a in data["accounts"]))
        self.assertNotIn("Secret1", json.dumps(data))

    def test_product_key_becomes_has_product_key(self) -> None:
        data = redact.redact_profile(self.secret_profile().to_dict(self.catalog))
        self.assertTrue(data["install"]["has_product_key"])
        self.assertNotIn("product_key", data["install"])
        self.assertNotIn("AAAAA", json.dumps(data))
        self.assertFalse(redact.redact_profile(Profile.from_catalog(self.catalog).to_dict())["install"]["has_product_key"])

    def test_free_texts_are_renamed_and_cleaned(self) -> None:
        data = redact.redact_profile(self.secret_profile().to_dict(self.catalog))
        self.assertEqual(data["comment_text"], "a note")
        self.assertEqual(data["author_text"], "Ann")
        self.assertNotIn("comment", data)
        self.assertNotIn("author", data)
        self.assertEqual(data["accounts"][0]["description_text"], "Local administrator (starter account)")
        self.assertNotIn("description", data["accounts"][0])

    def test_differences_hide_the_product_key(self) -> None:
        rows = redact.redact_differences([Difference("install", "product_key", "", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"),
                                          Difference("rule", "x", True, False),
                                          Difference("accounts", "accounts", ["Admin"], ["Admin", "User"])])
        self.assertEqual(rows[0], {"kind": "install", "key": "product_key", "before": redact.HIDDEN, "after": redact.HIDDEN})
        self.assertEqual(rows[1], {"kind": "rule", "key": "x", "before": True, "after": False})
        self.assertEqual(rows[2]["after"], ["Admin", "User"])

    def test_redacted_copy_blanks_passwords_and_replaces_a_custom_key(self) -> None:
        profile = self.secret_profile()
        copied = redact.redacted_copy(profile)
        self.assertEqual([a.password for a in copied.accounts], ["", ""])
        self.assertEqual(copied.install["product_key"], redact.KEY_PLACEHOLDER)
        self.assertEqual(profile.accounts[0].password, "Secret1")  # the original is untouched
        self.assertEqual(profile.install["product_key"], "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
        plain = redact.redacted_copy(Profile.from_catalog(self.catalog))
        self.assertEqual(plain.install["product_key"], "")  # no key: nothing to replace

    def test_public_keys_hold_the_generic_edition_keys(self) -> None:
        keys = redact.public_keys()
        self.assertTrue(set(EDITION_KEYS.values()) <= keys)
        self.assertIn("", keys)
        self.assertIn(redact.KEY_PLACEHOLDER, keys)
        self.assertNotIn("AAAAA-BBBBB-CCCCC-DDDDD-EEEEE", keys)


class RedactedBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = paths_in(Path(cls.tmp.name))
        cls.catalog = load_catalog(cls.paths.rules, docs_root=cls.paths.docs_root)
        cls.resources = Resources.load(cls.paths.resources)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()
        i18n.set_language("en")

    def build(self, profile: Profile):
        result, issues = check_and_build(self.catalog, profile, self.resources, self.paths.templates, "0.0.0")
        self.assertIsNotNone(result, [i.message for i in issues])
        return result

    def test_a_build_of_the_redacted_copy_passes(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        profile.accounts[0].password = "Secret1"
        redact.assert_redacted_build(self.build(redact.redacted_copy(profile)))

    def test_a_build_with_a_real_password_is_refused(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        profile.accounts[1].password = "Secret1"
        with self.assertRaises(RedactionError) as cm:
            redact.assert_redacted_build(self.build(profile))
        self.assertEqual(cm.exception.kind, "redaction_failed")
        self.assertNotIn("Secret1", cm.exception.message)

    def test_a_build_with_a_custom_key_is_refused_and_its_redacted_copy_passes(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        profile.install["product_key_mode"] = "custom"
        profile.install["product_key"] = "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"
        with self.assertRaises(RedactionError):
            redact.assert_redacted_build(self.build(profile))
        redacted = self.build(redact.redacted_copy(profile))
        redact.assert_redacted_build(redacted)
        self.assertIn(redact.KEY_PLACEHOLDER, redacted.xml)
        self.assertNotIn("AAAAA-BBBBB", redacted.xml)

    def test_the_generic_key_of_the_office_preset_passes(self) -> None:
        profile, _ = Profile.load(ROOT / "profiles" / "preset-office.json", self.catalog)
        result = self.build(profile)
        self.assertIn(EDITION_KEYS["Pro"], result.xml)
        redact.assert_redacted_build(result)

    def test_text_that_is_not_xml_is_refused(self) -> None:
        from winkickoff.core.render import BuildResult

        with self.assertRaises(RedactionError):
            redact.assert_redacted_build(BuildResult(xml="<unattend", scripts={}, rule_ids=[]))


class CheckNameTest(unittest.TestCase):
    def test_accepted_names(self) -> None:
        for name in ("Каса", "Профіль офісу", "Office 2026", "kasa.v2", "a", "x" * redact.MAX_NAME, "1-2_3"):
            with self.subTest(name=name):
                self.assertIsNone(redact.check_name(name))

    def test_refused_names(self) -> None:
        refused = ["", ACUTE + "abc", "a" + SOLIDUS + "b", "..", "a/b", "a\\b", "CON", "com1.json", "name.", " name",
                   "na" + ZERO_WIDTH + "me", "x" * (redact.MAX_NAME + 1), "a..b", "name ", "-name", ".name", "a\nb", "a\x00b",
                   "LPT9.txt", "nul"]
        for name in refused:
            with self.subTest(name=name):
                self.assertIsNotNone(redact.check_name(name))

    def test_non_text_is_refused(self) -> None:
        self.assertEqual(redact.check_name(None), "the name must be text")
        self.assertEqual(redact.check_name(5), "the name must be text")

    def test_reasons_name_the_problem(self) -> None:
        self.assertIn("path separators", redact.check_name("a/b"))
        self.assertIn("reserved", redact.check_name("COM1"))
        self.assertIn('".."', redact.check_name("a..b"))
        self.assertIn("space or a dot", redact.check_name("name."))
        self.assertIn("1 to 80", redact.check_name(""))


class SafeChildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "profiles"
        self.folder.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_good_name_lands_inside_the_folder(self) -> None:
        self.assertEqual(redact.safe_child(self.folder, "Каса", ".json"), self.folder / "Каса.json")
        self.assertFalse((self.folder / "Каса.json").exists())  # nothing is created

    def test_preset_names_are_refused(self) -> None:
        for name in ("preset-x", "Preset-office", "PRESET-strict"):
            with self.subTest(name=name):
                with self.assertRaises(ToolError) as cm:
                    redact.safe_child(self.folder, name, ".json")
                self.assertEqual(cm.exception.kind, "name_refused")
                self.assertEqual(cm.exception.data, {"name": name})

    def test_names_leaving_the_folder_are_refused(self) -> None:
        for name in ("..", "../x", "..\\x", "a/../../b", "C:\\x", "/x"):
            with self.subTest(name=name):
                with self.assertRaises(ToolError) as cm:
                    redact.safe_child(self.folder, name, ".json")
                self.assertEqual(cm.exception.kind, "name_refused")
        self.assertEqual(sorted(self.folder.iterdir()), [])


# --------------------------------------------------------------------------- journal


class JournalTest(unittest.TestCase):
    def test_append_since_and_count(self) -> None:
        journal = Journal()
        self.assertEqual((journal.count, journal.since(0), journal.last_time), (0, [], ""))
        first = journal.append("stdio", "c 1", "initialize", "", "", True, 3)
        second = journal.append("http", "c 1", "tools/call", "get_rule", "id=x", False, 12, "unknown_id")
        self.assertEqual((first, second, journal.count), (1, 2, 2))
        self.assertEqual([e.seq for e in journal.since(0)], [1, 2])
        self.assertEqual([e.seq for e in journal.since(1)], [2])
        self.assertEqual(journal.since(2), [])
        entry = journal.since(1)[0]
        self.assertEqual((entry.transport, entry.client, entry.method, entry.tool, entry.args, entry.ok, entry.ms, entry.note),
                         ("http", "c 1", "tools/call", "get_rule", "id=x", False, 12, "unknown_id"))
        self.assertRegex(entry.time, r"^\d\d:\d\d:\d\d$")
        self.assertEqual(journal.last_time, entry.time)

    def test_annotate_appends_to_the_note(self) -> None:
        journal = Journal()
        seq = journal.append("stdio", "", "tools/call", "set_rules", "", False, 30000, "window_timeout")
        journal.annotate(seq, "completed after timeout")
        self.assertEqual(journal.entries()[0].note, "window_timeout; completed after timeout")
        plain = journal.append("stdio", "", "ping", "", "", True, 0)
        journal.annotate(plain, "late")
        self.assertEqual(journal.entries()[1].note, "late")
        journal.annotate(99, "nothing")  # an unknown seq changes nothing
        self.assertEqual([e.note for e in journal.entries()], ["window_timeout; completed after timeout", "late"])

    def test_bounded_and_clear_keeps_the_sequence(self) -> None:
        journal = Journal(maxlen=2)
        for _ in range(3):
            journal.append("stdio", "", "ping", "", "", True, 0)
        self.assertEqual([e.seq for e in journal.entries()], [2, 3])
        journal.clear()
        self.assertEqual((journal.entries(), journal.count), ([], 3))

    def test_render_args_whitelists_scalars(self) -> None:
        self.assertEqual(render_args(None), "")
        self.assertEqual(render_args({}), "")
        self.assertEqual(render_args({"id": "apps.remove.onedrive", "enabled": True, "force": False, "limit": 5}),
                         "id=apps.remove.onedrive enabled=true force=false limit=5")

    def test_render_args_hides_free_text(self) -> None:
        self.assertEqual(render_args({"name": "Каса"}), "name=<text, 4 chars>")
        for key in ("comment", "author", "query", "value", "title"):
            with self.subTest(key=key):
                self.assertEqual(render_args({key: "ab"}), f"{key}=<text, 2 chars>")
        self.assertEqual(render_args({"id": "two words"}), "id=<text, 9 chars>")
        self.assertEqual(render_args({"id": "x" * 61}), "id=<text, 61 chars>")
        self.assertEqual(render_args({"id": "x" * 60}), "id=" + "x" * 60)

    def test_render_args_shows_containers_by_kind_and_size(self) -> None:
        self.assertEqual(render_args({"items": [1, 2, 3]}), "items=<list, 3 items>")
        self.assertEqual(render_args({"value": {"a": 1}}), "value=<object>")
        self.assertEqual(render_args({"x": 1.5, "y": None}), "x=<float> y=<NoneType>")


# --------------------------------------------------------------------------- McpServer.handle


class ServerTestCase(unittest.TestCase):
    """A headless server on the real catalog and the Office preset; every test gets a fresh session and journal."""

    @classmethod
    def setUpClass(cls) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = paths_in(Path(cls.tmp.name))
        cls.catalog = load_catalog(cls.paths.rules, docs_root=cls.paths.docs_root)
        cls.resources = Resources.load(cls.paths.resources)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()
        i18n.set_language("en")

    def setUp(self) -> None:
        profile, _ = Profile.load(ROOT / "profiles" / "preset-office.json", self.catalog)
        self.workspace = HeadlessWorkspace(self.paths, self.catalog, profile, self.resources, app_version="1.0.0-test")
        self.mode = "read"
        self.journal = Journal()
        self.server = McpServer(ToolRegistry(self.paths, LANGUAGES), ResourceRegistry(self.paths, LANGUAGES),
                                InlineBridge(self.workspace), self.journal, transport="stdio", mode=lambda: self.mode,
                                has_window=False, app_version="1.0.0-test")
        self.session = Session(id="s1", transport="stdio")
        self.next_id = 0

    # ----------------------------------------------------------------- helpers

    def request(self, method: str, params: dict | None = None, request_id: object = None) -> dict:
        self.next_id += 1
        message: dict = {"jsonrpc": "2.0", "id": self.next_id if request_id is None else request_id, "method": method}
        if params is not None:
            message["params"] = params
        return self.server.handle(message, self.session)

    def notify(self, method: str, params: dict | None = None) -> dict | None:
        message: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        return self.server.handle(message, self.session)

    def initialize(self, version: object = "2025-06-18", client: dict | None = None) -> dict:
        params: dict = {"protocolVersion": version, "capabilities": {}}
        if client is not None:
            params["clientInfo"] = client
        return self.request("initialize", params)

    def call(self, name: str, arguments: dict | None = None) -> dict:
        params: dict = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        return self.request("tools/call", params)

    def assertError(self, response: dict, code: int) -> dict:  # noqa: N802 - unittest style
        self.assertIn("error", response, response)
        self.assertEqual(response["error"]["code"], code, response["error"])
        self.assertNotIn("result", response)
        return response["error"]


class InitializeTest(ServerTestCase):
    def test_supported_versions_are_echoed(self) -> None:
        for version in ("2025-03-26", "2025-06-18", "2024-11-05"):
            with self.subTest(version=version):
                self.setUp()
                self.assertEqual(self.initialize(version)["result"]["protocolVersion"], version)
                self.assertEqual(self.session.protocol_version, version)

    def test_newer_or_unknown_versions_get_the_latest(self) -> None:
        for version in ("2025-11-25", "1.0.0", ""):
            with self.subTest(version=version):
                self.setUp()
                self.assertEqual(self.initialize(version)["result"]["protocolVersion"], "2025-06-18")
                self.assertTrue(self.session.initialized)

    def test_non_string_version_is_invalid_params_with_the_supported_list(self) -> None:
        for version in (1, None, ["2025-06-18"], True):
            with self.subTest(version=version):
                self.setUp()
                error = self.assertError(self.initialize(version), -32602)
                self.assertEqual(error["data"]["supported"], list(SUPPORTED_VERSIONS))
                self.assertEqual(error["data"]["requested"], version)
                self.assertFalse(self.session.initialized)
        self.assertError(self.request("initialize", {}), -32602)

    def test_client_name_lands_on_the_session(self) -> None:
        self.initialize(client={"name": "Claude Code", "version": "1.2"})
        self.assertEqual((self.session.client_name, self.session.client_version, self.session.client), ("Claude Code", "1.2", "Claude Code 1.2"))

    def test_client_name_is_cleaned_and_bounded(self) -> None:
        self.initialize(client={"name": "bad\nname\x00" + RLO + "x" * 100, "version": "v\n1"})
        self.assertNotIn("\n", self.session.client_name)
        self.assertNotIn("\x00", self.session.client_name)
        self.assertNotIn(RLO, self.session.client_name)
        self.assertTrue(self.session.client_name.startswith("bad name"))
        self.assertLessEqual(len(self.session.client_name), 80 + len(" [truncated]"))
        self.assertEqual(self.session.client_version, "v 1")
        self.request("initialize", {"protocolVersion": "2025-06-18", "clientInfo": "not an object"})
        self.assertEqual(self.session.client, "")

    def test_capabilities_server_info_and_instructions(self) -> None:
        result = self.initialize()["result"]
        self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}})
        self.assertEqual(result["serverInfo"], {"name": "winkickoff", "title": "WinKickOff", "version": "1.0.0-test"})
        self.assertEqual(result["instructions"], INSTRUCTIONS)
        self.assertIn("Passwords and product keys are never returned", result["instructions"])
        self.assertEqual(set(result), {"protocolVersion", "capabilities", "serverInfo", "instructions"})

    def test_response_keeps_the_request_id(self) -> None:
        self.assertEqual(self.initialize()["id"], 1)
        response = self.request("ping", request_id="abc")
        self.assertEqual((response["id"], response["result"], response["jsonrpc"]), ("abc", {}, "2.0"))


class HandshakeOrderTest(ServerTestCase):
    def test_a_request_before_initialize_is_invalid(self) -> None:
        for method in ("tools/list", "tools/call", "resources/list", "resources/read"):
            with self.subTest(method=method):
                self.assertError(self.request(method, {"name": "get_status", "uri": "winkickoff://status"}), -32600)
        self.assertFalse(self.session.initialized)

    def test_ping_works_before_initialize(self) -> None:
        self.assertEqual(self.request("ping")["result"], {})

    def test_tools_list_works_right_after_the_initialize_result(self) -> None:
        self.initialize()
        self.assertFalse(self.session.acknowledged)
        self.assertIn("tools", self.request("tools/list")["result"])

    def test_notifications_initialized_returns_none_and_acknowledges(self) -> None:
        self.initialize()
        self.assertIsNone(self.notify("notifications/initialized"))
        self.assertTrue(self.session.acknowledged)

    def test_other_notifications_are_ignored(self) -> None:
        self.initialize()
        for method in ("notifications/cancelled", "notifications/progress", "notifications/roots/list_changed", "notifications/unknown"):
            with self.subTest(method=method):
                self.assertIsNone(self.notify(method, {"requestId": 1}))
        self.assertFalse(self.session.acknowledged)
        self.assertIn("tools", self.request("tools/list")["result"])  # the session is unharmed

    def test_unknown_method_is_method_not_found(self) -> None:
        self.initialize()
        for method in ("server/discover", "prompts/list", "completion/complete", ""):
            with self.subTest(method=method):
                error = self.assertError(self.request(method), -32601)
                self.assertIn("Method not found", error["message"])

    def test_a_client_response_object_returns_none(self) -> None:
        self.initialize()
        before = self.journal.count
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "id": 5, "result": {}}, self.session))
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "id": 6, "error": {"code": -1, "message": "m"}}, self.session))
        self.assertEqual(self.journal.count, before)  # nothing was handled, nothing is journaled

    def test_header_versions(self) -> None:
        self.assertTrue(accepted_header_version(None))
        for value in SUPPORTED_VERSIONS + ("2025-11-25",):
            self.assertTrue(accepted_header_version(value), value)
        self.assertFalse(accepted_header_version("1.0"))
        self.assertFalse(accepted_header_version(""))


class ToolsListTest(ServerTestCase):
    def test_exactly_the_eighteen_tools(self) -> None:
        self.initialize()
        tools = self.request("tools/list")["result"]["tools"]
        self.assertEqual(len(tools), 18)
        self.assertEqual({t["name"] for t in tools}, TOOL_NAMES)

    def test_every_tool_listing_shape(self) -> None:
        self.initialize()
        for tool in self.request("tools/list")["result"]["tools"]:
            with self.subTest(tool=tool["name"]):
                self.assertEqual(set(tool), {"name", "title", "description", "inputSchema", "annotations"})
                self.assertNotIn("outputSchema", tool)
                self.assertTrue(tool["title"])
                self.assertRegex(tool["description"], r"^\[(read|edit|files)\] \S")
                self.assertEqual(tool["inputSchema"]["type"], "object")
                self.assertIs(tool["inputSchema"]["additionalProperties"], False)
                self.assertEqual(set(tool["annotations"]), {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"})
                self.assertIs(tool["annotations"]["openWorldHint"], False)
                self.assertIs(tool["annotations"]["destructiveHint"], False)
                self.assertRegex(tool["name"], r"^[a-z_]+$")

    def test_annotations_follow_the_mode(self) -> None:
        self.initialize()
        for tool in self.request("tools/list")["result"]["tools"]:
            mode = tool["description"].split("]", 1)[0][1:]
            self.assertIs(tool["annotations"]["readOnlyHint"], mode == "read", tool["name"])

    def test_a_cursor_is_invalid_params(self) -> None:
        self.initialize()
        self.assertError(self.request("tools/list", {"cursor": "x"}), -32602)
        self.assertIn("tools", self.request("tools/list", {"cursor": ""})["result"])


class ToolsCallTest(ServerTestCase):
    def test_a_read_tool_answers_with_text_and_structured_content(self) -> None:
        self.initialize()
        result = self.call("get_status")["result"]
        self.assertIs(result["isError"], False)
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        self.assertEqual((result["structuredContent"]["mode"], result["structuredContent"]["transport"],
                          result["structuredContent"]["has_window"], result["structuredContent"]["app_version"]),
                         ("read", "stdio", False, "1.0.0-test"))
        self.assertEqual(result["structuredContent"]["profile"]["name"], "Office")

    def test_unknown_tool_is_invalid_params(self) -> None:
        self.initialize()
        error = self.assertError(self.call("no_such_tool"), -32602)
        self.assertEqual(error["message"], "Unknown tool: no_such_tool")
        self.assertError(self.request("tools/call", {}), -32602)

    def test_arguments_must_be_an_object(self) -> None:
        self.initialize()
        self.assertError(self.request("tools/call", {"name": "get_status", "arguments": [1]}), -32602)
        self.assertIs(self.request("tools/call", {"name": "get_status", "arguments": None})["result"]["isError"], False)

    def test_a_tool_error_is_a_result_with_is_error(self) -> None:
        self.initialize()
        response = self.call("get_rule", {"id": "no.such.rule"})
        self.assertNotIn("error", response)
        result = response["result"]
        self.assertIs(result["isError"], True)
        self.assertEqual(result["structuredContent"]["error"], "unknown_id")
        self.assertEqual(result["structuredContent"]["id"], "no.such.rule")
        self.assertEqual(result["content"], [{"type": "text", "text": result["structuredContent"]["message"]}])

    def test_bad_arguments_are_a_tool_error(self) -> None:
        self.initialize()
        result = self.call("get_rule", {"id": 5})["result"]
        self.assertIs(result["isError"], True)
        self.assertEqual(result["structuredContent"]["error"], "invalid_arguments")
        self.assertEqual(result["structuredContent"]["problems"], ["$.id: expected string"])
        result = self.call("get_rule")["result"]
        self.assertEqual(result["structuredContent"]["problems"], ["$: missing id"])

    def test_mode_required_in_read_mode(self) -> None:
        self.initialize()
        result = self.call("set_rules", {"items": [{"id": "apps.remove.onedrive", "enabled": False}]})["result"]
        self.assertIs(result["isError"], True)
        self.assertEqual(result["structuredContent"]["error"], "mode_required")
        self.assertEqual((result["structuredContent"]["required"], result["structuredContent"]["current"]), ("edit", "read"))
        self.assertIn("how", result["structuredContent"])
        self.assertTrue(self.workspace.profile.is_enabled("apps.remove.onedrive"))  # nothing changed
        self.assertFalse(self.workspace.dirty)

    def test_the_mode_callable_is_read_on_every_call(self) -> None:
        self.initialize()
        self.mode = "edit"
        result = self.call("set_rules", {"items": [{"id": "apps.remove.onedrive", "enabled": False}]})["result"]
        self.assertIs(result["isError"], False)
        self.assertFalse(self.workspace.profile.is_enabled("apps.remove.onedrive"))
        self.assertTrue(self.workspace.dirty)

    def test_a_handler_exception_is_an_internal_error_logged_by_class_name_only(self) -> None:
        self.initialize()

        def boom(ctx, args):
            raise RuntimeError("secret argument text")

        spec = dataclasses.replace(self.server.tools.specs["get_status"], handler=boom)
        with mock.patch.dict(self.server.tools.specs, {"get_status": spec}):
            with self.assertLogs("winkickoff.mcp", level="ERROR") as logs:
                response = self.call("get_status")
        error = self.assertError(response, -32603)
        self.assertEqual(error, {"code": -32603, "message": "internal error"})
        self.assertEqual(logs.output, ["ERROR:winkickoff.mcp:get_status: RuntimeError"])
        self.assertNotIn("secret", "".join(logs.output))
        self.assertNotIn("secret", json.dumps(response))
        self.assertEqual(self.journal.entries()[-1].note, "internal")

    def test_the_result_size_cap_gives_result_too_large(self) -> None:
        self.initialize()
        with mock.patch("winkickoff.mcp.protocol.MAX_RESULT_BYTES", 1000):
            result = self.call("get_profile")["result"]
        self.assertIs(result["isError"], True)
        self.assertEqual(result["structuredContent"]["error"], "result_too_large")
        self.assertGreater(result["structuredContent"]["bytes"], 1000)
        self.assertIn("narrow the query", result["content"][0]["text"])
        self.assertEqual(len(json.dumps(result)) < 1000, True)
        self.assertIs(self.call("get_profile")["result"]["isError"], False)  # the cap was only patched

    def test_the_size_cap_on_a_resource_is_an_internal_error(self) -> None:
        self.initialize()
        with mock.patch("winkickoff.mcp.protocol.MAX_RESULT_BYTES", 1000):
            error = self.assertError(self.request("resources/read", {"uri": "winkickoff://profile"}), -32603)
        self.assertIn("narrow the query", error["message"])

    def test_resources_list_and_read(self) -> None:
        self.initialize()
        uris = {r["uri"] for r in self.request("resources/list")["result"]["resources"]}
        self.assertIn("winkickoff://status", uris)
        contents = self.request("resources/read", {"uri": "winkickoff://status"})["result"]["contents"]
        self.assertEqual(json.loads(contents[0]["text"])["mode"], "read")
        self.assertError(self.request("resources/read", {"uri": "winkickoff://nothing"}), -32002)


class JournalingTest(ServerTestCase):
    def test_one_entry_per_handled_message(self) -> None:
        steps = [
            lambda: self.initialize(client={"name": "c"}),
            lambda: self.notify("notifications/initialized"),
            lambda: self.request("tools/list"),
            lambda: self.call("get_status"),
            lambda: self.call("get_rule", {"id": "no.such.rule"}),
            lambda: self.call("no_such_tool"),
            lambda: self.request("server/discover"),
            lambda: self.notify("notifications/cancelled"),
            lambda: self.request("ping"),
            lambda: self.request("resources/read", {"uri": "winkickoff://nothing"}),
        ]
        for index, step in enumerate(steps, 1):
            step()
            self.assertEqual(self.journal.count, index)
        entries = self.journal.entries()
        self.assertEqual([e.method for e in entries][:4], ["initialize", "notifications/initialized", "tools/list", "tools/call"])
        self.assertEqual([e.ok for e in entries], [True, True, True, True, False, False, False, True, True, False])
        self.assertEqual(entries[4].tool, "get_rule")
        self.assertEqual(entries[4].note, "unknown_id")
        self.assertEqual(entries[5].note, "error -32602")
        self.assertEqual(entries[6].note, "error -32601")
        self.assertTrue(all(e.client == "c" for e in entries[1:]))
        self.assertTrue(all(e.transport == "stdio" for e in entries))

    def test_arguments_are_journaled_whitelisted(self) -> None:
        self.initialize()
        self.call("list_rules", {"query": "onedrive", "limit": 5, "group": "apps"})
        self.assertEqual(self.journal.entries()[-1].args, "query=<text, 8 chars> limit=5 group=apps")


if __name__ == "__main__":
    unittest.main()
