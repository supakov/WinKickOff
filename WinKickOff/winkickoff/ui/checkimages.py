"""Check-box images for the rule tree, drawn in code (no image files) and scaled to the screen DPI.

Check boxes are item images, not characters in the text: a click on the image toggles the rule,
a click on the expand indicator only opens the branch, a click on the text only selects.
"""

from __future__ import annotations

import tkinter as tk

BORDER = "#5b5b5b"
FILL_ON = "#2463c7"
FILL_OFF = "#ffffff"
MARK = "#ffffff"


def image_size(widget: tk.Misc) -> int:
    try:
        scale = float(widget.tk.call("tk", "scaling")) / (96 / 72)
    except (tk.TclError, ValueError):
        scale = 1.0
    return max(13, round(14 * scale))


def _draw_check(img: tk.PhotoImage, size: int) -> None:
    thickness = max(2, size // 7)
    points = [(0.20, 0.50), (0.42, 0.72), (0.80, 0.28)]
    steps = size * 2
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        for i in range(steps + 1):
            x = int((x0 + (x1 - x0) * i / steps) * size)
            y = int((y0 + (y1 - y0) * i / steps) * size)
            img.put(MARK, to=(x, y, min(size - 1, x + thickness), min(size - 1, y + thickness)))


def make_check_images(widget: tk.Misc) -> dict[str, tk.PhotoImage]:
    size = image_size(widget)
    images: dict[str, tk.PhotoImage] = {}
    for state in ("on", "off", "partial"):
        img = tk.PhotoImage(master=widget, width=size, height=size)
        img.put(BORDER, to=(0, 0, size, size))
        img.put(FILL_ON if state == "on" else FILL_OFF, to=(1, 1, size - 1, size - 1))
        if state == "on":
            _draw_check(img, size)
        elif state == "partial":
            q = max(3, size // 4)
            img.put(FILL_ON, to=(q, q, size - q, size - q))
        images[state] = img
    return images
