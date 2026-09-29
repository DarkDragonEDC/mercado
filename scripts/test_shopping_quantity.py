"""Ferramenta manual para diagnosticar o ajuste de Quantia da Compra Programada.

Uso (com o Albion aberto, num Pedido de Compra com o campo "Quantia" visível
e calibrado em Configuração → Calibrar Cliques → grupo "Compra Programada"):

    python scripts\\test_shopping_quantity.py [valor]

Por padrão testa "50"; passe outro número (ex.: 10) pra reproduzir um caso
que está falhando especificamente com aquele valor.

Mostra, passo a passo: onde vai clicar, o que vai colar, e a leitura BRUTA
do OCR (as duas tentativas, com confiança) antes de qualquer reconciliação —
isso separa se o problema é o clique/colar (o campo não mudou) ou a leitura
(mudou certo, mas o OCR não bateu). Também salva a imagem exata que foi
fotografada pra OCR, pra dar pra ver se tem algum ícone/elemento visual
atrapalhando dentro da área calibrada.

Não altera nada em offsets.json nem em lista_compras.json.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import cv2
import pyautogui
import pygetwindow as gw

import bot
from coordinate_system import get_client_geometry, resolve_rect


def get_albion_window():
    for title in ("Albion Online Client", "Albion Online"):
        windows = gw.getWindowsWithTitle(title)
        if windows:
            return windows[0]
    return None


def main() -> None:
    valor_alvo = sys.argv[1] if len(sys.argv) > 1 else "50"
    if not valor_alvo.isdigit():
        print(f"Valor inválido: '{valor_alvo}'. Use só dígitos, ex.: 10")
        return

    win = get_albion_window()
    if not win:
        print("Janela do Albion não encontrada. Abra o jogo e tente novamente.")
        return

    offsets = bot.carregar_offsets()
    geometry = get_client_geometry(win)
    rect = resolve_rect(offsets.get("shopping_qtd_valor"), geometry, offsets)
    if not rect:
        print("Campo 'shopping_qtd_valor' não calibrado. Calibre antes de testar.")
        return

    print(f"Retângulo calibrado (tela): {rect}")
    centro_x = rect[0] + rect[2] / 2
    centro_y = rect[1] + rect[3] / 2
    print(f"Vou clicar no centro: ({centro_x:.0f}, {centro_y:.0f})")

    input(
        f"\nAbra um item para Pedido de Compra, deixe o campo Quantia visível "
        f"e pressione Enter para eu tentar mudar para {valor_alvo}..."
    )

    print("Lendo o valor ATUAL antes de mexer...")
    antes, erro_antes = bot._ler_quantidade_pedido(win, offsets)
    print(f"  valor lido antes: {antes} (erro: '{erro_antes}')")

    print("\nClicando no campo...")
    pyautogui.click(centro_x, centro_y)
    time.sleep(0.3)

    print("Tirando o cursor do mouse de cima do número (senão ele encobre os dígitos na leitura)...")
    pyautogui.moveTo(centro_x, rect[1] + rect[3] + 30)
    time.sleep(0.2)

    print("Ctrl+A (selecionar tudo)...")
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)

    print("Delete (apagar)...")
    pyautogui.press("delete")
    time.sleep(0.2)

    print("Olha pro jogo AGORA: o campo ficou vazio/zerado? Aperte Enter para continuar.")
    input()

    print(f"Colando '{valor_alvo}'...")
    if not bot.definir_texto_area_transferencia(valor_alvo):
        print(f"Falha ao colocar '{valor_alvo}' na área de transferência.")
        return
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)

    print(f"Olha pro jogo AGORA: o campo mostra {valor_alvo}? Aperte Enter para eu ler com OCR.")
    input()

    region = rect
    capture = bot.capture_region(region)
    captura_path = Path(__file__).resolve().parent / "quantidade_capturada.png"
    capture.save(captura_path)
    print(f"Imagem exata da área capturada salva em: {captura_path}")

    gray = cv2.cvtColor(np.array(capture), cv2.COLOR_RGB2GRAY)
    scaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
    _, thresholded = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    for nome_img, img in (("cinza ampliado", scaled), ("binarizado", thresholded)):
        resultado = bot.get_reader().readtext(img, detail=1, allowlist="0123456789., ", paragraph=False)
        print(f"\nOCR bruto ({nome_img}): {resultado}")

    valor_esperado = int(valor_alvo)
    depois, erro_depois = bot._ler_quantidade_pedido(win, offsets, valor_esperado)
    print(f"\nLeitura reconciliada (esperando {valor_esperado}): {depois} (erro: '{erro_depois}')")

    if depois == valor_esperado:
        print("\n[OK] O mecanismo funcionou! O problema pode ser outra coisa no fluxo.")
    else:
        print(
            f"\n[FALHOU] Confira: o campo realmente mostrou {valor_alvo} no jogo? Se sim "
            "mas o OCR não bateu, o problema é leitura (dá uma olhada na imagem salva "
            "acima — pode ter algum ícone dentro da área calibrada). Se o campo NÃO "
            f"mudou pra {valor_alvo}, o problema é o clique/colar."
        )


if __name__ == "__main__":
    main()
