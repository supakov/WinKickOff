"""core/package.py and admx.check_templates: catalog files of imported templates, export, import, bundled catalogs.

A catalog file is untrusted input: every record is checked against what the template parser writes, the file is read
with size limits, and the rules of a more trusted source win when two imports hold the same policy. Everything is
written into temporary folders.
"""

from __future__ import annotations

import quiet_tk  # noqa: F401 - first: every window these tests open stays invisible
import copy
import gzip
import json
import lzma
import time
import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from winkickoff.core import admx, jsonfile
from winkickoff.core import package as package_module
from winkickoff.core.render import Renderer
from winkickoff.core.resources import Resources
from winkickoff.core.profile import Profile

import test_admx
from test_admx import ROOT, TOGGLE, AdmxTestCase

NOW = datetime(2026, 10, 4, 12, 0, 0)

ODD_ADMX = r"""<?xml version="1.0" encoding="utf-8"?>
<policyDefinitions xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <policyNamespaces><target prefix="odd" namespace="WinKickOff.Odd"/></policyNamespaces>
  <resources minRequiredRevision="1.0"/>
  <policies>
    <policy name="Good" class="Machine" displayName="$(string.Good)" explainText="$(string.Good)" key="Software\Policies\Odd" valueName="Good"/>
    <policy name="Lower" class="machine" displayName="$(string.Good)" key="Software\Policies\Odd" valueName="Lower"/>
    <policy name="" class="Machine" displayName="$(string.Good)" key="Software\Policies\Odd" valueName="NoName"/>
    <policy name="SameBool" class="Machine" displayName="$(string.Good)" key="Software\Policies\Odd">
      <elements><boolean id="B" valueName="B"><trueValue><decimal value="1"/></trueValue><falseValue><decimal value="1"/></falseValue></boolean></elements>
    </policy>
    <policy name="BackslashKey" class="Machine" displayName="$(string.Good)" key="Software\Policies\Odd" valueName="X">
      <enabledList><item key="\" valueName="Y"><value><decimal value="1"/></value></item></enabledList>
    </policy>
    <policy name="Cdata" class="Machine" displayName="$(string.Good)" key="Software\Policies\Odd" valueName="a]]&gt;b"/>
    <policy name="Braces" class="Machine" displayName="$(string.Good)" key="Software\Policies\Odd" valueName="Url">
      <enabledValue><string>https://example.com/{id}</string></enabledValue>
    </policy>
  </policies>
</policyDefinitions>
"""

ODD_ADML = """<?xml version="1.0" encoding="utf-8"?>
<policyDefinitionResources xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <displayName>odd</displayName><description>odd</description>
  <resources><stringTable><string id="Good">Good&#x7F;text</string></stringTable></resources>
</policyDefinitionResources>
"""


def write_odd_templates(folder: Path) -> Path:
    """Templates the parser reads although some policies are odd: they are skipped, the rest is imported."""
    for culture in ("en-US", "en-US - Copy"):
        (folder / culture).mkdir(parents=True)
        (folder / culture / "odd.adml").write_text(ODD_ADML, encoding="utf-8")
    (folder / "odd.admx").write_text(ODD_ADMX, encoding="utf-8")
    return folder



