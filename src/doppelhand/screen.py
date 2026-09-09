"""Screen capture through the Windows GDI, with no capture dependency."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PIL import Image

from doppelhand.errors import ActionError

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0
BI_RGB = 0
SM_CXSCREEN = 0
SM_CYSCREEN = 1

try:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
except (AttributeError, OSError) as exc:  # pragma: no cover - non-Windows import
    raise ImportError("doppelhand runs on Windows only") from exc


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# Handles are pointer-sized; without these the return values are truncated on 64-bit.
_user32.GetDC.restype = wintypes.HDC
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
_gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
]

_dpi_ready = False


def set_dpi_awareness() -> None:
    """Report true pixels. Without this, capture size and cursor coordinates disagree
    on any display scaled above 100%."""
    global _dpi_ready
    if _dpi_ready:
        return
    per_monitor_v2 = ctypes.c_void_p(-4)
    try:
        if _user32.SetProcessDpiAwarenessContext(per_monitor_v2):
            _dpi_ready = True
            return
    except AttributeError:
        pass
    try:
        result = ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        # E_ACCESSDENIED means an application manifest already chose the mode.
        _dpi_ready = result in (0, 0x80070005)
    except (AttributeError, OSError):
        _dpi_ready = bool(_user32.SetProcessDPIAware())


def screen_size() -> tuple[int, int]:
    """Primary display size in physical pixels."""
    set_dpi_awareness()
    return _user32.GetSystemMetrics(SM_CXSCREEN), _user32.GetSystemMetrics(SM_CYSCREEN)


def grab(region: tuple[int, int, int, int] | None = None) -> Image.Image:
    """Capture the primary display, or `(left, top, width, height)` of it."""
    set_dpi_awareness()
    if region is None:
        left, top = 0, 0
        width, height = screen_size()
    else:
        left, top, width, height = region
    if width <= 0 or height <= 0:
        raise ActionError(f"capture region has no area: {width}x{height}")

    screen_dc = _user32.GetDC(None)
    if not screen_dc:
        raise ActionError("could not open a device context for the screen")
    mem_dc = bitmap = previous = None
    try:
        mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
        bitmap = _gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not mem_dc or not bitmap:
            raise ActionError("could not allocate a bitmap for the capture")
        previous = _gdi32.SelectObject(mem_dc, bitmap)
        if not _gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top,
                             SRCCOPY | CAPTUREBLT):
            raise ActionError(f"screen copy failed (error {ctypes.get_last_error()})")

        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # negative height gives top-down rows
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB

        buffer = ctypes.create_string_buffer(width * height * 4)
        copied = _gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer,
                                  ctypes.byref(info), DIB_RGB_COLORS)
        if copied != height:
            raise ActionError(f"read {copied} of {height} scan lines from the capture")
        return Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1)
    finally:
        if previous:
            _gdi32.SelectObject(mem_dc, previous)
        if bitmap:
            _gdi32.DeleteObject(bitmap)
        if mem_dc:
            _gdi32.DeleteDC(mem_dc)
        _user32.ReleaseDC(None, screen_dc)
