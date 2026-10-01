"""Copying a secret to the clipboard without the clipboard history and the cloud clipboard of Windows.

Windows 10 and 11 keep a clipboard history (Win+V) and, when the user switched it on, upload it to the Microsoft
account. A program keeps an item out of both by placing the formats ExcludeClipboardContentFromMonitorProcessing,
CanIncludeInClipboardHistory = 0 and CanUploadToCloudClipboard = 0 next to the text. Tk cannot add formats, so the
access token goes through the Win32 clipboard API; on another platform, or when that fails, Tk's clipboard is used.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from typing import Any

log = logging.getLogger(__name__)
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
EXCLUSION_FORMATS = ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")
OPEN_ATTEMPTS = 5  # another program may hold the clipboard for a moment


def copy_secret(widget: Any, text: str) -> bool:
    """Put text on the clipboard; on Windows marked for exclusion from the history and the cloud clipboard. Returns
    True when the exclusion formats were set, False when Tk's plain clipboard had to be used instead."""
    if sys.platform == "win32":
        try:
            _copy_excluded(text)
            return True
        except (OSError, AttributeError, ValueError):
            log.warning("clipboard exclusion formats not set; plain clipboard used")
    widget.clipboard_clear()
    widget.clipboard_append(text)
    return False


def _copy_excluded(text: str) -> None:
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.GlobalAlloc.restype, kernel32.GlobalAlloc.argtypes = wintypes.HGLOBAL, [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype, kernel32.GlobalLock.argtypes = wintypes.LPVOID, [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype, kernel32.GlobalUnlock.argtypes = wintypes.BOOL, [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype, kernel32.GlobalFree.argtypes = wintypes.HGLOBAL, [wintypes.HGLOBAL]
    user32.OpenClipboard.restype, user32.OpenClipboard.argtypes = wintypes.BOOL, [wintypes.HWND]
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.restype, user32.SetClipboardData.argtypes = wintypes.HANDLE, [wintypes.UINT, wintypes.HANDLE]
    user32.RegisterClipboardFormatW.restype, user32.RegisterClipboardFormatW.argtypes = wintypes.UINT, [wintypes.LPCWSTR]

    def global_block(data: bytes) -> Any:
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise OSError("GlobalAlloc failed")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            raise OSError("GlobalLock failed")
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        return handle

    def put(fmt: int, data: bytes) -> None:
        handle = global_block(data)
        if not user32.SetClipboardData(fmt, handle):  # on success the clipboard owns the block
            kernel32.GlobalFree(handle)
            raise OSError("SetClipboardData failed")

    formats = [user32.RegisterClipboardFormatW(name) for name in EXCLUSION_FORMATS]
    if not all(formats):
        raise OSError("RegisterClipboardFormatW failed")
    for attempt in range(OPEN_ATTEMPTS):
        if user32.OpenClipboard(None):
            break
        if attempt == OPEN_ATTEMPTS - 1:
            raise OSError("the clipboard is held by another program")
        time.sleep(0.02)
    try:
        if not user32.EmptyClipboard():
            raise OSError("EmptyClipboard failed")
        put(CF_UNICODETEXT, text.encode("utf-16-le") + b"\0\0")
        for fmt in formats:
            put(fmt, (0).to_bytes(4, "little"))  # a DWORD 0: not in the history, not uploaded; the first by presence
    finally:
        user32.CloseClipboard()
