"""Drop-down menus in the theme colours on Windows.

Tk draws the items of a Windows drop-down menu itself, in the menu colours, but Windows paints a 2 px margin
around them in the system menu colour, a light frame in a dark theme. MenuMargins listens to menus opening in
this thread (a WinEvent hook limited to this process and thread) and gives each one the theme background
(SetMenuInfo MIM_BACKGROUND). Nothing outside this program changes and the hook ends with the window.
"""

from __future__ import annotations

import sys
from typing import Any

EVENT_SYSTEM_MENUPOPUPSTART = 0x0006
MN_GETHMENU = 0x01E1
MIM_BACKGROUND = 0x00000002
REDRAW = 0x0001 | 0x0004 | 0x0100 | 0x0400  # RDW_INVALIDATE, RDW_ERASE, RDW_UPDATENOW, RDW_FRAME


def colorref(color: str) -> int:
    """#rrggbb or #rgb as a Windows COLORREF (0x00bbggrr)."""
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return red | (green << 8) | (blue << 16)


class MenuMargins:
    def __init__(self, background: str) -> None:
        self._hook: Any = None
        self._brush: Any = None
        self._proc: Any = None
        if sys.platform != "win32" or not background:
            return
        try:
            self._start(colorref(background))
        except (AttributeError, OSError, ValueError):
            self.stop()

    def _start(self, color: int) -> None:
        import ctypes
        from ctypes import wintypes as wt

        user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32

        class MENUINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("fMask", wt.DWORD), ("dwStyle", wt.DWORD), ("cyMax", wt.UINT),
                        ("hbrBack", wt.HANDLE), ("dwContextHelpID", wt.DWORD), ("dwMenuData", ctypes.c_size_t)]

        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        user32.SetMenuInfo.argtypes = [wt.HANDLE, ctypes.POINTER(MENUINFO)]
        user32.SetWinEventHook.restype = wt.HANDLE
        user32.UnhookWinEvent.argtypes = [wt.HANDLE]
        gdi32.CreateSolidBrush.restype = wt.HANDLE
        gdi32.DeleteObject.argtypes = [wt.HANDLE]
        self._user32, self._gdi32 = user32, gdi32
        self._brush = gdi32.CreateSolidBrush(color)
        info = MENUINFO(ctypes.sizeof(MENUINFO), MIM_BACKGROUND, 0, 0, self._brush, 0, 0)

        def on_popup(_hook: Any, _event: int, hwnd: int, _object: int, _child: int, _thread: int, _time: int) -> None:
            try:
                menu = user32.SendMessageW(hwnd, MN_GETHMENU, 0, 0)
                if menu and user32.SetMenuInfo(menu, ctypes.byref(info)):
                    user32.RedrawWindow(hwnd, None, None, REDRAW)
            except Exception:  # noqa: BLE001  (never let an error escape into the Windows callback)
                pass

        prototype = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)
        self._proc = prototype(on_popup)  # kept referenced while the hook lives
        self._hook = user32.SetWinEventHook(EVENT_SYSTEM_MENUPOPUPSTART, EVENT_SYSTEM_MENUPOPUPSTART, None, self._proc,
                                            kernel32.GetCurrentProcessId(), kernel32.GetCurrentThreadId(), 0)

    @property
    def active(self) -> bool:
        return bool(self._hook)

    def stop(self) -> None:
        if self._hook:
            self._user32.UnhookWinEvent(self._hook)
            self._hook = None
        if self._brush:
            self._gdi32.DeleteObject(self._brush)
            self._brush = None
        self._proc = None
