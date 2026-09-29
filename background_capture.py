"""Captura o conteúdo da janela do Albion mesmo coberta por outras janelas.

``coordinate_system.capture_region`` (usado por ``bot.py``) chama
``PIL.ImageGrab.grab``, que copia pixels da área composta da tela: se outra
janela cobrir o Albion, a captura enxerga a janela de cima, não o jogo.

Este módulo usa ``PrintWindow`` com a flag ``PW_RENDERFULLCONTENT`` (GDI), que
pede ao Windows/DWM para renderizar o conteúdo atual da janela alvo para um
bitmap, independente do que está por cima — o mesmo mecanismo usado nas
miniaturas do Alt+Tab. Só não funciona com a janela minimizada.

Depende da aplicação renderizar via DWM (jogos em modo janela ou janela sem
borda geralmente funcionam; tela cheia exclusiva geralmente não). Valide com
``scripts/test_background_capture.py`` antes de integrar a ``bot.py``.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PIL import Image

PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0
BI_RGB = 0


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int
_user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
_user32.PrintWindow.restype = wintypes.BOOL

_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = wintypes.BOOL
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.DeleteDC.restype = wintypes.BOOL
_gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.LPVOID,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
]
_gdi32.GetDIBits.restype = ctypes.c_int


class WindowCaptureError(RuntimeError):
    pass


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Retorna (left, top, width, height) da janela inteira, em tela."""
    rect = RECT()
    if not _user32.GetWindowRect(wintypes.HWND(int(hwnd)), ctypes.byref(rect)):
        raise WindowCaptureError("GetWindowRect falhou.")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise WindowCaptureError("Janela com dimensão inválida (minimizada?).")
    return rect.left, rect.top, width, height


def capture_window(hwnd: int) -> Image.Image:
    """Retorna um snapshot RGB da janela inteira (com bordas), mesmo coberta."""
    _, _, width, height = get_window_rect(hwnd)

    hdc_screen = _user32.GetDC(None)
    if not hdc_screen:
        raise WindowCaptureError("GetDC(tela) falhou.")
    hdc_mem = _gdi32.CreateCompatibleDC(hdc_screen)
    bitmap = _gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    old_obj = _gdi32.SelectObject(hdc_mem, bitmap)

    try:
        ok = _user32.PrintWindow(wintypes.HWND(int(hwnd)), hdc_mem, PW_RENDERFULLCONTENT)
        if not ok:
            raise WindowCaptureError(
                "PrintWindow falhou; o app pode não suportar PW_RENDERFULLCONTENT."
            )

        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # top-down
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB

        buffer = ctypes.create_string_buffer(width * height * 4)
        scanlines = _gdi32.GetDIBits(
            hdc_mem, bitmap, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS
        )
        if scanlines == 0:
            raise WindowCaptureError("GetDIBits falhou.")

        image = Image.frombuffer("RGB", (width, height), buffer.raw, "raw", "BGRX", 0, 1)
        return image.copy()
    finally:
        _gdi32.SelectObject(hdc_mem, old_obj)
        _gdi32.DeleteObject(bitmap)
        _gdi32.DeleteDC(hdc_mem)
        _user32.ReleaseDC(None, hdc_screen)


def capture_client_region(
    hwnd: int, client_rect_screen: tuple[int, int, int, int]
) -> Image.Image:
    """Recorta a área do cliente (coordenadas de tela) do snapshot completo."""
    window_left, window_top, _, _ = get_window_rect(hwnd)
    left, top, width, height = client_rect_screen
    full = capture_window(hwnd)
    crop_left = left - window_left
    crop_top = top - window_top
    return full.crop((crop_left, crop_top, crop_left + width, crop_top + height))
