"""A delayed tool tip for a widget: text(event) decides what to show for the pointer position (the whole title of a
tree row that was cut, the whole title of the chosen option of a list), "" shows nothing. The tip is a borderless
top-level window next to the pointer; it hides when the pointer leaves, on a click, when the text changes and with the
widget."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

DELAY_MS = 600
WRAP = 480  # pixels: a long title wraps inside the tip


class Tooltip:
    def __init__(self, widget: tk.Widget, text: Callable[[tk.Event], str]) -> None:  # type: ignore[type-arg]
        self.widget = widget
        self.text = text
        self._job: str | None = None
        self._tip: tk.Toplevel | None = None
        self._shown = ""
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<Leave>", lambda _e: self.hide(), add="+")
        widget.bind("<ButtonPress>", lambda _e: self.hide(), add="+")
        widget.bind("<Destroy>", lambda _e: self.hide(), add="+")

    def _on_motion(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        text = self.text(event)
        if text == self._shown and self._tip is not None:
            return
        self.hide()
        if text:
            self._job = self.widget.after(DELAY_MS, lambda: self._show(text, event.x_root, event.y_root))

    def _show(self, text: str, x: int, y: int) -> None:
        self._job = None
        try:
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x + 16}+{y + 20}")
            ttk.Label(tip, text=text, wraplength=WRAP, justify="left", relief="solid", borderwidth=1, padding=(6, 3)).pack()
        except tk.TclError:  # the widget went away while the tip waited
            return
        self._tip, self._shown = tip, text

    def hide(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
        self._shown = ""
