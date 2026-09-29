"""Injeta cliques e movimentos de mouse direto na janela do Albion.

Usa PostMessage do Win32 (WM_MOUSEMOVE / WM_LBUTTONDOWN / WM_LBUTTONUP /
WM_MOUSEWHEEL) em vez de SendInput (o que ``pyautogui`` usa em ``bot.py``).
Isso evita tomar o cursor físico do usuário, mas depende do Albion processar
essas mensagens de janela para o elemento de UI clicado. Jogos que leem o
mouse via DirectInput/RawInput ou hooks de baixo nível podem ignorar essas
mensagens por completo.

Valide com ``scripts/test_background_click.py`` antes de integrar isto a
``bot.py``. Este módulo não é usado por nenhum outro arquivo ainda.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002

_user32 = ctypes.windll.user32
_user32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.ClientToScreen.restype = wintypes.BOOL


def _lparam(x: int, y: int) -> int:
    return (int(y) & 0xFFFF) << 16 | (int(x) & 0xFFFF)


def _post(hwnd: int, msg: int, wparam: int, lparam: int) -> bool:
    return bool(_user32.PostMessageW(wintypes.HWND(int(hwnd)), msg, wparam, lparam))


def move(hwnd: int, x: int, y: int) -> bool:
    """Move o cursor lógico da janela para (x, y) em coordenadas de cliente."""
    return _post(hwnd, WM_MOUSEMOVE, 0, _lparam(x, y))


def click(hwnd: int, x: int, y: int, *, button: str = "left", hold: float = 0.05) -> bool:
    """Clica em (x, y) (coordenadas de cliente) sem mover o cursor real."""
    if button == "left":
        down_msg, up_msg, mk = WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON
    else:
        down_msg, up_msg, mk = WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON

    lparam = _lparam(x, y)
    move(hwnd, x, y)
    ok_down = _post(hwnd, down_msg, mk, lparam)
    time.sleep(hold)
    ok_up = _post(hwnd, up_msg, 0, lparam)
    return ok_down and ok_up


def drag(
    hwnd: int,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    duration: float = 0.4,
    steps: int = 12,
) -> bool:
    """Arrasta de start a end (coordenadas de cliente) sem mover o cursor real."""
    sx, sy = start
    ex, ey = end
    move(hwnd, sx, sy)
    if not _post(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, _lparam(sx, sy)):
        return False
    step_delay = duration / max(steps, 1)
    for i in range(1, steps + 1):
        ix = sx + (ex - sx) * i // steps
        iy = sy + (ey - sy) * i // steps
        _post(hwnd, WM_MOUSEMOVE, MK_LBUTTON, _lparam(ix, iy))
        time.sleep(step_delay)
    return _post(hwnd, WM_LBUTTONUP, 0, _lparam(ex, ey))


def scroll(hwnd: int, screen_x: int, screen_y: int, delta_notches: int) -> bool:
    """Rola a roda do mouse. WM_MOUSEWHEEL exige coordenadas de TELA, não de cliente."""
    wparam = (int(delta_notches) * 120) << 16
    return _post(hwnd, WM_MOUSEWHEEL, wparam, _lparam(screen_x, screen_y))


def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = wintypes.POINT(int(x), int(y))
    _user32.ClientToScreen(wintypes.HWND(int(hwnd)), ctypes.byref(point))
    return point.x, point.y
