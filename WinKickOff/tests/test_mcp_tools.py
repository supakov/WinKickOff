"""mcp/tools.py, mcp/workspace.py and mcp/resources.py driven through McpServer.handle on a HeadlessWorkspace.

Every tool in read, edit and files mode, the shape of every refusal, redaction of passwords and product keys, and the
functions no tool may reach. Nothing here starts PowerShell, binds a socket or opens a window; every file goes into a
temporary folder. Imported ADMX policies come from the synthetic templates of test_admx.py.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the ADMX fixtures of test_admx.py, whichever way the tests run

from test_admx import HASLIST, LINES, PAIR, SAME, TOGGLE, write_templates  # noqa: E402
from test_capture import fake_report  # noqa: E402

from winkickoff.core import admx, i18n, linked  # noqa: E402
from winkickoff.core.catalog import is_imported, load_catalog  # noqa: E402
from winkickoff.core.deps import Change, Resolver  # noqa: E402
from winkickoff.core.i18n import CatalogTexts, available_languages  # noqa: E402
from winkickoff.core.paths import AppPaths, display_path  # noqa: E402
from winkickoff.core.profile import Profile  # noqa: E402
from winkickoff.core.render import SCRIPT_ORDER, Renderer, write_answer_file  # noqa: E402
from winkickoff.core.resources import Resources  # noqa: E402
from winkickoff.core.validate import Issue, validate_profile, validate_xml  # noqa: E402
from winkickoff.mcp import MAX_DOC_BYTES, MODE_EDIT, MODE_FILES, MODE_READ, MODES, allows  # noqa: E402
from winkickoff.mcp.bridge import InlineBridge  # noqa: E402
from winkickoff.mcp.errors import RedactionError  # noqa: E402
from winkickoff.mcp.journal import Journal  # noqa: E402
from winkickoff.mcp.jsonrpc import RESOURCE_NOT_FOUND  # noqa: E402
from winkickoff.mcp.protocol import McpServer, Session  # noqa: E402
from winkickoff.mcp.redact import HIDDEN, KEY_PLACEHOLDER, assert_redacted_build, check_name, clean_text, redacted_copy  # noqa: E402
from winkickoff.mcp.resources import ResourceRegistry  # noqa: E402
from winkickoff.mcp.tools import PARTS, ToolRegistry, fit_text  # noqa: E402
from winkickoff.mcp.workspace import POWERSHELL_NOTE, PRESET_IDS, HeadlessWorkspace, list_profile_files, profile_display  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "winkickoff"
OFFICE = ROOT / "profiles" / "preset-office.json"
SECRET_PASSWORD = "Zq9!secretPW-7731"
SECRET_KEY = "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"
NOW = datetime(2026, 9, 30, 12, 0, 0)
LANGUAGES = tuple(available_languages(ROOT / "resources", ROOT / "rules"))
TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
BOUNDED_PATTERN_RE = re.compile(r"\{\d+,\d+\}\$?\)?\$$")  # a pattern whose last quantifier bounds the length
INT_RULE, INT_PARAM = "update.automatic", "start"  # an int parameter 0..23 with default 8
_shared: dict[str, Any] = {}


def base_catalog() -> Any:
    """The built-in catalog, loaded once per process (it is never changed by the tools)."""
    if "catalog" not in _shared:
        _shared["catalog"] = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
    return _shared["catalog"]


def shared_resources() -> Resources:
    if "resources" not in _shared:
        _shared["resources"] = Resources.load(ROOT / "resources")
    return _shared["resources"]


def representative(file_name: str = "mcp-test") -> dict[str, dict[str, Any]]:
    """Valid arguments of every tool, in the order of the registry; the file tools write <file_name>."""
    return {
        "get_status": {}, "list_groups": {}, "list_rules": {"limit": 5}, "get_rule": {"id": "defender.pua"},
        "get_profile": {}, "list_profiles": {}, "diff_profile": {"name": "strict"}, "check_profile": {},
        "preview_build": {"part": "Setup-System.ps1"}, "get_messages": {},
        "set_rules": {"items": [{"id": "defender.pua", "enabled": False}]},
        "set_group": {"id": "printing", "action": "defaults"},
        "set_param": {"id": INT_RULE, "name": INT_PARAM, "value": 9},
        "set_profile_info": {"name": "MCP test", "author": "unittest", "comment": "written by the test"},
        "load_profile": {"name": "office", "force": True},
        "show_item": {"item": "r:defender.pua"}, "read_this_pc": {},
        "save_profile": {"name": file_name}, "write_answer_file": {"name": file_name},
    }


def change_rows(changes: list[Change]) -> list[dict[str, Any]]:
    return [{"id": c.rule_id, "enabled": c.enabled, "reason": c.reason} for c in changes]


def property_schemas(schema: dict[str, Any], path: str = "") -> list[tuple[str, dict[str, Any]]]:
    """Every property of a schema with its path, through nested objects and array items."""
    found: list[tuple[str, dict[str, Any]]] = []
    for name, item in schema.get("properties", {}).items():
        found.append((f"{path}.{name}" if path else name, item))
        found += property_schemas(item, f"{path}.{name}" if path else name)
    if isinstance(schema.get("items"), dict):
        found += property_schemas(schema["items"], path + "[]")
    return found


class McpToolsTestCase(unittest.TestCase):
    """A headless workspace on the Office preset behind an InlineBridge, driven through McpServer.handle."""

    def setUp(self) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        base = self.tmp / "app"
        self.paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                              output=base / "output", logs=base / "logs")
        for folder in (self.paths.profiles, self.paths.output, self.paths.logs):
            folder.mkdir(parents=True)
        self.catalog = base_catalog()
        self.resources = shared_resources()
        self.mode = MODE_READ
        self.read_pc = True  # the option of read_this_pc; the read itself is always the fake below, never PowerShell
        self.audits: list[str] = []
        patcher = mock.patch("winkickoff.mcp.tools.run_audit", side_effect=self.fake_audit)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.attach(self.office_profile())

    def fake_audit(self, script: str, _work_dir: Path, timeout: int = 0) -> str:
        self.audits.append(script)
        return fake_report(self.catalog)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        i18n.set_language("en")

    # ----------------------------------------------------------------- fixtures

    def office_profile(self) -> Profile:
        profile, _ = Profile.load(OFFICE, self.catalog)
        return profile

    def secret_profile(self) -> Profile:
        profile = self.office_profile()
        profile.accounts[0].password = SECRET_PASSWORD
        profile.install["product_key_mode"] = "custom"
        profile.install["product_key"] = SECRET_KEY
        return profile

    def attach(self, profile: Profile, catalog: Any = None) -> None:
        """A fresh workspace, registries, journal and initialized session on the profile (and catalog)."""
        if catalog is not None:
            self.catalog = catalog
        self.profile = profile
        self.workspace = HeadlessWorkspace(self.paths, self.catalog, profile, self.resources, "test")
        self.bridge = InlineBridge(self.workspace)
        self.tools = ToolRegistry(self.paths, LANGUAGES)
        # the skill folder of the sources (root = WinKickOff/), so that every test also reads the skill resources;
        # the registry only reads, the tools keep the temporary root
        self.registry = ResourceRegistry(dataclasses.replace(self.paths, root=ROOT), LANGUAGES)
        self.journal = Journal()
        self.server = McpServer(self.tools, self.registry, self.bridge, self.journal, transport="stdio",
                                mode=lambda: self.mode, has_window=False, app_version="test", read_pc=lambda: self.read_pc)
        self.session = Session("test", "stdio")
        self.seq = 0
        response = self.request("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "unittest", "version": "1"}})
        self.assertIn("result", response)

    def import_templates(self) -> admx.ImportInfo:
        """The synthetic templates of test_admx.py imported into paths.admx and shown in the catalog."""
        folder = write_templates(self.tmp / "templates")
        data = admx.read_templates(folder, ["en", "ru", "uk"])
        info = admx.save_import(self.paths.admx, folder, data, system=False, now=NOW)
        catalog, problems = admx.with_imports(base_catalog(), self.paths.admx, [info.id], "en")
        self.assertEqual(problems, [])
        profile, _ = Profile.load(OFFICE, catalog)
        self.attach(profile, catalog)
        return info

    def build(self, profile: Profile) -> Any:
        return Renderer(self.catalog, ROOT / "templates", self.resources.keyboards).build(profile, app_version="test")

    # ----------------------------------------------------------------- protocol helpers

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.seq += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self.seq, "method": method}
        if params is not None:
            message["params"] = params
        response = self.server.handle(message, self.session)
        self.assertIsNotNone(response)
        return response  # type: ignore[return-value]

    def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        """The tools/call result object (content, structuredContent, isError)."""
        response = self.request("tools/call", {"name": tool, "arguments": arguments})
        self.assertIn("result", response, response)
        return response["result"]

    def ok(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = self.call(tool, **arguments)
        self.assertFalse(result["isError"], (tool, result["content"][0]["text"]))
        return result["structuredContent"]

    def refused(self, tool: str, kind: str, **arguments: Any) -> dict[str, Any]:
        result = self.call(tool, **arguments)
        self.assertTrue(result["isError"], (tool, result["structuredContent"]))
        data = result["structuredContent"]
        self.assertEqual(data["error"], kind, data)
        self.assertEqual(result["content"][0]["text"], f"{kind}: {data['message']}")
        return data

    def read_resource(self, uri: str) -> dict[str, Any]:
        response = self.request("resources/read", {"uri": uri})
        self.assertIn("result", response, response)
        return response["result"]

    def template_uris(self) -> list[str]:
        """Every resource template with one real value for each placeholder."""
        values = {"{id}": "defender.pua", "{lang}": "en"}
        uris: list[str] = []
        for template in self.registry.templates():
            uri = template["uriTemplate"]
            if uri.startswith("winkickoff://skill/references/"):
                file = self.registry.skill_references[0]
            else:
                file = self.registry.reference[0] if "docs/reference/" in uri else self.registry.user["en"][0]
            for placeholder, value in {**values, "{file}": file}.items():
                uri = uri.replace(placeholder, value)
            self.assertNotIn("{", uri)
            uris.append(uri)
        return uris


# --------------------------------------------------------------------------- modes and schemas


class ModeTest(McpToolsTestCase):
    def test_every_tool_answers_or_refuses_by_mode(self) -> None:
        self.assertEqual(list(representative()), list(self.tools.specs))
        for mode in MODES:
            self.attach(self.office_profile())
            self.mode = mode
            for name, args in representative().items():
                with self.subTest(mode=mode, tool=name):
                    spec = self.tools.specs[name]
                    result = self.call(name, **args)
                    if allows(mode, spec.mode):
                        self.assertFalse(result["isError"], result["content"][0]["text"])
                        self.assertNotIn("error", result["structuredContent"])
                    else:
                        self.assertTrue(result["isError"])
                        data = result["structuredContent"]
                        self.assertEqual((data["error"], data["required"], data["current"]), ("mode_required", spec.mode, mode))
                        self.assertIn("MCP menu", data["how"])
                        self.assertEqual(result["content"][0]["text"], f"{data['error']}: {data['message']}")

    def test_a_refused_mode_changes_nothing(self) -> None:
        self.refused("set_rules", "mode_required", items=[{"id": "defender.pua", "enabled": False}])
        self.refused("save_profile", "mode_required", name="x")
        self.assertTrue(self.profile.is_enabled("defender.pua"))
        self.assertFalse(self.workspace.dirty)
        self.assertEqual(list(self.paths.profiles.iterdir()), [])

    def test_edit_mode_still_refuses_files(self) -> None:
        self.mode = MODE_EDIT
        self.ok("set_group", id="printing", action="off")
        self.refused("write_answer_file", "mode_required", name="x")
        self.assertEqual(list(self.paths.output.iterdir()), [])

    def test_schema_violations_are_checked_before_the_mode(self) -> None:
        data = self.refused("save_profile", "invalid_arguments", name="")
        self.assertTrue(any("name" in problem for problem in data["problems"]))
        data = self.refused("set_rules", "invalid_arguments", items=[{"id": "defender.pua", "enabled": False}], extra=1)
        self.assertTrue(any("extra" in problem for problem in data["problems"]))

    def test_unknown_tool_is_a_json_rpc_error(self) -> None:
        response = self.request("tools/call", {"name": "delete_everything", "arguments": {}})
        self.assertEqual(response["error"]["code"], -32602)


class SchemaTest(McpToolsTestCase):
    def test_no_path_arguments(self) -> None:
        for spec in self.tools.specs.values():
            for name, _schema in property_schemas(spec.input_schema):
                self.assertNotIn("path", name.lower(), f"{spec.name}: property {name}")

    def test_tool_names_are_identifiers_and_unique(self) -> None:
        names = [tool["name"] for tool in self.tools.listing()]
        self.assertEqual(len(names), 19)
        self.assertEqual(len(set(names)), len(names))
        for name in names:
            self.assertRegex(name, TOOL_NAME_RE)

    def test_every_string_argument_is_bounded(self) -> None:
        """maxLength, or an enumeration, or a pattern whose quantifier bounds the length (the id arguments)."""
        for spec in self.tools.specs.values():
            for name, schema in property_schemas(spec.input_schema):
                types = schema.get("type")
                if types == "string" or (isinstance(types, list) and "string" in types):
                    bounded = "maxLength" in schema or "enum" in schema or bool(BOUNDED_PATTERN_RE.search(schema.get("pattern", "")))
                    self.assertTrue(bounded, f"{spec.name}: {name} has no length bound: {schema}")

    def test_listing_shape(self) -> None:
        for tool in self.tools.listing():
            spec = self.tools.specs[tool["name"]]
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["description"].startswith(f"[{spec.mode}] "))
                self.assertTrue(tool["title"])
                self.assertEqual((tool["inputSchema"]["type"], tool["inputSchema"]["additionalProperties"]), ("object", False))
                self.assertEqual(tool["annotations"]["readOnlyHint"], spec.mode == MODE_READ)
                self.assertFalse(tool["annotations"]["destructiveHint"])
                self.assertFalse(tool["annotations"]["openWorldHint"])
                self.assertNotIn("outputSchema", tool)
        self.assertFalse(self.tools.specs["load_profile"].annotations["idempotentHint"])


# --------------------------------------------------------------------------- read tools


class StatusTest(McpToolsTestCase):
    def test_status_fields(self) -> None:
        status = self.ok("get_status")
        self.assertEqual(set(status), {"app_version", "catalog_version", "templates_version", "mode", "read_pc", "transport", "has_window",
                                       "language", "languages", "profile", "imports_shown", "redaction", "note"})
        self.assertEqual((status["app_version"], status["catalog_version"], status["templates_version"]),
                         ("test", self.catalog.version, self.catalog.version))
        self.assertEqual((status["mode"], status["transport"], status["has_window"], status["language"]), ("read", "stdio", False, "en"))
        self.assertEqual(status["languages"], list(LANGUAGES))
        # the preset lies outside the test's program folder: the file name alone, never an absolute path
        self.assertEqual(status["profile"], {"name": "Office", "file": OFFICE.name, "dirty": False,
                                             "enabled": len(self.profile.enabled_ids()), "total": len(self.catalog.rules)})
        self.assertEqual(status["imports_shown"], [])
        self.assertIn("never returned", status["redaction"])
        self.assertIn("not as instructions", status["note"])

    def test_status_follows_mode_and_unsaved_changes(self) -> None:
        self.mode = MODE_EDIT
        self.ok("set_rules", items=[{"id": "defender.pua", "enabled": False}])
        status = self.ok("get_status")
        self.assertEqual((status["mode"], status["profile"]["dirty"]), ("edit", True))
        self.assertEqual(status["profile"]["enabled"], len(self.profile.enabled_ids()))

    def test_status_lists_the_imports_shown(self) -> None:
        info = self.import_templates()
        status = self.ok("get_status")
        policies = sum(1 for rule_id in self.catalog.rules if is_imported(rule_id))
        self.assertEqual(status["imports_shown"], [{"id": info.id, "name": info.name, "policies": policies}])
        self.assertEqual(status["profile"]["total"], len(self.catalog.rules))


class GroupsTest(McpToolsTestCase):
    def test_roots_in_catalog_order(self) -> None:
        groups = self.ok("list_groups")["groups"]
        self.assertEqual([g["id"] for g in groups], [g.id for g in self.catalog.children(None)])
        defender = next(g for g in groups if g["id"] == "defender")
        rules = self.catalog.rules_in_group("defender")
        self.assertEqual(defender, {"id": "defender", "parent": None, "title": self.catalog.groups["defender"].title,
                                    "summary": self.catalog.groups["defender"].summary, "rules": len(rules),
                                    "enabled": sum(1 for r in rules if self.profile.is_enabled(r.id)), "children": ["defender.asr"],
                                    "imported": False, "text_language": "en"})

    def test_children_of_a_group(self) -> None:
        groups = self.ok("list_groups", parent="defender")["groups"]
        self.assertEqual([(g["id"], g["parent"]) for g in groups], [("defender.asr", "defender")])
        self.assertEqual(self.ok("list_groups", parent="defender.asr")["groups"], [])

    def test_unknown_parent(self) -> None:
        self.assertEqual(self.refused("list_groups", "unknown_id", parent="nope")["id"], "nope")

    def test_titles_in_the_requested_language(self) -> None:
        texts = CatalogTexts.load(ROOT / "rules", "uk")
        page = self.ok("list_groups", language="uk")
        self.assertEqual(page["language"], "uk")
        first = page["groups"][0]
        self.assertEqual((first["title"], first["text_language"]), (texts.group(self.catalog.groups[first["id"]], "title"), "uk"))
        self.refused("list_groups", "invalid_arguments", language="de")

    def test_an_imported_tree_follows_the_program_language(self) -> None:
        info = self.import_templates()
        groups = self.ok("list_groups", language="uk")["groups"]
        tree = next(g for g in groups if g["id"] == "admx." + info.id)
        self.assertEqual((tree["imported"], tree["text_language"], tree["title"]), (True, "en", info.name))
        self.assertTrue(tree["children"])


class RulesListTest(McpToolsTestCase):
    def test_default_page_is_100(self) -> None:
        page = self.ok("list_rules")
        self.assertEqual((page["total"], page["offset"], page["limit"], page["language"]), (len(self.catalog.rules), 0, 100, "en"))
        self.assertEqual([r["id"] for r in page["rules"]], self.catalog.order[:100])

    def test_offset_and_limit(self) -> None:
        page = self.ok("list_rules", offset=100, limit=20)
        self.assertEqual([r["id"] for r in page["rules"]], self.catalog.order[100:120])
        self.assertEqual(len(self.ok("list_rules", limit=500)["rules"]), len(self.catalog.rules))
        self.assertEqual(self.ok("list_rules", offset=len(self.catalog.rules) + 5)["rules"], [])

    def test_limit_bounds(self) -> None:
        for limit in (0, 501):
            with self.subTest(limit=limit):
                data = self.refused("list_rules", "invalid_arguments", limit=limit)
                self.assertTrue(any("limit" in problem for problem in data["problems"]))
        self.refused("list_rules", "invalid_arguments", offset=-1)
        self.refused("list_rules", "invalid_arguments", limit=True)

    def test_row_shape(self) -> None:
        row = self.ok("list_rules", limit=1)["rules"][0]
        rule = self.catalog.rules[row["id"]]
        self.assertEqual(row, {"id": rule.id, "group": rule.group, "title": rule.title, "level": rule.level, "phase": rule.phase,
                               "enabled": self.profile.is_enabled(rule.id), "default": rule.default, "risky": rule.level == "risky",
                               "imported": False, "covered_by": None, "text_language": "en"})

    def test_group_filter_includes_subgroups(self) -> None:
        page = self.ok("list_rules", group="defender", limit=500)
        self.assertEqual([r["id"] for r in page["rules"]], [r.id for r in self.catalog.rules_in_group("defender")])
        self.assertIn("defender.asr", {r["group"] for r in page["rules"]})
        self.assertEqual(self.refused("list_rules", "unknown_id", group="nope")["id"], "nope")

    def test_query_in_english(self) -> None:
        page = self.ok("list_rules", query="PUA")
        self.assertIn("defender.pua", [r["id"] for r in page["rules"]])
        self.assertEqual(page["total"], len(self.catalog.search("PUA")))
        self.refused("list_rules", "invalid_arguments", query="")

    def test_query_in_ukrainian(self) -> None:
        texts = CatalogTexts.load(ROOT / "rules", "uk")
        title = texts.rule(self.catalog.rules["defender.pua"], "title")
        self.assertNotEqual(title, self.catalog.rules["defender.pua"].title)
        page = self.ok("list_rules", query=title, language="uk")
        ids = [r["id"] for r in page["rules"]]
        self.assertIn("defender.pua", ids)
        row = page["rules"][ids.index("defender.pua")]
        self.assertEqual((row["title"], row["text_language"], page["language"]), (title, "uk", "uk"))
        self.assertEqual(self.ok("list_rules", query=title)["total"], 0)  # the English search does not know the Ukrainian title

    def test_enabled_filter(self) -> None:
        on = self.ok("list_rules", enabled=True, limit=500)
        off = self.ok("list_rules", enabled=False, limit=500)
        self.assertTrue(all(r["enabled"] for r in on["rules"]))
        self.assertFalse(any(r["enabled"] for r in off["rules"]))
        self.assertEqual((on["total"], on["total"] + off["total"]), (len(self.profile.enabled_ids()), len(self.catalog.rules)))

    def test_level_and_phase_filters(self) -> None:
        risky = self.ok("list_rules", level="risky", limit=500)
        self.assertEqual({r["level"] for r in risky["rules"]}, {"risky"})
        self.assertTrue(all(r["risky"] for r in risky["rules"]))
        self.assertEqual(risky["total"], sum(1 for r in self.catalog.rules.values() if r.level == "risky"))
        phase = self.ok("list_rules", phase="specialize", limit=500)
        self.assertEqual(phase["total"], sum(1 for r in self.catalog.rules.values() if r.phase == "specialize"))
        self.assertEqual({r["phase"] for r in phase["rules"]}, {"specialize"})
        self.refused("list_rules", "invalid_arguments", level="huge")
        self.refused("list_rules", "invalid_arguments", phase="never")

    def test_imported_filter(self) -> None:
        self.assertEqual(self.ok("list_rules", imported=True)["total"], 0)
        self.import_templates()
        page = self.ok("list_rules", imported=True, limit=500)
        self.assertEqual(page["total"], sum(1 for rule_id in self.catalog.rules if is_imported(rule_id)))
        self.assertTrue(all(r["imported"] and r["id"].startswith("admx.") and r["text_language"] == "en" for r in page["rules"]))
        self.assertEqual(self.ok("list_rules", imported=False, limit=500)["total"], len(base_catalog().rules))

    def test_filters_combine(self) -> None:
        page = self.ok("list_rules", group="defender", enabled=True, phase="specialize", limit=500)
        expected = [r.id for r in self.catalog.rules_in_group("defender") if self.profile.is_enabled(r.id) and r.phase == "specialize"]
        self.assertEqual([r["id"] for r in page["rules"]], expected)


class RuleCardTest(McpToolsTestCase):
    def test_built_in_rule_card(self) -> None:
        rule = self.catalog.rules["defender.pua"]
        card = self.ok("get_rule", id="defender.pua")
        self.assertEqual((card["id"], card["group"], card["phase"], card["level"]), (rule.id, rule.group, rule.phase, rule.level))
        self.assertEqual((card["title"], card["summary"], card["effect"], card["risk"]), (rule.title, rule.summary, rule.effect, rule.risk))
        self.assertEqual(card["group_title"], self.catalog.groups[rule.group].title)
        self.assertEqual((card["enabled"], card["default"], card["origin"], card["text_language"], card["linked"]),
                         (True, True, None, "en", None))
        self.assertEqual((card["requires"], card["required_by"], card["conflicts"]),
                         (list(rule.requires), self.catalog.required_by(rule.id), list(rule.conflicts)))
        self.assertEqual(card["dependents"], Resolver(self.catalog).dependents(rule.id))
        self.assertEqual([a["type"] for a in card["actions"]], [a.type for a in rule.actions])
        self.assertTrue(card["verify_steps"] and card["rollback_steps"])
        self.assertEqual(card["doc"], rule.doc or None)
        self.assertEqual(card["same_values"], [])

    def test_ukrainian_texts_when_requested(self) -> None:
        texts = CatalogTexts.load(ROOT / "rules", "uk")
        rule = self.catalog.rules["defender.pua"]
        card = self.ok("get_rule", id="defender.pua", language="uk")
        self.assertEqual((card["title"], card["text_language"]), (texts.rule(rule, "title"), "uk"))
        self.assertEqual(card["group_title"], texts.group(self.catalog.groups[rule.group], "title"))

    def test_parameters_with_current_values(self) -> None:
        self.mode = MODE_EDIT
        self.ok("set_param", id=INT_RULE, name=INT_PARAM, value=9)
        card = self.ok("get_rule", id=INT_RULE)
        param = {p["name"]: p for p in card["params"]}[INT_PARAM]
        definition = self.catalog.rules[INT_RULE].params[INT_PARAM]
        self.assertEqual(param, {"name": INT_PARAM, "type": "int", "title": definition.title, "value": 9, "default": definition.default,
                                 "min": definition.min, "max": definition.max})
        enum_card = self.ok("get_rule", id="defender.cloud")
        level = next(p for p in enum_card["params"] if p["type"] == "enum")
        self.assertEqual([v["value"] for v in level["values"]], [v for v, _ in self.catalog.rules["defender.cloud"].params[level["name"]].values])

    def test_imported_rule_card(self) -> None:
        info = self.import_templates()
        card = self.ok("get_rule", id=TOGGLE, language="uk")
        self.assertEqual(card["origin"], {"import": info.id, "name": info.name, "file": "wktest.admx", "policy": "SimpleToggle",
                                          "unreviewed_text": True})
        self.assertEqual(card["text_language"], "en")  # texts of imported policies follow the program, whatever is requested
        self.assertEqual((card["title"], card["enabled"], card["default"]), (self.catalog.rules[TOGGLE].title, False, False))
        self.assertEqual([p["name"] for p in card["params"]], ["state"])
        self.assertEqual(card["group_title"], self.catalog.groups[self.catalog.rules[TOGGLE].group].title)

    def test_a_linked_policy_is_shown_covered(self) -> None:
        self.import_templates()
        card = self.ok("get_rule", id=SAME)
        self.assertEqual(card["linked"], {"rule": "defender.pua", "equal": True, "covered": True, "values_from_rule": True})
        self.assertTrue(card["enabled"])  # shown on through the built-in rule
        self.assertEqual(card["same_values"], ["defender.pua"])
        row = next(r for r in self.ok("list_rules", query="Same as built-in")["rules"] if r["id"] == SAME)
        self.assertEqual((row["enabled"], row["covered_by"]), (True, "defender.pua"))

    def test_unknown_id_suggests_rules(self) -> None:
        data = self.refused("get_rule", "unknown_id", id="defender.puaa")
        self.assertEqual(data["id"], "defender.puaa")
        self.assertIn("defender.pua", data["suggestions"])
        self.assertLessEqual(len(data["suggestions"]), 3)
        self.assertEqual(self.refused("get_rule", "unknown_id", id="zzzz.qqqq")["suggestions"], [])

    def test_bad_or_missing_id(self) -> None:
        self.refused("get_rule", "invalid_arguments", id="a b")
        self.refused("get_rule", "invalid_arguments")


class ProfileTest(McpToolsTestCase):
    def test_profile_is_redacted(self) -> None:
        self.attach(self.secret_profile())
        data = self.ok("get_profile")
        self.assertEqual(data["install"]["has_product_key"], True)
        self.assertNotIn("product_key", data["install"])
        self.assertEqual([a["has_password"] for a in data["accounts"]], [True, False])
        self.assertFalse(any("password" in a for a in data["accounts"]))
        self.assertTrue(all("description_text" in a for a in data["accounts"]))
        self.assertIn("comment_text", data)
        self.assertIn("author_text", data)
        self.assertNotIn("comment", data)
        self.assertNotIn("author", data)
        text = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(SECRET_PASSWORD, text)
        self.assertNotIn(SECRET_KEY, text)

    def test_state_fields(self) -> None:
        data = self.ok("get_profile")
        self.assertEqual((data["name"], data["file"], data["dirty"], data["enabled_count"]),
                         ("Office", OFFICE.name, False, len(self.profile.enabled_ids())))
        self.assertEqual(data["rules"]["defender.pua"], {"enabled": True})
        self.assertEqual(data["changed_from_defaults"], [])

    def test_changed_from_defaults(self) -> None:
        self.mode = MODE_EDIT
        self.ok("set_rules", items=[{"id": "defender.pua", "enabled": False}])
        self.ok("set_param", id=INT_RULE, name=INT_PARAM, value=9)
        changed = self.ok("get_profile")["changed_from_defaults"]
        self.assertIn("defender.pua", changed)
        self.assertIn(INT_RULE, changed)
        self.assertEqual(changed, [r for r in self.catalog.order if r in changed])  # catalog order


class ProfilesListTest(McpToolsTestCase):
    def test_presets_from_data_and_user_files_from_root(self) -> None:
        self.assertNotEqual(self.paths.data, self.paths.root)
        other = self.office_profile()
        other.save(self.paths.profiles / "Профіль.json", self.catalog)
        (self.paths.profiles / "CON.json").write_text("{}", encoding="utf-8")  # a reserved name: counted, not listed
        (self.paths.profiles / "preset-mine.json").write_text("{}", encoding="utf-8")  # not a preset folder: ignored
        (self.paths.profiles / "broken.json").write_text("not json", encoding="utf-8")
        data = self.ok("list_profiles")
        presets = [p for p in data["profiles"] if p["kind"] == "preset"]
        self.assertEqual(sorted(p["name"] for p in presets), sorted(PRESET_IDS))
        self.assertTrue(all(p["readable"] and p["catalog_version"] == self.catalog.version for p in presets))
        users = {p["name"]: p for p in data["profiles"] if p["kind"] == "user"}
        self.assertEqual(sorted(users), ["broken", "Профіль"])
        self.assertEqual((users["Профіль"]["readable"], users["Профіль"]["title_text"]), (True, "Office"))
        self.assertEqual(users["broken"]["readable"], False)
        self.assertEqual(data["unlisted"], 1)
        for entry in data["profiles"]:
            self.assertEqual(set(entry), {"name", "kind", "title_text", "modified", "catalog_version", "readable"})

    def test_without_user_profiles(self) -> None:
        data = self.ok("list_profiles")
        self.assertEqual(([p["kind"] for p in data["profiles"]], data["unlisted"]), (["preset"] * 4, 0))


class DiffTest(McpToolsTestCase):
    def test_against_a_preset(self) -> None:
        strict, _ = Profile.load(ROOT / "profiles" / "preset-strict.json", self.catalog)
        expected = self.profile.diff(strict, self.catalog)
        self.assertTrue(expected)
        data = self.ok("diff_profile", name="strict")
        self.assertEqual(data["other"], "strict")
        self.assertEqual([(d["kind"], d["key"]) for d in data["differences"]], [(d.kind, d.key) for d in expected])
        for row, item in zip(data["differences"], expected):
            if item.kind in ("rule", "param"):
                self.assertEqual((row["before"], row["after"]), (item.before, item.after))

    def test_against_a_saved_user_profile(self) -> None:
        other = self.office_profile()
        other.rules["printing.spooler-automatic"].enabled = not other.rules["printing.spooler-automatic"].enabled
        other.set_param(INT_RULE, INT_PARAM, 11)
        other.save(self.paths.profiles / "Профіль.json", self.catalog)
        expected = self.profile.diff(other, self.catalog)
        data = self.ok("diff_profile", name="Профіль")
        self.assertEqual(data["differences"], [{"kind": d.kind, "key": d.key, "before": d.before, "after": d.after} for d in expected])
        self.assertIn(("param", f"{INT_RULE}.{INT_PARAM}"), [(d["kind"], d["key"]) for d in data["differences"]])

    def test_the_same_profile_has_no_differences(self) -> None:
        self.assertEqual(self.ok("diff_profile", name="office")["differences"], [])
        self.assertEqual(self.ok("diff_profile", name="OFFICE")["differences"], [])  # preset ids are case-insensitive

    def test_unknown_and_refused_names(self) -> None:
        self.assertEqual(self.refused("diff_profile", "unknown_id", name="nope")["name"], "nope")
        self.refused("diff_profile", "name_refused", name="..")
        self.refused("diff_profile", "name_refused", name="preset-office")

    def test_product_key_is_hidden(self) -> None:
        self.attach(self.secret_profile())
        data = self.ok("diff_profile", name="office")
        rows = {(d["kind"], d["key"]): d for d in data["differences"]}
        self.assertEqual((rows[("install", "product_key")]["before"], rows[("install", "product_key")]["after"]), (HIDDEN, HIDDEN))
        self.assertEqual((rows[("install", "product_key_mode")]["before"], rows[("install", "product_key_mode")]["after"]),
                         ("custom", "generic"))
        self.assertEqual(rows[("accounts", "accounts")]["before"], ["Admin", "User"])
        text = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(SECRET_KEY, text)
        self.assertNotIn(SECRET_PASSWORD, text)


class CheckTest(McpToolsTestCase):
    def test_equals_validate_profile_plus_validate_xml(self) -> None:
        build = self.build(self.profile)
        expected = validate_profile(self.profile, self.catalog, self.resources.keyboards) + validate_xml(build.xml)
        data = self.ok("check_profile")
        self.assertEqual([(i["level"], i["target"], i["message"], i["doc"]) for i in data["issues"]],
                         [(i.level, i.target, i.message, i.doc or None) for i in expected])
        self.assertEqual((data["ok"], data["errors"], data["warnings"]), (True, 0, sum(1 for i in expected if i.level == "warning")))
        self.assertEqual(data["build"], {"rules": len(build.rule_ids), "warnings": build.warnings})
        self.assertEqual((data["powershell_checked"], data["issues_language"]), (False, "en"))

    def test_errors_stop_the_build(self) -> None:
        self.profile.install["time_zone"] = ""
        data = self.ok("check_profile")
        self.assertEqual((data["ok"], data["build"], data["powershell_checked"]), (False, None, False))
        self.assertGreaterEqual(data["errors"], 1)
        self.assertIn("install.time_zone", [i["target"] for i in data["issues"] if i["level"] == "error"])

    def test_nothing_is_written(self) -> None:
        self.ok("check_profile")
        self.assertEqual(list(self.paths.output.iterdir()), [])
        self.assertEqual(list(self.paths.profiles.iterdir()), [])
        self.assertFalse(self.workspace.dirty)


class PreviewTest(McpToolsTestCase):
    def test_answer_file_text_equals_the_redacted_build(self) -> None:
        expected = self.build(redacted_copy(self.profile))
        result = self.call("preview_build")
        self.assertFalse(result["isError"])
        self.assertEqual(result["content"][0]["text"], expected.xml)
        self.assertEqual(result["structuredContent"], {"part": "autounattend.xml", "parts": list(PARTS), "redacted": True,
                                                       "bytes": len(expected.xml.encode("utf-8")), "truncated": False,
                                                       "rules": len(expected.rule_ids)})

    def test_each_script_part(self) -> None:
        expected = self.build(redacted_copy(self.profile))
        self.assertEqual(PARTS, ("autounattend.xml", *SCRIPT_ORDER))
        for part in SCRIPT_ORDER:
            with self.subTest(part=part):
                result = self.call("preview_build", part=part)
                self.assertFalse(result["isError"])
                self.assertEqual(result["content"][0]["text"], expected.scripts[part])
                self.assertEqual(result["structuredContent"]["part"], part)
        self.refused("preview_build", "invalid_arguments", part="Other.ps1")

    def test_secrets_are_absent_from_every_part(self) -> None:
        self.attach(self.secret_profile())
        for part in PARTS:
            with self.subTest(part=part):
                result = self.call("preview_build", part=part)
                self.assertFalse(result["isError"])
                text = result["content"][0]["text"]
                self.assertNotIn(SECRET_PASSWORD, text)
                self.assertNotIn(SECRET_KEY, text)
                self.assertTrue(result["structuredContent"]["redacted"])
        self.assertIn(KEY_PLACEHOLDER, self.call("preview_build")["content"][0]["text"])

    def test_short_passwords_do_not_trip_the_check(self) -> None:
        for password in ("1", "a", "Admin", "2026"):
            with self.subTest(password=password):
                profile = self.office_profile()
                profile.accounts[0].password = password
                self.attach(profile)
                self.assertTrue(self.ok("preview_build")["redacted"])

    def test_the_structural_check_refuses_an_unredacted_build(self) -> None:
        profile = self.secret_profile()
        with self.assertRaises(RedactionError):
            assert_redacted_build(self.build(profile))
        assert_redacted_build(self.build(redacted_copy(profile)))

    def test_errors_refuse_the_preview(self) -> None:
        self.profile.install["time_zone"] = ""
        self.assertTrue(self.refused("preview_build", "validation_failed")["errors"])

    def test_nothing_is_written(self) -> None:
        self.ok("preview_build")
        self.assertEqual(list(self.paths.output.iterdir()), [])


class MessagesTest(McpToolsTestCase):
    def test_headless_messages_follow_the_last_build(self) -> None:
        self.assertEqual(self.ok("get_messages"), {"issues": [], "issues_language": "en"})
        self.mode = MODE_FILES
        self.ok("write_answer_file", name="one")
        data = self.ok("get_messages")
        self.assertEqual(data["issues"][-1], {"level": "info", "target": "powershell", "message": POWERSHELL_NOTE, "doc": None})
        self.profile.install["time_zone"] = ""
        self.refused("write_answer_file", "validation_failed", name="two")
        self.assertIn("install.time_zone", [i["target"] for i in self.ok("get_messages")["issues"] if i["level"] == "error"])


# --------------------------------------------------------------------------- edit tools


class SetRulesTest(McpToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mode = MODE_EDIT

    def test_cascade_equals_the_resolver(self) -> None:
        expected = Resolver(self.catalog).set_rule(self.profile.copy(), "defender.asr", False)
        self.assertGreater(len(expected), 1)  # the ASR rules go off with their parent
        data = self.ok("set_rules", items=[{"id": "defender.asr", "enabled": False}])
        self.assertEqual(data["changes"], change_rows(expected))
        self.assertEqual((data["refused"], data["dirty"], data["issues_errors"]), ([], True, 0))
        self.assertTrue(self.workspace.dirty)
        self.assertFalse(any(self.profile.is_enabled(r) for r in self.catalog.required_by("defender.asr")))

    def test_enabling_pulls_the_requirements(self) -> None:
        for rule_id in ("update.unblock", INT_RULE):
            self.profile.rules[rule_id].enabled = False
        expected = Resolver(self.catalog).set_rule(self.profile.copy(), INT_RULE, True)
        data = self.ok("set_rules", items=[{"id": INT_RULE, "enabled": True}])
        self.assertEqual(data["changes"], change_rows(expected))
        self.assertIn({"id": "update.unblock", "enabled": True, "reason": f"required by {INT_RULE}"}, data["changes"])

    def test_several_items_in_order(self) -> None:
        copied = self.profile.copy()
        resolver = Resolver(self.catalog)
        expected = resolver.set_rule(copied, "defender.pua", False) + resolver.set_rule(copied, "printing.spooler-automatic", False)
        data = self.ok("set_rules", items=[{"id": "defender.pua", "enabled": False}, {"id": "printing.spooler-automatic", "enabled": False}])
        self.assertEqual(data["changes"], change_rows(expected))

    def test_unknown_ids_are_refused_and_the_rest_applied(self) -> None:
        data = self.ok("set_rules", items=[{"id": "no.such", "enabled": True}, {"id": "defender.pua", "enabled": False}])
        self.assertEqual(data["refused"], [{"id": "no.such", "reason": "unknown rule"}])
        self.assertEqual([c["id"] for c in data["changes"]], ["defender.pua"])
        self.assertFalse(self.profile.is_enabled("defender.pua"))

    def test_no_change_when_already_in_that_state(self) -> None:
        data = self.ok("set_rules", items=[{"id": "defender.pua", "enabled": True}])
        self.assertEqual((data["changes"], data["refused"]), ([], []))
        self.assertFalse(self.workspace.dirty)

    def test_conflicts_are_reported(self) -> None:
        self.import_templates()  # the built-in catalog has no conflicts; a two-state policy gives a conflicting pair
        self.assertEqual(self.catalog.rules[PAIR].conflicts, (PAIR + ".off",))
        self.profile.rules[PAIR + ".off"].enabled = True
        expected = Resolver(self.catalog).set_rule(self.profile.copy(), PAIR, True)
        data = self.ok("set_rules", items=[{"id": PAIR, "enabled": True}])
        self.assertEqual(data["changes"], change_rows(expected))
        self.assertIn({"id": PAIR + ".off", "enabled": False, "reason": f"conflicts with {PAIR}"}, data["changes"])
        self.assertEqual((self.profile.is_enabled(PAIR), self.profile.is_enabled(PAIR + ".off")), (True, False))

    def test_redundant_policies_are_dropped(self) -> None:
        self.import_templates()
        self.profile.rules[SAME].enabled = True  # as if set by hand while the built-in rule defender.pua is on
        self.assertEqual(linked.redundant(self.catalog, self.profile), [(SAME, "defender.pua")])
        data = self.ok("set_rules", items=[{"id": "printing.spooler-automatic", "enabled": False}])
        self.assertIn({"id": SAME, "enabled": False, "reason": "covered by defender.pua"}, data["changes"])
        self.assertFalse(self.profile.is_enabled(SAME))

    def test_a_linked_policy_switches_the_built_in_rule(self) -> None:
        self.import_templates()
        expected = Resolver(self.catalog).set_rule(self.profile.copy(), "defender.pua", False)
        data = self.ok("set_rules", items=[{"id": SAME, "enabled": False}])
        self.assertEqual(data["changes"], change_rows(expected))
        self.assertFalse(self.profile.is_enabled("defender.pua"))
        data = self.ok("set_rules", items=[{"id": SAME, "enabled": True}])
        self.assertEqual([c["id"] for c in data["changes"]], ["defender.pua"])  # the reviewed built-in rule is used
        self.assertFalse(self.profile.is_enabled(SAME))

    def test_a_covered_policy_already_on_needs_no_change(self) -> None:
        self.import_templates()
        data = self.ok("set_rules", items=[{"id": SAME, "enabled": True}])
        self.assertEqual(data["changes"], [])
        self.assertFalse(self.profile.is_enabled(SAME))

    def test_schema(self) -> None:
        self.refused("set_rules", "invalid_arguments", items=[])
        self.refused("set_rules", "invalid_arguments", items=[{"id": "defender.pua"}])
        self.refused("set_rules", "invalid_arguments", items=[{"id": "defender.pua", "enabled": "yes"}])
        self.refused("set_rules", "invalid_arguments", items=[{"id": "defender.pua", "enabled": True}] * 201)
        self.refused("set_rules", "invalid_arguments")


class SetGroupTest(McpToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mode = MODE_EDIT

    def test_off_and_on_equal_the_resolver(self) -> None:
        for action in ("off", "on"):
            with self.subTest(action=action):
                expected = Resolver(self.catalog).set_group(self.profile.copy(), "printing", action == "on")
                data = self.ok("set_group", id="printing", action=action)
                self.assertEqual(data, {"id": "printing", "action": action, "changes": change_rows(expected), "dirty": True, "issues_errors": 0})
        self.assertTrue(all(self.profile.is_enabled(r.id) for r in self.catalog.rules_in_group("printing")))

    def test_defaults_equal_reset_group(self) -> None:
        self.ok("set_group", id="defender", action="off")
        expected = Resolver(self.catalog).reset_group(self.profile.copy(), "defender")
        self.assertTrue(expected)
        data = self.ok("set_group", id="defender", action="defaults")
        self.assertEqual(data["changes"], change_rows(expected))
        for rule in self.catalog.rules_in_group("defender"):
            self.assertEqual(self.profile.is_enabled(rule.id), rule.default, rule.id)

    def test_an_imported_group_is_only_switched_off(self) -> None:
        info = self.import_templates()
        group = "admx." + info.id
        for action in ("on", "defaults"):
            with self.subTest(action=action):
                self.assertEqual(self.refused("set_group", "refused", id=group, action=action)["id"], group)
        self.assertFalse(any(self.profile.is_enabled(r) for r in self.catalog.rules if is_imported(r)))
        self.profile.rules[TOGGLE].enabled = True
        data = self.ok("set_group", id=group, action="off")
        self.assertEqual([c["id"] for c in data["changes"]], [TOGGLE])
        self.assertFalse(self.profile.is_enabled(TOGGLE))

    def test_unknown_group_and_bad_action(self) -> None:
        self.assertEqual(self.refused("set_group", "unknown_id", id="nope", action="on")["id"], "nope")
        self.refused("set_group", "invalid_arguments", id="printing", action="toggle")
        self.refused("set_group", "invalid_arguments", id="printing")
        self.assertFalse(self.workspace.dirty)


class SetParamTest(McpToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mode = MODE_EDIT

    def test_stores_a_good_value(self) -> None:
        data = self.ok("set_param", id=INT_RULE, name=INT_PARAM, value=9)
        self.assertEqual(data, {"id": INT_RULE, "name": INT_PARAM, "value": 9, "dirty": True})
        self.assertEqual(self.profile.param(self.catalog, INT_RULE, INT_PARAM), 9)
        self.assertTrue(self.workspace.dirty)

    def test_the_default_clears_the_override(self) -> None:
        self.ok("set_param", id=INT_RULE, name=INT_PARAM, value=9)
        default = self.catalog.rules[INT_RULE].params[INT_PARAM].default
        self.ok("set_param", id=INT_RULE, name=INT_PARAM, value=default)
        self.assertNotIn(INT_PARAM, self.profile.rules[INT_RULE].params)

    def test_rejects_a_bad_type(self) -> None:
        for value in ("9", True, [9], 9.5):
            with self.subTest(value=value):
                data = self.refused("set_param", "invalid_arguments", id=INT_RULE, name=INT_PARAM, value=value)
                self.assertTrue(data["message"])
        self.assertEqual(self.profile.rules[INT_RULE].params, {})
        self.assertFalse(self.workspace.dirty)

    def test_rejects_an_out_of_range_int(self) -> None:
        definition = self.catalog.rules[INT_RULE].params[INT_PARAM]
        for value in (definition.min - 1, definition.max + 1):
            with self.subTest(value=value):
                data = self.refused("set_param", "invalid_arguments", id=INT_RULE, name=INT_PARAM, value=value)
                self.assertIn("out of range", data["message"])
                self.assertEqual((data["id"], data["name"]), (INT_RULE, INT_PARAM))
        self.assertEqual(self.profile.rules[INT_RULE].params, {})

    def test_rejects_an_unknown_parameter_or_rule(self) -> None:
        data = self.refused("set_param", "invalid_arguments", id=INT_RULE, name="nope", value=1)
        self.assertEqual(data["params"], list(self.catalog.rules[INT_RULE].params))
        self.assertEqual(self.refused("set_param", "unknown_id", id="no.such", name="x", value=1)["id"], "no.such")

    def test_enum_values(self) -> None:
        allowed = [v for v, _ in self.catalog.rules["defender.cloud"].params["block_level"].values]
        data = self.refused("set_param", "invalid_arguments", id="defender.cloud", name="block_level", value="loud")
        self.assertEqual(data["values"], allowed)
        self.ok("set_param", id="defender.cloud", name="block_level", value=allowed[-1])
        self.assertEqual(self.profile.param(self.catalog, "defender.cloud", "block_level"), allowed[-1])

    def test_string_values_are_stripped_and_checked(self) -> None:
        data = self.ok("set_param", id="default-user.region", name="geo_id", value="  244 ")
        self.assertEqual(data["value"], "244")
        self.assertEqual(self.profile.param(self.catalog, "default-user.region", "geo_id"), "244")
        self.refused("set_param", "invalid_arguments", id="default-user.region", name="geo_id", value="a]]>b")
        self.refused("set_param", "invalid_arguments", id="default-user.region", name="geo_id", value=244)
        self.refused("set_param", "invalid_arguments", id="default-user.region", name="geo_id", value="x" * 4001)

    def test_a_value_that_introduces_a_validation_error_is_rolled_back(self) -> None:
        from winkickoff.mcp import workspace as workspace_module

        real = workspace_module.validate_profile
        calls: list[int] = []

        def after_the_change(profile: Profile, catalog: Any, keyboards: Any = None) -> list[Issue]:
            calls.append(1)
            issues = real(profile, catalog, keyboards)
            return issues + ([Issue("error", INT_RULE, "introduced by the test")] if len(calls) > 1 else [])

        with mock.patch.object(workspace_module, "validate_profile", after_the_change):
            data = self.refused("set_param", "validation_failed", id=INT_RULE, name=INT_PARAM, value=9)
        self.assertEqual(len(calls), 2)
        self.assertIn("introduced by the test", data["message"])
        self.assertEqual((data["id"], data["name"]), (INT_RULE, INT_PARAM))
        self.assertEqual(self.profile.rules[INT_RULE].params, {})  # restored
        self.assertFalse(self.workspace.dirty)

    def test_list_parameter_of_an_imported_policy(self) -> None:
        self.import_templates()
        data = self.ok("set_param", id=HASLIST, name="items", value=[" a.example ", "", "b.example"])
        self.assertEqual(data["value"], ["a.example", "b.example"])
        self.assertEqual(self.profile.param(self.catalog, HASLIST, "items"), ["a.example", "b.example"])
        data = self.refused("set_param", "invalid_arguments", id=HASLIST, name="items", value=["x]]>y"])
        self.assertIn("line 1", data["message"])
        self.refused("set_param", "invalid_arguments", id=HASLIST, name="items", value="a.example")
        self.refused("set_param", "invalid_arguments", id=HASLIST, name="items", value=[1])
        self.assertEqual(self.profile.param(self.catalog, HASLIST, "items"), ["a.example", "b.example"])
        data = self.refused("set_param", "invalid_arguments", id=LINES, name="text", value=[])  # required
        self.assertIn("cannot be empty", data["message"])
        self.refused("set_param", "invalid_arguments", id=HASLIST, name="items", value=["x" * 2001, "y" * 2001])  # joined 4000

    def test_schema(self) -> None:
        self.refused("set_param", "invalid_arguments", id=INT_RULE, name=INT_PARAM)
        self.refused("set_param", "invalid_arguments", id=INT_RULE, name="", value=1)
        self.refused("set_param", "invalid_arguments", id=INT_RULE, name=INT_PARAM, value={"a": 1})
        self.refused("set_param", "invalid_arguments", id=INT_RULE, name=INT_PARAM, value=None)


class ProfileInfoTest(McpToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mode = MODE_EDIT

    def test_strips_control_and_invisible_characters(self) -> None:
        data = self.ok("set_profile_info", name=" Office" + chr(7) + "-PC" + chr(0x200B) + " ", author="me" + chr(1) + chr(0x202E),
                       comment="line 1\r\nline 2" + chr(0xFEFF))
        self.assertEqual(data, {"name": "Office-PC", "author_text": "me", "comment_text": "line 1\nline 2", "dirty": True})
        self.assertEqual((self.profile.name, self.profile.author, self.profile.comment), ("Office-PC", "me", "line 1\nline 2"))
        self.assertTrue(self.workspace.dirty)

    def test_refuses_an_empty_name(self) -> None:
        self.refused("set_profile_info", "invalid_arguments", name="")
        data = self.refused("set_profile_info", "invalid_arguments", name=chr(7) + " ")
        self.assertIn("empty", data["message"])
        self.assertEqual(self.profile.name, "Office")
        self.assertFalse(self.workspace.dirty)

    def test_a_partial_update_keeps_the_other_fields(self) -> None:
        comment = self.profile.comment
        data = self.ok("set_profile_info", author="me")
        self.assertEqual((data["name"], data["author_text"], data["comment_text"]), ("Office", "me", comment))
        self.assertEqual((self.profile.name, self.profile.comment), ("Office", comment))

    def test_long_texts_are_refused_by_the_schema(self) -> None:
        self.refused("set_profile_info", "invalid_arguments", name="n" * 81)
        self.refused("set_profile_info", "invalid_arguments", comment="c" * 2001)


class LoadProfileTest(McpToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mode = MODE_EDIT

    def test_refuses_when_dirty_without_force(self) -> None:
        self.ok("set_rules", items=[{"id": "defender.pua", "enabled": False}])
        self.refused("load_profile", "unsaved_changes", name="strict")
        self.assertFalse(self.workspace.profile.is_enabled("defender.pua"))  # nothing replaced
        self.assertTrue(self.workspace.dirty)

    def test_force_drops_the_changes(self) -> None:
        self.ok("set_rules", items=[{"id": "defender.pua", "enabled": False}])
        strict, _ = Profile.load(ROOT / "profiles" / "preset-strict.json", self.catalog)
        data = self.ok("load_profile", name="strict", force=True)
        self.assertEqual(data, {"name": "strict", "file": "preset-strict.json", "warnings": [], "forced": True})  # name only: the preset lies outside the program folder of the test
        self.assertEqual(self.workspace.profile.to_dict(self.catalog), strict.to_dict(self.catalog))
        self.assertFalse(self.workspace.dirty)
        self.assertEqual(self.ok("get_status")["profile"]["name"], strict.name)

    def test_loads_when_clean(self) -> None:
        data = self.ok("load_profile", name="laptop")
        self.assertEqual((data["name"], data["forced"]), ("laptop", False))
        self.assertEqual(self.ok("get_status")["profile"]["dirty"], False)

    def test_loads_a_saved_user_profile(self) -> None:
        other = self.office_profile()
        other.name = "Office PC"
        other.save(self.paths.profiles / "Профіль.json", self.catalog)
        data = self.ok("load_profile", name="Профіль")
        self.assertEqual(data["file"], str(Path("profiles") / "Профіль.json"))
        self.assertEqual(self.workspace.profile.name, "Office PC")

    def test_unknown_and_refused_names(self) -> None:
        self.assertEqual(self.refused("load_profile", "unknown_id", name="nope")["name"], "nope")
        self.refused("load_profile", "name_refused", name="preset-x")
        self.refused("load_profile", "name_refused", name="..")
        self.refused("load_profile", "invalid_arguments", name="")
        self.assertEqual(self.workspace.profile.name, "Office")

    def test_a_damaged_file_is_load_failed(self) -> None:
        (self.paths.profiles / "bad.json").write_text("[1, 2]", encoding="utf-8")
        data = self.refused("load_profile", "load_failed", name="bad")
        self.assertIn("ValueError", data["message"])  # the exception class, never the text of the file
        self.assertEqual(self.workspace.profile.name, "Office")


class ShowItemTest(McpToolsTestCase):
    def test_headless_has_no_window(self) -> None:
        self.mode = MODE_EDIT
        for item in ("r:defender.pua", "g:defender", "data:accounts"):
            with self.subTest(item=item):
                self.assertEqual(self.ok("show_item", item=item), {"shown": False, "reason": "no window"})
        self.refused("show_item", "invalid_arguments", item="defender.pua")
        self.refused("show_item", "invalid_arguments", item="data:secrets")


# --------------------------------------------------------------------------- files tools


class SaveProfileTest(McpToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mode = MODE_FILES

    def test_writes_a_new_file_that_loads_back_equal(self) -> None:
        self.ok("set_rules", items=[{"id": "defender.pua", "enabled": False}])
        self.ok("set_param", id=INT_RULE, name=INT_PARAM, value=9)
        path = self.paths.profiles / "Профіль.json"
        data = self.ok("save_profile", name="Профіль")
        self.assertEqual(data, {"file": display_path(path, self.paths.root), "dirty": False})
        self.assertEqual([p.name for p in self.paths.profiles.iterdir()], ["Профіль.json"])
        self.assertFalse(self.workspace.dirty)
        loaded, warnings = Profile.load(path, self.catalog)
        self.assertEqual(warnings, [])
        self.assertEqual(loaded.to_dict(self.catalog), self.workspace.profile.to_dict(self.catalog))
        self.assertEqual((loaded.name, loaded.is_enabled("defender.pua"), loaded.param(self.catalog, INT_RULE, INT_PARAM)), ("Профіль", False, 9))
        self.assertEqual(self.ok("get_status")["profile"], {"name": "Профіль", "file": str(Path("profiles") / "Профіль.json"), "dirty": False,
                                                            "enabled": len(loaded.enabled_ids()), "total": len(self.catalog.rules)})

    def test_never_replaces_an_existing_file(self) -> None:
        path = self.paths.profiles / "Профіль.json"
        self.ok("save_profile", name="Профіль")
        before = path.read_bytes()
        self.ok("set_rules", items=[{"id": "defender.pua", "enabled": False}])
        self.assertEqual(self.refused("save_profile", "exists", name="Профіль")["name"], "Профіль")
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(self.workspace.dirty)

    def test_refuses_names(self) -> None:
        refused = ("preset-x", "Preset-Office", "..", "CON", "com1.json", "a/b", "a\\b", "name.", " name", chr(0x301) + "abc",
                   "a" + chr(0x338) + "b", "x" + chr(0x200B) + "y", "a" * 81)
        for name in refused:
            with self.subTest(name=name):
                result = self.call("save_profile", name=name)
                self.assertTrue(result["isError"])
                self.assertIn(result["structuredContent"]["error"], ("name_refused", "invalid_arguments"))
        self.assertEqual(list(self.paths.profiles.iterdir()), [])

    def test_accepted_names(self) -> None:
        for name in ("Профіль", "Профіль офісу", "Office 2026", "office.v2"):
            with self.subTest(name=name):
                self.assertIsNone(check_name(name))
                self.assertEqual(self.ok("save_profile", name=name)["file"], str(Path("profiles") / (name + ".json")))
        self.assertEqual(len(list(self.paths.profiles.iterdir())), 4)

    def test_the_file_holds_the_password_the_result_does_not(self) -> None:
        self.attach(self.secret_profile())
        data = self.ok("save_profile", name="secret")
        self.assertNotIn(SECRET_PASSWORD, json.dumps(data))
        text = (self.paths.profiles / "secret.json").read_text(encoding="utf-8")
        self.assertIn(SECRET_PASSWORD, text)  # a profile file keeps its passwords, as the window writes it
        self.assertIn(SECRET_KEY, text)


class WriteAnswerFileTest(McpToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mode = MODE_FILES

    def test_writes_the_build_of_the_open_profile(self) -> None:
        expected = self.build(self.profile)
        reference = self.tmp / "expected.xml"
        write_answer_file(expected, reference)
        target = self.paths.output / "Профіль.xml"
        data = self.ok("write_answer_file", name="Профіль")
        self.assertEqual(target.read_bytes(), reference.read_bytes())
        self.assertEqual([p.name for p in self.paths.output.iterdir()], ["Профіль.xml"])
        self.assertEqual((data["file"], data["rules"], data["powershell_checked"]),
                         (display_path(target, self.paths.root), len(expected.rule_ids), False))
        self.assertEqual(data["issues"][-1], {"level": "info", "target": "powershell", "message": POWERSHELL_NOTE, "doc": None})
        self.assertIn("autounattend.xml", data["note"])
        self.assertFalse(self.workspace.dirty)

    def test_refuses_an_existing_file(self) -> None:
        (self.paths.output / "one.xml").write_bytes(b"keep")
        self.assertEqual(self.refused("write_answer_file", "exists", name="one")["name"], "one")
        self.assertEqual((self.paths.output / "one.xml").read_bytes(), b"keep")

    def test_refuses_when_validation_has_errors(self) -> None:
        self.profile.install["time_zone"] = ""
        data = self.refused("write_answer_file", "validation_failed", name="two")
        self.assertTrue(data["errors"])
        self.assertEqual(list(self.paths.output.iterdir()), [])

    def test_refuses_names(self) -> None:
        for name in ("preset-x", "..", "CON", "a/b", "name."):
            with self.subTest(name=name):
                self.refused("write_answer_file", "name_refused", name=name)
        self.assertEqual(list(self.paths.output.iterdir()), [])

    def test_the_real_build_holds_the_secrets_the_result_does_not(self) -> None:
        self.attach(self.secret_profile())
        data = self.ok("write_answer_file", name="secret")
        text = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(SECRET_PASSWORD, text)
        self.assertNotIn(SECRET_KEY, text)
        written = (self.paths.output / "secret.xml").read_text(encoding="utf-8")
        self.assertIn(SECRET_PASSWORD, written)  # the file is the real answer file, as the window's Build writes it
        self.assertIn(SECRET_KEY, written)


# --------------------------------------------------------------------------- secrets and forbidden functions


class SecretsTest(McpToolsTestCase):
    def test_no_secret_leaves_any_tool(self) -> None:
        self.attach(self.secret_profile())
        self.mode = MODE_FILES
        args = representative("mcp-secret")
        first = [n for n in args if self.tools.specs[n].mode == MODE_READ]
        then = [n for n in args if self.tools.specs[n].mode != MODE_READ and n != "load_profile"]
        self.assertEqual(set(first + then + ["load_profile"]), set(self.tools.specs))
        texts: list[str] = []
        with self.assertLogs("winkickoff.mcp", level="DEBUG") as captured:
            for name in first + then:
                texts.append(json.dumps(self.ok(name, **args[name]), ensure_ascii=False))
            for part in PARTS:
                texts.append(json.dumps(self.call("preview_build", part=part), ensure_ascii=False))
            texts.append(json.dumps(self.ok("diff_profile", name="mcp-secret"), ensure_ascii=False))  # the saved copy, secrets inside
            texts.append(json.dumps(self.ok("get_profile"), ensure_ascii=False))
            texts.append(json.dumps(self.ok("get_messages"), ensure_ascii=False))
            texts.append(json.dumps(self.ok("load_profile", **args["load_profile"]), ensure_ascii=False))
            for entry in self.registry.listing():
                texts.append(json.dumps(self.read_resource(entry["uri"]), ensure_ascii=False))
            for uri in self.template_uris():
                texts.append(json.dumps(self.read_resource(uri), ensure_ascii=False))
            self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/unknown"}, self.session))  # one log line
        self.assertIn(SECRET_PASSWORD, (self.paths.profiles / "mcp-secret.json").read_text(encoding="utf-8"))  # the secret was there
        self.assertGreater(len(texts), 30)
        for text in texts + [str(entry) for entry in self.journal.entries()] + captured.output:
            self.assertNotIn(SECRET_PASSWORD, text)
            self.assertNotIn(SECRET_KEY, text)
        self.assertEqual(len(self.journal.entries()), self.seq + 1)  # one row per message, the notification included


class ForbiddenTest(McpToolsTestCase):
    TARGETS = ("winkickoff.core.apply.launch_elevated", "winkickoff.core.apply.run_audit", "winkickoff.mcp.tools.run_audit",
               "winkickoff.core.pscheck.check_scripts",
               "winkickoff.core.admx.save_import", "winkickoff.core.admx.delete_import", "winkickoff.core.admx.rename_import",
               "winkickoff.core.admx.read_templates", "winkickoff.core.settings.Settings.save", "os.startfile", "shutil.rmtree",
               "os.remove", "pathlib.Path.unlink")

    def test_forbidden_functions_unreachable(self) -> None:
        # the read of this PC runs its read-only PowerShell audit only with the option read_pc (ReadThisPcTest); off,
        # as at every start, nothing runs PowerShell, applies, deletes or imports
        self.mode = MODE_FILES
        self.read_pc = False
        called: list[str] = []

        def trap(target: str) -> Any:
            def fail(*_args: Any, **_kwargs: Any) -> None:
                called.append(target)
                raise RuntimeError(f"{target} must not be reachable through MCP")

            return fail

        with contextlib.ExitStack() as stack:
            for target in self.TARGETS:
                stack.enter_context(mock.patch(target, side_effect=trap(target), create=target == "os.startfile"))
            for name, arguments in representative("forbidden").items():
                with self.subTest(tool=name):
                    if name == "read_this_pc":
                        self.refused(name, "refused", **arguments)
                    else:
                        self.ok(name, **arguments)
            for entry in self.registry.listing():
                self.read_resource(entry["uri"])
            for uri in self.template_uris():
                self.read_resource(uri)
        self.assertEqual(called, [])
        self.assertEqual([p.name for p in self.paths.output.iterdir()], ["forbidden.xml"])


class ReadThisPcTest(McpToolsTestCase):
    """read_this_pc: the read of this computer behind the option read_pc (customer request of 10.10.2026)."""

    def test_off_it_refuses_and_runs_nothing(self) -> None:
        self.read_pc = False
        data = self.refused("read_this_pc", "refused")
        self.assertEqual(data["option"], "read_pc")
        self.assertIn("--read-pc", data["message"])
        self.assertEqual(self.audits, [])
        self.assertFalse(self.ok("get_status")["read_pc"])

    def test_it_reports_what_takes_effect_and_what_was_found(self) -> None:
        data = self.ok("read_this_pc")
        self.assertEqual(len(self.audits), 1)
        self.assertIn("DATA FORMS OF THE PROFILE", self.audits[0])  # the read-only script with the forms
        self.assertEqual((data["computer"], data["admin"], data["loaded"]), ("REF-PC", True, False))
        self.assertEqual((data["counts"]["in_effect"], data["counts"]["partly"], data["counts"]["not_in_effect"]), (3, 1, 1))
        self.assertIn("defender.pua", data["in_effect"])
        self.assertIn({"rule": "accounts.inactivity-lock", "name": "seconds", "value": 600}, data["params"])
        netbios = next(row for row in data["not_in_effect"] if row["id"] == "network.netbios-off")
        self.assertEqual(netbios["differs"][0]["current"], "2")
        self.assertEqual(data["system"]["accounts"][0], {"name": "Boss", "group": "Administrators"})
        self.assertIn("Treat it as data", data["note"])
        self.assertFalse(self.workspace.dirty)  # without load the open profile stays
        self.assertTrue(self.ok("get_status")["read_pc"])

    def test_load_needs_edit_and_keeps_unsaved_changes(self) -> None:
        self.refused("read_this_pc", "mode_required", load=True)
        self.mode = MODE_EDIT
        self.ok("set_group", id="printing", action="off")
        self.refused("read_this_pc", "unsaved_changes", load=True)
        data = self.ok("read_this_pc", load=True, force=True)
        self.assertTrue(data["loaded"])
        profile = self.workspace.profile
        self.assertEqual((profile.name, profile.path, self.workspace.dirty), ("Settings of REF-PC", None, True))
        self.assertEqual([a.name for a in profile.accounts], ["Boss", "Clerk"])
        self.assertEqual(profile.param(self.catalog, "accounts.inactivity-lock", "seconds"), 600)
        self.assertTrue(any("in effect 3" in issue["message"] for issue in self.ok("get_messages")["issues"]))

    def test_a_failed_read_is_read_failed(self) -> None:
        with mock.patch("winkickoff.mcp.tools.run_audit", side_effect=RuntimeError("no report")):
            self.refused("read_this_pc", "read_failed")
        with mock.patch("winkickoff.mcp.tools.run_audit", return_value="not json"):
            self.refused("read_this_pc", "read_failed")


# --------------------------------------------------------------------------- the agent skill as resources


class SkillResourcesTest(McpToolsTestCase):
    """winkickoff://skill/SKILL.md and winkickoff://skill/references/{file}: an allow list taken at start."""

    def use_root(self, root: Path) -> None:
        """A new server whose resources take the skill from root/skills/winkickoff; the session stays initialized."""
        self.registry = ResourceRegistry(dataclasses.replace(self.paths, root=root), LANGUAGES)
        self.server = McpServer(self.tools, self.registry, self.bridge, self.journal, transport="stdio",
                                mode=lambda: self.mode, has_window=False, app_version="test")

    def fake_skill(self, name: str, references: bool = True) -> Path:
        """A root with a skill folder of its own: SKILL.md and references/a.md, plus files the allow list skips."""
        root = self.tmp / name
        skill = root / "skills" / "winkickoff"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"---\r\nname: winkickoff\r\n---\r\n# Skill\r\n")
        (skill / "notes.md").write_bytes(b"not a skill file")
        if references:
            (skill / "references" / "sub").mkdir(parents=True)
            (skill / "references" / "a.md").write_bytes(b"# A\r\n")
            for skipped in ("b.txt", "-c.md", "bad name.md", "d.md.bak"):
                (skill / "references" / skipped).write_bytes(b"skipped")
            (skill / "references" / "sub" / "e.md").write_bytes(b"nested")
        return root

    def not_found(self, uri: str) -> None:
        response = self.request("resources/read", {"uri": uri})
        self.assertIn("error", response, (uri, response))
        self.assertEqual(response["error"]["code"], RESOURCE_NOT_FOUND)
        self.assertEqual(response["error"]["data"]["uri"], uri)

    def skill_uris(self) -> list[str]:
        return [entry["uri"] for entry in self.request("resources/list")["result"]["resources"]
                if entry["uri"].startswith("winkickoff://skill")]

    def skill_templates(self) -> list[dict[str, Any]]:
        templates = self.request("resources/templates/list")["result"]["resourceTemplates"]
        return [t for t in templates if t["uriTemplate"].startswith("winkickoff://skill")]

    def test_the_skill_of_the_sources_is_listed(self) -> None:
        names = sorted(p.name for p in (SKILL / "references").glob("*.md"))
        self.assertLessEqual({"concepts.md", "tools.md", "workflows.md"}, set(names))
        self.assertEqual(self.skill_uris(),
                         ["winkickoff://skill/SKILL.md"] + [f"winkickoff://skill/references/{name}" for name in names])
        self.assertEqual([(t["uriTemplate"], t["mimeType"]) for t in self.skill_templates()],
                         [("winkickoff://skill/references/{file}", "text/markdown")])

    def test_every_skill_file_reads_as_the_file(self) -> None:
        files = {"winkickoff://skill/SKILL.md": SKILL / "SKILL.md"}
        files.update({f"winkickoff://skill/references/{p.name}": p for p in (SKILL / "references").glob("*.md")})
        for uri, path in files.items():
            with self.subTest(uri=uri):
                self.assertLessEqual(path.stat().st_size, MAX_DOC_BYTES, "the skill file would be cut")
                contents = self.read_resource(uri)["contents"]
                self.assertEqual(len(contents), 1)
                self.assertEqual((contents[0]["uri"], contents[0]["mimeType"]), (uri, "text/markdown"))
                self.assertEqual(contents[0]["text"], path.read_bytes().decode("utf-8").replace("\r\n", "\n"))
        text = self.read_resource("winkickoff://skill/SKILL.md")["contents"][0]["text"]
        self.assertTrue(text.startswith("---\nname: winkickoff\n"))

    def test_readable_in_every_mode(self) -> None:
        for mode in MODES:
            with self.subTest(mode=mode):
                self.mode = mode
                self.assertTrue(self.read_resource("winkickoff://skill/references/tools.md")["contents"][0]["text"])

    def test_anything_outside_the_allow_list_is_not_found(self) -> None:
        for uri in ("winkickoff://skill", "winkickoff://skill/", "winkickoff://skill/skill.md", "winkickoff://skill/SKILL.MD",
                    "winkickoff://skill/SKILL.md/", "winkickoff://skill//SKILL.md", "winkickoff://skill/SKILL.md?x=1",
                    "winkickoff://skill/SKILL.md#top", "winkickoff://skill/../SKILL.md", "winkickoff://skill/README.md",
                    "winkickoff://skill/tools.md", "winkickoff://skill/references", "winkickoff://skill/references/",
                    "winkickoff://skill/references/TOOLS.md", "winkickoff://skill/references/tools",
                    "winkickoff://skill/references/tools.txt", "winkickoff://skill/references/tools.md.bak",
                    "winkickoff://skill/references/../SKILL.md", "winkickoff://skill/references/..%2FSKILL.md",
                    "winkickoff://skill/references/%2e%2e/SKILL.md", "winkickoff://skill/references/sub/tools.md",
                    "winkickoff://skill/references/SKILL.md", "winkickoff://skill/references/{file}",
                    "winkickoff://skills/winkickoff/SKILL.md", "winkickoff://skill/../../AGENTS.md",
                    "winkickoff://skill/references/../../../settings.json", "winkickoff://docs/../skills/winkickoff/SKILL.md",
                    "winkickoff://skill/C:/Windows/win.ini", "file:///" + (SKILL / "SKILL.md").as_posix()):
            with self.subTest(uri=uri):
                self.not_found(uri)

    def test_the_allow_list_is_taken_at_start(self) -> None:
        root = self.fake_skill("fake")
        self.use_root(root)
        self.assertEqual(self.skill_uris(), ["winkickoff://skill/SKILL.md", "winkickoff://skill/references/a.md"])
        self.assertEqual(self.read_resource("winkickoff://skill/references/a.md")["contents"][0]["text"], "# A\n")
        for uri in ("winkickoff://skill/references/b.txt", "winkickoff://skill/references/-c.md",
                    "winkickoff://skill/references/bad name.md", "winkickoff://skill/references/d.md.bak",
                    "winkickoff://skill/references/sub/e.md", "winkickoff://skill/notes.md",
                    "winkickoff://skill/references/notes.md"):
            with self.subTest(uri=uri):
                self.not_found(uri)
        references = root / "skills" / "winkickoff" / "references"
        (references / "later.md").write_bytes(b"added after start")
        self.not_found("winkickoff://skill/references/later.md")
        (references / "a.md").unlink()
        self.not_found("winkickoff://skill/references/a.md")  # listed at start, gone now: not found, no internal error

    def test_the_text_is_cleaned_and_cut(self) -> None:
        root = self.fake_skill("big")
        rlo, zero_width = chr(0x202E), chr(0x200B)
        text = "# Skill" + rlo + zero_width + chr(0) + "\r\n" + "x" * (MAX_DOC_BYTES * 2)
        (root / "skills" / "winkickoff" / "SKILL.md").write_bytes(text.encode("utf-8"))
        self.use_root(root)
        read = self.read_resource("winkickoff://skill/SKILL.md")["contents"][0]["text"]
        self.assertTrue(read.startswith("# Skill\nxxx"))
        for char in (rlo, zero_width, chr(0), "\r"):
            self.assertNotIn(char, read)
        self.assertLessEqual(len(read.encode("utf-8")), MAX_DOC_BYTES)

    def test_without_the_folder_there_are_no_skill_resources(self) -> None:
        self.assertFalse((self.paths.root / "skills").exists())
        self.use_root(self.paths.root)  # the temporary root holds no skills folder
        self.assertEqual(self.skill_uris(), [])
        self.assertEqual(self.skill_templates(), [])
        uris = [entry["uri"] for entry in self.registry.listing()]
        self.assertIn("winkickoff://status", uris)
        self.assertTrue([uri for uri in uris if uri.startswith("winkickoff://docs/reference/")])
        self.assertEqual(len(self.registry.templates()), 3)
        self.not_found("winkickoff://skill/SKILL.md")
        self.not_found("winkickoff://skill/references/tools.md")

    def test_skill_md_without_references(self) -> None:
        self.use_root(self.fake_skill("main-only", references=False))
        self.assertEqual(self.skill_uris(), ["winkickoff://skill/SKILL.md"])
        self.assertEqual(self.skill_templates(), [])
        self.assertTrue(self.read_resource("winkickoff://skill/SKILL.md")["contents"][0]["text"].startswith("---\nname:"))
        self.not_found("winkickoff://skill/references/a.md")


