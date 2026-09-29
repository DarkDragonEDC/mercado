"""Ferramenta manual para validar captura em segundo plano do Albion.

Uso (com o Albion aberto):

    .venv\\Scripts\\python.exe scripts\\test_background_capture.py

Passos:
    1. Deixe o Albion aberto (não minimizado).
    2. Cubra a janela do Albion com outra janela (navegador, bloco de notas).
    3. Pressione Enter no terminal.
    4. O script salva duas imagens em ``logs/``:
         - background_capture_tela.png   -> captura antiga (ImageGrab, vê a
           janela que está por cima).
         - background_capture_janela.png -> captura nova (PrintWindow, deve
           mostrar o Albion mesmo coberto).
    5. Abra as duas imagens e compare. Se a segunda mostrar o jogo, a captura
       em segundo plano funciona neste PC/config e podemos integrar ao bot.

Não altera nada em bot.py; é só um experimento isolado.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygetwindow as gw

import background_capture
from app_paths import logs_dir
from coordinate_system import capture_region, get_client_geometry


def get_albion_window():
    for title in ("Albion Online Client", "Albion Online"):
        windows = gw.getWindowsWithTitle(title)
        if windows:
            return windows[0]
    return None


def main() -> None:
    win = get_albion_window()
    if not win:
        print("Janela do Albion não encontrada. Abra o jogo e tente novamente.")
        return

    geometry = get_client_geometry(win)
    print(
        f"Janela encontrada. hwnd={geometry.hwnd} "
        f"área_cliente={geometry.width}x{geometry.height}"
    )

    input(
        "\nCubra a janela do Albion com outra janela (navegador, bloco de "
        "notas etc.) e pressione Enter..."
    )

    out_dir = logs_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    path_tela = out_dir / "background_capture_tela.png"
    path_janela = out_dir / "background_capture_janela.png"

    region = (geometry.left, geometry.top, geometry.width, geometry.height)

    print("Capturando pela tela (método antigo, ImageGrab)...")
    try:
        capture_region(region).save(path_tela)
        print(f"  salvo em {path_tela}")
    except Exception as exc:
        print(f"  falhou: {exc}")

    print("Capturando pela janela (método novo, PrintWindow)...")
    try:
        image = background_capture.capture_client_region(geometry.hwnd, region)
        image.save(path_janela)
        print(f"  salvo em {path_janela}")
    except Exception as exc:
        print(f"  falhou: {exc}")

    print(
        "\nAbra as duas imagens e compare. Se background_capture_janela.png "
        "mostrar o jogo (não a janela que está cobrindo), a captura em "
        "segundo plano funciona neste PC."
    )


if __name__ == "__main__":
    main()
