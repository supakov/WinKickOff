"""Check-box images for the rule tree, drawn in code (no image files) and scaled to the screen DPI.

Check boxes are item images, not characters in the text: a click on the image toggles the rule,
a click on the expand indicator only opens the branch, a click on the text only selects.
"""

from __future__ import annotations

import tkinter as tk

from winkickoff.core.themes import LIGHT_COLORS


def image_size(widget: tk.Misc) -> int:
    try:
        scale = float(widget.tk.call("tk", "scaling")) / (96 / 72)
    except (tk.TclError, ValueError):
        scale = 1.0
    return max(13, round(14 * scale))


def _draw_check(img: tk.PhotoImage, size: int, mark: str) -> None:
    thickness = max(2, size // 7)
    points = [(0.20, 0.50), (0.42, 0.72), (0.80, 0.28)]
    steps = size * 2
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        for i in range(steps + 1):
            x = int((x0 + (x1 - x0) * i / steps) * size)
            y = int((y0 + (y1 - y0) * i / steps) * size)
            img.put(mark, to=(x, y, min(size - 1, x + thickness), min(size - 1, y + thickness)))


def make_check_images(widget: tk.Misc, colors: dict[str, str] | None = None) -> dict[str, tk.PhotoImage]:
    """The three check box images in the colours of the theme (check_border, check_on, check_off, check_mark)."""
    palette = {**LIGHT_COLORS, **{k: v for k, v in (colors or {}).items() if v}}
    border, fill_on, fill_off = palette["check_border"], palette["check_on"], palette["check_off"]
    size = image_size(widget)
    images: dict[str, tk.PhotoImage] = {}
    for state in ("on", "off", "partial"):
        img = tk.PhotoImage(master=widget, width=size, height=size)
        img.put(border, to=(0, 0, size, size))
        img.put(fill_on if state == "on" else fill_off, to=(1, 1, size - 1, size - 1))
        if state == "on":
            _draw_check(img, size, palette["check_mark"])
        elif state == "partial":
            q = max(3, size // 4)
            img.put(fill_on, to=(q, q, size - q, size - q))
        images[state] = img
    return images
