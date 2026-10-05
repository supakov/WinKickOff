"""The program writes only inside its own folder (portable): a full session from start to close.

app_paths() is replaced by a temporary program folder; data (rules, templates) come from the
repository. After the session the repository tree must be unchanged and the temporary folder
must hold only the program's own working files. Dialogs are replaced by mocks.
"""

from __future__ import annotations

import quiet_tk  # noqa: F401 - first: every window these tests open stays invisible
import logging
import tempfile
import time
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001 - no display or no Tk: the test is skipped
    TK_OK = False

from winkickoff.core.paths import AppPaths

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    """Files of the repository with size and modification time (caches and git excluded)."""
    skip = {".git", "__pycache__", "output", "logs"}
    return {
        str(p.relative_to(folder)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in folder.rglob("*")
        if p.is_file() and not (skip & set(p.relative_to(folder).parts))
    }


@unittest.skipUnless(TK_OK, "Tk is not available")
class PortableSessionTest(unittest.TestCase):
    def tearDown(self) -> None:
        from winkickoff.core import i18n

        i18n.set_language("en")  # create_app switched to the Windows language; later tests read English

    def test_full_session_writes_only_into_the_program_folder(self) -> None:
        before = snapshot(REPO)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "WinKickOff"
            base.mkdir()
            paths = AppPaths(root=base, data=ROOT, docs_root=REPO, profiles=base / "profiles",
                             output=base / "output", logs=base / "logs")
            for folder in (paths.profiles, paths.output, paths.logs):
                folder.mkdir()

            from winkickoff import app

            with mock.patch.object(app, "app_paths", return_value=paths), \
                 mock.patch.object(app, "_enable_dpi_awareness"), \
                 mock.patch("winkickoff.ui.main_window.filedialog.asksaveasfilename") as save_dialog, \
                 mock.patch("winkickoff.ui.main_window.messagebox") as boxes:
                boxes.askyesno.return_value = False
                boxes.askyesnocancel.return_value = False
                win = app.create_app(withdraw=True)
                try:
                    win.toggle_item("r:network.netbios-off")
                    save_dialog.return_value = str(paths.profiles / "Профіль.json")
                    self.assertTrue(win.save_profile())
                    save_dialog.return_value = str(paths.output / "autounattend.xml")
                    win.build()
                    deadline = time.monotonic() + 120
                    while (win._busy or not (paths.output / "autounattend.xml").exists()) and time.monotonic() < deadline:
                        win.update()
                        time.sleep(0.05)
                    self.assertTrue((paths.output / "autounattend.xml").exists(), [c.args for c in boxes.showerror.call_args_list])
                    win.on_close()
                finally:
                    try:
                        win.destroy()
                    except tk.TclError:
                        pass
                    for handler in list(logging.getLogger().handlers):
                        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename).is_relative_to(base):
                            logging.getLogger().removeHandler(handler)
                            handler.close()

            written = sorted(str(p.relative_to(base)) for p in base.rglob("*") if p.is_file())
            self.assertEqual(
                written,
                sorted([str(Path("logs/winkickoff.log")), str(Path("output/autounattend.xml")),
                        str(Path("profiles/Профіль.json")), "settings.json"]),
            )
            self.assertIn("Профіль.json", (base / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot(REPO), before, "the session changed files of the repository")


if __name__ == "__main__":
    unittest.main()