class PackageTestCase(AdmxTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.data = admx.read_templates(self.templates, ["en", "ru", "uk"])
        self.info = admx.save_import(self.store, self.templates, self.data, system=False, now=NOW)
        self.file = self.tmp / "exported.json"

    def exported(self) -> dict:
        package_module.export_package(self.store, self.info.id, self.file)
        return jsonfile.read(self.file, nulls=True)

    def write(self, value: object, name: str = "edited.json") -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path


class ExportImportTest(PackageTestCase):
    def test_export_writes_the_records_in_an_envelope(self) -> None:
        value = self.exported()
        self.assertEqual([value[k] for k in ("format", "version", "kind", "name")],
                         ["winkickoff-catalog", 1, "admx", self.info.name])
        self.assertEqual(value["templates"], self.data)
        self.assertNotIn(str(self.templates), self.file.read_text(encoding="utf-8"))  # no path of this computer
        self.assertEqual(self.file.read_bytes().count(b"\n"), self.file.read_bytes().count(b"\r\n"))

    def test_an_imported_file_gives_the_same_rules(self) -> None:
        self.exported()
        package = package_module.read_package(self.file)
        info = package_module.import_package(self.store, self.file, package, now=NOW)
        self.assertTrue(info.id.startswith("package-"))
        self.assertEqual((info.name, info.folder, info.policies), (self.info.name, str(self.file), self.info.policies))
        _, data = admx.load_import(self.store, info.id)
        self.assertEqual(data, self.data)
        first, _ = admx.with_imports(self.base, self.store, [self.info.id], "en")
        second, _ = admx.with_imports(self.base, self.store, [info.id], "en")
        self.assertEqual(first.rules[TOGGLE].actions, second.rules[TOGGLE].actions)
        self.assertEqual(package_module.find_package_imports(self.store, self.file), [info])
        again = package_module.import_package(self.store, self.file, replace=info, now=NOW)
        self.assertEqual(again.id, info.id)

    def test_compressed_files_are_read(self) -> None:
        self.exported()
        text = self.file.read_bytes()
        for suffix, packed in ((".json.gz", gzip.compress(text)), (".json.xz", lzma.compress(text))):
            with self.subTest(suffix=suffix):
                path = self.tmp / ("c" + suffix)
                path.write_bytes(packed)
                self.assertEqual(package_module.read_package(path).templates, self.data)

    def test_a_build_with_a_policy_of_the_file_writes_its_value(self) -> None:
        self.exported()
        info = package_module.import_package(self.store, self.file, now=NOW)
        catalog, _ = admx.with_imports(self.base, self.store, [info.id], "en")
        profile = Profile.from_catalog(catalog)
        profile.rules[TOGGLE].enabled = True
        renderer = Renderer(catalog, ROOT / "templates", Resources.load(ROOT / "resources").keyboards)
        self.assertIn("# [" + TOGGLE + "]", renderer.build(profile, app_version="test").scripts["Setup-System.ps1"])


class RefusedFilesTest(PackageTestCase):
    def assert_refused(self, value: object, fragment: str) -> None:
        with self.assertRaises(admx.AdmxError) as ctx:
            package_module.read_package(self.write(value))
        self.assertIn(fragment, str(ctx.exception))

    def edited(self, change) -> dict:
        value = copy.deepcopy(self.exported())
        change(value)
        return value

    def test_envelope(self) -> None:
        self.assert_refused({"format": "other"}, "not a WinKickOff catalog file")
        self.assert_refused(self.edited(lambda v: v.update(version=2)), "version 2")
        self.assert_refused(self.edited(lambda v: v.update(kind="rules")), "unknown kind")
        self.assert_refused(self.edited(lambda v: v.update(extra=1)), "unknown fields ['extra']")
        self.assert_refused(self.edited(lambda v: v.update(name="")), "bad name")
        self.assert_refused(self.edited(lambda v: v.update(name="a" * 200)), "bad name")
        self.assert_refused(self.edited(lambda v: v.update(windows="Windows; rm")), "bad Windows version")
        self.assert_refused(self.edited(lambda v: v.update(comment="text")), "list of lines")

    def test_strict_json(self) -> None:
        text = json.dumps(self.exported())
        path = self.tmp / "twice.json"
        path.write_text(text.replace('"kind": "admx"', '"kind": "admx", "kind": "admx"'), encoding="utf-8")
        with self.assertRaisesRegex(admx.AdmxError, "appears twice"):
            package_module.read_package(path)

    def test_records_that_the_parser_never_writes(self) -> None:
        policy = lambda v: v["templates"]["policies"][0]  # noqa: E731
        write = lambda v: policy(v)["enabled"][0]  # noqa: E731
        cases = [
            (lambda v: write(v).update(name="a$b"), "value name without unsafe characters"),
            (lambda v: write(v).update(key="Software\\" + chr(0x2019)), "registry key without unsafe characters"),
            (lambda v: write(v).update(kind="Binary"), "one of"),
            (lambda v: write(v).update(value=-1), "an integer from 0"),
            (lambda v: write(v).update(value=None), "an integer from 0"),
            (lambda v: write(v).update(extra=1), "an object with key, name, kind and value"),
            (lambda v: policy(v).update({"class": "Kernel"}), "one of ('Machine', 'User', 'Both')"),
            (lambda v: policy(v).update(file="..\\x.admx"), "the name of an .admx file"),
            (lambda v: policy(v).update(title={"en-US": "a" + chr(7)}), "without control characters"),
            (lambda v: policy(v).update(script="x"), "an object with the fields"),
            (lambda v: v["templates"].update(more=[]), "an object with the fields"),
            (lambda v: v["templates"].update(policies={}), "a list of at most"),
            (lambda v: write(v).update(name="a]]>b"), "value name without unsafe characters"),
            (lambda v: write(v).update(key="Software\\a]]>b"), "registry key without unsafe characters"),
        ]
        for change, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_refused(self.edited(change), fragment)

    def test_elements(self) -> None:
        def elements(v: dict) -> list:
            return next(p for p in v["templates"]["policies"] if p["elements"])["elements"]

        def first(kind: str):
            def pick(v: dict) -> dict:
                for policy in v["templates"]["policies"]:
                    for element in policy["elements"]:
                        if (element.get("element") or element["type"]) == kind:
                            return element
                raise AssertionError(kind)
            return pick

        cases = [
            (lambda v: elements(v)[0].update(param="state"), "a unique parameter name"),
            (lambda v: elements(v)[0].update(param="Bad Name"), "a unique parameter name"),
            (lambda v: elements(v).append(copy.deepcopy(elements(v)[0])), "a unique parameter name"),
            (lambda v: first("enum")(v).update(default=99), "one of the values"),
            (lambda v: first("int")(v).update(default=first("int")(v)["max"] + 1), "an integer from"),
            (lambda v: first("string")(v).update(default="a]]>b"), "a string without unsafe characters"),
            (lambda v: first("list")(v).update(prefix="p$"), "a safe prefix"),
            (lambda v: first("list")(v).update(kind="DWord"), "a list element"),
            (lambda v: first("multiText")(v).update(kind="String"), "a multiText element"),
            (lambda v: first("enum")(v).update(script="x"), "the fields"),
            (lambda v: first("bool")(v).update(kind="String"), "DWord"),
            (lambda v: first("bool")(v).update(default=1), "true or false"),
            (lambda v: first("enum")(v).update(values=[["1", None]], default="1"), "an integer from 0"),
            (lambda v: first("enum")(v).update(values=[[1, None], [1, None]], default=1), "a value given once"),
            (lambda v: first("enum")(v).update(values=[[1, "Block"]], default=1), "texts by culture"),
            (lambda v: first("int")(v).update(min=5, max=4, default=5), "an integer from 5"),
            (lambda v: first("list")(v).update(additive="yes"), "true or false"),
            (lambda v: first("list")(v).update(explicit=True, prefix="p"), "not with explicit names"),
            (lambda v: first("multiText")(v).update(default=["a" + chr(1)]), "a string without unsafe characters"),
            (lambda v: elements(v)[0].update(label={"not a culture": "x"}), "bad culture"),
            (lambda v: elements(v)[0].update(id="a" + chr(1)), "without control characters"),
            (lambda v: elements(v)[0].update(element=["x"]), "unknown element"),
            (lambda v: elements(v)[0].update(type={"x": 1}), "unknown element"),
            (lambda v: v["templates"]["policies"][0].update(enabled=[]), "nothing to write"),
        ]
        for change, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_refused(self.edited(change), fragment)

    def test_chains_of_categories_are_bounded(self) -> None:
        def chain(length: int):  # type: ignore[no-untyped-def]
            def change(v: dict) -> None:
                v["templates"]["categories"] = {f"x:c{i}": {"title": {"en-US": f"c{i}"}, "parent": f"x:c{i - 1}" if i else ""}
                                                for i in range(length)}
                v["templates"]["policies"][0]["category"] = f"x:c{length - 1}"
            return change

        def cycle(v: dict) -> None:
            v["templates"]["categories"] = {"x:a": {"title": {}, "parent": "x:b"}, "x:b": {"title": {}, "parent": "x:a"}}

        self.assert_refused(self.edited(chain(1200)), "a chain of parent categories of at most 32 levels")
        self.assert_refused(self.edited(cycle), "without a cycle")
        package_module.read_package(self.write(self.edited(chain(admx.MAX_CATEGORY_DEPTH))))  # 32 levels are fine

    def test_sections_of_the_records(self) -> None:
        category = lambda v: next(iter(v["templates"]["categories"].values()))  # noqa: E731
        cases = [
            (lambda v: category(v).update(extra=1), "title and parent"),
            (lambda v: category(v).update(parent=5), "a text of at most"),
            (lambda v: v["templates"].update(skipped=[{"file": "a"}]), "file, policy and reason"),
            (lambda v: v["templates"].update(problems=[5]), "a text of at most"),
            (lambda v: v["templates"].update(cultures=["en US"]), "culture names"),
            (lambda v: v["templates"].update(files=-1), "an integer from 0"),
            (lambda v: v["templates"].update(format=99), "an integer from 1"),
        ]
        for change, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_refused(self.edited(change), fragment)

    def test_the_store_leaves_no_folder_when_a_text_cannot_be_written(self) -> None:
        data = copy.deepcopy(self.data)
        data["problems"] = ["a" + chr(0xD800)]  # what jsonfile refuses to read, given directly
        before = sorted(p.name for p in self.store.iterdir())
        with self.assertRaises(UnicodeEncodeError):
            admx.store_import(self.store, "package-20261004-130000", "x", data, "N", "", now=NOW)
        self.assertEqual(sorted(p.name for p in self.store.iterdir()), before)

    def test_text_that_cannot_be_written_and_long_messages(self) -> None:
        def surrogate(v: dict) -> None:
            v["templates"]["policies"][0]["title"] = {"en-US": "a" + chr(0xD800)}  # json.dumps escapes it as \ud800

        self.assert_refused(self.edited(surrogate), "lone surrogate")
        self.assertEqual([p.name for p in self.store.iterdir()], [self.info.id])  # no folder of a failed import
        def long_culture(v: dict) -> None:
            v["templates"]["policies"][0]["title"] = {"en" + "-abcdefgh" * 5000: "x" + chr(1)}

        for change in (lambda v: v.update(name="n" * 100000), lambda v: v.update(windows="9" * 100000),
                       lambda v: v.update(kind="k" * 100000), lambda v: v.update(version="v" * 100000), long_culture):
            with self.assertRaises(admx.AdmxError) as ctx:
                package_module.read_package(self.write(self.edited(change)))
            self.assertLess(len(str(ctx.exception)), 300)

    def test_size_limits(self) -> None:
        self.exported()
        packed = self.tmp / "big.json.xz"
        packed.write_bytes(lzma.compress(self.file.read_bytes()))
        with mock.patch.object(package_module, "MAX_PACKAGE_JSON", 1000), self.assertRaisesRegex(admx.AdmxError, "larger than"):
            package_module.read_package(packed)
        with mock.patch.object(package_module, "MAX_PACKAGE_FILE", 100), self.assertRaisesRegex(admx.AdmxError, "larger than"):
            package_module.read_package(packed)

    def test_a_tampered_policy_of_a_saved_import_is_skipped(self) -> None:
        data = copy.deepcopy(self.data)
        next(p for p in data["policies"] if p["name"] == "SimpleToggle")["enabled"][0]["name"] = "x`y"
        next(p for p in data["policies"] if p["elements"])["elements"][0]["type"] = ["x"]
        (self.store / self.info.id / admx.DATA_FILE).write_text(json.dumps(data), encoding="utf-8")
        catalog, problems = admx.with_imports(self.base, self.store, [self.info.id], "en")
        self.assertEqual(problems, [])
        self.assertNotIn(TOGGLE, catalog.rules)  # the tampered policies are left out ...
        self.assertIn(test_admx.PAIR, catalog.rules)  # ... the others load
        skipped = {(s["policy"], s["reason"]) for s in admx.load_import(self.store, self.info.id)[1]["skipped"]}
        self.assertIn(("SimpleToggle", "unsafe"), skipped)
        self.assertIn("4 skipped", catalog.groups["admx." + self.info.id].summary)  # 2 of the templates and these 2


class TrustAndBundledTest(PackageTestCase):
    def test_the_more_trusted_source_makes_the_shared_rules(self) -> None:
        self.exported()
        edited = jsonfile.read(self.file, nulls=True)
        toggle = next(p for p in edited["templates"]["policies"] if p["name"] == "SimpleToggle")
        toggle["enabled"][0]["value"] = 7  # the same policy with another value
        path = self.write(edited, "other.json")
        other = package_module.import_package(self.store, path, now=NOW)
        self.assertEqual(admx.trust_order([other.id, self.info.id, "bundled-x", "system-1"]),
                         ["bundled-x", "system-1", self.info.id, other.id])
        for order in ([other.id, self.info.id], [self.info.id, other.id]):
            with self.subTest(order=order):
                catalog, _ = admx.with_imports(self.base, self.store, order, "en")
                self.assertEqual(catalog.origins[TOGGLE].import_id, self.info.id)  # the folder, not the file
                self.assertEqual(catalog.rules[TOGGLE].params["state"].default, 1)  # not the 7 of the file
                # the trees keep the order in which they are shown
                self.assertLess(catalog.groups["admx." + order[0]].order, catalog.groups["admx." + order[1]].order)

    def test_bundled_then_system_then_folder(self) -> None:
        def stored(import_id: str, value: int) -> str:
            data = copy.deepcopy(self.data)
            next(p for p in data["policies"] if p["name"] == "SimpleToggle")["enabled"][0]["value"] = value
            return admx.store_import(self.store, import_id, "x", data, import_id, "", now=NOW).id

        system, bundled = stored("system-20261004-120000", 8), stored("bundled-test", 9)
        for shown, owner, value in (([self.info.id, system], system, 8), ([self.info.id, system, bundled], bundled, 9),
                                    ([bundled, self.info.id], bundled, 9)):
            with self.subTest(shown=shown):
                catalog, problems = admx.with_imports(self.base, self.store, shown, "en")
                self.assertEqual(problems, [])
                self.assertEqual(catalog.origins[TOGGLE].import_id, owner)
                self.assertEqual(catalog.rules[TOGGLE].params["state"].default, value)
                orders = [catalog.groups["admx." + i].order for i in shown]
                self.assertEqual(orders, sorted(orders))

    def test_bundled_catalogs(self) -> None:
        self.exported()
        folder = self.tmp / "catalogs"
        folder.mkdir()
        (folder / "Windows Test.json.xz").write_bytes(lzma.compress(self.file.read_bytes()))
        (folder / "README.md").write_text("x", encoding="utf-8")
        found = package_module.bundled_catalogs(folder)
        self.assertEqual([(c.label, c.import_id) for c in found], [("Windows Test", "bundled-windows-test")])
        info = package_module.import_bundled(self.store, found[0], now=NOW)
        self.assertEqual(info.id, "bundled-windows-test")
        renamed = admx.rename_import(self.store, info.id, "My tree")
        again = package_module.import_bundled(self.store, found[0], now=NOW)
        self.assertEqual((again.id, again.name), (info.id, renamed.name))  # updated in place, the name stays
        self.assertEqual(package_module.bundled_catalogs(self.tmp / "missing"), [])

    def test_repository_catalogs_and_the_pack_tool(self) -> None:
        folder = ROOT / "catalogs"
        for path in sorted(folder.glob("*.json")):  # the catalogs of the program are valid packages
            with self.subTest(file=path.name):
                package_module.read_package(path)
        self.assertEqual(sorted(p.name for p in folder.iterdir() if not p.name.endswith(".json")), ["README.md"])
        import importlib.util
        spec = importlib.util.spec_from_file_location("pack_catalogs", ROOT / "tools" / "pack_catalogs.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.exported()
        source = self.tmp / "source"
        source.mkdir()
        (source / "one.json").write_bytes(self.file.read_bytes())
        with mock.patch("builtins.print"):
            written = tool.pack(source, self.tmp / "packed")
        self.assertEqual([p.name for p in written], ["one.json.xz"])
        self.assertEqual(package_module.read_package(written[0]).templates, self.data)
        (source / "one_.json").write_bytes(self.file.read_bytes())  # the same id, another file name
        self.assertEqual(package_module.bundled_collisions(source), {"bundled-one": ["one.json", "one_.json"]})
        with mock.patch("builtins.print"), self.assertRaisesRegex(SystemExit, "bundled-one"):
            tool.pack(source, self.tmp / "packed2")
        (source / "one_.json").unlink()
        (source / "broken.json").write_text('{"format": "x"}', encoding="utf-8")
        with mock.patch("builtins.print"), self.assertRaises(admx.AdmxError):
            tool.pack(source, self.tmp / "packed3")


class DamagedStoreTest(PackageTestCase):
    """The folder admx/ is writable: a damaged or edited import is left out with a message, the start goes on."""

    def damage(self, name: str, text: str) -> None:
        (self.store / self.info.id / name).write_text(text, encoding="utf-8")

    def test_damaged_files_are_reported_never_raised(self) -> None:
        meta = json.loads((self.store / self.info.id / admx.META_FILE).read_text(encoding="utf-8"))
        records = json.dumps(self.data)
        cases = [
            (admx.DATA_FILE, '{"policies": [], "problems": ' + "[" * 100000 + "]" * 100000 + "}", "deeper than"),
            (admx.DATA_FILE, "[" + ",".join(["{}"] * 1_100_000) + "]", "values"),
            (admx.META_FILE, "[]", "must hold an object"),
            (admx.META_FILE, json.dumps(dict(meta, policies={})), "wrong type"),
            (admx.META_FILE, json.dumps(dict(meta, cultures=5)), "wrong type"),
            (admx.META_FILE, json.dumps(dict(meta, format=[2])), "unsupported import"),
            (admx.META_FILE, "[" * 1000 + "]" * 1000, "deeper than"),
            (admx.META_FILE, "[" * 100000 + "]" * 100000, "larger than"),
        ]
        for name, text, fragment in cases:
            with self.subTest(file=name, fragment=fragment):
                self.damage(admx.META_FILE, json.dumps(meta))
                self.damage(admx.DATA_FILE, records)
                self.damage(name, text)
                catalog, problems = admx.with_imports(self.base, self.store, [self.info.id], "en")
                self.assertIs(catalog, self.base)
                self.assertEqual(len(problems), 1)
                self.assertIn(fragment, problems[0])
                if name == admx.META_FILE:
                    self.assertEqual(admx.list_imports(self.store), [])

    def test_an_import_of_an_older_version_with_odd_records_still_loads(self) -> None:
        data = copy.deepcopy(self.data)
        data["cultures"] = ["en-US", "en-US - Copy"]
        policy = next(p for p in data["policies"] if p["name"] == "Pair")
        policy["title"]["en-US - Copy"] = "copy"
        policy["title"]["en-US"] = "Pair" + chr(0x7F)
        next(p for p in data["policies"] if p["name"] == "SimpleToggle")["class"] = "machine"
        data["problems"] = ["ru-RU/wktest.adml: [Errno 13] Permission denied: 'C:\\Users\\Ivan\\t\\ru-RU\\wktest.adml'"]
        (self.store / self.info.id / admx.DATA_FILE).write_text(json.dumps(data), encoding="utf-8")  # as 1.2 kept it
        info, loaded = admx.load_import(self.store, self.info.id)
        self.assertEqual(loaded["cultures"], ["en-US"])
        pair = next(p for p in loaded["policies"] if p["name"] == "Pair")
        self.assertEqual(pair["title"], {"en-US": "Pair ", "ru-RU": data["policies"][2]["title"].get("ru-RU", "")}
                         if "ru-RU" in data["policies"][2]["title"] else {"en-US": "Pair "})
        self.assertIn(("SimpleToggle", "broken"), {(s["policy"], s["reason"]) for s in loaded["skipped"]})
        self.assertEqual(loaded["problems"], ["ru-RU/wktest.adml: [Errno 13] Permission denied: 'wktest.adml'"])
        package_module.export_package(self.store, info.id, self.file)
        self.assertNotIn("Ivan", self.file.read_text(encoding="utf-8"))

    def test_long_folder_names_and_names_of_older_versions(self) -> None:
        folder = test_admx.write_templates(self.tmp / ("T" * 110))
        info = admx.save_import(self.store, folder, self.data, system=False, now=NOW)
        self.assertLessEqual(len(info.name), admx.MAX_NAME)
        self.assertTrue(info.name.endswith(", 2026-10-04 12:00"), info.name)
        meta_path = self.store / self.info.id / admx.META_FILE
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta_path.write_text(json.dumps(dict(meta, name="N" * 128)), encoding="utf-8")  # as an older version kept it
        self.assertEqual(admx.load_import(self.store, self.info.id)[0].name, "N" * 128)
        package_module.export_package(self.store, self.info.id, self.file)
        name = package_module.read_package(self.file).name
        self.assertEqual((len(name), name[-3:]), (admx.MAX_NAME, "..."))


class ParserAndBoundsTest(PackageTestCase):
    def test_the_parser_skips_what_the_check_would_refuse(self) -> None:
        folder = write_odd_templates(self.tmp / "odd")
        data = admx.read_templates(folder, ["en"])
        self.assertEqual(data["cultures"], ["en-US"])  # "en-US - Copy" is not a culture
        self.assertEqual(sorted(p["name"] for p in data["policies"]), ["Braces", "Good"])
        reasons = {s["policy"]: s["reason"] for s in data["skipped"]}
        self.assertEqual(reasons, {"Lower": "broken", "": "broken", "SameBool": "broken", "BackslashKey": "unsafe",
                                   "Cdata": "unsafe"})
        good = next(p for p in data["policies"] if p["name"] == "Good")
        self.assertEqual(good["title"], {"en-US": "Good text"})  # DEL, allowed by XML, became a space
        info = admx.save_import(self.store, folder, data, system=False, now=NOW)  # one odd policy never stops the import
        catalog, problems = admx.with_imports(self.base, self.store, [info.id], "en")
        self.assertEqual(problems, [])
        braces = "admx.winkickoff.odd.braces"
        profile = Profile.from_catalog(catalog)
        profile.rules[braces].enabled = True
        renderer = Renderer(catalog, ROOT / "templates", Resources.load(ROOT / "resources").keyboards)
        script = renderer.build(profile, app_version="test").scripts["Setup-System.ps1"]
        self.assertIn("-Value 'https://example.com/{id}'", script)  # a fixed text stays text, never a placeholder

    def test_a_fixed_text_with_braces_in_a_catalog_file_stays_text(self) -> None:
        value = self.exported()
        policy = next(p for p in value["templates"]["policies"] if p["name"] == "With_Elements")
        policy["enabled"] = [{"key": "Software\\Policies\\WKTest\\User", "name": "Fixed", "kind": "String",
                              "value": "x{seconds}y"}]
        info = package_module.import_package(self.store, self.write(value), now=NOW)
        catalog, _ = admx.with_imports(self.base, self.store, [info.id], "en")
        profile = Profile.from_catalog(catalog)
        profile.rules[test_admx.ELEMENTS].enabled = True
        renderer = Renderer(catalog, ROOT / "templates", Resources.load(ROOT / "resources").keyboards)
        script = renderer.build(profile, app_version="test").scripts["Setup-System.ps1"]
        self.assertIn("-Name 'Fixed' -Type String -Value 'x{seconds}y'", script)

    def test_reading_is_bounded_in_time(self) -> None:
        value = self.exported()
        template = next(p for p in value["templates"]["policies"] if p["name"] == "SimpleToggle")
        value["templates"]["policies"] = [copy.deepcopy(template) for _ in range(5000)]  # 5000 policies with one id
        value["templates"]["categories"] = {f"x:c{i}": {"title": {"en-US": f"c{i}"}, "parent": f"x:c{i - 1}" if i else ""}
                                            for i in range(admx.MAX_CATEGORY_DEPTH)}
        for policy in value["templates"]["policies"]:
            policy["category"] = f"x:c{admx.MAX_CATEGORY_DEPTH - 1}"
        info = package_module.import_package(self.store, self.write(value), now=NOW)
        started = time.monotonic()
        catalog, problems = admx.with_imports(self.base, self.store, [info.id], "en")
        self.assertLess(time.monotonic() - started, 15.0)  # quadratic numbering took minutes here
        self.assertEqual(problems, [])
        ids = sorted(r for r in catalog.rules if r.startswith("admx.winkickoff.test.simpletoggle"))
        self.assertEqual(len(ids), 5000)

    def test_ids_do_not_depend_on_the_language_or_on_disabled_states(self) -> None:
        value = self.exported()
        policies = value["templates"]["policies"]
        first = next(p for p in policies if p["name"] == "SimpleToggle")
        second = copy.deepcopy(first)
        second["name"] = "SIMPLETOGGLE"  # the same id after lowercasing
        first["title"], second["title"] = {"en-US": "A", "ru-RU": "Z"}, {"en-US": "B", "ru-RU": "Y"}
        for write in second["enabled"] + second["disabled"]:
            write["key"] = "Software\\Policies\\WKTest\\Second"
        main = next(p for p in policies if p["name"] == "Pair")  # it has a Disabled rule <id>.off
        named_off = copy.deepcopy(next(p for p in policies if p["name"] == "SameAsBuiltin"))
        named_off["namespace"], named_off["name"] = main["namespace"] + ".Pair", "off"
        policies += [second, named_off]
        info = package_module.import_package(self.store, self.write(value), now=NOW)
        keys = {}
        for language in ("en", "ru"):
            catalog, _ = admx.with_imports(self.base, self.store, [info.id], language)
            keys[language] = {r: str(catalog.rules[r].actions[0].fields["path"]) for r in catalog.rules
                              if r.startswith("admx.winkickoff.test.simpletoggle")}
            self.assertIn(test_admx.PAIR + ".off", catalog.rules)
            self.assertEqual(catalog.rules[test_admx.PAIR + ".off"].title.split(" (")[0],
                             catalog.rules[test_admx.PAIR].title.split(" (")[0])  # still the Disabled state of Pair
            self.assertIn(test_admx.PAIR + ".off-2", catalog.rules)  # the policy named "off" is numbered
        self.assertEqual(keys["en"], keys["ru"])
        self.assertEqual(len(keys["en"]), 2)

    def test_a_choice_never_moves_to_a_less_trusted_source(self) -> None:
        def stored(import_id: str, value: int) -> str:
            data = copy.deepcopy(self.data)
            next(p for p in data["policies"] if p["name"] == "SimpleToggle")["enabled"][0]["value"] = value
            return admx.store_import(self.store, import_id, "x", data, import_id, "", now=NOW).id

        system, package = stored("system-20261004-120000", 1), stored("package-20261004-120000", 9)
        both, _ = admx.with_imports(self.base, self.store, [system, package], "en")
        profile = Profile.from_catalog(both)
        profile.rules[TOGGLE].enabled = True
        saved = profile.to_dict(both)
        self.assertEqual(saved["rules"][TOGGLE]["source"], "system")
        only_package, _ = admx.with_imports(self.base, self.store, [package], "en")
        moved, warnings = Profile.from_dict(saved, only_package)
        self.assertFalse(moved.is_enabled(TOGGLE))  # not given to the catalog file without a word
        self.assertIn(TOGGLE, moved.unknown)
        self.assertTrue(any("more trusted source" in w for w in warnings))
        back, _ = Profile.from_dict(moved.to_dict(only_package), both)
        self.assertTrue(back.is_enabled(TOGGLE))  # the choice comes back with the templates of this Windows


class RoundFourTest(PackageTestCase):
    """Defects found by the review of round 3 (05.10.2026)."""

    def stored(self, import_id: str, value: int, change=None) -> str:  # type: ignore[no-untyped-def]
        data = copy.deepcopy(self.data)
        next(p for p in data["policies"] if p["name"] == "SimpleToggle")["enabled"][0]["value"] = value
        if change:
            change(data)
        return admx.store_import(self.store, import_id, "x", data, import_id, "", now=NOW).id

    def test_paths_are_cut_in_linear_time_with_both_quotes(self) -> None:
        started = time.monotonic()
        for _ in range(200):
            admx.without_paths("'C:" + "a" * 4093)  # a quote that never closes
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(admx.without_paths('x: "C:\\Users\\O\'Brien\\t\\a.admx" and \'\\\\server\\share\\b.adml\''),
                         'x: "a.admx" and \'b.adml\'')

    def test_a_deep_profile_is_refused_as_value_error(self) -> None:
        deep: object = "x"
        for _ in range(600):
            deep = [deep]
        good = Profile.from_catalog(self.base).to_dict(self.base)
        with self.assertRaises(ValueError):
            Profile.from_dict(dict(good, unknown={"x.y": {"params": {"p": deep}}}), self.base)
        path = self.tmp / "deep.json"
        path.write_text(json.dumps(dict(good, unknown={"x.y": {"params": {"p": deep}}})), encoding="utf-8")
        with self.assertRaises(ValueError):
            Profile.load(path, self.base)
        from winkickoff.core.importer import ImportFailed, import_xml

        xml = Renderer(self.base, ROOT / "templates", Resources.load(ROOT / "resources").keyboards).build(
            Profile.from_catalog(self.base), app_version="test").xml
        start = xml.index("<Profile") + xml[xml.index("<Profile"):].index(">") + 1
        end = xml.index("</Profile>")
        broken = xml[:start] + "<![CDATA[" + "[" * 20000 + "]" * 20000 + "]]>" + xml[end:]
        with self.assertRaises(ImportFailed):
            import_xml(broken, self.base)

    def test_the_kind_kept_is_the_most_trusted_one_the_choice_was_in_effect_in(self) -> None:
        package = self.stored("package-20261004-120000", 9)
        only_package, _ = admx.with_imports(self.base, self.store, [package], "en")
        profile = Profile.from_catalog(only_package)
        profile.rules[TOGGLE].enabled = True  # chosen in the catalog file
        system = self.stored("system-20261004-120000", 1)
        both, _ = admx.with_imports(self.base, self.store, [system, package], "en")
        profile, _ = Profile.from_dict(profile.to_dict(only_package), both)  # now the system import holds it
        self.assertTrue(profile.is_enabled(TOGGLE))
        saved = profile.to_dict(both)
        self.assertEqual(saved["rules"][TOGGLE]["source"], "system")
        back, warnings = Profile.from_dict(saved, only_package)
        self.assertFalse(back.is_enabled(TOGGLE))  # it was in effect with the values of this Windows
        self.assertTrue(any("more trusted source" in w for w in warnings))

    def test_a_choice_saved_before_1_3_never_goes_to_a_catalog_file(self) -> None:
        package, folder = self.stored("package-20261004-120000", 9), self.info.id
        only_package, _ = admx.with_imports(self.base, self.store, [package], "en")
        only_folder, _ = admx.with_imports(self.base, self.store, [folder], "en")
        old = Profile.from_catalog(self.base).to_dict(self.base)
        old["rules"][TOGGLE] = {"enabled": True}  # no "source": saved by 1.2
        profile, warnings = Profile.from_dict(old, only_package)
        self.assertFalse(profile.is_enabled(TOGGLE))
        self.assertTrue(any("more trusted source" in w for w in warnings))
        self.assertTrue(Profile.from_dict(old, only_folder)[0].is_enabled(TOGGLE))  # a folder of templates, as in 1.2

    def test_a_disabled_rule_never_replaces_a_rule_of_another_import(self) -> None:
        def net_off(data: dict) -> None:
            policy = next(p for p in data["policies"] if p["name"] == "SameAsBuiltin")
            policy["namespace"], policy["name"] = "Contoso.Policies.Net", "Off"

        def net(data: dict) -> None:
            policy = next(p for p in data["policies"] if p["name"] == "Pair")  # has a Disabled rule
            policy["namespace"], policy["name"] = "Contoso.Policies", "Net"

        system, package = self.stored("system-20261004-120000", 1, net_off), self.stored("package-20261004-120000", 1, net)
        catalog, problems = admx.with_imports(self.base, self.store, [system, package], "en")
        self.assertEqual(problems, [])
        self.assertEqual(catalog.origins["admx.contoso.policies.net.off"].import_id, system)
        self.assertNotIn("admx.contoso.policies.net", catalog.rules)  # the policy of the file is left out

    def test_the_id_of_an_import_comes_from_its_folder(self) -> None:
        meta_path = self.store / self.info.id / admx.META_FILE
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta_path.write_text(json.dumps(dict(meta, id="bundled-windows")), encoding="utf-8")
        with self.assertRaisesRegex(admx.AdmxError, "names another import"):
            admx.load_import(self.store, self.info.id)

    def test_characters_the_answer_file_cannot_hold_and_dot_segments(self) -> None:
        for name in ("a" + chr(0xFFFF), "a" + chr(0x85)):
            self.assertFalse(admx.safe_name(name), repr(name))
            self.assertFalse(admx.safe_value(name), repr(name))
        for key in ("..\\.DEFAULT\\Control Panel", "Software\\.\\X", "Software/../X", "Software\\\\X"):
            self.assertFalse(admx.safe_key(key), key)
        self.assertTrue(admx.safe_key("Software\\Policies\\Vendor.App"))
        value = self.exported()
        value["templates"]["policies"][0]["enabled"][0]["key"] = "..\\.DEFAULT\\Control Panel"
        with self.assertRaisesRegex(admx.AdmxError, "registry key without unsafe characters"):
            package_module.read_package(self.write(value))

    def test_a_boolean_never_becomes_an_enum_value(self) -> None:
        from winkickoff.mcp.errors import ToolError
        from winkickoff.mcp.workspace import normalise_param_value

        catalog, _ = admx.with_imports(self.base, self.store, [self.info.id], "en")
        state = catalog.rules[TOGGLE].params["state"]
        with self.assertRaises(ToolError):
            normalise_param_value(catalog.rules[TOGGLE], state, False)
        saved = Profile.from_catalog(catalog).to_dict(catalog)
        saved["rules"][TOGGLE] = {"enabled": True, "params": {"state": False}, "source": "folder"}  # as MCP of 1.2 stored it
        profile, _ = Profile.from_dict(saved, catalog)
        self.assertEqual(profile.rules[TOGGLE].params["state"], 0)
        self.assertNotIsInstance(profile.rules[TOGGLE].params["state"], bool)

    def test_duplicate_ids_are_numbered_as_1_2_numbered_them_in_english(self) -> None:
        value = self.exported()
        policies = value["templates"]["policies"]
        first = next(p for p in policies if p["name"] == "SimpleToggle")
        second = copy.deepcopy(first)
        first["title"], second["title"] = {"en-US": "Zeta"}, {"en-US": "Alpha"}
        for write in second["enabled"] + second["disabled"]:
            write["key"] = "Software\\Policies\\WKTest\\Second"
        policies.append(second)  # after the first in the file, before it by its English title
        info = package_module.import_package(self.store, self.write(value), now=NOW)
        catalog, _ = admx.with_imports(self.base, self.store, [info.id], "ru")
        self.assertEqual(str(catalog.rules[TOGGLE].actions[0].fields["path"]), "HKLM:\\Software\\Policies\\WKTest\\Second")
        self.assertEqual(str(catalog.rules[TOGGLE + "-2"].actions[0].fields["path"]), "HKLM:\\Software\\Policies\\WKTest")

    def test_wrong_types_of_a_profile_are_warned_about(self) -> None:
        good = Profile.from_catalog(self.base).to_dict(self.base)
        rules = dict(good["rules"])
        rules["remote.registry-off"] = {"enabled": 0}
        rules["defender.pua"] = {"enabled": "yes"}
        profile, warnings = Profile.from_dict(dict(good, rules=rules, install={"edition": 5}, languages={"ui_language": 7}),
                                              self.base)
        self.assertFalse(profile.is_enabled("remote.registry-off"))  # 0 is off, as in 1.2
        self.assertTrue(profile.is_enabled("defender.pua"))  # the default, with a warning
        for fragment in ("defender.pua: the saved state", "install.edition", "languages.ui_language"):
            self.assertTrue(any(fragment in w for w in warnings), fragment)
        self.assertIsInstance(Profile.from_dict(dict(good, install=5), self.base)[0], Profile)


class PackageWindowTest(AdmxTestCase):
    window = test_admx.WindowTest.window  # not imported by name: unittest would run its tests here again

    def pump(self, win, seconds: float = 20.0) -> None:  # type: ignore[no-untyped-def]
        """Run the event loop until the background read is over (the window may be rebuilt and gone then)."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                win.update()
            except tk.TclError:
                return
            if win.restart_state is not None or not win._busy:
                return
            time.sleep(0.02)
        self.fail("the background read did not finish")

    def exported(self, paths) -> Path:  # type: ignore[no-untyped-def]
        target = self.tmp / "catalog.json"
        info = admx.list_imports(paths.admx)[0]
        package_module.export_package(paths.admx, info.id, target)
        return target

    def test_the_menu(self) -> None:
        win, _, _ = self.window()
        bar = win.nametowidget(win.cget("menu"))
        index = next(i for i in range(bar.index("end") + 1) if bar.type(i) == "cascade" and bar.entrycget(i, "label") == "ADMX")
        menu = win.nametowidget(bar.entrycget(index, "menu"))
        entries = {menu.entrycget(i, "label"): str(menu.entrycget(i, "state")) for i in range(menu.index("end") + 1)
                   if menu.type(i) != "separator"}
        self.assertEqual(entries["Import a catalog file..."], "normal")
        self.assertEqual(entries["Export imported templates"], "normal")
        self.assertEqual(entries["Import a catalog of the program"], "disabled")  # catalogs/ holds only its README

    def test_a_catalog_file_is_imported_in_the_background(self) -> None:
        win, info, paths = self.window()
        target = self.exported(paths)
        with mock.patch("winkickoff.ui.main_window.filedialog.askopenfilename", return_value=str(target)), \
                mock.patch("winkickoff.ui.main_window.messagebox.askyesnocancel") as ask:
            win.import_catalog_file()
            self.assertTrue(win._busy)
            self.pump(win)
        ask.assert_not_called()  # the first import of the file asks nothing
        new = [i.id for i in admx.list_imports(paths.admx) if i.id.startswith("package-")]
        self.assertEqual(len(new), 1)
        self.assertEqual(win.restart_state["item"], "g:admx." + new[0])
        self.assertEqual(win.settings.admx, [info.id, new[0]])
        self.assertIn("imported", win.restart_state["status"])

    def test_a_second_import_of_the_same_file_asks(self) -> None:
        for answer in (True, False, None):
            with self.subTest(answer=answer):
                self._tmp.cleanup()
                self.setUp()
                win, info, paths = self.window()
                target = self.exported(paths)
                first = package_module.import_package(paths.admx, target, now=NOW)
                with mock.patch("winkickoff.ui.main_window.filedialog.askopenfilename", return_value=str(target)), \
                        mock.patch("winkickoff.ui.main_window.messagebox.askyesnocancel", return_value=answer) as ask:
                    win.import_catalog_file()
                    self.pump(win)
                ask.assert_called_once()
                ids = sorted(i.id for i in admx.list_imports(paths.admx) if i.id.startswith("package-"))
                if answer is None:
                    self.assertEqual((ids, win.restart_state), ([first.id], None))
                elif answer:
                    self.assertEqual(ids, [first.id])
                    self.assertIn("updated", win.restart_state["status"])
                    self.assertEqual(win.settings.admx, [info.id, first.id])
                else:
                    self.assertEqual(len(ids), 2)
                    self.assertEqual(win.settings.admx[-1], [i for i in ids if i != first.id][0])
                try:
                    win.destroy()
                except tk.TclError:
                    pass

    def test_a_catalog_of_the_program(self) -> None:
        win, info, paths = self.window()
        target = self.exported(paths)
        folder = self.tmp / "catalogs"
        folder.mkdir()
        (folder / "Test catalog.json.xz").write_bytes(lzma.compress(target.read_bytes()))
        catalog = package_module.bundled_catalogs(folder)[0]
        win.import_bundled_catalog(catalog)
        self.pump(win)
        self.assertEqual(win.restart_state["item"], "g:admx.bundled-test-catalog")
        self.assertEqual(win.settings.admx, [info.id, "bundled-test-catalog"])

    def test_errors_are_shown_and_the_window_waits_for_the_read(self) -> None:
        win, info, paths = self.window()
        target = self.tmp / "out.json"
        with mock.patch("winkickoff.ui.main_window.filedialog.asksaveasfilename", return_value=str(target)), \
                mock.patch("winkickoff.ui.main_window.package_module.export_package", side_effect=OSError("disk full")), \
                mock.patch("winkickoff.ui.main_window.messagebox.showerror") as error:
            win.export_templates(info.id, info.name)
        self.assertIn("disk full", error.call_args[0][1])
        with mock.patch("winkickoff.ui.main_window.messagebox.showerror") as error:
            win.finish_catalog({"error": admx.AdmxError("x" * 100000)}, None, False)
            win.finish_catalog({"package": None}, mock.Mock(side_effect=UnicodeEncodeError("utf-8", "a", 0, 1, "bad")), False)
        self.assertEqual(error.call_count, 2)
        self.assertLess(len(error.call_args_list[0][0][1]), 2000)
        win.set_busy(True, "reading")
        with mock.patch("winkickoff.ui.main_window.simpledialog.askstring") as rename:
            win.import_vars[info.id].set(False)  # the check button of the menu toggles its variable first
            win.show_templates(info.id, False)
            win.change_language("ru")
            win.change_theme("dark")
            win.rename_templates(info.id, info.name)
        rename.assert_not_called()
        self.assertIsNone(win.restart_state)
        self.assertTrue(win.import_vars[info.id].get())
        self.assertEqual((win.language_var.get(), win.theme_var.get()), (win.settings.language, win.settings.theme))
        win.set_busy(False)


if __name__ == "__main__":
    unittest.main()
