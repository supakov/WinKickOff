"""core/paths.py: portable path resolution in source and frozen modes."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from winkickoff.core import paths as paths_module


class PathsTest(unittest.TestCase):
    def test_source_mode_root_is_package_folder(self) -> None:
        p = paths_module.app_paths(create=False)
        self.assertEqual(p.root.name, "WinKickOff")
        self.assertEqual(p.data, p.root)
        self.assertEqual(p.docs_root, p.root.parent)
        self.assertTrue((p.rules / "groups.toml").exists())

    def test_frozen_mode_uses_executable_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe_dir = Path(tmp) / "dist" / "WinKickOff"
            exe_dir.mkdir(parents=True)
            fake_exe = exe_dir / "WinKickOff.exe"
            fake_exe.write_bytes(b"")
            internal = exe_dir / "_internal"
            internal.mkdir()
            saved = (getattr(sys, "frozen", None), getattr(sys, "_MEIPASS", None), sys.executable)
            try:
                sys.frozen = True  # type: ignore[attr-defined]
                sys._MEIPASS = str(internal)  # type: ignore[attr-defined]
                sys.executable = str(fake_exe)
                p = paths_module.app_paths(create=True)
            finally:
                if saved[0] is None:
                    del sys.frozen  # type: ignore[attr-defined]
                else:
                    sys.frozen = saved[0]  # type: ignore[attr-defined]
                if saved[1] is None:
                    del sys._MEIPASS  # type: ignore[attr-defined]
                else:
                    sys._MEIPASS = saved[1]  # type: ignore[attr-defined]
                sys.executable = saved[2]
            self.assertEqual(p.root, exe_dir.resolve())
            self.assertEqual(p.data, internal)
            self.assertTrue((exe_dir / "profiles").is_dir())
            self.assertTrue((exe_dir / "output").is_dir())
            self.assertTrue((exe_dir / "logs").is_dir())

    def test_display_path_relative_inside_root(self) -> None:
        root = Path(tempfile.gettempdir())
        inside = root / "a" / "b.json"
        self.assertEqual(paths_module.display_path(inside, root), str(Path("a") / "b.json"))


if __name__ == "__main__":
    unittest.main()
