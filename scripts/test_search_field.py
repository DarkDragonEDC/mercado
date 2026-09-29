"""Ferramenta manual para validar a busca do mercado (campo "Procurar...").

Uso (com o Albion aberto, no mercado, com o campo "Procurar..." visível):

    python scripts\\test_search_field.py

O script pede para você posicionar o cursor real sobre o campo "Procurar...",
grava essa posição, clica de verdade nele (clique real, já sabemos que
PostMessage não funciona nesse jogo) e cola um nome de teste via área de
transferência (Ctrl+V) — o mesmo mecanismo que bot.py usa de verdade,
escolhido porque lida bem com acentuação em português, diferente de digitar
caractere por caractere. Você confirma visualmente se a lista filtrou.

Não altera nada em bot.py nem em offsets.json; é só um experimento isolado.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ctypes
from ctypes import wintypes

import pyautogui
import pygetwindow as gw

from bot import definir_texto_area_transferencia
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


def main() -> None:
    win = get_albion_window()
    if not win:
        print("Janela do Albion não encontrada. Abra o jogo e tente novamente.")
        return

    geometry = get_client_geometry(win)
    print(f"Janela encontrada. área_cliente={geometry.width}x{geometry.height}")

    input(
        "\nAbra o mercado (a tela com o campo 'Procurar...' visível), "
        "posicione o CURSOR REAL em cima desse campo e pressione Enter "
        "(não clique ainda)..."
    )

    x, y = get_cursor_pos()
    if not geometry.contains(x, y):
        print("Cursor fora da área do Albion. Cancelado.")
        return
    print(f"Posição capturada: ({x},{y})")

    nome_teste = input(
        "\nDigite um nome de item pra usar no teste (ex: Machado): "
    ).strip() or "Machado"

    print("Clicando no campo de busca...")
    pyautogui.click(x, y)
    time.sleep(0.3)

    print("Selecionando tudo e apagando (Ctrl+A, Delete) antes de colar...")
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.2)

    print(f"Colando '{nome_teste}' via área de transferência (Ctrl+V)...")
    if not definir_texto_area_transferencia(nome_teste):
        print("Falha ao colocar o texto na área de transferência.")
        return
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1.0)

    print(
        "\nOlha pro jogo: a lista filtrou pra mostrar só itens com esse "
        "nome? O texto apareceu certinho no campo (sem faltar acento/letra)? "
        "Precisou apertar Enter pra filtrar, ou filtrou sozinho ao colar?"
    )


if __name__ == "__main__":
    main()
