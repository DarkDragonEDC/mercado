"""Lista a janela do Albion e todas as janelas 'filhas' dentro dela.

Uso:
    python scripts\\inspect_albion_window.py

Só lê informações, não clica em nada. Ajuda a descobrir se existe uma janela
filha (ex.: a área de renderização do jogo) diferente da janela principal —
o que explicaria por que PostMessage na janela principal não funcionou.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygetwindow as gw

_user32 = ctypes.windll.user32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
_user32.EnumChildWindows.restype = wintypes.BOOL
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
_user32.GetClientRect.restype = wintypes.BOOL


def get_albion_window():
    for title in ("Albion Online Client", "Albion Online"):
        windows = gw.getWindowsWithTitle(title)
        if windows:
            return windows[0]
    return None


def describe(hwnd: int) -> str:
    class_buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(wintypes.HWND(hwnd), class_buf, 256)
    text_buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(wintypes.HWND(hwnd), text_buf, 256)
    rect = RECT()
    _user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return (
        f"hwnd={hwnd} classe='{class_buf.value}' titulo='{text_buf.value}' "
        f"cliente={width}x{height}"
    )


def main() -> None:
    win = get_albion_window()
    if not win:
        print("Janela do Albion não encontrada. Abra o jogo e tente novamente.")
        return

    hwnd = int(getattr(win, "_hWnd", 0) or 0)
    print("Janela principal:")
    print(" ", describe(hwnd))

    children: list[int] = []

    def _callback(child_hwnd: int, _lparam: int) -> bool:
        children.append(child_hwnd)
        return True

    enum_proc = WNDENUMPROC(_callback)
    _user32.EnumChildWindows(wintypes.HWND(hwnd), enum_proc, 0)

    print(f"\nJanelas filhas encontradas: {len(children)}")
    for child in children:
        print(" ", describe(child))

    if not children:
        print(
            "\nNenhuma janela filha. O jogo renderiza tudo direto na janela "
            "principal — provavelmente lê o mouse por RawInput/DirectInput, "
            "não pela fila de mensagens do Windows."
        )


if __name__ == "__main__":
    main()
