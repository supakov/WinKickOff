"""Windows opened by the tests stay invisible on the screen of the person who runs them.

Every Tk root and Toplevel created after this module is imported is made fully transparent at once, before Tk shows
it, and on Windows becomes a tool window, which has no button on the taskbar. Without it the main window flashed for
a moment: it is built visible and the tests withdraw it only afterwards (the theme code maps it while building), and
the comparison window opened on top of everything. The windows still exist and are laid out, so the tests that need a
mapped window (the Treeview lays out rows only then) work as before.

Every test module that opens a window imports this module before it creates the first one, including the probe
"tk.Tk(); destroy()" that decides whether Tk is available.
"""

from __future__ import annotations

import sys

try:
    import tkinter as tk
except ImportError:  # no Tk: the window tests are skipped anyway
    tk = None  # type: ignore[assignment]


def quiet(window: object) -> None:
    """Make one window invisible (alpha 0) and keep it off the taskbar."""
    try:
        window.attributes("-alpha", 0.0)  # type: ignore[attr-defined]
        if sys.platform == "win32":
            window.attributes("-toolwindow", True)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - a platform without these attributes: the window stays as it is
        pass


if tk is not None and not getattr(tk.Tk, "_quiet_tk", False):
    _tk_init = tk.Tk.__init__
    _toplevel_init = tk.Toplevel.__init__

    def _quiet_tk_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _tk_init(self, *args, **kwargs)
        quiet(self)

    def _quiet_toplevel_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _toplevel_init(self, *args, **kwargs)
        quiet(self)

    tk.Tk.__init__ = _quiet_tk_init  # type: ignore[method-assign]
    tk.Toplevel.__init__ = _quiet_toplevel_init  # type: ignore[method-assign]
    tk.Tk._quiet_tk = True  # type: ignore[attr-defined]
