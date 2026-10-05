"""The JSON files of the catalog: canonical layout, ASCII rule files, generated files up to date, strict reading, tools.

tools/format_catalog.py writes the canonical layout; tools/make_browser_rules.py and tools/make_shell_rules.py write
rules/14-browsers.json and rules/17-shell.json. A hand edit of a generated file or a file in another layout fails here.
Everything the tools write in these tests goes into temporary folders.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import lzma
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from winkickoff.core import jsonfile

ROOT = Path(__file__).resolve().parents[1]
BS = chr(92)


def tool(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CatalogFilesTest(unittest.TestCase):
    def test_every_catalog_file_is_canonical(self) -> None:
        formatter = tool("format_catalog")
        files = formatter.catalog_files()
        self.assertIn(ROOT / "rules" / "groups.json", files)
        self.assertIn(ROOT / "rules" / "lang" / "uk.json", files)
        wrong = [str(p.relative_to(ROOT)) for p in files if p.read_bytes() != formatter.canonical(p)]
        self.assertEqual(wrong, [], "run python tools/format_catalog.py")

    def test_rule_files_are_ascii(self) -> None:
        """The catalog source is English; translations live in rules/lang/<code>.json."""
        for path in sorted((ROOT / "rules").glob("*.json")):
            with self.subTest(file=path.name):
                path.read_bytes().decode("ascii")

    def test_generated_files_are_up_to_date(self) -> None:
        for name, target in (("make_browser_rules", "14-browsers.json"), ("make_shell_rules", "17-shell.json")):
            with self.subTest(tool=name):
                expected = jsonfile.dumps(tool(name).catalog_file()).replace("\n", "\r\n").encode("utf-8")
                self.assertEqual((ROOT / "rules" / target).read_bytes(), expected, f"run python tools/{name}.py")


class FormatToolTest(unittest.TestCase):
    """tools/format_catalog.py on a temporary tree: exit codes, what it writes, catalogs of the program with null."""

    def tree(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / "rules" / "lang").mkdir(parents=True)
        (root / "catalogs").mkdir()
        jsonfile.write(root / "rules" / "groups.json", {"groups": [{"id": "a", "title": "A"}]})
        (root / "rules" / "10-x.json").write_text(json.dumps({"rules": []}), encoding="utf-8")  # not canonical
        return root

    def test_exit_codes_and_writing(self) -> None:
        formatter = tool("format_catalog")
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print") as shown:
            root = self.tree(tmp)
            before = (root / "rules" / "10-x.json").read_bytes()
            self.assertEqual(formatter.main(["--check"], root), 1)
            self.assertEqual((root / "rules" / "10-x.json").read_bytes(), before)  # --check writes nothing
            self.assertEqual(formatter.main([], root), 0)
            self.assertEqual((root / "rules" / "10-x.json").read_bytes(), b'{"rules": []}\r\n')
            self.assertEqual(formatter.main(["--check"], root), 0)
            (root / "rules" / "11-broken.json").write_text('{"rules": [', encoding="utf-8")
            (root / "rules" / "12-x.json").write_text(json.dumps({"rules": []}), encoding="utf-8")
            self.assertEqual(formatter.main([], root), 2)
            self.assertEqual((root / "rules" / "12-x.json").read_bytes(), b'{"rules": []}\r\n')  # the others still done
            printed = " ".join(str(call.args[0]) for call in shown.call_args_list)
            self.assertIn("11-broken.json", printed)

    def test_a_catalog_of_the_program_with_null_is_canonical_after_make_admx_catalogs(self) -> None:
        import test_admx  # the templates of the ADMX tests

        maker, formatter = tool("make_admx_catalogs"), tool("format_catalog")
        from winkickoff.core.package import read_package

        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            root = self.tree(tmp)
            templates = test_admx.write_templates(Path(tmp) / "templates")
            target = root / "catalogs" / "Test templates.json"
            maker.main([str(templates), str(target), "--name", "Test templates", "--windows", "10.0.26200"])
            package = read_package(target)
            self.assertEqual(package.name, "Test templates")
            self.assertIn(b"null", target.read_bytes())  # delete writes and check box texts
            self.assertEqual(formatter.canonical(target), target.read_bytes())
            self.assertEqual(formatter.main(["--check"], root), 1)  # only 10-x.json is not canonical
            target.write_text(json.dumps({"format": "winkickoff-catalog"}), encoding="utf-8")
            self.assertEqual(formatter.main([], root), 2)  # a catalog of the program is checked as a catalog file
            with self.assertRaises(SystemExit):
                maker.main([str(templates), str(root / "catalogs" / "x.json.xz"), "--name", "X"])


class JsonFileTest(unittest.TestCase):
    def test_canonical_layout(self) -> None:
        value = {"id": "a", "tags": ["x", "y"], "actions": [{"type": "reg", "value": 1}], "long": ["z" * 70, "w" * 70]}
        self.assertEqual(jsonfile.dumps(value),
                         '{\n  "id": "a",\n  "tags": ["x", "y"],\n  "actions": [{"type": "reg", "value": 1}],\n'
                         '  "long": [\n    "' + "z" * 70 + '",\n    "' + "w" * 70 + '"\n  ]\n}\n')
        self.assertEqual(jsonfile.loads(jsonfile.dumps(value)), value)
        self.assertEqual(jsonfile.dumps({"a": {}, "b": []}), '{"a": {}, "b": []}\n')

    def test_the_writer_refuses_what_it_could_not_read_back(self) -> None:
        for value in ({1: "x"}, {1: "x" * 130}, {"a": float("inf")}, [float("nan")], {"a": {1: "x"}}, {"a": [{None: 1}]},
                      {"a": {1: "x", "1": "y"}}):
            with self.subTest(value=str(value)[:20]), self.assertRaises(jsonfile.JsonFileError):
                jsonfile.dumps(value)

    def test_strict_reading(self) -> None:
        for text, fragment in (('{"a": 1, "a": 2}', "appears twice"), ('{"a": null}', "is null"), ("[1, null]", "holds null"),
                               ("[NaN]", "NaN"), ("[Infinity]", "Infinity"), ("null", "holds null"), ("{", "JSON syntax"),
                               ("[1e400]", "too large"), ("[-1e999]", "too large"),
                               ('["a' + BS + 'ud800b"]', "lone surrogate"), ('{"' + BS + 'udc00": 1}', "lone surrogate"),
                               ("[" * 40 + "]" * 40, "deeper than"), ("[" * 100000 + "]" * 100000, "deeper than")):
            with self.subTest(text=text[:20]), self.assertRaises(jsonfile.JsonFileError) as ctx:
                jsonfile.loads(text)
            self.assertIn(fragment, str(ctx.exception))
        self.assertEqual(jsonfile.loads('["' + BS + "ud83d" + BS + 'ude00"]'), [chr(0x1F600)])  # a pair is one character
        self.assertEqual(jsonfile.loads('{"a": null}', nulls=True), {"a": None})

    def test_the_number_of_values_is_bounded_before_parsing(self) -> None:
        text = "[" + ",".join(["{}"] * 2000) + "]"
        self.assertEqual(len(jsonfile.loads(text)), 2000)
        with self.assertRaisesRegex(jsonfile.JsonFileError, "more than 1000 values"):
            jsonfile.loads(text, max_items=1000)
        with mock.patch("json.loads") as parse, self.assertRaises(jsonfile.JsonFileError):
            jsonfile.loads(text, max_items=1000)
        parse.assert_not_called()

    def test_messages_quote_only_a_little_of_the_file(self) -> None:
        key = "k" * 100000
        with self.assertRaises(jsonfile.JsonFileError) as ctx:
            jsonfile.loads('{"' + key + '": 1, "' + key + '": 2}')
        self.assertLess(len(str(ctx.exception)), 200)

    def test_compressed_files_are_read_with_limits(self) -> None:
        text = jsonfile.dumps({"rules": ["x" * 1000]}).encode("utf-8")
        for name, packed in (("gzip", gzip.compress(text)), ("xz", lzma.compress(text, format=lzma.FORMAT_XZ))):
            with self.subTest(format=name):
                self.assertEqual(jsonfile.decode(packed), {"rules": ["x" * 1000]})
                for broken, fragment in ((packed[:-12], "cut off"), (packed + packed, "follows the"),
                                         (packed[:10] + b"\x00" * 30 + packed[40:], "")):
                    with self.assertRaises(jsonfile.JsonFileError) as ctx:
                        jsonfile.decode(broken)
                    self.assertIn(fragment, str(ctx.exception))
                with self.assertRaises(jsonfile.JsonFileError) as ctx:
                    jsonfile.decode(packed, limit=500)  # a small file that unpacks into more than the limit
                self.assertIn("larger than 500 bytes when unpacked", str(ctx.exception))

    def test_a_bomb_is_stopped_while_it_unpacks(self) -> None:
        """Valid JSON, so only the limit can stop it; the decompressor is never asked for more than limit + 1 bytes."""
        payload = b'["' + b"a" * (8 * 1024 * 1024) + b'"]'
        limit = 1024 * 1024
        real = zlib.decompressobj
        asked: list[int] = []

        class Spy:
            def __init__(self, wbits: int) -> None:
                self.inner = real(wbits=wbits)

            def decompress(self, data: bytes, max_length: int = 0) -> bytes:
                asked.append(max_length)
                return self.inner.decompress(data, max_length)

            def __getattr__(self, name: str):
                return getattr(self.inner, name)

        real_xz = lzma.LZMADecompressor
        asked_xz: list[int] = []

        class XzSpy:
            def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
                self.inner = real_xz(**kwargs)

            def decompress(self, data: bytes, max_length: int = -1) -> bytes:
                asked_xz.append(max_length)
                return self.inner.decompress(data, max_length)

            def __getattr__(self, name: str):
                return getattr(self.inner, name)

        for name, bomb in (("gzip", gzip.compress(payload)), ("xz", lzma.compress(payload))):
            with self.subTest(format=name):
                self.assertLess(len(bomb), 64 * 1024)
                with mock.patch.object(jsonfile.zlib, "decompressobj", Spy), \
                        mock.patch.object(jsonfile.lzma, "LZMADecompressor", XzSpy), \
                        self.assertRaises(jsonfile.JsonFileError) as ctx:
                    jsonfile.decode(bomb, limit=limit)
                self.assertIn("larger than 1 MB when unpacked", str(ctx.exception))
        for sizes in (asked, asked_xz):
            self.assertTrue(sizes and all(0 < size <= limit + 1 for size in sizes), sizes)

    def test_xz_memory_is_bounded(self) -> None:
        packed = lzma.compress(b'{"a": 1}', format=lzma.FORMAT_XZ, preset=9)  # its decoder needs about 65 MB
        self.assertEqual(jsonfile.decode(packed), {"a": 1})
        with mock.patch.object(jsonfile, "MAX_XZ_MEMORY", 1024 * 1024), self.assertRaises(jsonfile.JsonFileError) as ctx:
            jsonfile.decode(packed)
        self.assertIn("of memory to unpack", str(ctx.exception))
        with mock.patch.object(jsonfile.lzma, "LZMADecompressor", side_effect=MemoryError()), \
                self.assertRaisesRegex(jsonfile.JsonFileError, "not enough memory"):
            jsonfile.decode(packed)

    def test_file_limits_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json.xz"
            path.write_bytes(lzma.compress(b'{"a": "\xd1\x82"}'))
            self.assertEqual(jsonfile.read(path), {"a": chr(0x442)})
            with self.assertRaises(jsonfile.JsonFileError):
                jsonfile.read(path, file_limit=10)
            path.write_bytes(b'{"a": "\xff"}')
            with self.assertRaisesRegex(jsonfile.JsonFileError, "UTF-8"):
                jsonfile.read(path)
            with self.assertRaisesRegex(jsonfile.JsonFileError, "cannot read"):
                jsonfile.read(Path(tmp) / "missing.json")


if __name__ == "__main__":
    unittest.main()