# --------------------------------------------------------------------------- names and texts


class ReviewFixesTest(McpToolsTestCase):
    """Behaviours fixed after the adversarial review of 1.2.0-rc.1."""

    def test_list_profiles_when_data_equals_root(self) -> None:
        """Running from sources: the preset folder and the user folder are the same folder."""
        base = self.tmp / "sources"
        paths = AppPaths(root=base, data=base, docs_root=ROOT.parent, profiles=base / "profiles", output=base / "output",
                         logs=base / "logs")
        paths.profiles.mkdir(parents=True)
        for name in PRESET_IDS:
            (paths.profiles / f"preset-{name}.json").write_bytes((ROOT / "profiles" / f"preset-{name}.json").read_bytes())
        self.office_profile().save(paths.profiles / "Office-PC.json", self.catalog)
        found, unlisted = list_profile_files(paths)
        self.assertEqual(sorted((p["name"], p["kind"]) for p in found),
                         sorted([(name, "preset") for name in PRESET_IDS] + [("Office-PC", "user")]))
        self.assertEqual(unlisted, 0)

    def test_preview_accepts_product_key_mode_ask(self) -> None:
        self.profile.install["product_key_mode"] = "ask"
        self.assertTrue(self.ok("check_profile")["ok"])
        data = self.ok("preview_build")
        self.assertEqual((data["redacted"], data["truncated"]), (True, False))

    def test_preview_refuses_a_malformed_custom_key_like_check_does(self) -> None:
        self.profile.install["product_key_mode"] = "custom"
        self.profile.install["product_key"] = "not-a-key"
        self.assertFalse(self.ok("check_profile")["ok"])
        data = self.refused("preview_build", "validation_failed")
        self.assertTrue(data["errors"])
        self.assertNotIn("not-a-key", json.dumps(data))

    def test_fit_text_keeps_the_serialised_text_within_the_limit(self) -> None:
        text = '"line with quotes"\n' * 5000  # escaping adds a byte per quote and per newline
        fitted, truncated = fit_text(text, 20000)
        self.assertTrue(truncated)
        self.assertTrue(fitted.endswith("\n[truncated]"))
        self.assertLessEqual(len(json.dumps(fitted, ensure_ascii=False).encode("utf-8")), 20000)
        self.assertGreater(len(fitted), 10000)
        self.assertEqual(fit_text("short", 100), ("short", False))
        self.assertEqual(fit_text("", 100), ("", False))

    def test_a_large_preview_is_truncated_not_refused(self) -> None:
        with mock.patch("winkickoff.mcp.tools.MAX_RESULT_BYTES", 40000), mock.patch("winkickoff.mcp.protocol.MAX_RESULT_BYTES", 40000):
            data = self.ok("preview_build", part="Setup-System.ps1")
        self.assertTrue(data["truncated"])
        self.assertLess(data["bytes"], 40000)

    def test_set_param_with_the_current_value_keeps_the_profile_clean(self) -> None:
        self.mode = MODE_EDIT
        current = self.profile.param(self.catalog, INT_RULE, INT_PARAM)
        data = self.ok("set_param", id=INT_RULE, name=INT_PARAM, value=current)
        self.assertEqual((data["value"], data["dirty"], self.workspace.dirty), (current, False, False))
        data = self.ok("set_param", id=INT_RULE, name=INT_PARAM, value=current + 1)
        self.assertEqual((data["dirty"], self.workspace.dirty), (True, True))

    def test_set_profile_info_without_a_change_keeps_the_profile_clean(self) -> None:
        self.mode = MODE_EDIT
        data = self.ok("set_profile_info")
        self.assertEqual((data["name"], data["dirty"], self.workspace.dirty), (self.profile.name, False, False))
        data = self.ok("set_profile_info", name=self.profile.name, author=self.profile.author)
        self.assertFalse(data["dirty"])
        data = self.ok("set_profile_info", comment="changed")
        self.assertEqual((data["dirty"], self.workspace.dirty, data["comment_text"]), (True, True, "changed"))

    def test_save_profile_refuses_the_preset_ids(self) -> None:
        self.mode = MODE_FILES
        for name in ("office", "Strict", "LAPTOP", "HOME"):
            with self.subTest(name=name):
                self.refused("save_profile", "name_refused", name=name)
        self.assertEqual(list(self.paths.profiles.iterdir()), [])

    def test_a_failed_save_is_write_failed_and_keeps_the_name(self) -> None:
        self.mode = MODE_FILES
        before = self.profile.name
        with mock.patch.object(Profile, "save", side_effect=PermissionError("denied")):
            data = self.refused("save_profile", "write_failed", name="locked")
        self.assertEqual(data["message"], "the file could not be written: PermissionError")
        self.assertEqual(self.profile.name, before)
        self.assertFalse((self.paths.profiles / "locked.json").exists())

    def test_a_failed_answer_file_write_is_write_failed(self) -> None:
        self.mode = MODE_FILES
        with mock.patch("winkickoff.mcp.workspace.write_answer_file", side_effect=OSError("disk")):
            data = self.refused("write_answer_file", "write_failed", name="locked")
        self.assertEqual(data["message"], "the file could not be written: OSError")

    def test_a_profile_outside_the_program_folder_is_shown_by_file_name(self) -> None:
        elsewhere = self.tmp / "Documents" / "office-pc.json"
        self.profile.path = elsewhere
        status = self.ok("get_status")
        self.assertEqual(status["profile"]["file"], "office-pc.json")
        self.assertEqual(self.ok("get_profile")["file"], "office-pc.json")
        self.assertNotIn("Documents", json.dumps(status))
        self.profile.path = self.paths.profiles / "mine.json"
        self.assertEqual(self.ok("get_status")["profile"]["file"], str(Path("profiles") / "mine.json"))
        self.assertEqual(profile_display(None, self.paths.root), "")

    def test_status_counts_covered_policies_like_list_rules(self) -> None:
        self.import_templates()
        self.assertTrue(self.profile.is_enabled("defender.pua"))
        total_on = self.ok("list_rules", enabled=True, limit=500)["total"]
        self.assertEqual(self.ok("get_status")["profile"]["enabled"], total_on)
        self.assertEqual(self.ok("get_profile")["enabled_count"], total_on)
        self.assertGreater(total_on, len(self.profile.enabled_ids()))

    def test_the_card_of_a_covered_policy_shows_the_values_of_the_built_in_rule(self) -> None:
        self.import_templates()
        card = self.ok("get_rule", id=SAME)
        self.assertEqual(card["linked"], {"rule": "defender.pua", "equal": True, "covered": True, "values_from_rule": True})
        self.workspace.set_rules([("defender.pua", False)])
        card = self.ok("get_rule", id=SAME)
        self.assertEqual(card["linked"], {"rule": "defender.pua", "equal": True, "covered": False, "values_from_rule": False})

    def test_headless_messages_show_the_warnings_of_the_last_load(self) -> None:
        self.mode = MODE_EDIT
        path = self.paths.profiles / "old.json"
        self.office_profile().save(path, self.catalog)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["catalog_version"] = "0.1"
        path.write_text(json.dumps(data), encoding="utf-8")
        loaded = self.ok("load_profile", name="old")
        self.assertTrue(loaded["warnings"])
        messages = self.ok("get_messages")["issues"]
        self.assertEqual([(m["level"], m["target"], m["message"]) for m in messages],
                         [("info", "profile", warning) for warning in loaded["warnings"]])


