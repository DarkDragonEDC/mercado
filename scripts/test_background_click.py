"""Ferramenta manual para validar clique em segundo plano no Albion.

Uso (com o Albion aberto):

    .venv\\Scripts\\python.exe scripts\\test_background_click.py

O script pede para você posicionar o CURSOR REAL sobre um botão de teste
dentro do jogo, grava essa posição, MOVE o cursor real para o canto da tela e
então tenta clicar via PostMessage direto na janela do Albion, sem tocar o
mouse físico. Se o jogo reagir ao clique mesmo com o cursor real no canto,
a injeção direta na janela funciona para aquela área da UI.

Não altera nada em bot.py nem em offsets.json; é só um experimento isolado.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygetwindow as gw

import background_input
from coordinate_system import get_client_geometry


def get_albion_window():
    for title in ("Albion Online Client", "Albion Online"):
        windows = gw.getWindowsWithTitle(title)
        if windows:
            return windows[0]
    return None


def get_cursor_pos() -> tuple[int, int]:
    point = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def move_real_cursor(x: int, y: int) -> None:
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def main() -> None:
    win = get_albion_window()
    if not win:
        print("Janela do Albion nao encontrada. Abra o jogo e tente novamente.")
        return

    geometry = get_client_geometry(win)
    print(
        f"Janela encontrada. hwnd={geometry.hwnd} "
        f"area_cliente={geometry.width}x{geometry.height}"
    )

    input(
        "\nPosicione o CURSOR REAL sobre o botao/item que quer testar dentro "
        "do Albion e pressione Enter (nao clique ainda)..."
    )

    screen_x, screen_y = get_cursor_pos()
    if not geometry.contains(screen_x, screen_y):
        print("Cursor fora da area do Albion. Cancelado.")
        return

    client_x = screen_x - geometry.left
    client_y = screen_y - geometry.top
    print(
        f"Posicao capturada: tela=({screen_x},{screen_y}) "
        f"cliente=({client_x},{client_y})"
    )

    print("Movendo o cursor real para o canto da tela...")
    move_real_cursor(5, 5)
    time.sleep(1.0)

    print("Enviando clique via PostMessage direto na janela...")
    ok = background_input.click(geometry.hwnd, client_x, client_y)
    print(f"PostMessage retornou: {ok}")

    print(
        "\nVerifique no jogo se o clique realmente aconteceu (botao reagiu, "
        "menu abriu, item foi selecionado etc.) mesmo com o cursor real no "
        "canto da tela. Isso decide se vale integrar isto ao bot.py."
    )


if __name__ == "__main__":
    main()
