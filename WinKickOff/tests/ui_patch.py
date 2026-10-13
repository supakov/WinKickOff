"""patch_window(name, ...): replace a module-level name of the window (messagebox, run_audit, plan_apply) in every
module of the window at once. Since 13.10.2026 the methods of MainWindow live in ui/main_window.py and its mixins
(window_detail, window_profiles, window_thispc, window_admx, window_mcp), so a test need not know which module calls
the name. The keyword arguments are those of mock.patch (return_value, wraps, side_effect); the one replacement is
yielded. A name of a module (tkinter.messagebox.askyesno, winkickoff.core.apply.launch_elevated) is patched there."""

from __future__ import annotations

import contextlib
import importlib
from collections.abc import Iterator
from typing import Any
from unittest import mock

WINDOW_MODULES = ("main_window", "window_detail", "window_profiles", "window_thispc", "window_admx", "window_mcp")


@contextlib.contextmanager
def patch_window(name: str, **kwargs: Any) -> Iterator[mock.MagicMock]:
    replacement = mock.MagicMock(**kwargs)
    with contextlib.ExitStack() as stack:
        patched = 0
        for module_name in WINDOW_MODULES:
            module = importlib.import_module(f"winkickoff.ui.{module_name}")
            if hasattr(module, name):
                stack.enter_context(mock.patch.object(module, name, replacement))
                patched += 1
        if not patched:
            raise AttributeError(f"no module of the window has {name}")
        yield replacement