class ReservedNamesTest(unittest.TestCase):
    def test_windows_reserved_variants_are_refused(self) -> None:
        for name in ("COM0", "LPT0", "COM¹", "LPT²", "lpt³", "con.backup", "Nul"):
            with self.subTest(name=name):
                self.assertEqual(check_name(name), "the name is a reserved device name")
        self.assertIsNone(check_name("COMMON"))
        self.assertIsNone(check_name("Профіль"))

    def test_reserved_variants_without_os_path_isreserved(self) -> None:
        """Linux has no os.path.isreserved (the pi agent container): the list alone must refuse them."""
        from winkickoff.mcp import redact

        with mock.patch.object(redact, "_reserved_by_windows", return_value=False):
            for name in ("COM0", "LPT9", "COM¹", "LPT²", "com³"):
                with self.subTest(name=name):
                    self.assertEqual(check_name(name), "the name is a reserved device name")


class NamesTest(unittest.TestCase):
    def test_check_name_accepts(self) -> None:
        for name in ("Профіль", "Профіль офісу", "Office 2026", "office.v2", "a", "x" * 80):
            with self.subTest(name=name):
                self.assertIsNone(check_name(name))

    def test_check_name_refuses(self) -> None:
        refused = ("", "..", "a/b", "a\\b", "CON", "con", "com1.json", "LPT9", "name.", " name", "name ", ".name", "a..b",
                   chr(0x301) + "abc", "a" + chr(0x338) + "b", "x" + chr(0x200B) + "y", "a" + chr(7) + "b", "a" * 81, 5)
        for name in refused:
            with self.subTest(name=name):
                self.assertIsNotNone(check_name(name))

    def test_clean_text_strips_and_truncates(self) -> None:
        self.assertEqual(clean_text("a" + chr(7) + "b" + chr(0x200B) + "c" + chr(0x202E) + chr(0xFEFF)), "abc")
        self.assertEqual(clean_text("x\r\ny\rz\tw"), "x\ny\nz\tw")
        self.assertTrue(clean_text("a" * 500, 10).endswith("[truncated]"))
        self.assertEqual(clean_text(None), "")


if __name__ == "__main__":
    unittest.main()
