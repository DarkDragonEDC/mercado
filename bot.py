"""Núcleo de automação do Albion Elite.

As coordenadas v2 de ``offsets.json`` são normalizadas em relação à área
interna da janela do Albion. Toda conversão para a tela passa por
``coordinate_system``; não há heurística de âncora nem soma direta de bordas.
"""

from __future__ import annotations

import ctypes
import collections
import json
import os
import random
import sys
import threading
import time
import traceback
import unicodedata
from difflib import SequenceMatcher
from ctypes import wintypes
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyautogui
import pygetwindow as gw

from app_paths import calibration_assets_dir, logs_dir, migrate_legacy_state, user_file
from category_config import ITEM_TIERS
from performance_telemetry import observe_performance, start_performance_telemetry
from coordinate_system import (
    ClientGeometry,
    capture_region as _capture_region,
    get_client_geometry,
    load_settings,
    resolve_point,
    resolve_rect,
    save_settings,
    validate_calibration,
)


if getattr(sys, "frozen", False):
    try:
        torch_lib = os.path.join(sys._MEIPASS, "torch", "lib")
        if os.path.exists(torch_lib):
            os.add_dll_directory(torch_lib)
            os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

_reader = None
buy_callback = None
item_icon_prefetch_callback = None

# A lista de categorias possui uma pequena animacao no cliente do Albion. Este
# atraso existe somente entre abrir o menu e escolher uma categoria; nao entra
# no loop de itens nem na criacao de ordens.
CATEGORY_MENU_OPEN_DELAY = 1.5
PROTECTED_PAUSE_ENABLED_KEY = "pausa_protegida_ativa"
PROTECTED_PAUSE_INTERVAL_RANGE = (45 * 60, 90 * 60)
PROTECTED_PAUSE_DURATION_RANGE = (3 * 60, 7 * 60)
VERIFICAR_MEDIA_SEMANAL_KEY = "verificar_media_semanal"
OCR_CPU_THREADS = 3
# Taxa cobrada pelo jogo ao criar um pedido de compra; nao e devolvida se o
# pedido for cancelado (diferente do valor reservado do pedido em si).
TAXA_PEDIDO_COMPRA_PERCENTUAL = 0.025


def _bundled_ocr_models() -> str | None:
    """Retorna a pasta local de modelos quando o pacote os inclui."""
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_dir = Path(__file__).resolve().parent

    model_dir = base_dir / "ocr_models"
    required = ("craft_mlt_25k.pth", "latin_g2.pth")
    if model_dir.is_dir() and all((model_dir / name).is_file() for name in required):
        return str(model_dir)
    return None


def get_reader():
    global _reader
    if _reader is None:
        import easyocr
        import torch

        use_gpu = torch.cuda.is_available()
        if not use_gpu:
            # No i5-10400, tres threads mantiveram praticamente a mesma
            # latencia de quatro threads, com carga de CPU consideravelmente
            # menor. A quantidade afeta apenas paralelismo, nunca o resultado.
            torch.set_num_threads(OCR_CPU_THREADS)
        reader_options: dict[str, Any] = {}
        model_dir = _bundled_ocr_models()
        if model_dir:
            reader_options.update(
                model_storage_directory=model_dir,
                download_enabled=False,
            )
        _reader = easyocr.Reader(
            ["pt", "en"],
            gpu=use_gpu,
            verbose=False,
            **reader_options,
        )
    return _reader


migrate_legacy_state()
OFFSETS_FILE = str(user_file("offsets.json"))
CONTROL_FILE = str(user_file("bot_control.json"))
LISTA_COMPRAS_FILE = str(user_file("lista_compras.json"))
_templates_cache: dict[str, Any] = {}


class BotStoppedException(BaseException):
    """Interrupção imediata solicitada por bot_control.json."""


def carregar_offsets() -> dict[str, Any]:
    return load_settings(OFFSETS_FILE)


def carregar_lista_compras() -> list[dict[str, Any]]:
    """Le a lista de Compra Programada; formato invalido ou ausente vira []."""
    dados = load_settings(LISTA_COMPRAS_FILE)
    itens = dados.get("itens") if isinstance(dados, dict) else None
    return itens if isinstance(itens, list) else []


def salvar_lista_compras(itens: list[dict[str, Any]]) -> None:
    save_settings(LISTA_COMPRAS_FILE, {"itens": itens})


def chave_item_lista_compras(item: dict[str, Any]) -> tuple[str, Any, str]:
    """Identifica um item da lista por nome+tier+encantamento (ignora quantidade/status)."""
    return (
        str(item.get("nome", "")).strip(),
        item.get("tier"),
        str(item.get("encantamento") or "").strip(),
    )


def reverter_progresso_nao_pausado(
    status_inicial: dict[tuple[str, Any, str], Any],
    lista_atual: list[dict[str, Any]],
) -> int:
    """Volta para "pendente" os itens que só mudaram de status nesta rodada.

    Usado quando a Compra Programada é interrompida sem ser por uma pausa
    (PARAR, erro de calibragem, etc.): PARAR reseta o progresso da rodada, só
    a pausa preserva. Pedidos já criados no jogo não são desfeitos — só o
    status na lista volta para pendente, e a checagem de pedido próprio no
    topo evita duplicar o pedido na próxima rodada. Retorna quantos itens
    foram revertidos.
    """
    revertidos = 0
    for item in lista_atual:
        chave = chave_item_lista_compras(item)
        if status_inicial.get(chave) == "pendente" and item.get("status") != "pendente":
            item["status"] = "pendente"
            item.pop("_tentativas", None)
            revertidos += 1
    return revertidos


# A linha do topo em "Pedidos de Compra" fica com um tom mais escuro quando o
# pedido ali e do proprio jogador (medido no jogo: ~RGB 180,151,125 contra
# ~RGB 220,186,152 de uma linha comum). A diferenca e praticamente so de
# brilho, entao um limiar no canal mais claro basta e nao precisa de OCR nem
# de memoria entre execucoes - o pedido sumir (por venda) e refletido na hora.
COR_LINHA_PEDIDO_PROPRIO_LIMIAR_BRILHO = 200


def linha_pedido_e_minha(
    offsets: dict[str, Any], win, chave_cor: str = "compra_topo_cor"
) -> tuple[bool, float | None]:
    """Le a cor de fundo do topo de Pedidos de Compra; escura = pedido meu.

    chave_cor permite reaproveitar a mesma lógica em outras telas cuja
    amostra de cor fica em outra posição (ex.: "remover_pedidos_topo_cor" na
    tela "Editar pedido de compra", que fica em pixels diferentes da tela
    "Criar Pedido de Compra").

    Retorna (False, None) sem erro quando a chave ainda nao foi calibrada,
    preservando o comportamento atual para quem nao recalibrar esse ponto
    opcional. O brilho medido tambem e retornado para diagnostico.
    """
    geometry = get_client_geometry(win)
    region = resolve_rect(offsets.get(chave_cor), geometry, offsets)
    if not region:
        return False, None
    amostra = np.array(capture_region(region))
    if amostra.size == 0:
        return False, None
    media = amostra.reshape(-1, amostra.shape[-1]).mean(axis=0)
    brilho = float(media[:3].max())
    return brilho < COR_LINHA_PEDIDO_PROPRIO_LIMIAR_BRILHO, brilho


def media_semanal_disponivel(win, offsets: dict[str, Any]) -> tuple[bool | None, str]:
    """Lê o campo "Preço médio" (Histórico de mercado) do item aberto.

    Só é chamada quando a verificação está ativada nas configurações
    (VERIFICAR_MEDIA_SEMANAL_KEY). Se o campo mostrar "Sem média disponível",
    o item não teve saída na última semana e a compra não deve ser feita.

    Retorna (True, "") com um valor numérico confirmado, (False, motivo)
    quando o campo mostra explicitamente que não há média ou quando a
    leitura não pôde ser confirmada (por segurança, qualquer leitura
    ambígua bloqueia a compra em vez de presumir que está tudo bem -- mesmo
    critério já usado nas outras confirmações por OCR deste bot), ou
    (None, motivo) quando a área ainda não foi calibrada.
    """
    geometry = get_client_geometry(win)
    region = resolve_rect(offsets.get("preco_medio"), geometry, offsets)
    if not region:
        return None, "área do preço médio não calibrada"

    capture = capture_region(region)
    gray = cv2.cvtColor(np.array(capture), cv2.COLOR_RGB2GRAY)
    scaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
    _, thresholded = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    resultado = get_reader().readtext(thresholded, detail=0)
    texto_bruto = " ".join(str(item) for item in resultado)

    # A área calibrada normalmente inclui texto ao redor do valor (o rótulo
    # "Preço médio:", às vezes parte do seletor "24 horas"), então não dá pra
    # usar limpar_num aqui -- ela rejeita a leitura inteira se sobrar
    # qualquer letra junto do número, o que faria toda leitura válida (ex.:
    # "Preço médio: 43.637") ser tratada como não confirmada. Em vez disso,
    # confere a frase explícita primeiro, e senão apenas se há algum dígito
    # em algum lugar do texto -- suficiente pra essa checagem ser só
    # "tem valor numérico ou não", sem precisar do valor exato.
    normalizado = _normalizar_texto_menu(texto_bruto)
    if "sem medi" in normalizado:
        return False, "sem média disponível (item sem saída na última semana)"
    if any(caractere.isdigit() for caractere in texto_bruto):
        return True, ""
    return False, f"não foi possível confirmar o preço médio (leitura: '{texto_bruto}')"


def limpar_num(texto) -> int:
    """Converte uma leitura de OCR em prata, falhando de forma segura."""
    if not texto:
        return 0
    if isinstance(texto, str):
        raw = texto
    else:
        partes = []
        for item in texto:
            if isinstance(item, (tuple, list)) and len(item) >= 2 and isinstance(item[1], str):
                partes.append(item[1])
            else:
                partes.append(str(item))
        raw = " ".join(partes)
    raw = raw.strip()
    if not raw:
        return 0
    substituido = (
        raw.replace("I", "1")
        .replace("l", "1")
        .replace("O", "0")
        .replace("o", "0")
    )
    if any(caractere.isalpha() for caractere in substituido):
        return 0
    numero = "".join(caractere for caractere in substituido if caractere.isdigit())
    if not numero or len(numero) > 8:
        return 0
    return int(numero)


def validar_compra_financeira(
    preco_compra: int,
    preco_venda: int,
    lucro_minimo_percent: float,
    valor_max_prata: int,
) -> tuple[bool, str]:
    """Valida todos os limites financeiros; qualquer dado inválido bloqueia."""
    if valor_max_prata <= 0:
        return False, "limite máximo de prata inválido"
    if preco_compra <= 0:
        return False, "preço de compra não reconhecido"
    if preco_compra > valor_max_prata:
        return False, f"preço {preco_compra} excede o limite {valor_max_prata}"
    if preco_venda <= 0:
        return False, "preço de venda não reconhecido"
    if not 0 <= lucro_minimo_percent <= 100:
        return False, "lucro mínimo inválido"
    limite_por_lucro = preco_venda * (1 - lucro_minimo_percent / 100)
    if preco_compra > limite_por_lucro:
        return False, (
            f"preço {preco_compra} não preserva lucro mínimo de "
            f"{lucro_minimo_percent}% sobre a venda {preco_venda}"
        )
    return True, ""


def ler_lucro_minimo_config(offsets: dict[str, Any]) -> float:
    """Lê a regra v2; configurações antigas mantêm o mesmo limite efetivo."""
    if "lucro_minimo_venda" in offsets:
        return float(offsets.get("lucro_minimo_venda", 40.0))
    if "lucro" not in offsets:
        return 40.0
    custo_max_antigo = float(offsets.get("lucro", 80.0))
    return 100.0 - custo_max_antigo


def calcular_limite_disponivel_sessao(
    limite_por_ordem: int,
    banca_operacional: int,
    gasto_confirmado: int,
) -> int:
    """Aplica à ordem o saldo restante do orçamento desta execução."""
    if banca_operacional <= 0:
        return limite_por_ordem
    restante = max(0, banca_operacional - max(0, gasto_confirmado))
    return min(limite_por_ordem, restante)


def item_em_cooldown(
    bloqueados_ate: dict[tuple[str, int, int], float],
    chave: tuple[str, int, int],
    agora: float | None = None,
) -> bool:
    instante = time.monotonic() if agora is None else agora
    expira = bloqueados_ate.get(chave, 0.0)
    if expira <= instante:
        bloqueados_ate.pop(chave, None)
        return False
    return True


def check_control() -> tuple[bool, str]:
    if os.path.exists(CONTROL_FILE):
        try:
            with open(CONTROL_FILE, "r", encoding="utf-8") as arquivo:
                data = json.load(arquivo)
            return data.get("run", False), data.get("mode", "buy")
        except Exception:
            pass
    return False, "buy"


def controle_deve_preservar_posicao() -> bool:
    """Le se a parada atual pediu para preservar a posicao (pausa, nao PARAR).

    Campo aditivo de bot_control.json; ausente ou arquivo antigo => False,
    preservando o comportamento de reinicio total ja existente.
    """
    if os.path.exists(CONTROL_FILE):
        try:
            with open(CONTROL_FILE, "r", encoding="utf-8") as arquivo:
                data = json.load(arquivo)
            return bool(data.get("preserve_position", False))
        except Exception:
            pass
    return False


def auto_cycle_enabled() -> bool:
    if not os.path.exists(CONTROL_FILE):
        return False
    try:
        with open(CONTROL_FILE, "r", encoding="utf-8") as arquivo:
            return bool(json.load(arquivo).get("auto_cycle", False))
    except Exception:
        return False


def get_cycle_order_limit(offsets: dict[str, Any]) -> int:
    """Limite seguro do ciclo; arquivos antigos continuam usando 48."""
    try:
        value = int(offsets.get("cycle_order_limit", 48))
    except (TypeError, ValueError):
        return 48
    return value if 1 <= value <= 48 else 48


def trocar_modo_controle(mode: str) -> None:
    auto_cycle = auto_cycle_enabled()
    with open(CONTROL_FILE, "w", encoding="utf-8") as arquivo:
        json.dump({"run": True, "mode": mode, "auto_cycle": auto_cycle}, arquivo)


def check_stop() -> str:
    run_status, mode = check_control()
    if not run_status:
        raise BotStoppedException()
    return mode


def smart_sleep(duration: float) -> None:
    """Espera verificando a cada 10 ms se o bot foi desligado."""
    start = time.time()
    while time.time() - start < duration:
        check_stop()
        time.sleep(0.01)


def solicitar_intervencao_manual(reason: str) -> None:
    """Para imediatamente sem usar teclas ou qualquer fechamento genérico."""
    _run, mode = check_control()
    auto_cycle = auto_cycle_enabled()
    try:
        with open(CONTROL_FILE, "w", encoding="utf-8") as arquivo:
            json.dump(
                {"run": False, "mode": mode, "auto_cycle": auto_cycle},
                arquivo,
            )
    finally:
        print(f"[INTERVENÇÃO NECESSÁRIA] {reason}", flush=True)
    raise BotStoppedException()


class ProtectedPauseScheduler:
    """Agenda pausas somente quando o motor alcança um checkpoint seguro."""

    def __init__(self, rng=None, clock=None):
        self.rng = rng or random.SystemRandom()
        self.clock = clock or time.monotonic
        self.enabled = False
        self.next_pause_at: float | None = None

    def reset(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.next_pause_at = None
        if self.enabled:
            self._schedule_next()

    def sync(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled != self.enabled:
            self.reset(enabled)
        elif enabled and self.next_pause_at is None:
            self._schedule_next()

    def _schedule_next(self) -> None:
        delay = self.rng.randint(*PROTECTED_PAUSE_INTERVAL_RANGE)
        self.next_pause_at = self.clock() + delay

    def due(self) -> bool:
        return bool(
            self.enabled
            and self.next_pause_at is not None
            and self.clock() >= self.next_pause_at
        )

    def begin_pause(self) -> int:
        duration = self.rng.randint(*PROTECTED_PAUSE_DURATION_RANGE)
        self.next_pause_at = None
        return duration

    def finish_pause(self) -> None:
        if self.enabled:
            self._schedule_next()


def _format_pause_duration(seconds: int) -> str:
    minutes, remaining_seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes}m {remaining_seconds:02d}s"


def protected_pause_checkpoint(
    scheduler: ProtectedPauseScheduler,
    offsets: dict[str, Any],
    *,
    settings_loader=None,
    sleep_fn=None,
    log_fn=None,
) -> bool:
    """Executa uma pausa vencida; deve ser chamada apenas entre operações atômicas."""
    enabled = bool(offsets.get(PROTECTED_PAUSE_ENABLED_KEY, False))
    scheduler.sync(enabled)
    if not scheduler.due():
        return False

    loader = settings_loader or carregar_offsets
    sleeper = sleep_fn or smart_sleep
    emit = log_fn or (lambda message: print(message, flush=True))
    duration = scheduler.begin_pause()
    deadline = scheduler.clock() + duration
    emit(f" [PAUSA PROTEGIDA] Iniciada por {_format_pause_duration(duration)}.")
    last_reported_minute = None

    while True:
        remaining = max(0, int(deadline - scheduler.clock() + 0.999))
        if remaining <= 0:
            break
        current_settings = loader()
        if not bool(current_settings.get(PROTECTED_PAUSE_ENABLED_KEY, False)):
            scheduler.reset(False)
            emit(" [PAUSA PROTEGIDA] Cancelada porque a função foi desativada.")
            return False
        remaining_minute = (remaining + 59) // 60
        if remaining_minute != last_reported_minute:
            last_reported_minute = remaining_minute
            emit(f" [PAUSA PROTEGIDA] Restam {_format_pause_duration(remaining)}.")
        sleeper(min(1.0, remaining))

    scheduler.finish_pause()
    emit(" [PAUSA PROTEGIDA] Encerrada. Retomando automação.")
    return True


def capture_region(region):
    """Captura sem deixar uma falha temporaria do Windows encerrar o bot."""
    attempts = 0
    while True:
        try:
            image = _capture_region(region)
            if attempts:
                print(" [CAPTURA] Imagem recuperada. Retomando com seguranca.", flush=True)
            return image
        except OSError as exc:
            attempts += 1
            if attempts == 1:
                print(
                    f" [CAPTURA] Tela indisponivel ({exc}). "
                    "Cliques pausados ate o Windows liberar a imagem...",
                    flush=True,
                )
            elif attempts % 20 == 0:
                print(" [CAPTURA] Ainda aguardando a tela ficar disponivel...", flush=True)
            check_stop()
            time.sleep(0.5)


def resource_path(relative_path: str) -> str:
    relative = Path(relative_path)
    if relative.parent == Path("assets") and relative.name in {
        "fechar.png",
        "aviso_sim.png",
        "aviso_nao.png",
        "pedido_usuario.png",
        "vender_usuario.png",
        "editar_pedido_usuario.png",
        "cancelar_pedido_usuario.png",
    }:
        active_template = calibration_assets_dir() / relative.name
        if active_template.is_file():
            return str(active_template)

    local_path = os.path.abspath(relative_path)
    if os.path.exists(local_path):
        return local_path

    base_path = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    internal_path = os.path.join(base_path, relative_path)
    if os.path.exists(internal_path):
        return internal_path
    return local_path


def get_template(path: str):
    full_path = resource_path(path)
    if full_path not in _templates_cache:
        if os.path.exists(full_path):
            _templates_cache[full_path] = cv2.imread(full_path, 0)
        else:
            print(f" [!] Imagem não encontrada: {full_path}", flush=True)
            _templates_cache[full_path] = None
    return _templates_cache.get(full_path)


def invalidate_template_cache() -> None:
    """Força a releitura das amostras após uma nova calibragem visual."""
    _templates_cache.clear()


def verificar_referencia_proxima_offset(
    win,
    offsets: dict[str, Any],
    offset_key: str,
    template_names: tuple[str, ...],
    threshold: float = 0.58,
) -> tuple[bool | None, float, str]:
    """Confere um elemento perto da coordenada calibrada usando captura pequena.

    ``None`` significa que a referência não está disponível e permite ao
    chamador usar OCR ou outra validação existente como fallback.
    """
    try:
        geometry = get_client_geometry(win)
    except Exception:
        return None, -1.0, "janela indisponivel"
    point = resolve_point(offsets.get(offset_key), geometry, offsets)
    if not point:
        return None, -1.0, "coordenada indisponivel"

    templates: list[tuple[str, Any]] = []
    for name in template_names:
        template = get_template(os.path.join("assets", name))
        if template is not None:
            templates.append((name, template))
    if not templates:
        return None, -1.0, "referencia indisponivel"

    max_width = max(template.shape[1] for _, template in templates)
    max_height = max(template.shape[0] for _, template in templates)
    search_width = max(80, int(max_width * 1.9))
    search_height = max(60, int(max_height * 2.2))
    left = max(geometry.left, int(point[0] - search_width / 2))
    top = max(geometry.top, int(point[1] - search_height / 2))
    right = min(geometry.right, left + search_width)
    bottom = min(geometry.bottom, top + search_height)
    left = max(geometry.left, right - search_width)
    top = max(geometry.top, bottom - search_height)
    if right <= left or bottom <= top:
        return None, -1.0, "regiao visual invalida"

    screenshot = capture_region((left, top, right - left, bottom - top))
    screen_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    best_score = -1.0
    best_name = templates[0][0]
    for name, original in templates:
        for scale in (0.8, 0.9, 1.0, 1.1, 1.2):
            if scale == 1.0:
                template = original
            else:
                width = max(8, int(original.shape[1] * scale))
                height = max(8, int(original.shape[0] * scale))
                template = cv2.resize(
                    original, (width, height), interpolation=cv2.INTER_AREA
                )
            if (
                template.shape[0] > screen_gray.shape[0]
                or template.shape[1] > screen_gray.shape[1]
            ):
                continue
            result = cv2.matchTemplate(
                screen_gray, template, cv2.TM_CCOEFF_NORMED
            )
            _, score, _, _ = cv2.minMaxLoc(result)
            if score > best_score:
                best_score = float(score)
                best_name = name
    return best_score >= threshold, best_score, best_name


def esperar_referencia_proxima_offset(
    win,
    offsets: dict[str, Any],
    offset_key: str,
    template_names: tuple[str, ...],
    timeout: float = 0.7,
    threshold: float = 0.58,
) -> bool | None:
    """Espera brevemente uma referência local, sem OCR nem tela inteira."""
    deadline = time.time() + max(0.0, timeout)
    last_result: bool | None = None
    while True:
        check_stop()
        result, _score, _name = verificar_referencia_proxima_offset(
            win, offsets, offset_key, template_names, threshold
        )
        if result is None:
            return None
        if result:
            return True
        last_result = False
        if time.time() >= deadline:
            return last_result
        smart_sleep(0.10)


def localizar_referencia_na_area_offset(
    win,
    offsets: dict[str, Any],
    offset_key: str,
    template_names: tuple[str, ...],
    threshold: float = 0.72,
) -> tuple[tuple[float, float] | None, float, str]:
    """Localiza uma referência apenas ao redor da área calibrada e devolve seu centro."""
    try:
        geometry = get_client_geometry(win)
    except Exception:
        return None, -1.0, "janela indisponivel"
    calibrated = resolve_rect(offsets.get(offset_key), geometry, offsets)
    if not calibrated:
        return None, -1.0, "area nao calibrada"

    templates: list[tuple[str, Any]] = []
    for name in template_names:
        template = get_template(os.path.join("assets", name))
        if template is not None:
            templates.append((name, template))
    if not templates:
        return None, -1.0, "referencia indisponivel"

    left, top, width, height = calibrated
    max_width = max(template.shape[1] for _, template in templates)
    max_height = max(template.shape[0] for _, template in templates)
    pad_x = max(10, width // 2, max_width // 3)
    pad_y = max(8, height // 2, max_height // 3)
    search_left = max(geometry.left, int(left - pad_x))
    search_top = max(geometry.top, int(top - pad_y))
    search_right = min(geometry.right, int(left + width + pad_x))
    search_bottom = min(geometry.bottom, int(top + height + pad_y))
    if search_right <= search_left or search_bottom <= search_top:
        return None, -1.0, "area visual invalida"

    screenshot = capture_region(
        (search_left, search_top, search_right - search_left, search_bottom - search_top)
    )
    screen_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    best_score = -1.0
    best_name = templates[0][0]
    best_position = None
    for name, original in templates:
        for scale in (0.85, 0.9, 1.0, 1.1, 1.15):
            if scale == 1.0:
                template = original
            else:
                scaled_width = max(8, int(original.shape[1] * scale))
                scaled_height = max(8, int(original.shape[0] * scale))
                template = cv2.resize(
                    original,
                    (scaled_width, scaled_height),
                    interpolation=cv2.INTER_AREA,
                )
            if (
                template.shape[0] > screen_gray.shape[0]
                or template.shape[1] > screen_gray.shape[1]
            ):
                continue
            result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(result)
            if score > best_score:
                best_score = float(score)
                best_name = name
                best_position = (
                    search_left + location[0] + template.shape[1] / 2,
                    search_top + location[1] + template.shape[0] / 2,
                )
    if best_position is None or best_score < threshold:
        return None, best_score, best_name
    return best_position, best_score, best_name


def esperar_referencia_sumir(
    win,
    offsets: dict[str, Any],
    offset_key: str,
    template_names: tuple[str, ...],
    timeout: float = 1.0,
    threshold: float = 0.58,
) -> bool | None:
    """Confirma que um modal/botão saiu da coordenada após a ação."""
    deadline = time.time() + max(0.0, timeout)
    while True:
        check_stop()
        result, _score, _name = verificar_referencia_proxima_offset(
            win, offsets, offset_key, template_names, threshold
        )
        if result is None:
            return None
        if not result:
            return True
        if time.time() >= deadline:
            return False
        smart_sleep(0.10)


def get_albion_window():
    for title in ("Albion Online Client", "Albion Online"):
        windows = gw.getWindowsWithTitle(title)
        if windows:
            return windows[0]
    return None


def ensure_game_region_visible(win, region) -> tuple[bool, str]:
    """Confirma que a área a capturar pertence ao cliente do Albion na tela."""
    if not win or not region:
        return False, "Janela/área do Albion indisponível."
    hwnd = int(getattr(win, "_hWnd", 0) or 0)
    if not hwnd:
        return False, "Não foi possível identificar a janela do Albion."
    try:
        if win.isMinimized:
            return False, "A janela do Albion está minimizada."
        user32 = ctypes.windll.user32
        foreground = int(user32.GetForegroundWindow() or 0)
        if foreground != hwnd:
            try:
                win.activate()
            except Exception:
                user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
            time.sleep(0.25)

        left, top, width, height = region
        points = (
            (left + width // 2, top + height // 2),
            (left + 8, top + 8),
            (left + width - 8, top + height - 8),
        )
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = ctypes.c_void_p
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        for x, y in points:
            point_hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
            root_hwnd = user32.GetAncestor(point_hwnd, 2) if point_hwnd else None
            if int(root_hwnd or 0) != hwnd:
                return (
                    False,
                    "Outra janela está cobrindo a área da loja. Deixe o Albion em primeiro plano.",
                )
        return True, "Área do Albion visível."
    except Exception as exc:
        return False, f"Falha ao validar visibilidade da loja: {exc}"


def registrar_erro_fatal(exc: BaseException) -> None:
    details = traceback.format_exc()
    try:
        diagnostic_path = logs_dir() / "diagnostico_bot.log"
        with diagnostic_path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "=" * 72 + "\n")
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            handle.write(f"{type(exc).__name__}: {exc}\n")
            handle.write(details)
    except Exception:
        pass
    print(f" [!] Erro fatal: {type(exc).__name__}: {exc}", flush=True)
    print(details, flush=True)


def obter_safe_box(offsets: dict[str, Any], win):
    """Retorna o retângulo absoluto que envolve as calibragens válidas."""
    if not offsets or not win:
        return None
    geometry = get_client_geometry(win)
    all_xs: list[int] = []
    all_ys: list[int] = []
    for key, value in offsets.items():
        if key == "area_lista":
            continue
        rect = resolve_rect(value, geometry, offsets)
        if rect:
            left, top, width, height = rect
            all_xs.extend((left, left + width))
            all_ys.extend((top, top + height))
            continue
        point = resolve_point(value, geometry, offsets)
        if point:
            all_xs.append(point[0])
            all_ys.append(point[1])
    if not all_xs or not all_ys:
        return None
    return {
        "left": max(geometry.left, min(all_xs) - 60),
        "top": max(geometry.top, min(all_ys) - 60),
        "right": min(geometry.right, max(all_xs) + 60),
        "bottom": min(geometry.bottom, max(all_ys) + 60),
    }


def safe_click(x: float, y: float, win) -> bool:
    """Clica somente dentro da área interna real da janela do jogo."""
    if not win:
        return False
    geometry = get_client_geometry(win)
    if not geometry.contains(x, y):
        print(f" [!] Bloqueado clique fora da janela do jogo: ({x}, {y})", flush=True)
        return False
    safe_x = max(geometry.left, min(x, geometry.right - 1))
    safe_y = max(geometry.top, min(y, geometry.bottom - 1))
    pyautogui.click(safe_x, safe_y)
    return True


def get_abs_pos(btn_data, win, offsets=None):
    """Converte exclusivamente coordenadas v2 normalizadas para a tela."""
    offsets = offsets or carregar_offsets()
    return resolve_point(btn_data, get_client_geometry(win), offsets)


def clicar_offset(nome: str, win, offsets=None) -> bool:
    offsets = offsets or carregar_offsets()
    pos = get_abs_pos(offsets.get(nome), win, offsets)
    return bool(pos and safe_click(pos[0], pos[1], win))


def clicar_centro_bbox(bbox, win) -> bool:
    """Clica no centro de um objeto detectado com left/top/width/height."""
    return safe_click(
        bbox.left + bbox.width / 2,
        bbox.top + bbox.height / 2,
        win,
    )


def realizar_scroll(
    offsets: dict[str, Any],
    win,
    chave_start: str = "drag_start",
    chave_end: str = "drag_end",
) -> bool:
    if not win:
        return False
    geometry = get_client_geometry(win)
    start = resolve_point(offsets.get(chave_start), geometry, offsets)
    end = resolve_point(offsets.get(chave_end), geometry, offsets)
    if not (start and end):
        return False
    sx, sy = start
    ex, ey = end

    pyautogui.moveTo(sx, sy)
    pyautogui.mouseDown(button="left")
    smart_sleep(0.1)
    pyautogui.moveTo(ex, ey, duration=0.7)
    smart_sleep(0.5)
    pyautogui.mouseUp(button="left")
    return True


def retornar_ao_topo(
    offsets: dict[str, Any],
    win,
    chave_start: str = "top_start",
    chave_end: str = "top_end",
) -> bool:
    if not win:
        return False
    geometry = get_client_geometry(win)
    start = resolve_point(offsets.get(chave_start), geometry, offsets)
    end = resolve_point(offsets.get(chave_end), geometry, offsets)
    if not (start and end):
        return False
    sx, sy = start
    ex, ey = end
    pyautogui.moveTo(sx, sy)
    pyautogui.dragTo(ex, ey, duration=0.8, button="left")
    smart_sleep(1.0)
    return True


def tem_mais_paginas(win, offsets: dict[str, Any], chave_btn: str = "btn_proxima") -> bool:
    """Detecta a cor dourada da seta de próxima página."""
    geometry = get_client_geometry(win)
    point = resolve_point(offsets.get(chave_btn), geometry, offsets)
    if not point:
        return False
    px, py = point
    try:
        shot_left = max(geometry.left, px - 20)
        shot_top = max(geometry.top, py - 20)
        shot_right = min(geometry.right, px + 20)
        shot_bottom = min(geometry.bottom, py + 20)
        shot = capture_region(
            region=(shot_left, shot_top, shot_right - shot_left, shot_bottom - shot_top)
        )
        for x_in in range(shot.width):
            for y_in in range(shot.height):
                r, g, b = shot.getpixel((x_in, y_in))

                if r > 100 and g > 80:
                    ratio_rb = r / (b + 1)
                    ratio_gb = g / (b + 1)
                    if ratio_rb >= 2.5 and ratio_gb >= 1.8 and abs(int(r) - int(g)) <= 90:
                        return True
    except Exception as exc:
        print(f"Erro ao verificar páginas: {exc}", flush=True)
    return False


def clicar_proxima_pagina(
    win,
    offsets: dict[str, Any],
    chave_btn: str = "btn_proxima",
    chave_top_start: str = "top_start",
    chave_top_end: str = "top_end",
) -> bool:
    pos = resolve_point(offsets.get(chave_btn), get_client_geometry(win), offsets)
    if not pos:
        return False
    if not safe_click(pos[0], pos[1], win):
        return False
    smart_sleep(2.0)
    # O Albion preserva a posição vertical da lista entre páginas. Sem este
    # retorno explícito, a página seguinte pode abrir diretamente no final.
    return retornar_ao_topo(offsets, win, chave_top_start, chave_top_end)


def _normalizar_texto_menu(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join("".join(char if char.isalnum() else " " for char in text).split())


def analisar_encantamento_icone(icon_image) -> tuple[str, dict[str, Any]]:
    """Classifica o brilho e devolve evidencias para diagnostico local.

    A funcao preserva os mesmos limites usados pelo loop operacional. O
    dicionario retornado existe somente para observabilidade e nao participa da
    decisao de compra.
    """
    diagnostic: dict[str, Any] = {
        "value": "",
        "status": "not_read",
        "neon_pixels": 0,
        "threshold_pixels": 35,
        "scores": {".1": 0, ".2": 0, ".3": 0, ".4": 0},
        "winner": None,
        "winner_pixels": 0,
        "runner_up_pixels": 0,
        "margin_pixels": 0,
    }
    try:
        icon_bgr = cv2.cvtColor(np.array(icon_image), cv2.COLOR_RGB2BGR)
        h_i, w_i, _ = icon_bgr.shape
        diagnostic["crop_size"] = [int(w_i), int(h_i)]
        if h_i <= 0 or w_i <= 0:
            diagnostic["status"] = "invalid_crop"
            return "", diagnostic

        mask_border = np.zeros((h_i, w_i), dtype=np.uint8)
        esp = max(2, int(min(h_i, w_i) * 0.15))
        cv2.rectangle(mask_border, (0, 0), (w_i, h_i), 255, -1)
        cv2.rectangle(mask_border, (esp, esp), (w_i - esp, h_i - esp), 0, -1)
        hsv = cv2.cvtColor(icon_bgr, cv2.COLOR_BGR2HSV)
        mask_neon = (
            (mask_border == 255)
            & (hsv[:, :, 1] >= 100)
            & (hsv[:, :, 2] >= 100)
        )
        h_vals = hsv[:, :, 0][mask_neon]
        diagnostic["neon_pixels"] = int(len(h_vals))
        if len(h_vals) < 40:
            diagnostic.update(value=".0", status="default_zero_insufficient_color")
            return ".0", diagnostic

        scores = {
            ".1": int(np.sum((h_vals >= 48) & (h_vals <= 75))),
            ".2": int(np.sum((h_vals >= 78) & (h_vals <= 98))),
            ".3": int(np.sum((h_vals >= 128) & (h_vals <= 148))),
            ".4": int(np.sum((h_vals >= 20) & (h_vals <= 38))),
        }
        ranking = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        winner, winner_pixels = ranking[0]
        runner_up_pixels = ranking[1][1]
        diagnostic.update(
            scores=scores,
            winner=winner,
            winner_pixels=int(winner_pixels),
            runner_up_pixels=int(runner_up_pixels),
            margin_pixels=int(winner_pixels - runner_up_pixels),
        )
        if winner_pixels >= diagnostic["threshold_pixels"]:
            diagnostic.update(value=winner, status="color_match")
            return winner, diagnostic

        diagnostic.update(value=".0", status="default_zero_weak_color")
        return ".0", diagnostic
    except Exception as exc:
        diagnostic.update(status="error", error_type=type(exc).__name__)
        return "", diagnostic


def _ocr_tokens_for_log(value: Any) -> list[str]:
    """Normaliza a saida bruta do OCR para JSON sem alterar seu conteudo."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value[:160]]
    tokens: list[str] = []
    for item in value:
        if isinstance(item, (tuple, list)) and len(item) >= 2 and isinstance(item[1], str):
            tokens.append(item[1][:160])
        else:
            tokens.append(str(item)[:160])
    return tokens[:20]


def _price_read_status(raw_tokens: list[str], parsed_value: int) -> str:
    """Descreve a leitura sem confundir campo vazio com falta de liquidez."""
    if parsed_value > 0:
        return "parsed"
    if not raw_tokens:
        return "empty_capture"
    normalized = _normalizar_texto_menu(" ".join(raw_tokens))
    if normalized in {"n a", "na", "sem oferta", "sem ofertas"}:
        return "explicit_no_offer"
    if normalized and set(normalized.replace(" ", "")) <= {"0"}:
        return "explicit_zero"
    return "unparsed_text"


TIER_QUALIFICADORES = (
    (7, ("grao mestre", "graomestre", "grandmaster")),
    (8, ("anciao", "elder")),
    (6, ("mestre", "master")),
    (5, ("perito", "expert")),
    (4, ("adepto", "adept")),
    (3, ("iniciante", "journeyman")),
    (2, ("novato", "novice")),
)


def detectar_tier_nome(nome: str) -> int | None:
    """Identifica o tier pelos qualificadores usados no nome do item."""
    normalized = _normalizar_texto_menu(nome)
    for tier, names in TIER_QUALIFICADORES:
        if any(marker in normalized for marker in names):
            return tier
    return None


def remover_qualificador_tier(nome: str) -> str:
    """Tira o qualificador de tier do nome (ex.: "Lança do Adepto" -> "lanca").

    Equipamentos no jogo trazem o tier como palavra no fim do nome (Novato,
    Iniciante, Adepto, Perito, Mestre, Grão-Mestre, Ancião), não como número
    -- os mesmos marcadores que detectar_tier_nome já reconhece. Usado para
    comparar o nome base lido contra o nome digitado na Compra Programada sem
    depender do qualificador de tier, já que a busca do mercado por si só não
    distingue itens diferentes que compartilham parte do nome (ex.: "Lança do
    Adepto" vs "Lança Garceira do Adepto" vs "Lança-virotes do Adepto").
    """
    normalized = _normalizar_texto_menu(nome)
    for _tier, markers in TIER_QUALIFICADORES:
        for marker in markers:
            normalized = normalized.replace(marker, " ")
    palavras = [p for p in normalized.split() if p not in {"do", "de", "da"}]
    return " ".join(palavras)


NOME_BASE_SIMILARIDADE_MINIMA = 0.85


def nomes_base_correspondem(nome_base_lido: str, nome_base_alvo: str) -> bool:
    """Compara dois nomes base (já sem qualificador de tier) tolerando OCR.

    Erros comuns de OCR (ex.: "Erudito" lido como "€rudito" -- o "E" confundido
    com o símbolo de euro -- que depois vira "rudito" quando a normalização
    descarta caracteres não-ASCII) fariam uma comparação exata sempre falhar
    por causa de uma letra só. Em vez de exigir igualdade perfeita, aceita
    nomes "parecidos o suficiente" (razão de similaridade via SequenceMatcher),
    com o limiar alto o bastante para ainda rejeitar itens realmente
    diferentes que só compartilham uma palavra (ex.: "Lança" vs "Lança
    Garceira" fica bem abaixo do limiar).
    """
    if not nome_base_lido or not nome_base_alvo:
        return False
    razao = SequenceMatcher(None, nome_base_lido, nome_base_alvo).ratio()
    return razao >= NOME_BASE_SIMILARIDADE_MINIMA


def detectar_tier_icone(icon_image) -> int | None:
    """Fallback OCR: lê somente o pequeno numeral romano no canto do ícone."""
    try:
        image = np.array(icon_image)
        height, width = image.shape[:2]
        if height < 8 or width < 8:
            return None
        crop = image[: max(8, int(height * 0.45)), : max(8, int(width * 0.45))]
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        scaled = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        readings = get_reader().readtext(
            scaled,
            detail=0,
            allowlist="IVX",
            paragraph=False,
        )
        roman = "".join(
            char for text in readings for char in str(text).upper() if char in "IVX"
        )
        roman_to_tier = {
            "II": 2,
            "III": 3,
            "IV": 4,
            "V": 5,
            "VI": 6,
            "VII": 7,
            "VIII": 8,
        }
        return roman_to_tier.get(roman)
    except Exception as exc:
        print(f" [TIER] Falha ao ler numeral do icone: {exc}", flush=True)
        return None


def validar_tier_item(
    nome: str,
    allowed_tiers: Any,
    icon_image=None,
) -> tuple[bool, int | None, str]:
    """Aplica o filtro; OCR do ícone ocorre só quando o nome é ambíguo."""
    allowed = {
        int(tier)
        for tier in (allowed_tiers or ())
        if str(tier).isdigit() and int(tier) in ITEM_TIERS
    }
    if allowed == set(ITEM_TIERS):
        return True, detectar_tier_nome(nome), "todos os tiers habilitados"
    if not allowed:
        return False, None, "nenhum tier habilitado"

    tier = detectar_tier_nome(nome)
    source = "nome"
    if tier is None and icon_image is not None:
        tier = detectar_tier_icone(icon_image)
        source = "icone"
    if tier is None:
        return False, None, "tier nao reconhecido com filtro ativo"
    if tier not in allowed:
        return False, tier, f"T{tier} desmarcado ({source})"
    return True, tier, f"T{tier} permitido ({source})"


CATEGORIA_CLIQUE_KEYS = {
    "ARMAS": "cat_clique_armas",
    "PEITORAL": "cat_clique_peitoral",
    "CAPACETES": "cat_clique_capacetes",
    "BOTAS": "cat_clique_botas",
    "MÃO SECUNDARIA": "cat_clique_mao_secundaria",
    "CAPAS": "cat_clique_capas",
    "BOLSAS": "cat_clique_bolsas",
    "EQUIP COLETA": "cat_clique_equip_coleta",
    "ARTEFATO": "cat_clique_artefato",
}

def ler_quantidade_artefatos(offsets: dict[str, Any]) -> int:
    """Quantidade de unidades por pedido do modo Artefatos (mínimo 1)."""
    try:
        return max(1, int(offsets.get("artefatos_quantidade", 1) or 1))
    except (TypeError, ValueError):
        return 1


# Alvo fixo usado pelo modo "artefatos" (aba dedicada): trava a navegação
# nessa única categoria, independente de cat_ativo/cat_sequence/cat_enabled
# configurados pelo usuário para a aba COMPRA normal.
ARTEFATO_CATEGORY_TARGETS: list[dict[str, str]] = [
    {
        "category": "ARTEFATO",
        "key": CATEGORIA_CLIQUE_KEYS["ARTEFATO"],
        "label": "ARTEFATO",
    }
]


def executar_troca_categoria(
    win,
    offsets: dict[str, Any],
    proxima_cat_key: str,
) -> bool:
    print(
        f" [>>>] Trocando para categoria: "
        f"{proxima_cat_key.replace('cat_clique_', '').upper()}",
        flush=True,
    )
    geometry = get_client_geometry(win)
    cat_princ = resolve_point(offsets.get("cat_clique_principal"), geometry, offsets)
    if not cat_princ:
        print(" [!] Erro: Clique do Menu Categoria não calibrado!", flush=True)
        return False

    pos_cat = resolve_point(offsets.get(proxima_cat_key), geometry, offsets)
    if not pos_cat:
        print(f" [!] Erro: Clique da categoria {proxima_cat_key} não calibrado!", flush=True)
        return False

    if not safe_click(cat_princ[0], cat_princ[1], win):
        print(" [!] O clique para abrir Categorias foi bloqueado.", flush=True)
        return False
    smart_sleep(CATEGORY_MENU_OPEN_DELAY)

    if not safe_click(pos_cat[0], pos_cat[1], win):
        print(f" [!] O clique da categoria {proxima_cat_key} foi bloqueado.", flush=True)
        return False
    smart_sleep(1.5)
    retornar_ao_topo(offsets, win)
    return True


def selecionar_categoria_compra_programada(
    win,
    offsets: dict[str, Any],
    categoria_nome: str,
) -> tuple[bool, str]:
    """Seleciona a Categoria no dropdown do painel de busca da Compra Programada.

    Reaproveita os mesmos pontos calibrados do menu de categorias do modo de
    compra normal (cat_clique_principal + cat_clique_<categoria>) -- o
    dropdown "Categoria" de dentro do "Criar Pedido de Compra" abre no mesmo
    local da tela. Não chama retornar_ao_topo: aquele gesto de arrastar é
    específico da lista paginada do modo de compra normal, não existe nesse
    painel de busca.
    """
    categoria_key = CATEGORIA_CLIQUE_KEYS.get(categoria_nome.strip().upper())
    if not categoria_key:
        return False, f"categoria '{categoria_nome}' desconhecida"

    geometry = get_client_geometry(win)
    cat_princ = resolve_point(offsets.get("cat_clique_principal"), geometry, offsets)
    if not cat_princ:
        return False, "clique do menu Categoria não calibrado"
    pos_cat = resolve_point(offsets.get(categoria_key), geometry, offsets)
    if not pos_cat:
        return False, f"clique da categoria {categoria_key} não calibrado"

    if not safe_click(cat_princ[0], cat_princ[1], win):
        return False, "clique para abrir Categorias foi bloqueado"
    smart_sleep(CATEGORY_MENU_OPEN_DELAY)

    if not safe_click(pos_cat[0], pos_cat[1], win):
        return False, f"clique da categoria {categoria_key} foi bloqueado"
    smart_sleep(0.5)
    return True, ""


def build_active_category_targets(
    category_sequence: Any,
    category_enabled: Any,
    category_keys: dict[str, str],
) -> list[dict[str, str]]:
    """Monta a navegação apenas com categorias, preservando ordem e seleção."""
    enabled = category_enabled if isinstance(category_enabled, dict) else {}
    ordered_names: list[str] = []
    if isinstance(category_sequence, list):
        for name in category_sequence:
            if name in category_keys and name not in ordered_names:
                ordered_names.append(name)
    for name in category_keys:
        if name not in ordered_names:
            ordered_names.append(name)
    return [
        {"category": name, "key": category_keys[name], "label": name}
        for name in ordered_names
        if bool(enabled.get(name, True))
    ]


def validar_amostra_botao_pedido(
    width: int,
    height: int,
    client_width: int | None = None,
    client_height: int | None = None,
) -> tuple[bool, str]:
    """Valida se o recorte parece conter um único botão Pedido de Compra."""
    if width < 35 or height < 12:
        return False, "O recorte está pequeno demais para conter o botão inteiro."

    aspect_ratio = width / max(1, height)
    if aspect_ratio < 1.4:
        return False, (
            "A amostra ficou alta/vertical. Selecione APENAS UM botão "
            "Pedido de Compra, com um retângulo justo — não a coluna inteira."
        )
    if aspect_ratio > 8.0:
        return False, "O recorte ficou largo demais. Contorne somente um botão."

    if client_width and width > client_width * 0.30:
        return False, "O recorte ficou largo demais. Contorne somente um botão."
    if client_height and height > client_height * 0.13:
        return False, (
            "O recorte contém mais de uma linha. Selecione APENAS UM botão "
            "Pedido de Compra."
        )
    return True, ""


def _ordenar_botoes_pedido(candidates):
    """Remove detecções repetidas e devolve as linhas de cima para baixo."""
    unique = []
    for _score, box in sorted(candidates, key=lambda item: item[0], reverse=True):
        center_x = box.left + box.width / 2
        center_y = box.top + box.height / 2
        duplicate = any(
            abs(center_x - (current.left + current.width / 2)) < max(15, min(box.width, current.width) * 0.55)
            and abs(center_y - (current.top + current.height / 2)) < max(15, min(box.height, current.height) * 0.55)
            for current in unique
        )
        if not duplicate:
            unique.append(box)

    ordered = []
    for box in sorted(
        unique,
        key=lambda item: (item.top + item.height / 2, item.left + item.width / 2),
    ):
        center_y = box.top + box.height / 2
        if not ordered:
            ordered.append(box)
            continue
        previous_y = ordered[-1].top + ordered[-1].height / 2
        if center_y - previous_y > max(18, min(box.height, ordered[-1].height) * 0.55):
            ordered.append(box)
    return ordered[:5]


def _perceptual_hash(image: np.ndarray) -> bytes:
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(image, (32, 32), interpolation=cv2.INTER_AREA)
    normalized = resized.astype(np.float32) / 255.0
    coefficients = cv2.dct(normalized)[:16, :16]
    useful = coefficients.flatten()[1:]
    bits = useful >= float(np.median(useful))
    return np.packbits(bits).tobytes()


def _assinatura_visual_linha(image: np.ndarray) -> tuple[bytes, bytes, bytes]:
    """Cria uma assinatura perceptual compacta sem executar OCR adicional."""
    if image.size == 0:
        return b"", b"", b""
    icon_width = max(24, min(image.shape[1] // 3, int(image.shape[0] * 1.35)))
    icon = image[:, :icon_width]
    name_area = image[:, icon_width:]
    name_hash = _perceptual_hash(name_area if name_area.size else image)
    icon_hash = _perceptual_hash(icon)
    if image.ndim != 3:
        return name_hash, icon_hash, bytes(16)

    hsv = cv2.cvtColor(icon, cv2.COLOR_RGB2HSV)
    colorful = hsv[:, :, 1] >= 45
    if not np.any(colorful):
        return name_hash, icon_hash, bytes(16)
    hue_hist = cv2.calcHist([hsv], [0], colorful.astype(np.uint8), [12], [0, 180])
    saturation_hist = cv2.calcHist(
        [hsv], [1], colorful.astype(np.uint8), [4], [45, 256]
    )
    histogram = np.concatenate((hue_hist.flatten(), saturation_hist.flatten()))
    histogram /= max(1.0, float(histogram.sum()))
    color_signature = bytes(np.clip(np.rint(histogram * 255), 0, 255).astype(np.uint8))
    return name_hash, icon_hash, color_signature


def _assinaturas_linhas_pedido(
    screen_gray: np.ndarray,
    region: tuple[int, int, int, int],
    boxes,
) -> list[tuple[bytes, bytes, bytes]]:
    """Assina ícone/nome de cada linha, excluindo botões e barra animados."""
    if not boxes or screen_gray.size == 0:
        return []
    centers = [
        int(round((box.top - region[1]) + box.height / 2)) for box in boxes
    ]
    spacings = [
        later - earlier
        for earlier, later in zip(centers, centers[1:])
        if later > earlier
    ]
    typical_spacing = int(np.median(spacings)) if spacings else max(
        48, int(max(box.height for box in boxes) * 1.8)
    )
    row_height = max(40, min(screen_gray.shape[0], typical_spacing))
    button_left = min(int(box.left - region[0]) for box in boxes)
    content_right = max(32, min(screen_gray.shape[1], button_left - 12))

    signatures: list[tuple[bytes, bytes, bytes]] = []
    for center in centers:
        top = max(0, center - row_height // 2)
        bottom = min(screen_gray.shape[0], top + row_height)
        top = max(0, bottom - row_height)
        signatures.append(
            _assinatura_visual_linha(screen_gray[top:bottom, :content_right])
        )
    return signatures


def _distancia_assinaturas(
    first: tuple[bytes, bytes, bytes],
    second: tuple[bytes, bytes, bytes],
) -> float:
    if not first[0] or len(first[0]) != len(second[0]):
        return 1.0
    name_differing = sum(
        (left ^ right).bit_count() for left, right in zip(first[0], second[0])
    )
    name_distance = name_differing / (len(first[0]) * 8)
    if len(first[1]) != len(second[1]) or len(first[2]) != len(second[2]):
        return 1.0
    icon_differing = sum(
        (left ^ right).bit_count() for left, right in zip(first[1], second[1])
    )
    icon_distance = icon_differing / max(1, len(first[1]) * 8)
    color_distance = sum(
        abs(int(left) - int(right)) for left, right in zip(first[2], second[2])
    ) / max(1, len(first[2]) * 255)
    return max(name_distance / 0.12, icon_distance / 0.12, color_distance / 0.012)


def assinaturas_equivalentes(
    first: tuple[bytes, bytes, bytes],
    second: tuple[bytes, bytes, bytes],
    tolerance: float = 0.10,
) -> bool:
    return _distancia_assinaturas(first, second) <= tolerance


def conjuntos_assinaturas_equivalentes(
    first: list[tuple[bytes, bytes, bytes]],
    second: list[tuple[bytes, bytes, bytes]],
) -> bool:
    """Compara duas telas sem depender da posição vertical exata das linhas."""
    if len(first) != len(second) or not first:
        return False
    remaining = list(second)
    for signature in first:
        match = next(
            (
                index
                for index, candidate in enumerate(remaining)
                if assinaturas_equivalentes(signature, candidate)
            ),
            None,
        )
        if match is None:
            return False
        remaining.pop(match)
    return True


def assinatura_ja_vista(
    signature: tuple[bytes, bytes, bytes],
    seen: list[tuple[bytes, bytes, bytes]],
) -> bool:
    return any(assinaturas_equivalentes(signature, current) for current in seen)


def filtrar_linhas_novas(
    boxes,
    signatures: list[tuple[bytes, bytes, bytes]],
    seen: list[tuple[bytes, bytes, bytes]],
):
    """Separa linhas inéditas sem modificar o histórico do chamador."""
    new_rows = [
        (button, signature)
        for button, signature in zip(boxes, signatures)
        if not assinatura_ja_vista(signature, seen)
    ]
    return new_rows, len(boxes) - len(new_rows)


def criar_chave_semantica_linha(
    name: str,
    sale_price: int,
    buy_price: int,
    signature: tuple[bytes, bytes, bytes],
):
    """Última barreira contra ordem duplicada após uma leitura visual ruidosa."""
    return (
        _normalizar_texto_menu(name),
        int(sale_price),
        int(buy_price),
        signature[2],
    )


def detectar_botoes_pedido(
    win,
    offsets: dict[str, Any],
    incluir_assinaturas: bool = False,
):
    """Localiza botões de pedido usando primeiro a amostra calibrada no PC."""
    geometry = get_client_geometry(win)
    region = resolve_rect(offsets.get("area_lista"), geometry, offsets)
    if not region:
        result = ([], -1.0, "área_lista inválida")
        return (*result, []) if incluir_assinaturas else result

    screenshot = capture_region(region)
    screen_rgb = np.array(screenshot)
    screen_gray = cv2.cvtColor(screen_rgb, cv2.COLOR_RGB2GRAY)
    Box = collections.namedtuple("Box", ["left", "top", "width", "height"])
    template_specs = (
        # A amostra feita nesta máquina deve conservar exatamente o tamanho
        # capturado. Redimensioná-la desloca o centro calculado do clique.
        (os.path.join("assets", "pedido_usuario.png"), 0.72, (1.0,)),
        # O modelo distribuído com o programa continua multiescala como fallback.
        (os.path.join("assets", "pedido.png"), 0.68, (0.75, 0.85, 0.95, 1.0, 1.05, 1.15, 1.3)),
    )
    best_score = -1.0
    best_template = "nenhum template"

    for template_path, threshold, scales in template_specs:
        resolved_path = resource_path(template_path)
        if not os.path.exists(resolved_path):
            continue
        template_original = get_template(resolved_path)
        if template_original is None:
            continue
        if template_path.endswith("pedido_usuario.png"):
            valid, reason = validar_amostra_botao_pedido(
                template_original.shape[1],
                template_original.shape[0],
                geometry.width,
                geometry.height,
            )
            if not valid:
                best_template = f"pedido_usuario.png inválido: {reason}"
                continue

        template_candidates = []
        for scale in scales:
            if scale == 1.0:
                template = template_original
            else:
                width = max(8, int(template_original.shape[1] * scale))
                height = max(8, int(template_original.shape[0] * scale))
                template = cv2.resize(template_original, (width, height), interpolation=cv2.INTER_AREA)
            if template.shape[0] > screen_gray.shape[0] or template.shape[1] > screen_gray.shape[1]:
                continue
            result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            if score > best_score:
                best_score = float(score)
                best_template = os.path.basename(resolved_path)
            if score < threshold:
                continue
            neighborhood = cv2.dilate(result, np.ones((9, 9), dtype=np.uint8))
            ys, xs = np.where((result >= threshold) & (result >= neighborhood - 1e-7))
            for px, py in zip(xs, ys):
                template_candidates.append(
                    (
                        float(result[py, px]),
                        Box(
                            region[0] + int(px),
                            region[1] + int(py),
                            template.shape[1],
                            template.shape[0],
                        ),
                    )
                )
        ordered = _ordenar_botoes_pedido(template_candidates)
        if ordered:
            # A amostra do usuário tem prioridade. O template padrão só é usado
            # como fallback, evitando misturar duas listas de detecções.
            result = (ordered, best_score, os.path.basename(resolved_path))
            if incluir_assinaturas:
                return (
                    *result,
                    _assinaturas_linhas_pedido(screen_rgb, region, ordered),
                )
            return result

    result = ([], best_score, best_template)
    return (*result, []) if incluir_assinaturas else result


def detectar_botoes_vender(win, offsets: dict[str, Any]):
    """Localiza os botoes Vender dentro da area calibrada, de cima para baixo."""
    geometry = get_client_geometry(win)
    region = resolve_rect(offsets.get("sell_buttons_area"), geometry, offsets)
    if not region:
        return [], -1.0, "sell_buttons_area invalida"

    screenshot = capture_region(region)
    screen_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    Box = collections.namedtuple("Box", ["left", "top", "width", "height"])
    template_specs = (
        (os.path.join("assets", "vender_usuario.png"), 0.72, (1.0,)),
        (os.path.join("assets", "btn_vender.png"), 0.68,
         (0.75, 0.85, 0.95, 1.0, 1.05, 1.15, 1.3)),
    )
    best_score = -1.0
    best_template = "nenhum template"

    for template_path, threshold, scales in template_specs:
        resolved_path = resource_path(template_path)
        if not os.path.exists(resolved_path):
            continue
        template_original = get_template(resolved_path)
        if template_original is None:
            continue

        candidates = []
        for scale in scales:
            if scale == 1.0:
                template = template_original
            else:
                width = max(8, int(template_original.shape[1] * scale))
                height = max(8, int(template_original.shape[0] * scale))
                template = cv2.resize(template_original, (width, height), interpolation=cv2.INTER_AREA)
            if template.shape[0] > screen_gray.shape[0] or template.shape[1] > screen_gray.shape[1]:
                continue
            result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            if score > best_score:
                best_score = float(score)
                best_template = os.path.basename(resolved_path)
            if score < threshold:
                continue
            neighborhood = cv2.dilate(result, np.ones((9, 9), dtype=np.uint8))
            ys, xs = np.where((result >= threshold) & (result >= neighborhood - 1e-7))
            for px, py in zip(xs, ys):
                candidates.append((
                    float(result[py, px]),
                    Box(
                        region[0] + int(px),
                        region[1] + int(py),
                        template.shape[1],
                        template.shape[0],
                    ),
                ))
        ordered = _ordenar_botoes_pedido(candidates)
        if ordered:
            return ordered, best_score, os.path.basename(resolved_path)

    return [], best_score, best_template


def detectar_botoes_por_template(
    win,
    offsets: dict[str, Any],
    area_key: str,
    template_filename: str,
    threshold: float = 0.72,
):
    """Localiza todas as ocorrências de UM botão calibrado numa área da lista.

    Uso genérico para telas com N botões repetidos e apenas 1 amostra
    calibrada pelo usuário (sem template padrão de fallback), como os botões
    EDITAR e X de cancelar no modo Remover Pedidos.
    """
    geometry = get_client_geometry(win)
    region = resolve_rect(offsets.get(area_key), geometry, offsets)
    if not region:
        return [], -1.0, f"{area_key} inválida"

    screenshot = capture_region(region)
    screen_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    Box = collections.namedtuple("Box", ["left", "top", "width", "height"])

    resolved_path = resource_path(os.path.join("assets", template_filename))
    if not os.path.exists(resolved_path):
        return [], -1.0, f"{template_filename} não calibrado"
    template = get_template(resolved_path)
    if template is None:
        return [], -1.0, f"{template_filename} inválido"
    if template.shape[0] > screen_gray.shape[0] or template.shape[1] > screen_gray.shape[1]:
        return [], -1.0, "área menor que o template calibrado"

    result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
    _, best_score, _, _ = cv2.minMaxLoc(result)
    if best_score < threshold:
        return [], float(best_score), os.path.basename(resolved_path)

    neighborhood = cv2.dilate(result, np.ones((9, 9), dtype=np.uint8))
    ys, xs = np.where((result >= threshold) & (result >= neighborhood - 1e-7))
    candidates = [
        (
            float(result[py, px]),
            Box(region[0] + int(px), region[1] + int(py), template.shape[1], template.shape[0]),
        )
        for px, py in zip(xs, ys)
    ]
    ordered = _ordenar_botoes_pedido(candidates)
    return ordered, float(best_score), os.path.basename(resolved_path)


def parear_editar_com_cancelar(botoes_editar, botoes_cancelar, tolerancia_vertical: float = 22.0):
    """Pareia cada botão EDITAR com o X de cancelar da mesma linha.

    O pareamento usa proximidade vertical (mesmo eixo Y aproximado), já que
    EDITAR e X ficam lado a lado na mesma linha da lista. Cada botão só pode
    ser usado em um par; pares cuja distância mínima exceda a tolerância
    ficam de fora (linha ambígua/incompleta é ignorada, não adivinhada).
    Retorna pares ordenados de cima para baixo.
    """
    disponiveis_cancelar = list(botoes_cancelar)
    pares = []
    for editar in botoes_editar:
        centro_editar_y = editar.top + editar.height / 2
        melhor_idx = None
        melhor_dist = None
        for idx, cancelar in enumerate(disponiveis_cancelar):
            centro_cancelar_y = cancelar.top + cancelar.height / 2
            dist = abs(centro_editar_y - centro_cancelar_y)
            if dist <= tolerancia_vertical and (melhor_dist is None or dist < melhor_dist):
                melhor_dist = dist
                melhor_idx = idx
        if melhor_idx is not None:
            pares.append((editar, disponiveis_cancelar.pop(melhor_idx)))
    pares.sort(key=lambda par: par[0].top + par[0].height / 2)
    return pares


def capturar_conteudo_linha(area_region, editar_box) -> np.ndarray:
    """Recorta o conteúdo (ícone/nome) à esquerda do botão EDITAR de uma linha
    numa posição FIXA da tela.

    Usado para confirmar que uma linha mudou depois de cancelar um pedido.
    Comparar apenas a contagem total de itens não é confiável: se a lista
    tiver mais pedidos do que cabe na tela, cancelar um item visível faz um
    item escondido subir para a mesma posição, mantendo a contagem igual
    mesmo com o conteúdo daquela linha tendo mudado por completo.
    """
    left = area_region[0]
    right = max(left + 10, editar_box.left - 12)
    top = editar_box.top
    bottom = editar_box.top + editar_box.height
    if bottom <= top or right <= left:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    screenshot = capture_region((left, top, right - left, bottom - top))
    return np.array(screenshot)


def extrair_valor_venda(textos) -> int | None:
    """Converte o OCR do preco; zero, N/A e texto vazio nao sao vendaveis."""
    if not textos:
        return None
    raw = textos if isinstance(textos, str) else " ".join(str(item) for item in textos)
    normalized = raw.strip().upper().replace(" ", "")
    if not normalized or "N/A" in normalized or normalized in {"NA", "N.A", "N-A"}:
        return None
    corrected = (
        normalized.replace("I", "1").replace("L", "1")
        .replace("O", "0").replace("S", "5")
    )
    if any(char.isalpha() for char in corrected):
        return None
    digits = "".join(char for char in corrected if char.isdigit())
    if not digits:
        return None
    value = int(digits)
    return value if value > 0 else None


def ler_valor_venda(win, offsets: dict[str, Any]) -> tuple[int | None, str]:
    try:
        geometry = get_client_geometry(win)
        region = resolve_rect(offsets.get("sell_price_value"), geometry, offsets)
        if not region:
            return None, "area de preco invalida"
        image = capture_region(region)
        gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
        scaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
        _, threshold = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        started = time.perf_counter()
        textos = get_reader().readtext(threshold, detail=0)
        observe_performance("ocr_sale_price", time.perf_counter() - started)
        raw = " ".join(textos).strip()
        return extrair_valor_venda(textos), raw
    except Exception as exc:
        return None, f"erro de leitura: {exc}"


def confirmar_fechamento_modal_venda(
    win,
    offsets: dict[str, Any],
) -> bool | None:
    """Confirma o fechamento por controles que existem somente no modal.

    O botao Criar pode produzir falso positivo contra elementos da lista que
    reaparece depois da venda. O controle de reduzir preco e uma referencia
    mais especifica e, por isso, e verificado primeiro.
    """
    menos_sumiu = esperar_referencia_sumir(
        win,
        offsets,
        "sell_price_minus",
        ("btn_diminuir_preco.png",),
        timeout=0.8,
    )
    if menos_sumiu is True:
        return True

    criar_sumiu = esperar_referencia_sumir(
        win,
        offsets,
        "sell_create_button",
        ("btn_criar_venda.png",),
        timeout=0.35,
    )
    if criar_sumiu is True:
        return True
    if menos_sumiu is None and criar_sumiu is None:
        return None
    return False


def executar_cliques_venda(win, offsets: dict[str, Any], botao_vender) -> str | None:
    """Abre o item, reduz o preco em um e cria o pedido de venda."""
    if not clicar_centro_bbox(botao_vender, win):
        return None
    smart_sleep(0.55)
    check_stop()

    modal_visual = esperar_referencia_proxima_offset(
        win,
        offsets,
        "sell_price_minus",
        ("btn_diminuir_preco.png",),
        timeout=0.35,
    )
    if modal_visual is False:
        print(
            " [VENDA][VISUAL] Modal ainda nao confirmado; usando a leitura "
            "do preco como verificacao de fallback.",
            flush=True,
        )
    valor, texto_lido = ler_valor_venda(win, offsets)
    if valor is None:
        print(
            f" [VENDA] Item ignorado: preco vazio, zero ou N/A (OCR: {texto_lido or 'vazio'}).",
            flush=True,
        )
        if not clicar_offset("sell_close_button", win, offsets):
            return None
        smart_sleep(0.45)
        return "skipped"
    if not clicar_offset("sell_price_minus", win, offsets):
        return None
    smart_sleep(0.18)
    check_stop()

    criar_visual = esperar_referencia_proxima_offset(
        win,
        offsets,
        "sell_create_button",
        ("btn_criar_venda.png",),
        timeout=0.35,
    )
    if criar_visual is False:
        print(
            " [VENDA][PARADA SEGURA] Botao Criar nao confirmado no modal; "
            "nenhum clique foi feito nessa coordenada.",
            flush=True,
        )
        clicar_offset("sell_close_button", win, offsets)
        return None
    if not clicar_offset("sell_create_button", win, offsets):
        return None
    modal_fechou = confirmar_fechamento_modal_venda(win, offsets)
    if modal_fechou is False:
        print(
            " [VENDA][RECUPERACAO] O fechamento do modal ficou ambiguo; "
            "verificando o X antes de continuar.",
            flush=True,
        )
        garantir_modal_fechado(win, offsets)
        smart_sleep(0.30)
    smart_sleep(0.20)
    return "sold"


def realizar_scroll_venda(win, offsets: dict[str, Any], itens: int = 5) -> bool:
    """Rola a lista de venda e confirma visualmente que os produtos mudaram."""
    geometry = get_client_geometry(win)
    buttons_region = resolve_rect(offsets.get("sell_buttons_area"), geometry, offsets)
    if not buttons_region:
        return False

    right = buttons_region[0] + buttons_region[2]
    probe_left = max(
        geometry.left,
        buttons_region[0] - max(buttons_region[2] * 5, 240),
    )
    probe_region = (
        probe_left,
        buttons_region[1],
        right - probe_left,
        buttons_region[3],
    )
    try:
        before = cv2.cvtColor(np.array(capture_region(probe_region)), cv2.COLOR_RGB2GRAY)
        point_x = buttons_region[0] + buttons_region[2] // 2
        point_y = buttons_region[1] + buttons_region[3] // 2
        if not geometry.contains(point_x, point_y):
            return False
        pyautogui.moveTo(point_x, point_y)
        pyautogui.scroll(-abs(int(itens)))
        smart_sleep(0.65)
        after = cv2.cvtColor(np.array(capture_region(probe_region)), cv2.COLOR_RGB2GRAY)
        if before.shape != after.shape:
            return True
        change = float(np.mean(cv2.absdiff(before, after)))
        print(f" [VENDA] Movimento visual da lista: {change:.2f}", flush=True)
        return change >= 1.0
    except Exception as exc:
        print(f" [!] Falha ao rolar a lista de venda: {exc}", flush=True)
        return False


def ler_contador_transacoes(win, offsets: dict[str, Any]) -> tuple[int | None, str]:
    """Le o numero exibido no botao lateral de Transacoes Concluidas."""
    try:
        geometry = get_client_geometry(win)
        region = resolve_rect(offsets.get("cycle_counter_area"), geometry, offsets)
        if not region:
            return None, "area do contador invalida"
        image = capture_region(region)
        gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
        scaled = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        textos = get_reader().readtext(scaled, detail=0, allowlist="0123456789")
        raw = "".join(textos).strip()
        digits = "".join(char for char in raw if char.isdigit())
        return (int(digits), raw) if digits else (None, raw)
    except Exception as exc:
        return None, f"erro de leitura: {exc}"


def ler_numero_pagina_compra(win, offsets: dict[str, Any]) -> tuple[int | None, str]:
    """Lê somente o numeral calibrado entre as setas da lista de compra."""
    try:
        geometry = get_client_geometry(win)
        region = resolve_rect(offsets.get("buy_page_number_area"), geometry, offsets)
        if not region:
            return None, "area da pagina invalida"
        image = capture_region(region)
        gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
        scaled = cv2.resize(gray, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
        enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(scaled)
        _level, threshold = cv2.threshold(
            enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        leituras: list[str] = []
        for candidate in (enhanced, threshold):
            textos = get_reader().readtext(
                candidate,
                detail=0,
                allowlist="0123456789",
                paragraph=False,
            )
            raw = "".join(str(texto) for texto in textos).strip()
            if raw:
                leituras.append(raw)
                digits = "".join(char for char in raw if char.isdigit())
                if digits:
                    pagina = int(digits)
                    if 1 <= pagina <= 999:
                        return pagina, raw
        return None, " / ".join(leituras)
    except Exception as exc:
        return None, f"erro de leitura: {exc}"


def confirmar_pagina_compra(
    win,
    offsets: dict[str, Any],
    pagina_esperada: int,
) -> tuple[bool, int | None, str]:
    """Exige duas leituras iguais antes de confiar na página de compra."""
    primeira, raw_primeira = ler_numero_pagina_compra(win, offsets)
    smart_sleep(0.20)
    segunda, raw_segunda = ler_numero_pagina_compra(win, offsets)
    confirmado = (
        primeira is not None
        and primeira == segunda
        and primeira == int(pagina_esperada)
    )
    raw = f"{raw_primeira or 'vazio'} / {raw_segunda or 'vazio'}"
    return confirmado, segunda, raw


def restaurar_navegacao_compra(
    win,
    offsets: dict[str, Any],
    estado: dict[str, Any],
) -> bool:
    """Restaura categoria, página e deslocamento salvos pelo Ciclo."""
    category_key = estado.get("category_key")
    pagina = int(estado.get("page", 0) or 0)
    scroll_batches = int(estado.get("scroll_batches", 0) or 0)
    label = str(estado.get("category_label") or "categoria")
    if not category_key or pagina < 1 or scroll_batches < 0:
        print(
            " [CICLO][PARADA SEGURA] A posicao de compra salva esta incompleta.",
            flush=True,
        )
        return False

    print(
        f" [CICLO] Restaurando {label}, pagina {pagina}, "
        f"deslocamentos {scroll_batches}...",
        flush=True,
    )
    if not executar_troca_categoria(win, offsets, str(category_key)):
        return False

    for numero in range(2, pagina + 1):
        if not tem_mais_paginas(win, offsets):
            print(
                f" [CICLO][PARADA SEGURA] A pagina {numero} nao esta disponivel.",
                flush=True,
            )
            return False
        if not clicar_proxima_pagina(win, offsets):
            return False

    for _ in range(scroll_batches):
        if not realizar_scroll(offsets, win):
            print(
                " [CICLO][PARADA SEGURA] Nao foi possivel restaurar a posicao da lista.",
                flush=True,
            )
            return False
        smart_sleep(0.30)

    confirmado, lida, raw = confirmar_pagina_compra(win, offsets, pagina)
    if not confirmado:
        print(
            f" [CICLO][PARADA SEGURA] Pagina esperada={pagina}, "
            f"lida={lida}, OCR={raw}. Compras nao retomadas.",
            flush=True,
        )
        return False
    print(
        f" [CICLO] Pagina {pagina} confirmada. Retomando da posicao salva.",
        flush=True,
    )
    return True


def contador_ciclo_confirmado(
    primeira: int | None,
    segunda: int | None,
    limite: int,
) -> bool:
    """Aceita somente duas leituras iguais, plausiveis e acima do limite."""
    return (
        primeira is not None
        and segunda is not None
        and 1 <= primeira <= 48
        and primeira == segunda
        and primeira >= limite
    )


def confirmar_limite_contador(
    win,
    offsets: dict[str, Any],
    primeira: int,
    limite: int,
) -> tuple[bool, int | None, str]:
    """Faz a leitura extra apenas quando o ciclo parece atingir o limite."""
    if not 1 <= primeira <= 48:
        return False, None, "valor fora da faixa 1-48"
    smart_sleep(0.25)
    segunda, raw = ler_contador_transacoes(win, offsets)
    return contador_ciclo_confirmado(primeira, segunda, limite), segunda, raw


def esperar_template_ciclo(
    win,
    template_name: str,
    timeout: float = 3.0,
    threshold: float = 0.68,
) -> bool:
    """Espera uma confirmacao visual durante uma transicao do ciclo."""
    template_path = resource_path(os.path.join("assets", template_name))
    deadline = time.time() + timeout
    while time.time() < deadline:
        check_stop()
        if localizar_imagem_cv2(template_path, win, threshold=threshold):
            return True
        smart_sleep(0.20)
    return False


def esperar_botoes_ciclo(win, offsets: dict[str, Any], mode: str, timeout: float = 4.0) -> bool:
    """Confirma que a lista esperada apareceu antes de mudar o modo interno."""
    detector = detectar_botoes_vender if mode == "sell" else detectar_botoes_pedido
    deadline = time.time() + timeout
    while time.time() < deadline:
        check_stop()
        botoes, _score, _template = detector(win, offsets)
        if botoes:
            return True
        smart_sleep(0.20)
    return False


def coletar_e_abrir_vendas(win, offsets: dict[str, Any]) -> bool:
    """Abre transacoes, coleta tudo e troca o mercado para a tela de venda."""
    for attempt in range(2):
        if not clicar_offset("cycle_counter_area", win, offsets):
            return False
        if esperar_template_ciclo(win, "btn_pegar_todos.png"):
            break
        if attempt == 0:
            print(" [CICLO] Transacoes nao confirmadas; repetindo a abertura...", flush=True)
    else:
        print(" [CICLO][PARADA SEGURA] A tela Transacoes Concluidas nao apareceu.", flush=True)
        return False

    if not clicar_offset("cycle_collect_all", win, offsets):
        return False
    print(" [CICLO] Aguardando 10 segundos para receber todos os itens...", flush=True)
    smart_sleep(10.0)

    for attempt in range(2):
        if not clicar_offset("cycle_sell_menu", win, offsets):
            return False
        if esperar_botoes_ciclo(win, offsets, "sell"):
            break
        if attempt == 0:
            print(" [CICLO] Tela de venda nao confirmada; repetindo a abertura...", flush=True)
    else:
        print(" [CICLO][PARADA SEGURA] A tela Vender do Inventario nao apareceu.", flush=True)
        return False

    print(" [CICLO] Coleta concluida e tela de venda confirmada.", flush=True)
    trocar_modo_controle("sell")
    return True


def abrir_ordens_de_compra(win, offsets: dict[str, Any]) -> bool:
    for attempt in range(2):
        if not clicar_offset("cycle_buy_menu", win, offsets):
            return False
        if esperar_botoes_ciclo(win, offsets, "buy"):
            break
        if attempt == 0:
            print(" [CICLO] Tela de compra nao confirmada; repetindo a abertura...", flush=True)
    else:
        print(" [CICLO][PARADA SEGURA] Criar Pedido de Compra nao apareceu.", flush=True)
        return False

    print(" [CICLO] Tela de compra confirmada. Retomando as ordens.", flush=True)
    trocar_modo_controle("buy")
    return True


def localizar_imagem_cv2(
    template_path: str,
    win,
    screen_gray=None,
    threshold: float = 0.75,
):
    template_original = get_template(template_path)
    if template_original is None:
        return None

    if screen_gray is None:
        geometry = get_client_geometry(win)
        screenshot = capture_region(
            region=(geometry.left, geometry.top, geometry.width, geometry.height)
        )
        screen_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_BGR2GRAY)

    melhor_val = -1.0
    melhor_loc = None
    melhor_escala = 1.0
    for escala in (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3):
        if escala == 1.0:
            template = template_original
        else:
            width = int(template_original.shape[1] * escala)
            height = int(template_original.shape[0] * escala)
            if width < 10 or height < 10:
                continue
            template = cv2.resize(
                template_original,
                (width, height),
                interpolation=cv2.INTER_AREA,
            )

        if template.shape[0] > screen_gray.shape[0] or template.shape[1] > screen_gray.shape[1]:
            continue
        result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > melhor_val:
            melhor_val = max_val
            melhor_loc = max_loc
            melhor_escala = escala

    if melhor_loc is not None and melhor_val >= threshold:
        geometry = get_client_geometry(win)
        width = int(template_original.shape[1] * melhor_escala)
        height = int(template_original.shape[0] * melhor_escala)
        return (
            geometry.left + melhor_loc[0] + width / 2,
            geometry.top + melhor_loc[1] + height / 2,
        )
    return None


def confirmar_sim(win, offsets: dict[str, Any]) -> bool:
    """Procura visualmente o botão SIM e usa btn_sim como fallback."""
    imagens_sim = (
        os.path.join("assets", "sim.png"),
        os.path.join("assets", "sim.png.png"),
        os.path.join("assets", "aviso_sim.png"),
    )

    for _ in range(5):
        check_stop()
        geometry = get_client_geometry(win)
        screenshot = capture_region(
            region=(geometry.left, geometry.top, geometry.width, geometry.height)
        )
        screen_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
        for image_path in imagens_sim:
            pos = localizar_imagem_cv2(image_path, win, screen_gray, threshold=0.6)
            if pos:
                safe_click(pos[0], pos[1], win)
                print(f" [V] Botão SIM ({os.path.basename(image_path)}) RECONHECIDO!", flush=True)
                return True
        smart_sleep(0.2)


    fallback = get_abs_pos(offsets.get("btn_sim"), win, offsets)
    fallback_visual = esperar_referencia_proxima_offset(
        win,
        offsets,
        "btn_sim",
        ("sim.png", "sim.png.png", "aviso_sim.png"),
        timeout=0.35,
        threshold=0.55,
    )
    if fallback and fallback_visual:
        print(
            f" [VISUAL] SIM confirmado perto da calibragem em "
            f"({int(fallback[0])}, {int(fallback[1])}).",
            flush=True,
        )
        return safe_click(fallback[0], fallback[1], win)
    print(
        " [COMPRA][PARADA SEGURA] Botao SIM nao confirmado; "
        "fallback de coordenada bloqueado.",
        flush=True,
    )
    return False


def cancelar_confirmacao_compra_se_aberta(win, offsets: dict[str, Any]) -> bool:
    """Cancela somente o diálogo confirmado visualmente por SIM + NÃO.

    Ausência simultânea dos dois botões significa que não há confirmação
    aberta. Qualquer estado parcial é ambíguo e exige intervenção manual.
    """
    sim_visivel = esperar_referencia_proxima_offset(
        win,
        offsets,
        "btn_sim",
        ("sim.png", "sim.png.png", "aviso_sim.png"),
        timeout=0.25,
        threshold=0.60,
    )
    nao_pos, nao_score, nao_name = localizar_referencia_na_area_offset(
        win,
        offsets,
        "btn_nao",
        ("aviso_nao.png",),
        threshold=0.72,
    )
    nao_disponivel = nao_score >= 0.0
    nao_visivel = nao_pos is not None

    if sim_visivel is False and nao_disponivel and not nao_visivel:
        return True
    if sim_visivel is not True or not nao_visivel:
        print(
            " [COMPRA][PARADA SEGURA] Diálogo de confirmação em estado "
            "ambíguo; nenhum cancelamento presumido foi executado.",
            flush=True,
        )
        return False

    if not safe_click(nao_pos[0], nao_pos[1], win):
        print(
            " [COMPRA][PARADA SEGURA] Clique visual no botão NÃO foi bloqueado.",
            flush=True,
        )
        return False
    print(
        f" [RECUPERAÇÃO] Botão NÃO ({nao_name}, confiança {nao_score:.2f}) "
        "reconhecido e acionado.",
        flush=True,
    )

    sim_sumiu = esperar_referencia_sumir(
        win,
        offsets,
        "btn_sim",
        ("sim.png", "sim.png.png", "aviso_sim.png"),
        timeout=1.0,
        threshold=0.60,
    )
    nao_sumiu = esperar_referencia_sumir(
        win,
        offsets,
        "btn_nao",
        ("aviso_nao.png",),
        timeout=0.5,
        threshold=0.72,
    )
    if sim_sumiu is True and nao_sumiu is True:
        print(" [RECUPERAÇÃO] Confirmação cancelada e fechada com segurança.", flush=True)
        return True
    print(
        " [COMPRA][PARADA SEGURA] O diálogo não desapareceu após clicar em NÃO.",
        flush=True,
    )
    return False


def recuperar_ou_parar_compra(win, offsets: dict[str, Any], reason: str) -> None:
    """Fecha uma confirmação visível; se não puder provar o fechamento, para."""
    if cancelar_confirmacao_compra_se_aberta(win, offsets):
        return
    solicitar_intervencao_manual(
        f"{reason} O botão NÃO não pôde ser confirmado e o bot foi parado."
    )


def garantir_modal_fechado(win, offsets: dict[str, Any]) -> bool:
    """Localiza e clica no X de um modal aberto próximo à âncora."""
    smart_sleep(0.08)
    geometry = get_client_geometry(win)
    anchor_point = resolve_point(offsets.get("ancora"), geometry, offsets)
    if not anchor_point:
        return True
    ax, ay = anchor_point
    region = (
        max(geometry.left, min(int(ax - 30), geometry.right - 60)),
        max(geometry.top, min(int(ay - 30), geometry.bottom - 60)),
        60,
        60,
    )
    screenshot = capture_region(region)
    screen_gray = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)

    for template_path in (
        "assets/fechar.png",
        "assets/fechar_btn.png",
        "assets/btn_fechar_modal.png",
    ):
        template = get_template(template_path)
        if template is None:
            continue
        for escala in (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3):
            resized = template
            if escala != 1.0:
                width = int(template.shape[1] * escala)
                height = int(template.shape[0] * escala)
                if width < 10 or height < 10:
                    continue
                resized = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
            if resized.shape[0] > screen_gray.shape[0] or resized.shape[1] > screen_gray.shape[1]:
                continue
            result = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, value, _, location = cv2.minMaxLoc(result)
            if value >= 0.82:
                pos = (
                    region[0] + location[0] + resized.shape[1] / 2,
                    region[1] + location[1] + resized.shape[0] / 2,
                )
                print(
                    " [!] Modal/Item ainda aberto; fechando por segurança "
                    "antes de analisar o próximo item...",
                    flush=True,
                )
                safe_click(pos[0], pos[1], win)
                smart_sleep(0.15)
                return False
    return True


def _tolerancia_ocr_preco(*valores: int) -> int:
    """Margem curta para variacoes de antialiasing, nunca maior que 50 prata."""
    maior = max((abs(int(value)) for value in valores if value), default=0)
    return max(2, min(50, round(maior * 0.001)))


def _escolher_preco_confirmado(
    readings: list[tuple[int, float]],
    esperado: int | None = None,
) -> tuple[int | None, str]:
    """Concilia duas leituras OCR próximas sem afrouxar os limites financeiros."""
    first, second = readings
    if esperado and esperado > 0:
        # O botão (+) torna o preço final conhecido antecipadamente. Uma leitura
        # exata basta; a outra transformação da mesma imagem pode conter ruído.
        exact = [item for item in readings if item[0] == esperado and item[1] >= 0.35]
        if exact:
            return esperado, ""

    if first[0] <= 0 or second[0] <= 0:
        return None, "preço final não reconhecido nas duas leituras"
    if max(first[1], second[1]) < 0.55:
        return None, (
            f"confiança insuficiente no preço final "
            f"({first[1]:.2f}/{second[1]:.2f})"
        )

    tolerance = _tolerancia_ocr_preco(first[0], second[0], esperado or 0)
    if abs(first[0] - second[0]) > tolerance:
        return None, (
            f"leituras divergentes do preço final ({first[0]} e {second[0]}; "
            f"tolerância {tolerance})"
        )

    if esperado and esperado > 0:
        selected = min(readings, key=lambda item: abs(item[0] - esperado))
    else:
        selected = max(readings, key=lambda item: item[1])
    if esperado and esperado > 0 and abs(selected[0] - esperado) > tolerance:
        return None, (
            f"preço final {selected[0]} não corresponde ao valor esperado "
            f"{esperado} (tolerância {tolerance})"
        )
    return selected[0], ""


def _ler_preco_compra_confirmacao(
    win,
    offsets: dict[str, Any],
    preco_esperado: int | None = None,
):
    """Faz duas leituras independentes do preço atual usando a mesma captura."""
    geometry = get_client_geometry(win)
    region = resolve_rect(offsets.get("preco_final_compra"), geometry, offsets)
    if not region:
        return None, "área do preço final no modal não calibrada"

    capture = capture_region(region)
    gray = cv2.cvtColor(np.array(capture), cv2.COLOR_RGB2GRAY)
    scaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
    _, thresholded = cv2.threshold(
        scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    readings = []
    ocr_started = time.perf_counter()
    for image in (scaled, thresholded):
        result = get_reader().readtext(
            image,
            detail=1,
            allowlist="0123456789., ",
            paragraph=False,
        )
        value = limpar_num(result)
        confidences = [
            float(item[2])
            for item in result
            if isinstance(item, (tuple, list)) and len(item) >= 3
        ]
        confidence = min(confidences) if confidences else 0.0
        readings.append((value, confidence))

    observe_performance(
        "ocr_purchase_confirmation",
        time.perf_counter() - ocr_started,
    )

    return _escolher_preco_confirmado(readings, preco_esperado)


def _confirmar_preco_final_compra(
    win,
    offsets: dict[str, Any],
    preco_esperado: int,
) -> tuple[int | None, str]:
    """Lê o preço final e faz uma única repetição rápida somente se necessário."""
    final_price, error = _ler_preco_compra_confirmacao(
        win, offsets, preco_esperado
    )
    if final_price is not None:
        return final_price, ""

    smart_sleep(0.2)
    retry_price, retry_error = _ler_preco_compra_confirmacao(
        win, offsets, preco_esperado
    )
    if retry_price is not None:
        print(" [COMPRA] Preço final confirmado na repetição rápida.", flush=True)
        return retry_price, ""
    return None, f"{error}; repetição: {retry_error}"


def definir_texto_area_transferencia(texto: str) -> bool:
    """Coloca texto na área de transferência do Windows via ctypes puro.

    Usado para colar (Ctrl+V) nomes de item na busca do mercado. Cola em vez
    de simular tecla por tecla porque nomes em portugues tem acentuacao
    (ç, ã, é...) que digitação de tecla por tecla nao reproduz de forma
    confiável, e evita uma dependencia externa de digitação nunca usada no
    motor de compra (ver test_purchase_motor_never_uses_escape_as_recovery).
    """
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    # Sem estes tipos, o ctypes assume c_int (32 bits) para os ponteiros/
    # handles retornados, truncando-os em Windows x64 e causando falha de
    # acesso silenciosa ao usá-los depois.
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        dados = texto.encode("utf-16le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dados))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            return False
        ctypes.memmove(ptr, dados, len(dados))
        kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            return False
        return True
    finally:
        user32.CloseClipboard()


def _ler_quantidade_pedido(
    win,
    offsets: dict[str, Any],
    quantidade_esperada: int | None = None,
) -> tuple[int | None, str]:
    """Lê o valor mostrado no controle Quantia do pedido de compra.

    Reaproveita _escolher_preco_confirmado: a lógica de reconciliar duas
    leituras OCR contra um valor esperado é a mesma para preço e quantidade.
    """
    geometry = get_client_geometry(win)
    region = resolve_rect(offsets.get("shopping_qtd_valor"), geometry, offsets)
    if not region:
        return None, "área da quantidade não calibrada"

    capture = capture_region(region)
    gray = cv2.cvtColor(np.array(capture), cv2.COLOR_RGB2GRAY)
    scaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
    _, thresholded = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    readings = []
    for image in (scaled, thresholded):
        result = get_reader().readtext(
            image, detail=1, allowlist="0123456789., ", paragraph=False
        )
        value = limpar_num(result)
        confidences = [
            float(item[2])
            for item in result
            if isinstance(item, (tuple, list)) and len(item) >= 3
        ]
        confidence = min(confidences) if confidences else 0.0
        readings.append((value, confidence))
    return _escolher_preco_confirmado(readings, quantidade_esperada)


def _ajustar_quantidade_pedido(
    win,
    offsets: dict[str, Any],
    quantidade_desejada: int,
) -> tuple[bool, str]:
    """Cola a quantidade desejada no campo Quantia (clique, apaga, cola).

    Clica no valor da Quantia, seleciona tudo e apaga antes de colar (evita
    concatenar com o valor anterior, ex.: "1" + "100" virando "1100"). Não
    precisa confirmar com Enter. Muito mais rápido do que clicar num botão
    (+) repetidamente para quantidades grandes (ex.: 100+).

    Não confirma o valor colado por OCR: esse campo tem elementos visuais
    (setas/indicadores) perto dos dígitos que atrapalham a leitura mesmo numa
    área bem calibrada. Quem confirma de fato é o preço final do pedido, lido
    depois já considerando preço × quantidade (ver
    executar_cliques_compra_programada) — se a quantidade não colou certo,
    esse total não bate e a compra é cancelada com segurança.
    """
    quantidade_desejada = max(1, int(quantidade_desejada))
    geometry = get_client_geometry(win)
    rect = resolve_rect(offsets.get("shopping_qtd_valor"), geometry, offsets)
    if not rect:
        return False, "área da quantidade não calibrada"
    centro_x = rect[0] + rect[2] / 2
    centro_y = rect[1] + rect[3] / 2
    # Ponto fora do retângulo lido por OCR do preço final mais adiante: depois
    # de clicar, o cursor fica parado exatamente em cima do número (é onde
    # clicamos), e o cursor do próprio jogo desenhado por cima dos dígitos
    # atrapalharia qualquer leitura naquela área. Tira o cursor dali.
    longe_x = centro_x
    longe_y = rect[1] + rect[3] + 30

    if not safe_click(centro_x, centro_y, win):
        return False, "clique no campo de quantidade foi bloqueado"
    smart_sleep(0.15)
    pyautogui.moveTo(longe_x, longe_y)
    smart_sleep(0.1)
    pyautogui.hotkey("ctrl", "a")
    smart_sleep(0.05)
    pyautogui.press("delete")
    smart_sleep(0.1)
    if not definir_texto_area_transferencia(str(quantidade_desejada)):
        return False, "não foi possível colocar a quantidade na área de transferência"
    pyautogui.hotkey("ctrl", "v")
    smart_sleep(0.3)
    return True, ""


def executar_cliques_compra_programada(
    win,
    offsets: dict[str, Any],
    preco_detectado: int,
    quantidade_desejada: int,
    valor_maximo_pedido: int = 0,
) -> tuple[bool, int | None, str]:
    """Cria um pedido de Compra Programada: Quantia -> MAIS(preço) -> CRIAR -> SIM.

    Deliberadamente NÃO chama validar_compra_financeira: a lista programada
    não respeita banca operacional nem lucro mínimo (decisão explícita do
    usuário). Em vez disso, valida o total do pedido (preço unitário ×
    quantidade + taxa de 2,5% sobre esse total) contra valor_maximo_pedido,
    se for maior que zero — 0 significa sem limite.

    O campo "Preço" no jogo mostra o preço POR UNIDADE (confirmado ao vivo:
    com Quantia=100, o campo Preço mostrou 2.361, a Taxa mostrou 5.902 e o
    Total 242.002 — só batem como 2.361×100 + 2,5% sobre esse total; o campo
    Preço em si não muda com a quantidade). Por isso a confirmação por OCR
    aqui compara contra o preço unitário esperado, não contra o total. O
    total (usado só para o limite de gasto e para os logs de estatística) é
    calculado à parte, multiplicando o preço unitário confirmado pela
    quantidade.

    Retorna (sucesso, preço_unitário_final_ou_None, motivo). motivo é "" no
    sucesso, "limite_excedido" quando bloqueado pelo teto configurado, ou uma
    descrição curta de outra falha.
    """
    quantidade_desejada = max(1, int(quantidade_desejada))
    preco_unitario_alvo = preco_detectado + 1
    total_estimado = preco_unitario_alvo * quantidade_desejada
    taxa_estimada = round(total_estimado * TAXA_PEDIDO_COMPRA_PERCENTUAL)
    if valor_maximo_pedido and (total_estimado + taxa_estimada) > valor_maximo_pedido:
        print(
            f" [COMPRA PROGRAMADA] Bloqueado: total estimado "
            f"{total_estimado + taxa_estimada} (preço {total_estimado} + taxa "
            f"{taxa_estimada}) excede o limite de {valor_maximo_pedido}.",
            flush=True,
        )
        return False, None, "limite_excedido"

    ajustou, erro_qtd = _ajustar_quantidade_pedido(win, offsets, quantidade_desejada)
    if not ajustou:
        print(f" [COMPRA PROGRAMADA] Cancelado: {erro_qtd}.", flush=True)
        recuperar_ou_parar_compra(
            win, offsets, "Falha ao ajustar a quantidade do pedido."
        )
        return False, None, "falha"

    if not clicar_offset("btn_mais", win, offsets):
        return False, None, "falha"
    smart_sleep(0.2)

    expected_final_price = preco_unitario_alvo
    final_price, validation_error = _confirmar_preco_final_compra(
        win, offsets, expected_final_price
    )
    if final_price is None:
        print(f" [COMPRA PROGRAMADA] Cancelado: {validation_error}.", flush=True)
        recuperar_ou_parar_compra(
            win, offsets, "Falha ao validar o preço final da compra."
        )
        return False, None, "falha"
    price_tolerance = _tolerancia_ocr_preco(final_price, expected_final_price)
    if abs(final_price - expected_final_price) > price_tolerance:
        print(
            f" [COMPRA PROGRAMADA] Cancelado: após o (+), esperava "
            f"{expected_final_price}, mas leu {final_price} "
            f"(tolerância OCR {price_tolerance}).",
            flush=True,
        )
        recuperar_ou_parar_compra(
            win, offsets, "O preço final divergiu do valor esperado."
        )
        return False, None, "falha"

    criar_visual = esperar_referencia_proxima_offset(
        win,
        offsets,
        "btn_criar",
        ("btn_pedido_compra.png",),
        timeout=0.35,
        threshold=0.55,
    )
    if criar_visual is False:
        print(
            " [COMPRA PROGRAMADA][PARADA SEGURA] O botão Criar não foi "
            "confirmado visualmente.",
            flush=True,
        )
        recuperar_ou_parar_compra(
            win, offsets, "O botão Criar não foi confirmado visualmente."
        )
        return False, None, "falha"

    if not clicar_offset("btn_criar", win, offsets):
        return False, None, "falha"
    smart_sleep(0.3)

    confirmou = confirmar_sim(win, offsets)
    if not confirmou:
        recuperar_ou_parar_compra(
            win, offsets, "O botão SIM não foi confirmado visualmente."
        )
        return False, None, "falha"
    confirmacao_fechou = esperar_referencia_sumir(
        win,
        offsets,
        "btn_sim",
        ("sim.png", "sim.png.png", "aviso_sim.png"),
        timeout=1.0,
        threshold=0.60,
    )
    if confirmacao_fechou is False:
        print(
            " [COMPRA PROGRAMADA][PARADA SEGURA] A confirmação continuou "
            "aberta depois do SIM.",
            flush=True,
        )
        recuperar_ou_parar_compra(
            win, offsets, "A confirmação continuou aberta depois do SIM."
        )
        return False, None, "falha"
    smart_sleep(0.10)
    return True, final_price, ""


def executar_cliques_compra(
    win,
    offsets: dict[str, Any],
    preco_detectado: int,
    preco_venda: int,
    lucro_minimo_percent: float,
    valor_max_prata: int,
    quantidade_desejada: int = 1,
) -> bool:
    """Executa [QUANTIA ->] MAIS -> CRIAR -> SIM.

    O fechamento do modal fica a cargo do loop principal. Centralizar essa
    etapa evita fechar o mercado duas vezes e mantém válidas as coordenadas
    dos próximos itens detectados na lista.

    quantidade_desejada > 1 (usado pelo modo Artefatos) ajusta o campo
    Quantia antes do "+" (mesmo mecanismo já usado pela Compra Programada,
    ver _ajustar_quantidade_pedido) e passa a validar o TOTAL do pedido
    (preço unitário × quantidade + taxa) contra o limite configurado, além
    da checagem unitária normal de validar_compra_financeira. Com o valor
    padrão (1), nenhum código novo executa -- comportamento idêntico ao de
    antes desta mudança para as demais categorias.
    """
    quantidade_desejada = max(1, int(quantidade_desejada))
    latest_offsets = carregar_offsets()
    try:
        latest_limit = int(latest_offsets.get("valor_max", 0))
    except (TypeError, ValueError):
        latest_limit = 0
    effective_limit = min(valor_max_prata, latest_limit) if latest_limit > 0 else 0
    allowed, reason = validar_compra_financeira(
        preco_detectado, preco_venda, lucro_minimo_percent, effective_limit
    )
    if not allowed:
        print(f" [BLOQUEIO FINANCEIRO] Compra cancelada: {reason}.", flush=True)
        return False

    if quantidade_desejada > 1:
        total_estimado = (preco_detectado + 1) * quantidade_desejada
        taxa_estimada = round(total_estimado * TAXA_PEDIDO_COMPRA_PERCENTUAL)
        if effective_limit and (total_estimado + taxa_estimada) > effective_limit:
            print(
                f" [BLOQUEIO FINANCEIRO] Compra cancelada: total estimado "
                f"{total_estimado + taxa_estimada} (preço {total_estimado} + "
                f"taxa {taxa_estimada}) para {quantidade_desejada} unidade(s) "
                f"excede o limite {effective_limit}.",
                flush=True,
            )
            return False
        ajustou, erro_qtd = _ajustar_quantidade_pedido(win, offsets, quantidade_desejada)
        if not ajustou:
            print(f" [BLOQUEIO FINANCEIRO] Compra cancelada: {erro_qtd}.", flush=True)
            recuperar_ou_parar_compra(
                win, offsets, "Falha ao ajustar a quantidade do pedido."
            )
            return False

    if not clicar_offset("btn_mais", win, offsets):
        return False
    smart_sleep(0.2)

    expected_final_price = preco_detectado + 1
    final_price, validation_error = _confirmar_preco_final_compra(
        win, offsets, expected_final_price
    )
    if final_price is None:
        print(
            f" [BLOQUEIO FINANCEIRO] Compra cancelada: {validation_error}.",
            flush=True,
        )
        recuperar_ou_parar_compra(
            win, offsets, "Falha ao validar o preço final da compra."
        )
        return False
    price_tolerance = _tolerancia_ocr_preco(final_price, expected_final_price)
    if abs(final_price - expected_final_price) > price_tolerance:
        print(
            f" [BLOQUEIO FINANCEIRO] Compra cancelada: após o (+), esperava "
            f"{expected_final_price}, mas leu {final_price} "
            f"(tolerância OCR {price_tolerance}).",
            flush=True,
        )
        recuperar_ou_parar_compra(
            win, offsets, "O preço final divergiu do valor esperado."
        )
        return False
    allowed, reason = validar_compra_financeira(
        final_price, preco_venda, lucro_minimo_percent, effective_limit
    )
    if not allowed:
        print(f" [BLOQUEIO FINANCEIRO] Compra cancelada: {reason}.", flush=True)
        recuperar_ou_parar_compra(
            win, offsets, "O preço final ultrapassou os limites financeiros."
        )
        return False
    if quantidade_desejada > 1:
        total_final = final_price * quantidade_desejada
        taxa_final = round(total_final * TAXA_PEDIDO_COMPRA_PERCENTUAL)
        if effective_limit and (total_final + taxa_final) > effective_limit:
            print(
                f" [BLOQUEIO FINANCEIRO] Compra cancelada: total confirmado "
                f"{total_final + taxa_final} (preço {total_final} + taxa "
                f"{taxa_final}) para {quantidade_desejada} unidade(s) excede "
                f"o limite {effective_limit}.",
                flush=True,
            )
            recuperar_ou_parar_compra(
                win, offsets, "O total do pedido excedeu o limite configurado."
            )
            return False

    criar_visual = esperar_referencia_proxima_offset(
        win,
        offsets,
        "btn_criar",
        ("btn_pedido_compra.png",),
        timeout=0.35,
        threshold=0.55,
    )
    if criar_visual is False:
        print(
            " [COMPRA][PARADA SEGURA] O preco foi lido, mas o botao Criar "
            "nao foi confirmado visualmente.",
            flush=True,
        )
        recuperar_ou_parar_compra(
            win, offsets, "O botão Criar não foi confirmado visualmente."
        )
        return False

    if not clicar_offset("btn_criar", win, offsets):
        return False
    smart_sleep(0.3)

    confirmou = confirmar_sim(win, offsets)
    if not confirmou:
        recuperar_ou_parar_compra(
            win, offsets, "O botão SIM não foi confirmado visualmente."
        )
        return False
    confirmacao_fechou = esperar_referencia_sumir(
        win,
        offsets,
        "btn_sim",
        ("sim.png", "sim.png.png", "aviso_sim.png"),
        timeout=1.0,
        threshold=0.60,
    )
    if confirmacao_fechou is False:
        print(
            " [COMPRA][PARADA SEGURA] A confirmacao continuou aberta depois do SIM.",
            flush=True,
        )
        recuperar_ou_parar_compra(
            win, offsets, "A confirmação continuou aberta depois do SIM."
        )
        return False
    smart_sleep(0.10)
    return True

def main():
    performance_path = start_performance_telemetry(logs_dir())
    print(f">>> Log de desempenho: {performance_path}", flush=True)

    def warmup():
        started = time.perf_counter()
        try:
            get_reader()
        except Exception:
            pass
        finally:
            observe_performance("ocr_startup", time.perf_counter() - started)

    threading.Thread(target=warmup, daemon=True).start()
    print("\n>>> MOTOR ELITE PRONTO!", flush=True)

    def pausar_controle():
        with open(CONTROL_FILE, "w", encoding="utf-8") as arquivo:
            json.dump({"run": False, "mode": "buy"}, arquivo)

    def reverter_lista_compras_se_nao_pausado(status_inicial_lista, lista_concluida):
        if lista_concluida or controle_deve_preservar_posicao():
            return
        lista_final = carregar_lista_compras()
        revertidos = reverter_progresso_nao_pausado(status_inicial_lista, lista_final)
        if revertidos:
            salvar_lista_compras(lista_final)
            print(
                f" [COMPRA PROGRAMADA] Interrompido sem pausa; "
                f"{revertidos} item(ns) voltaram para PENDENTE.",
                flush=True,
            )

    standby_logged = False
    execucao_ativa = False
    gasto_sessao = 0
    itens_bloqueados_ate: dict[tuple[str, int, int], float] = {}
    cycle_resume_state: dict[str, Any] | None = None
    protected_pause_scheduler = ProtectedPauseScheduler()
    while True:
        run_status, mode = check_control()
        if run_status:
            if not execucao_ativa:
                gasto_sessao = 0
                itens_bloqueados_ate = {}
                cycle_resume_state = None
                try:
                    initial_settings = carregar_offsets()
                except Exception:
                    initial_settings = {}
                protected_pause_scheduler.reset(
                    bool(initial_settings.get(PROTECTED_PAUSE_ENABLED_KEY, False))
                )
                execucao_ativa = True
            standby_logged = False
            print(f"\n>>> BOT INICIADO! MODO: {mode.upper()}", flush=True)
            try:
                if mode in ("buy", "artefatos"):
                    is_artefatos_mode = mode == "artefatos"
                    if cycle_resume_state is not None and not controle_deve_preservar_posicao():
                        # Havia posicao salva de uma pausa anterior, mas o pedido mais
                        # recente foi um PARAR (nao uma pausa); descarta e reinicia.
                        cycle_resume_state = None
                    resume_pending = cycle_resume_state is not None
                    saved_state = cycle_resume_state or {}
                    itens_total = int(saved_state.get("items_total", 0) or 0)
                    cat_idx = int(saved_state.get("category_index", 0) or 0)
                    scrolls_sem_itens = 0
                    primeiro_ciclo = not resume_pending
                    categorias_sem_reconhecimento = 0
                    last_counter_check = 0.0
                    current_page = int(saved_state.get("page", 1) or 1)
                    scroll_batches = int(saved_state.get("scroll_batches", 0) or 0)
                    current_category_key = saved_state.get("category_key")
                    current_category_label = saved_state.get("category_label")
                    seen_row_signatures = list(
                        saved_state.get("seen_row_signatures", []) or []
                    )
                    seen_semantic_rows = set(
                        saved_state.get("seen_semantic_rows", []) or []
                    )
                    pending_scroll_signatures: list[
                        tuple[bytes, bytes, bytes]
                    ] | None = None
                    prefetched_detection = None

                    def resolver_estado_ciclo_ao_parar():
                        """Decide, ao parar, se guarda a posição (pausa) ou descarta (PARAR).

                        Chamada tanto na saída graciosa do loop quanto nos handlers de
                        exceção mais abaixo: check_stop() pode disparar
                        BotStoppedException no meio do processamento de um item (via
                        smart_sleep), pulando o topo do loop onde essa checagem
                        normalmente aconteceria -- sem isso, uma pausa no meio de um
                        item perdia a posição salva e a próxima retomada recomeçava do
                        zero, como se tivesse sido um PARAR.
                        """
                        if controle_deve_preservar_posicao():
                            print(
                                " [PAUSA] Posição salva "
                                f"({current_category_label or 'sem categoria'}, "
                                f"página {current_page}). Continue para retomar dali.",
                                flush=True,
                            )
                            return {
                                "category_index": cat_idx,
                                "category_key": current_category_key,
                                "category_label": current_category_label,
                                "page": current_page,
                                "scroll_batches": scroll_batches,
                                "items_total": itens_total,
                                "seen_row_signatures": list(seen_row_signatures),
                                "seen_semantic_rows": list(seen_semantic_rows),
                            }
                        return None

                    while True:
                        run_m, m_mode = check_control()
                        if not run_m:
                            cycle_resume_state = resolver_estado_ciclo_ao_parar()
                            break
                        if m_mode != mode:
                            break
                        check_stop()
                        offsets = carregar_offsets()
                        protected_pause_checkpoint(protected_pause_scheduler, offsets)
                        banca_operacional = int(offsets.get("banca_operacional", 0) or 0)
                        if banca_operacional > 0 and gasto_sessao >= banca_operacional:
                            print(
                                f" [ORÇAMENTO] Banca operacional de {banca_operacional} prata "
                                "foi comprometida nesta execução. Bot pausado.",
                                flush=True,
                            )
                            pausar_controle()
                            break
                        win = get_albion_window()
                        if not win:

                            smart_sleep(1)
                            continue
                        geometry = get_client_geometry(win)
                        calibration_ok, calibration_reason = validate_calibration(offsets, geometry, mode=mode)
                        if not calibration_ok:
                            print(f" [!] Calibragem bloqueada: {calibration_reason}", flush=True)
                            pausar_controle()
                            break
                        store_region = resolve_rect(offsets.get("area_lista"), geometry, offsets)
                        visible, visibility_reason = ensure_game_region_visible(win, store_region)
                        if not visible:
                            print(f" [!] Operação bloqueada: {visibility_reason}", flush=True)
                            pausar_controle()
                            break

                        if (
                            not resume_pending
                            and pending_scroll_signatures is None
                            and auto_cycle_enabled()
                            and time.time() - last_counter_check >= 2.0
                        ):
                            last_counter_check = time.time()
                            cycle_limit = get_cycle_order_limit(offsets)
                            contador, contador_raw = ler_contador_transacoes(win, offsets)
                            if contador is not None:
                                print(
                                    f" [CICLO] Transações concluídas: {contador} "
                                    f"(OCR: {contador_raw}).",
                                    flush=True,
                                )
                            if contador is not None and contador >= cycle_limit:
                                confirmado, segunda, segunda_raw = confirmar_limite_contador(
                                    win, offsets, contador, cycle_limit
                                )
                                if not confirmado:
                                    print(
                                        f" [CICLO] Leitura descartada: primeira={contador}, "
                                        f"segunda={segunda}, OCR={segunda_raw or 'vazio'}.",
                                        flush=True,
                                    )
                                else:
                                    pagina_ok, pagina_lida, pagina_raw = confirmar_pagina_compra(
                                        win, offsets, current_page
                                    )
                                    if not current_category_key or not pagina_ok:
                                        print(
                                            f" [CICLO][PARADA SEGURA] Nao foi possivel salvar "
                                            f"a navegacao: pagina esperada={current_page}, "
                                            f"lida={pagina_lida}, OCR={pagina_raw}. Configure a "
                                            "area do numero da pagina e use categorias automaticas.",
                                            flush=True,
                                        )
                                        pausar_controle()
                                        break
                                    cycle_resume_state = {
                                        "category_index": cat_idx,
                                        "category_key": current_category_key,
                                        "category_label": current_category_label,
                                        "page": current_page,
                                        "scroll_batches": scroll_batches,
                                        "items_total": itens_total,
                                        "seen_row_signatures": list(seen_row_signatures),
                                        "seen_semantic_rows": list(seen_semantic_rows),
                                    }
                                    print(
                                        f" [CICLO] Limite {cycle_limit} confirmado em duas leituras "
                                        f"({contador}). Posicao salva em "
                                        f"{current_category_label}, pagina {current_page}. "
                                        "Coletando e abrindo vendas...",
                                        flush=True,
                                    )
                                    garantir_modal_fechado(win, offsets)
                                    if not coletar_e_abrir_vendas(win, offsets):
                                        print(" [!] Falha ao iniciar o ciclo de vendas.", flush=True)
                                        cycle_resume_state = None
                                        pausar_controle()
                                    break

                        if is_artefatos_mode:
                            cat_ativo = True
                            active_targets = ARTEFATO_CATEGORY_TARGETS
                        else:
                            cat_ativo = offsets.get("cat_ativo", False)
                            cat_sequence = offsets.get("cat_sequence", [])
                            cat_enabled = offsets.get("cat_enabled", {})
                            cat_keys = CATEGORIA_CLIQUE_KEYS
                            active_targets = build_active_category_targets(
                                cat_sequence,
                                cat_enabled,
                                cat_keys,
                            )

                        if cat_ativo and not active_targets:
                            print(
                                " [!] Nenhuma categoria está marcada. "
                                "Selecione ao menos uma categoria na tela CATEGORIAS.",
                                flush=True,
                            )
                            pausar_controle()
                            break

                        if resume_pending:
                            saved_category_key = saved_state.get("category_key")
                            restored_index = next(
                                (
                                    index
                                    for index, target in enumerate(active_targets)
                                    if target["key"] == saved_category_key
                                ),
                                None,
                            )
                            if restored_index is None:
                                print(
                                    " [CICLO][PARADA SEGURA] A categoria salva nao esta mais ativa.",
                                    flush=True,
                                )
                                cycle_resume_state = None
                                pausar_controle()
                                break
                            cat_idx = restored_index
                            if not restaurar_navegacao_compra(
                                win, offsets, saved_state
                            ):
                                cycle_resume_state = None
                                pausar_controle()
                                break
                            resume_pending = False
                            cycle_resume_state = None
                            last_counter_check = time.time()

                        if primeiro_ciclo and cat_ativo and active_targets:
                            primeiro_ciclo = False
                            target = active_targets[cat_idx]
                            print(
                                f" [>>>] Iniciando com: {target['label']}",
                                flush=True,
                            )
                            if not executar_troca_categoria(win, offsets, target["key"]):
                                print(
                                    " [!] A categoria inicial não pôde ser selecionada. "
                                    "O bot foi pausado para não operar na tela anterior.",
                                    flush=True,
                                )
                                pausar_controle()
                                break
                            current_category_key = target["key"]
                            current_category_label = target["label"]
                            current_page = 1
                            scroll_batches = 0
                            seen_row_signatures = []
                            seen_semantic_rows = set()
                            pending_scroll_signatures = None
                            prefetched_detection = None
                            offsets = carregar_offsets()

                        garantir_modal_fechado(win, offsets)
                        try:
                            if prefetched_detection is not None:
                                (
                                    botoes,
                                    melhor_score,
                                    template_usado,
                                    row_signatures,
                                ) = prefetched_detection
                                prefetched_detection = None
                            else:
                                detection_started = time.perf_counter()
                                (
                                    botoes,
                                    melhor_score,
                                    template_usado,
                                    row_signatures,
                                ) = detectar_botoes_pedido(
                                    win, offsets, incluir_assinaturas=True
                                )
                                observe_performance(
                                    "purchase_button_detection",
                                    time.perf_counter() - detection_started,
                                )
                        except Exception as e:
                            print(f" [!] Erro na detecção dos pedidos: {e}", flush=True)
                            botoes, melhor_score, template_usado, row_signatures = (
                                [],
                                -1.0,
                                "erro",
                                [],
                            )

                        if pending_scroll_signatures is not None and botoes:
                            previous_signatures = pending_scroll_signatures
                            pending_scroll_signatures = None
                            if conjuntos_assinaturas_equivalentes(
                                previous_signatures, row_signatures
                            ):
                                print(
                                    " [>>>] Fim real da página confirmado: "
                                    "a lista não se moveu.",
                                    flush=True,
                                )
                                if cat_ativo and active_targets and tem_mais_paginas(
                                    win, offsets
                                ):
                                    if not clicar_proxima_pagina(win, offsets):
                                        print(
                                            " [CICLO][PARADA SEGURA] Não foi possível "
                                            "abrir a próxima página e retornar ao topo.",
                                            flush=True,
                                        )
                                        pausar_controle()
                                        break
                                    current_page += 1
                                    itens_total = 0
                                    scroll_batches = 0
                                    scrolls_sem_itens = 0
                                    seen_row_signatures = []
                                    seen_semantic_rows = set()
                                    prefetched_detection = None
                                    continue

                                if cat_ativo and len(active_targets) > 1:
                                    cat_idx = (cat_idx + 1) % len(active_targets)
                                    target = active_targets[cat_idx]
                                    if not executar_troca_categoria(
                                        win, offsets, target["key"]
                                    ):
                                        print(
                                            " [!] A próxima categoria não pôde ser selecionada.",
                                            flush=True,
                                        )
                                        pausar_controle()
                                        break
                                    current_category_key = target["key"]
                                    current_category_label = target["label"]
                                    current_page = 1
                                    itens_total = 0
                                    scroll_batches = 0
                                    scrolls_sem_itens = 0
                                    seen_row_signatures = []
                                    seen_semantic_rows = set()
                                    prefetched_detection = None
                                    continue

                                print(
                                    " [>>>] Última página da categoria atingida. "
                                    "Bot pausado para não repetir ordens.",
                                    flush=True,
                                )
                                pausar_controle()
                                break

                            # A captura feita para confirmar o movimento será
                            # reutilizada no próximo ciclo. Assim o contador do
                            # Ciclo pode ser verificado sem uma segunda captura.
                            scroll_batches += 1
                            prefetched_detection = (
                                botoes,
                                melhor_score,
                                template_usado,
                                row_signatures,
                            )
                            continue

                        if not botoes:
                            pending_scroll_signatures = None
                            print(
                                f" [DBG] Pedido não reconhecido; melhor score={melhor_score:.3f} "
                                f"({template_usado}).",
                                flush=True,
                            )

                        if not botoes:
                            print(" [!] Nenhum item encontrado na área. Verificando se há um item/modal aberto...", flush=True)
                            if not garantir_modal_fechado(win, offsets):
                                print(" [!] Modal aberto detectado e fechado com sucesso! Retomando processo...", flush=True)
                                scrolls_sem_itens = 0
                                smart_sleep(0.5)
                                continue
                            print(" [!] Nenhum modal aberto detectado. Arrastando...", flush=True)
                            scrolls_sem_itens += 1
                            if scrolls_sem_itens >= 3:
                                if cat_ativo and active_targets:
                                    if itens_total > 0 and tem_mais_paginas(win, offsets):
                                        print(" [>>>] Fim dos itens detectado. Passando de página via setinha amarela...", flush=True)
                                        if not clicar_proxima_pagina(win, offsets):
                                            print(
                                                " [COMPRA][PARADA SEGURA] Falha ao abrir "
                                                "a próxima página e retornar ao topo.",
                                                flush=True,
                                            )
                                            pausar_controle()
                                            break
                                        current_page += 1
                                        scroll_batches = 0
                                        seen_row_signatures = []
                                        seen_semantic_rows = set()
                                        itens_total = 0
                                        scrolls_sem_itens = 0
                                        continue
                                    if itens_total == 0:
                                        categorias_sem_reconhecimento += 1
                                    else:
                                        categorias_sem_reconhecimento = 0
                                    if len(active_targets) == 1 or categorias_sem_reconhecimento >= len(active_targets):
                                        print(
                                            " [!] Nenhum botão Pedido foi reconhecido em um ciclo completo. "
                                            "Refaça AMOSTRA BOTÃO PEDIDO e ÁREA DA LISTA. O bot foi pausado "
                                            "para evitar um loop de cliques.",
                                            flush=True,
                                        )
                                        pausar_controle()
                                        break
                                    print(" [>>>] Fim da categoria atingido (setinha apagada/indisponível)!", flush=True)
                                    cat_idx = (cat_idx + 1) % len(active_targets)
                                    target = active_targets[cat_idx]
                                    if not executar_troca_categoria(
                                        win, offsets, target["key"]
                                    ):
                                        print(
                                            " [!] A próxima categoria não pôde ser selecionada. "
                                            "O bot foi pausado para não operar na tela anterior.",
                                            flush=True,
                                        )
                                        pausar_controle()
                                        break
                                    current_category_key = target["key"]
                                    current_category_label = target["label"]
                                    current_page = 1
                                    scroll_batches = 0
                                    itens_total = 0
                                    scrolls_sem_itens = 0
                                    seen_row_signatures = []
                                    seen_semantic_rows = set()
                                    continue
                                print(" [!] Fim da página atingido e troca automática inativa. Parando bot...", flush=True)
                                pausar_controle()
                                break
                            if realizar_scroll(offsets, win):
                                scroll_batches += 1
                                smart_sleep(0.3)
                            continue

                        scrolls_sem_itens = 0
                        categorias_sem_reconhecimento = 0
                        if len(row_signatures) != len(botoes):
                            print(
                                " [COMPRA][PARADA SEGURA] A identificação das linhas "
                                "ficou incompleta; nenhum item será clicado.",
                                flush=True,
                            )
                            pausar_controle()
                            break

                        new_rows, repeated_rows = filtrar_linhas_novas(
                            botoes,
                            row_signatures,
                            seen_row_signatures,
                        )
                        if not new_rows:
                            print(
                                " [COMPRA][PARADA SEGURA] A lista mudou, mas todas as "
                                "linhas já haviam sido vistas. Operação pausada para "
                                "não repetir ordens.",
                                flush=True,
                            )
                            pausar_controle()
                            break
                        if repeated_rows:
                            print(
                                f" [COMPRA] {repeated_rows} linha(s) sobreposta(s) "
                                "ignorada(s) sem novo OCR.",
                                flush=True,
                            )

                        for b, row_signature in new_rows:
                            run_m, m_mode = check_control()
                            if not run_m or m_mode != mode:
                                break
                            seen_row_signatures.append(row_signature)
                            itens_total += 1
                            progresso_pagina = (itens_total - 1) % 50 + 1
                            clicar_centro_bbox(b, win)
                            smart_sleep(0.4)
                            geometry = get_client_geometry(win)
                            o_n = resolve_rect(offsets.get("nome"), geometry, offsets)
                            o_v = resolve_rect(offsets.get("venda"), geometry, offsets)
                            o_c = resolve_rect(offsets.get("compra"), geometry, offsets)
                            if not (o_n and o_v and o_c):
                                print(" [!] Áreas de OCR inválidas; refaça a calibragem.", flush=True)
                                pausar_controle()
                                break

                            def ler_tudo_rapido(regs_dict):
                                """Lê múltiplas regiões com APENAS UM print da tela (ULTRA RÁPIDO)."""
                                ocr_started = time.perf_counter()
                                min_x = min(r[0] for r in regs_dict.values())
                                min_y = min(r[1] for r in regs_dict.values())
                                max_x = max(r[0] + r[2] for r in regs_dict.values())
                                max_y = max(r[1] + r[3] for r in regs_dict.values())
                                smart_sleep(0.2)
                                cap = capture_region((min_x, min_y, max_x - min_x, max_y - min_y))
                                big_img_gray = cv2.cvtColor(np.array(cap), cv2.COLOR_RGB2GRAY)
                                resultados = {}
                                for key, reg in regs_dict.items():
                                    y_rel, x_rel = reg[1] - min_y, reg[0] - min_x
                                    crop = big_img_gray[y_rel:y_rel + reg[3], x_rel:x_rel + reg[2]]
                                    scaled = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
                                    _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                                    resultados[key] = get_reader().readtext(thresh, detail=0)
                                observe_performance(
                                    "ocr_purchase_item",
                                    time.perf_counter() - ocr_started,
                                )
                                return resultados

                            dados = ler_tudo_rapido({"nome": o_n, "venda": o_v, "compra": o_c})
                            nome_raw, venda_raw, compra_raw = dados["nome"], dados["venda"], dados["compra"]
                            nome = " ".join(nome_raw).strip() or "Item"
                            nome_sem_encantamento = nome
                            encantamento = ""
                            encantamento_diag: dict[str, Any] = {
                                "value": "",
                                "status": "region_missing",
                                "neon_pixels": 0,
                                "scores": {".1": 0, ".2": 0, ".3": 0, ".4": 0},
                            }
                            notification_icon = None
                            o_i = resolve_rect(offsets.get("icone"), geometry, offsets)
                            if o_i:
                                try:
                                    cap_icon = capture_region(o_i)
                                    notification_icon = cap_icon.copy()
                                    encantamento, encantamento_diag = analisar_encantamento_icone(
                                        cap_icon
                                    )
                                    if encantamento_diag.get("status") == "error":
                                        print(
                                            " [!] Erro ao detectar encantamento: "
                                            f"{encantamento_diag.get('error_type', 'erro desconhecido')}",
                                            flush=True,
                                        )
                                except Exception as e:
                                    print(f" [!] Erro ao detectar encantamento: {e}", flush=True)
                                    encantamento = ""
                                    encantamento_diag = {
                                        "value": "",
                                        "status": "capture_error",
                                        "error_type": type(e).__name__,
                                    }
                            if encantamento:
                                nome = f"{nome} {encantamento}"

                            pv, pc = limpar_num(venda_raw), limpar_num(compra_raw)
                            semantic_key = criar_chave_semantica_linha(
                                nome,
                                pv,
                                pc,
                                row_signature,
                            )
                            if semantic_key in seen_semantic_rows:
                                itens_total = max(0, itens_total - 1)
                                print(
                                    " [COMPRA] Linha repetida confirmada pelos dados "
                                    "já lidos; nenhuma ordem será criada.",
                                    flush=True,
                                )
                                anchor_point = resolve_point(
                                    offsets.get("ancora"),
                                    get_client_geometry(win),
                                    offsets,
                                )
                                if anchor_point:
                                    safe_click(anchor_point[0], anchor_point[1], win)
                                garantir_modal_fechado(win, offsets)
                                continue
                            seen_semantic_rows.add(semantic_key)

                            cost_pct = round((pc / pv) * 100, 1) if pv > 0 else 0
                            lucro_minimo_percent = ler_lucro_minimo_config(offsets)
                            valor_max_prata = int(offsets.get("valor_max", 1_000_000))
                            valor_max_prata = calcular_limite_disponivel_sessao(
                                valor_max_prata, banca_operacional, gasto_sessao
                            )
                            compra_valida, motivo_bloqueio = validar_compra_financeira(
                                pc, pv, lucro_minimo_percent, valor_max_prata
                            )
                            chave_item = (nome, pv, pc)
                            if item_em_cooldown(itens_bloqueados_ate, chave_item):
                                compra_valida = False
                                motivo_bloqueio = (
                                    "item temporariamente ignorado após falha na confirmação final"
                                )
                            pedido_proprio_no_topo, brilho_linha_topo = linha_pedido_e_minha(offsets, win)
                            if pedido_proprio_no_topo:
                                compra_valida = False
                                motivo_bloqueio = (
                                    "pedido de compra no topo já é meu (cor da linha, "
                                    f"brilho={brilho_linha_topo:.1f}); nenhum novo pedido necessário"
                                )
                            if compra_valida and bool(offsets.get(VERIFICAR_MEDIA_SEMANAL_KEY, False)):
                                media_ok, media_motivo = media_semanal_disponivel(win, offsets)
                                if media_ok is None:
                                    print(
                                        f" [!] Verificação de média semanal bloqueada: "
                                        f"{media_motivo}.",
                                        flush=True,
                                    )
                                    pausar_controle()
                                    break
                                if not media_ok:
                                    compra_valida = False
                                    motivo_bloqueio = media_motivo
                            tier_valido = True
                            tier_item = detectar_tier_nome(nome)
                            tier_motivo = "filtro de tier inativo"
                            compra_valida = compra_valida and tier_valido
                            if not tier_valido:
                                motivo_bloqueio = tier_motivo
                            if tier_item is None:
                                tier_source = "unrecognized"
                            elif detectar_tier_nome(nome_sem_encantamento) is not None:
                                tier_source = "name"
                            elif "icone" in tier_motivo:
                                tier_source = "icon"
                            else:
                                tier_source = "unknown"
                            dentro_da_porcentagem = (
                                pv > 0 and pc <= pv * (1 - lucro_minimo_percent / 100)
                            )
                            dentro_do_limite_prata = 0 < pc <= valor_max_prata
                            eh_oportunidade = int(compra_valida)
                            nome_tokens_log = _ocr_tokens_for_log(nome_raw)
                            venda_tokens_log = _ocr_tokens_for_log(venda_raw)
                            compra_tokens_log = _ocr_tokens_for_log(compra_raw)
                            ocr_diagnostic = {
                                "schema": 1,
                                "sequence": {
                                    "overall": int(itens_total),
                                    "page_slot": int(progresso_pagina),
                                },
                                "navigation": {
                                    "category": str(
                                        active_targets[cat_idx].get("category", "")
                                    ) if cat_ativo and active_targets else "",
                                    "subtype": "",
                                },
                                "name": {
                                    "raw": nome_tokens_log,
                                    "parsed": nome_sem_encantamento,
                                },
                                "tier": {
                                    "value": int(tier_item) if tier_item is not None else None,
                                    "source": tier_source,
                                    "reason": tier_motivo,
                                },
                                "enchantment": encantamento_diag,
                                "prices": {
                                    "sale_raw": venda_tokens_log,
                                    "sale_status": _price_read_status(venda_tokens_log, pv),
                                    "buy_raw": compra_tokens_log,
                                    "buy_status": _price_read_status(compra_tokens_log, pc),
                                    "sale": int(pv),
                                    "buy": int(pc),
                                },
                                "evaluation": {
                                    "approved": bool(eh_oportunidade),
                                    "reason": motivo_bloqueio,
                                    "cost_percent": float(cost_pct),
                                    "minimum_profit_percent": float(lucro_minimo_percent),
                                    "available_order_limit": int(valor_max_prata),
                                    "own_order_still_top": bool(pedido_proprio_no_topo),
                                    "own_order_row_brightness": brilho_linha_topo,
                                },
                            }
                            print(
                                "[OCR_DIAG] "
                                + json.dumps(
                                    ocr_diagnostic,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                                flush=True,
                            )
                            print(f"[DATA] {nome}|{pv}|{pc}|{cost_pct}%|{eh_oportunidade}", flush=True)
                            tier_log = f"T{tier_item}" if tier_item else "T?"
                            print(f" [#{progresso_pagina}/50] Item: {nome} | Tier: {tier_log} | Venda: {pv} | Compra: {pc} | Custo: {cost_pct}%", flush=True)

                            if eh_oportunidade:
                                # Só o modo Artefatos cria pedidos com mais de 1 unidade;
                                # com 1, todas as contas abaixo ficam idênticas às de antes.
                                quantidade_pedido = (
                                    ler_quantidade_artefatos(offsets) if is_artefatos_mode else 1
                                )
                                lucro_estimado = (pv * 0.93 - pc) * quantidade_pedido
                                if item_icon_prefetch_callback is not None:
                                    try:
                                        item_icon_prefetch_callback(nome, notification_icon)
                                    except Exception:
                                        # O cache visual jamais pode interferir na compra.
                                        pass
                                print(f" [$$] DENTRO DOS PARÂMETROS (lucro mínimo {lucro_minimo_percent}% e {valor_max_prata} Prata)! COMPRANDO...", flush=True)
                                comprou = executar_cliques_compra(
                                    win,
                                    offsets,
                                    pc,
                                    pv,
                                    lucro_minimo_percent,
                                    valor_max_prata,
                                    quantidade_pedido,
                                )
                                if comprou:
                                    gasto_sessao += (pc + 1) * quantidade_pedido
                                    itens_bloqueados_ate.pop(chave_item, None)
                                    if banca_operacional > 0:
                                        print(
                                            f" [ORÇAMENTO] Comprometido nesta execução: "
                                            f"{gasto_sessao}/{banca_operacional} prata.",
                                            flush=True,
                                        )
                                    print(f"[BUY] {lucro_estimado}", flush=True)
                                    # Linha aditiva para o relatorio da sessao; nao faz parte
                                    # do contrato [BUY] existente e pode ser ignorada por quem
                                    # nao a reconhece.
                                    print(
                                        "[BUY_DETAIL] "
                                        + json.dumps(
                                            {
                                                "nome": nome_sem_encantamento,
                                                "tier": tier_item,
                                                "encantamento": encantamento,
                                                "venda": pv,
                                                "compra": pc,
                                                "preco_pedido": (pc + 1) * quantidade_pedido,
                                                "taxa_pedido": round(
                                                    (pc + 1)
                                                    * quantidade_pedido
                                                    * TAXA_PEDIDO_COMPRA_PERCENTUAL
                                                ),
                                                "lucro_estimado": lucro_estimado,
                                                "quantidade": quantidade_pedido,
                                            },
                                            ensure_ascii=False,
                                            separators=(",", ":"),
                                        ),
                                        flush=True,
                                    )
                                    if buy_callback is not None:
                                        try:
                                            buy_callback(nome, lucro_estimado, notification_icon)
                                        except Exception as e:
                                            print(f" [!] Erro no buy_callback: {e}", flush=True)
                                else:
                                    itens_bloqueados_ate[chave_item] = time.monotonic() + 600.0
                                    print(
                                        " [SEGURANÇA] Item ignorado por 10 minutos após falha "
                                        "na confirmação da compra.",
                                        flush=True,
                                    )
                            else:
                                print(f" [!] Pulando: {motivo_bloqueio}.", flush=True)

                            # No caminho de compra, garantir_modal_fechado()
                            # deve ser a unica etapa de fechamento. Nenhuma tecla
                            # de fechamento e permitida durante a automacao.
                            if not eh_oportunidade:
                                anchor_point = resolve_point(offsets.get("ancora"), get_client_geometry(win), offsets)
                                if anchor_point:
                                    safe_click(anchor_point[0], anchor_point[1], win)
                                else:
                                    solicitar_intervencao_manual(
                                        "A âncora visual para fechar o item ficou indisponível; "
                                        "nenhuma tecla ou clique presumido foi enviado."
                                    )
                            garantir_modal_fechado(win, offsets)
                            smart_sleep(0.01)

                        if itens_total > 60:
                            print(
                                " [COMPRA][PARADA SEGURA] Mais de 60 linhas únicas "
                                "foram identificadas na mesma página. Operação pausada "
                                "para evitar paginação incorreta.",
                                flush=True,
                            )
                            pausar_controle()
                            break

                        # Depois de processar os botoes que estavam visiveis,
                        # desloca a lista para revelar o proximo lote. Sem este
                        # passo, o ciclo detectava e processava os mesmos botoes
                        # repetidamente e realizar_scroll() so era chamado quando
                        # nenhum botao era encontrado.
                        print(" [>>>] Lote processado. Descendo a lista...", flush=True)
                        pending_scroll_signatures = list(row_signatures)
                        if realizar_scroll(offsets, win):
                            smart_sleep(0.3)
                            continue

                        pending_scroll_signatures = None
                        print(
                            " [!] Scroll nao calibrado: verifique drag_start e drag_end.",
                            flush=True,
                        )
                        smart_sleep(0.3)

                elif mode == "sell":
                    print(">>> MODO DE VENDA ATIVADO", flush=True)
                    sell_index = 0
                    no_buttons_cycles = 0
                    while True:
                        run_m, m_mode = check_control()
                        if not run_m or m_mode != "sell":
                            break
                        check_stop()
                        win = get_albion_window()
                        if not win:
                            smart_sleep(1.0)
                            continue
                        offsets = carregar_offsets()
                        protected_pause_checkpoint(protected_pause_scheduler, offsets)
                        geometry = get_client_geometry(win)
                        calibration_ok, calibration_reason = validate_calibration(
                            offsets, geometry, mode="sell"
                        )
                        if not calibration_ok:
                            print(f" [!] Calibragem de venda bloqueada: {calibration_reason}", flush=True)
                            pausar_controle()
                            break
                        sell_region = resolve_rect(
                            offsets.get("sell_buttons_area"), geometry, offsets
                        )
                        visible, visibility_reason = ensure_game_region_visible(win, sell_region)
                        if not visible:
                            print(f" [!] Venda bloqueada: {visibility_reason}", flush=True)
                            pausar_controle()
                            break

                        botoes, score, template_name = detectar_botoes_vender(win, offsets)
                        if not botoes:
                            no_buttons_cycles += 1
                            print(
                                f" [VENDA] Aguardando outro item vendavel; score={score:.3f} "
                                f"({template_name}).",
                                flush=True,
                            )
                            if auto_cycle_enabled() and no_buttons_cycles >= 2:
                                print(
                                    " [CICLO] Zero itens para vender. Voltando para ordens de compra...",
                                    flush=True,
                                )
                                if not abrir_ordens_de_compra(win, offsets):
                                    pausar_controle()
                                break
                            smart_sleep(1.0)
                            continue

                        no_buttons_cycles = 0

                        if sell_index >= len(botoes):
                            print(
                                " [VENDA] Itens visiveis analisados. Descendo 5 itens...",
                                flush=True,
                            )
                            if realizar_scroll_venda(win, offsets, itens=5):
                                sell_index = 0
                            else:
                                print(
                                    " [VENDA] Final da lista atingido. Aguardando novos itens...",
                                    flush=True,
                                )
                                if auto_cycle_enabled():
                                    print(
                                        " [CICLO] Lista de vendas concluída. Voltando para compras...",
                                        flush=True,
                                    )
                                    if not abrir_ordens_de_compra(win, offsets):
                                        pausar_controle()
                                    break
                                smart_sleep(1.0)
                            continue

                        # Reprocessa a tela depois de cada venda porque o inventario
                        # reorganiza as linhas quando um item sai da lista.
                        botao = botoes[sell_index]
                        print(
                            f" [VENDA] Vendendo primeiro item visivel em "
                            f"X:{botao.left} Y:{botao.top}...",
                            flush=True,
                        )
                        sale_result = executar_cliques_venda(win, offsets, botao)
                        if not sale_result:
                            print(" [!] Nao foi possivel concluir a venda.", flush=True)
                            pausar_controle()
                            break
                        if sale_result == "sold":
                            print(" [VENDA] Pedido de venda criado com sucesso.", flush=True)
                        if sale_result == "skipped":
                            # O item continua na lista. Avanca uma linha para nao
                            # abrir repetidamente o mesmo item sem preco.
                            sell_index += 1

                elif mode == "close":
                    print(">>> MODO DE FECHAMENTO DE ORDENS ATIVADO", flush=True)
                    while True:
                        run_m, m_mode = check_control()
                        if not run_m or m_mode != "close":
                            break
                        check_stop()
                        win = get_albion_window()
                        if not win:
                            smart_sleep(1)
                            continue
                        offsets = carregar_offsets()
                        protected_pause_checkpoint(protected_pause_scheduler, offsets)
                        geometry = get_client_geometry(win)
                        calibration_ok, calibration_reason = validate_calibration(offsets, geometry, mode="close")
                        if not calibration_ok:
                            print(f" [!] Calibragem bloqueada: {calibration_reason}", flush=True)
                            pausar_controle()
                            break
                        region = resolve_rect(offsets.get("area_fecha_pedidos"), geometry, offsets)
                        if not region:
                            print(" [!] Área de reconhecimento de ordens inválida.", flush=True)
                            pausar_controle()
                            break
                        botoes = []
                        for path_x in [os.path.join("assets", "x.png")]:
                            full_path = resource_path(path_x)
                            if not os.path.exists(full_path):
                                continue
                            try:
                                screenshot = capture_region(region)
                                screen_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                                screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_BGR2GRAY)
                                template_original = get_template(path_x)
                                if template_original is None:
                                    continue
                                import collections
                                Box = collections.namedtuple("Box", ["left", "top", "width", "height"])
                                for escala in (0.7, 0.85, 1.0, 1.15, 1.3):
                                    if escala == 1.0:
                                        t_resized = template_original
                                    else:
                                        nw = int(template_original.shape[1] * escala)
                                        nh = int(template_original.shape[0] * escala)
                                        t_resized = cv2.resize(template_original, (nw, nh), interpolation=cv2.INTER_AREA)
                                    if t_resized.shape[0] > screen_gray.shape[0] or t_resized.shape[1] > screen_gray.shape[1]:
                                        continue
                                    res = cv2.matchTemplate(screen_gray, t_resized, cv2.TM_CCOEFF_NORMED)
                                    loc = np.where(res >= 0.65)
                                    for pt in zip(*loc[::-1]):
                                        botoes.append(Box(region[0] + pt[0], region[1] + pt[1], t_resized.shape[1], t_resized.shape[0]))
                            except Exception as e:
                                print(f" [!] Erro na busca multi-escala do X: {e}", flush=True)

                        if not botoes:
                            print(" [>>>] Nenhum 'X' encontrado na área. Pausando bot automaticamente!", flush=True)
                            pausar_controle()
                            break
                        botoes_unicos = []
                        for b in botoes:
                            duplicado = any(abs(b.top - u.top) < 15 and abs(b.left - u.left) < 15 for u in botoes_unicos)
                            if not duplicado:
                                botoes_unicos.append(b)
                        print(f" [>>>] Encontrados {len(botoes_unicos)} ordens para fechar. Clicando...", flush=True)
                        for b in botoes_unicos:
                            check_stop()
                            safe_click(b.left + b.width / 2, b.top + b.height / 2, win)
                            print(f"  [-] Ordem fechada em X:{b.left} Y:{b.top}", flush=True)
                            smart_sleep(0.1)
                        smart_sleep(1.0)

                elif mode == "shopping":
                    print(">>> COMPRA PROGRAMADA ATIVADA", flush=True)
                    ultimo_nome_buscado = None
                    ultima_categoria_selecionada = None
                    lista_concluida = False
                    status_inicial_lista: dict[tuple[str, Any, str], Any] = {}
                    status_inicial_lista = {
                        chave_item_lista_compras(item): item.get("status")
                        for item in carregar_lista_compras()
                    }
                    while True:
                        run_m, m_mode = check_control()
                        if not run_m or m_mode != "shopping":
                            break
                        check_stop()
                        win = get_albion_window()
                        if not win:
                            ultimo_nome_buscado = None
                            ultima_categoria_selecionada = None
                            smart_sleep(1)
                            continue
                        offsets = carregar_offsets()
                        valor_maximo_pedido = int(
                            offsets.get("compra_programada_valor_maximo", 0) or 0
                        )
                        protected_pause_checkpoint(protected_pause_scheduler, offsets)
                        geometry = get_client_geometry(win)
                        calibration_ok, calibration_reason = validate_calibration(
                            offsets, geometry, mode="shopping"
                        )
                        if not calibration_ok:
                            print(f" [!] Calibragem bloqueada: {calibration_reason}", flush=True)
                            pausar_controle()
                            break
                        store_region = resolve_rect(offsets.get("area_lista"), geometry, offsets)
                        visible, visibility_reason = ensure_game_region_visible(win, store_region)
                        if not visible:
                            print(f" [!] Operação bloqueada: {visibility_reason}", flush=True)
                            pausar_controle()
                            break

                        lista = carregar_lista_compras()
                        pendentes = [item for item in lista if item.get("status") == "pendente"]
                        if not pendentes:
                            print(
                                " [COMPRA PROGRAMADA] Lista concluída (nenhum item "
                                "pendente).",
                                flush=True,
                            )
                            pausar_controle()
                            lista_concluida = True
                            break

                        item_alvo = pendentes[0]
                        nome_alvo = str(item_alvo.get("nome", "")).strip()
                        try:
                            tier_alvo = int(item_alvo.get("tier"))
                        except (TypeError, ValueError):
                            tier_alvo = None
                        encantamento_alvo = str(item_alvo.get("encantamento") or "").strip()
                        categoria_alvo = str(item_alvo.get("categoria") or "").strip()
                        try:
                            quantidade_alvo = max(1, int(item_alvo.get("quantidade", 1) or 1))
                        except (TypeError, ValueError):
                            quantidade_alvo = 1

                        if not nome_alvo or tier_alvo is None:
                            item_alvo["status"] = "nao_encontrado"
                            salvar_lista_compras(lista)
                            print(
                                " [COMPRA PROGRAMADA] Linha inválida na lista (sem "
                                "nome ou tier); marcada como não encontrada.",
                                flush=True,
                            )
                            continue

                        # Categoria (opcional): filtra o dropdown "Categoria" do painel
                        # de busca antes de digitar o nome, reduzindo itens diferentes
                        # que só compartilham uma palavra do nome (ex.: "Martelo" traz
                        # junto "Cabeça de Martelo", que não é a mesma coisa). Reaproveita
                        # os mesmos pontos calibrados do menu de categorias do modo de
                        # compra normal. Pula se o próximo item já estiver na mesma
                        # categoria selecionada.
                        if categoria_alvo and categoria_alvo != ultima_categoria_selecionada:
                            garantir_modal_fechado(win, offsets)
                            categoria_ok, categoria_erro = selecionar_categoria_compra_programada(
                                win, offsets, categoria_alvo
                            )
                            if categoria_ok:
                                ultima_categoria_selecionada = categoria_alvo
                                ultimo_nome_buscado = None
                            else:
                                print(
                                    f" [!] Não foi possível selecionar a categoria "
                                    f"'{categoria_alvo}': {categoria_erro}.",
                                    flush=True,
                                )

                        # Busca pelo nome + tier + encantamento juntos (ex.: "Robe de
                        # Erudito T4.0"). A busca do jogo é por palavra solta (não filtra
                        # por tier/encantamento sozinha), então quem garante o item certo
                        # é sempre a conferência de tier + encantamento + nome base por
                        # linha, mais abaixo (ver remover_qualificador_tier) -- mas manter
                        # o termo completo aqui não atrapalha e preserva o texto original
                        # que já era usado.
                        termo_busca = f"{nome_alvo} T{tier_alvo}{encantamento_alvo}"

                        print(
                            f" [COMPRA PROGRAMADA] Procurando '{termo_busca}' "
                            f"x{quantidade_alvo}...",
                            flush=True,
                        )

                        if termo_busca == ultimo_nome_buscado:
                            print(
                                " [COMPRA PROGRAMADA] Mesmo termo de busca do item "
                                "anterior; reaproveitando a busca já filtrada.",
                                flush=True,
                            )
                        else:
                            busca_point = resolve_point(offsets.get("busca_mercado"), geometry, offsets)
                            if not busca_point:
                                print(" [!] Campo de busca não calibrado.", flush=True)
                                pausar_controle()
                                break
                            garantir_modal_fechado(win, offsets)
                            if not safe_click(busca_point[0], busca_point[1], win):
                                print(" [!] Clique no campo de busca foi bloqueado.", flush=True)
                                pausar_controle()
                                break
                            smart_sleep(0.2)
                            pyautogui.hotkey("ctrl", "a")
                            smart_sleep(0.05)
                            pyautogui.press("delete")
                            smart_sleep(0.15)
                            if not definir_texto_area_transferencia(termo_busca):
                                print(
                                    " [!] Não foi possível colocar o termo de busca na "
                                    "área de transferência.",
                                    flush=True,
                                )
                                pausar_controle()
                                break
                            pyautogui.hotkey("ctrl", "v")
                            smart_sleep(0.8)
                            ultimo_nome_buscado = termo_busca

                        garantir_modal_fechado(win, offsets)
                        try:
                            botoes, _score, _template = detectar_botoes_pedido(win, offsets)
                        except Exception as e:
                            print(
                                f" [!] Erro na detecção dos resultados da busca: {e}",
                                flush=True,
                            )
                            botoes = []

                        if not botoes:
                            if not garantir_modal_fechado(win, offsets):
                                print(
                                    " [COMPRA PROGRAMADA] Modal aberto detectado e "
                                    "fechado; tentando novamente...",
                                    flush=True,
                                )
                                ultimo_nome_buscado = None
                                smart_sleep(0.3)
                                continue
                            print(
                                f" [COMPRA PROGRAMADA] Nenhum resultado visível para "
                                f"'{termo_busca}'.",
                                flush=True,
                            )
                            item_alvo["_tentativas"] = int(item_alvo.get("_tentativas", 0)) + 1
                            if item_alvo["_tentativas"] >= 3:
                                item_alvo["status"] = "nao_encontrado"
                                print(
                                    f" [COMPRA PROGRAMADA] '{termo_busca}' não encontrado "
                                    "após 3 tentativas.",
                                    flush=True,
                                )
                            salvar_lista_compras(lista)
                            smart_sleep(0.3)
                            continue

                        pedido_criado = False
                        for b in botoes:
                            run_m, m_mode = check_control()
                            if not run_m or m_mode != "shopping":
                                break
                            clicar_centro_bbox(b, win)
                            smart_sleep(0.4)
                            geometry = get_client_geometry(win)
                            o_n = resolve_rect(offsets.get("nome"), geometry, offsets)
                            o_v = resolve_rect(offsets.get("venda"), geometry, offsets)
                            o_c = resolve_rect(offsets.get("compra"), geometry, offsets)
                            o_i = resolve_rect(offsets.get("icone"), geometry, offsets)
                            if not (o_n and o_v and o_c):
                                print(" [!] Áreas de OCR inválidas; refaça a calibragem.", flush=True)
                                pausar_controle()
                                break

                            def _ler_linha_programada(regs_dict):
                                min_x = min(r[0] for r in regs_dict.values())
                                min_y = min(r[1] for r in regs_dict.values())
                                max_x = max(r[0] + r[2] for r in regs_dict.values())
                                max_y = max(r[1] + r[3] for r in regs_dict.values())
                                smart_sleep(0.2)
                                cap = capture_region(
                                    (min_x, min_y, max_x - min_x, max_y - min_y)
                                )
                                big_gray = cv2.cvtColor(np.array(cap), cv2.COLOR_RGB2GRAY)
                                out = {}
                                for key, reg in regs_dict.items():
                                    y_rel, x_rel = reg[1] - min_y, reg[0] - min_x
                                    crop = big_gray[y_rel:y_rel + reg[3], x_rel:x_rel + reg[2]]
                                    scaled = cv2.resize(
                                        crop, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR
                                    )
                                    _, thresh = cv2.threshold(
                                        scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                                    )
                                    out[key] = get_reader().readtext(thresh, detail=0)
                                return out

                            dados = _ler_linha_programada({"nome": o_n, "venda": o_v, "compra": o_c})
                            nome_lido = " ".join(dados["nome"]).strip()
                            pv, pc = limpar_num(dados["venda"]), limpar_num(dados["compra"])

                            encantamento_lido = ""
                            icon_capture = None
                            if o_i:
                                try:
                                    icon_capture = capture_region(o_i)
                                    encantamento_lido, _diag = analisar_encantamento_icone(
                                        icon_capture
                                    )
                                except Exception:
                                    encantamento_lido = ""

                            tier_lido = detectar_tier_nome(nome_lido)
                            if tier_lido is None and icon_capture is not None:
                                try:
                                    tier_lido = detectar_tier_icone(icon_capture)
                                except Exception:
                                    tier_lido = None

                            # A busca do mercado sozinha não distingue itens
                            # diferentes que compartilham parte do nome (ex.:
                            # "Lança do Adepto" vs "Lança Garceira do Adepto"
                            # vs "Lança-virotes do Adepto" aparecem juntos
                            # buscando por "Lança"); por isso o nome base (sem
                            # o qualificador de tier) também precisa bater com
                            # o que foi digitado na lista -- tolerando erro de
                            # OCR de uma letra (ex.: "Erudito" lido errado),
                            # ver nomes_base_correspondem.
                            nome_base_lido = remover_qualificador_tier(nome_lido)
                            nome_base_alvo = remover_qualificador_tier(nome_alvo)
                            bate = (
                                pc > 0
                                and tier_lido == tier_alvo
                                and (encantamento_lido or "") == encantamento_alvo
                                and nomes_base_correspondem(nome_base_lido, nome_base_alvo)
                            )
                            print(
                                f" [COMPRA PROGRAMADA][DIAG] nome='{nome_lido}' "
                                f"base='{nome_base_lido}' (alvo='{nome_base_alvo}') "
                                f"tier={tier_lido} (alvo={tier_alvo}) "
                                f"encant='{encantamento_lido}' (alvo='{encantamento_alvo}') "
                                f"compra={pc} -> bate={bate}",
                                flush=True,
                            )

                            if bate:
                                pedido_proprio_no_topo, brilho_linha_topo = linha_pedido_e_minha(
                                    offsets, win
                                )
                                if pedido_proprio_no_topo:
                                    print(
                                        f" [COMPRA PROGRAMADA] O topo já é meu pedido "
                                        f"(cor da linha, brilho={brilho_linha_topo:.1f}); "
                                        f"{nome_lido} {encantamento_lido} considerado "
                                        "atendido.",
                                        flush=True,
                                    )
                                    item_alvo["status"] = "pedido_criado"
                                    item_alvo["preco_pedido"] = pc
                                    salvar_lista_compras(lista)
                                    pedido_criado = True
                                    media_bloqueou = False
                                elif bool(offsets.get(VERIFICAR_MEDIA_SEMANAL_KEY, False)):
                                    media_ok, media_motivo = media_semanal_disponivel(win, offsets)
                                    if media_ok is None:
                                        print(
                                            f" [!] Verificação de média semanal bloqueada: "
                                            f"{media_motivo}.",
                                            flush=True,
                                        )
                                        pausar_controle()
                                        break
                                    media_bloqueou = not media_ok
                                    if media_bloqueou:
                                        print(
                                            f" [COMPRA PROGRAMADA] Bloqueado: {media_motivo}.",
                                            flush=True,
                                        )
                                        item_alvo["status"] = "sem_media"
                                        salvar_lista_compras(lista)
                                        pedido_criado = True
                                else:
                                    media_bloqueou = False

                                if not pedido_proprio_no_topo and not media_bloqueou:
                                    sucesso, preco_final, motivo = executar_cliques_compra_programada(
                                        win, offsets, pc, quantidade_alvo, valor_maximo_pedido
                                    )
                                    if sucesso:
                                        preco_total_pedido = preco_final * quantidade_alvo
                                        print(
                                            f" [COMPRA PROGRAMADA] Pedido criado: {nome_lido} "
                                            f"{encantamento_lido} x{quantidade_alvo} a "
                                            f"{preco_final}/un (total {preco_total_pedido}).",
                                            flush=True,
                                        )
                                        item_alvo["status"] = "pedido_criado"
                                        item_alvo["preco_pedido"] = preco_total_pedido
                                        salvar_lista_compras(lista)
                                        pedido_criado = True
                                        lucro_estimado_pedido = (pv * 0.93 - pc) * quantidade_alvo
                                        print(f"[BUY] {lucro_estimado_pedido}", flush=True)
                                        # Linha aditiva para o relatorio da sessao; nao faz parte
                                        # do contrato [BUY] existente e pode ser ignorada por quem
                                        # nao a reconhece.
                                        print(
                                            "[BUY_DETAIL] "
                                            + json.dumps(
                                                {
                                                    "nome": nome_alvo,
                                                    "tier": tier_alvo,
                                                    "encantamento": encantamento_alvo,
                                                    "venda": pv,
                                                    "compra": pc,
                                                    "quantidade": quantidade_alvo,
                                                    "preco_pedido": preco_total_pedido,
                                                    "taxa_pedido": round(
                                                        preco_total_pedido * TAXA_PEDIDO_COMPRA_PERCENTUAL
                                                    ),
                                                    "lucro_estimado": lucro_estimado_pedido,
                                                },
                                                ensure_ascii=False,
                                                separators=(",", ":"),
                                            ),
                                            flush=True,
                                        )
                                    elif motivo == "limite_excedido":
                                        item_alvo["status"] = "limite_excedido"
                                        salvar_lista_compras(lista)
                                        pedido_criado = True
                                    else:
                                        print(
                                            " [COMPRA PROGRAMADA] Falha ao criar o pedido; "
                                            "tentará novamente no próximo ciclo.",
                                            flush=True,
                                        )
                                garantir_modal_fechado(win, offsets)
                                break

                            anchor_point = resolve_point(offsets.get("ancora"), geometry, offsets)
                            if anchor_point:
                                safe_click(anchor_point[0], anchor_point[1], win)
                            garantir_modal_fechado(win, offsets)

                        if not pedido_criado:
                            item_alvo["_tentativas"] = int(item_alvo.get("_tentativas", 0)) + 1
                            if item_alvo["_tentativas"] >= 3:
                                item_alvo["status"] = "nao_encontrado"
                                print(
                                    f" [COMPRA PROGRAMADA] '{termo_busca}' não encontrado "
                                    "após 3 tentativas.",
                                    flush=True,
                                )
                            salvar_lista_compras(lista)

                        smart_sleep(0.3)

                    reverter_lista_compras_se_nao_pausado(status_inicial_lista, lista_concluida)

                elif mode == "remover_pedidos":
                    print(">>> MODO REMOVER PEDIDOS ATIVADO", flush=True)
                    itens_mantidos_no_topo = 0
                    scrolls_sem_itens = 0
                    while True:
                        run_m, m_mode = check_control()
                        if not run_m or m_mode != "remover_pedidos":
                            break
                        check_stop()
                        win = get_albion_window()
                        if not win:
                            smart_sleep(1)
                            continue
                        offsets = carregar_offsets()
                        protected_pause_checkpoint(protected_pause_scheduler, offsets)
                        geometry = get_client_geometry(win)
                        calibration_ok, calibration_reason = validate_calibration(
                            offsets, geometry, mode="remover_pedidos"
                        )
                        if not calibration_ok:
                            print(f" [!] Calibragem bloqueada: {calibration_reason}", flush=True)
                            pausar_controle()
                            break
                        area_region = resolve_rect(
                            offsets.get("remover_pedidos_area_lista"), geometry, offsets
                        )
                        visible, visibility_reason = ensure_game_region_visible(win, area_region)
                        if not visible:
                            print(f" [!] Operação bloqueada: {visibility_reason}", flush=True)
                            pausar_controle()
                            break

                        botoes_editar, _score_editar, _tmpl_editar = detectar_botoes_por_template(
                            win, offsets, "remover_pedidos_area_lista", "editar_pedido_usuario.png"
                        )
                        botoes_cancelar, _score_cancelar, _tmpl_cancelar = detectar_botoes_por_template(
                            win, offsets, "remover_pedidos_area_lista", "cancelar_pedido_usuario.png"
                        )
                        pares = parear_editar_com_cancelar(botoes_editar, botoes_cancelar)

                        # Um pedido mantido (ainda meu) continua na lista, no mesmo
                        # lugar -- só um cancelamento remove uma linha e desloca as
                        # de baixo. Por isso um contador simples de "quantos itens do
                        # topo já confirmei" basta: ele nunca recua sozinho, e um
                        # cancelamento naturalmente libera a próxima posição.
                        if itens_mantidos_no_topo >= len(pares):
                            # realizar_scroll() só confirma que o gesto calibrado foi
                            # executado, não que a lista mudou -- numa lista curta que
                            # já cabe inteira na tela, rolar não tem efeito nenhum. Sem
                            # comparar as posições antes/depois, um "sucesso" vazio
                            # zeraria o contador pra sempre e reprocessaria os mesmos
                            # itens já mantidos em loop infinito.
                            posicoes_antes = {
                                (par[0].left, par[0].top) for par in pares
                            }
                            if realizar_scroll(
                                offsets, win, "remover_pedidos_drag_start", "remover_pedidos_drag_end"
                            ):
                                smart_sleep(0.5)
                                botoes_editar_pos, _, _ = detectar_botoes_por_template(
                                    win, offsets, "remover_pedidos_area_lista",
                                    "editar_pedido_usuario.png",
                                )
                                botoes_cancelar_pos, _, _ = detectar_botoes_por_template(
                                    win, offsets, "remover_pedidos_area_lista",
                                    "cancelar_pedido_usuario.png",
                                )
                                pares_pos_scroll = parear_editar_com_cancelar(
                                    botoes_editar_pos, botoes_cancelar_pos
                                )
                                posicoes_depois = {
                                    (par[0].left, par[0].top) for par in pares_pos_scroll
                                }
                                if posicoes_depois != posicoes_antes:
                                    itens_mantidos_no_topo = 0
                                    scrolls_sem_itens = 0
                                    continue

                            scrolls_sem_itens += 1
                            if scrolls_sem_itens < 3:
                                smart_sleep(0.3)
                                continue
                            tem_proxima = tem_mais_paginas(
                                win, offsets, "remover_pedidos_btn_proxima"
                            )
                            if tem_proxima and clicar_proxima_pagina(
                                win,
                                offsets,
                                "remover_pedidos_btn_proxima",
                                "remover_pedidos_top_start",
                                "remover_pedidos_top_end",
                            ):
                                itens_mantidos_no_topo = 0
                                scrolls_sem_itens = 0
                                smart_sleep(0.5)
                                continue
                            print(
                                " [REMOVER PEDIDOS] Nenhum pedido novo encontrado na lista. "
                                "Varredura concluída.",
                                flush=True,
                            )
                            pausar_controle()
                            break

                        scrolls_sem_itens = 0
                        editar_box, cancelar_box = pares[itens_mantidos_no_topo]
                        print(
                            f" [REMOVER PEDIDOS][DBG] {len(pares)} par(es) na tela; "
                            f"processando posição {itens_mantidos_no_topo + 1} "
                            f"(EDITAR em X:{int(editar_box.left)} Y:{int(editar_box.top)}).",
                            flush=True,
                        )
                        check_stop()
                        clicar_centro_bbox(editar_box, win)
                        smart_sleep(0.8)

                        pedido_proprio, brilho = linha_pedido_e_minha(
                            offsets, win, "remover_pedidos_topo_cor"
                        )
                        if brilho is None:
                            print(
                                " [!] Não foi possível ler a cor de referência "
                                "('remover_pedidos_topo_cor'); recalibre esse ponto.",
                                flush=True,
                            )
                            garantir_modal_fechado(win, offsets)
                            pausar_controle()
                            break

                        garantir_modal_fechado(win, offsets)
                        smart_sleep(0.2)

                        if pedido_proprio:
                            itens_mantidos_no_topo += 1
                            print(
                                " [REMOVER PEDIDOS] Pedido ainda é o topo do livro; mantendo.",
                                flush=True,
                            )
                        else:
                            check_stop()
                            # A confirmação compara o CONTEÚDO da linha numa posição
                            # fixa da tela, não a contagem total de itens: se houver
                            # mais pedidos do que cabem na tela, cancelar este item
                            # faz um item escondido subir para a mesma posição, e a
                            # contagem visível continua igual mesmo com a linha tendo
                            # mudado por completo.
                            #
                            # O cursor do mouse precisa ficar longe da linha antes de
                            # CADA captura: se o jogo destaca/ilumina a linha sob o
                            # cursor (hover), a comparação veria essa iluminação como
                            # "mudou" mesmo sem o cancelamento ter feito efeito ainda
                            # -- mesmo problema já visto na leitura do campo de
                            # quantidade da Compra Programada.
                            ponto_longe_x = area_region[0] + 10
                            ponto_longe_y = max(0, area_region[1] - 25)
                            pyautogui.moveTo(ponto_longe_x, ponto_longe_y)
                            smart_sleep(0.1)
                            conteudo_antes = capturar_conteudo_linha(area_region, editar_box)
                            assinatura_antes = _assinatura_visual_linha(conteudo_antes)
                            print(
                                " [REMOVER PEDIDOS] Pedido perdeu a posição; cancelando...",
                                flush=True,
                            )
                            # Às vezes um clique simplesmente não registra (tooltip
                            # cobrindo o botão, engasgo momentâneo do jogo com o
                            # volume de cancelamentos etc.). Em vez de desistir e
                            # pausar a sessão inteira no primeiro clique sem efeito,
                            # tenta clicar de novo algumas vezes antes de admitir
                            # que precisa de intervenção humana.
                            cancelamento_confirmado = False
                            for _tentativa_clique in range(3):
                                clicar_centro_bbox(cancelar_box, win)
                                pyautogui.moveTo(ponto_longe_x, ponto_longe_y)
                                for _tentativa_confirmacao in range(4):
                                    smart_sleep(0.3)
                                    conteudo_depois = capturar_conteudo_linha(area_region, editar_box)
                                    assinatura_depois = _assinatura_visual_linha(conteudo_depois)
                                    distancia = _distancia_assinaturas(assinatura_antes, assinatura_depois)
                                    print(
                                        f" [REMOVER PEDIDOS][DBG] clique {_tentativa_clique + 1}, "
                                        f"tentativa {_tentativa_confirmacao + 1}: "
                                        f"distância visual = {distancia:.3f} (confirma se > 0.10)",
                                        flush=True,
                                    )
                                    if not assinaturas_equivalentes(assinatura_antes, assinatura_depois):
                                        cancelamento_confirmado = True
                                        break
                                if cancelamento_confirmado:
                                    break
                                print(
                                    " [REMOVER PEDIDOS] Clique sem efeito aparente; "
                                    "tentando novamente...",
                                    flush=True,
                                )
                            if not cancelamento_confirmado:
                                print(
                                    " [REMOVER PEDIDOS][PARADA SEGURA] Não foi possível "
                                    "confirmar visualmente que o pedido foi cancelado; "
                                    "pausando para não reprocessar o mesmo item.",
                                    flush=True,
                                )
                                pausar_controle()
                                break
                            print(
                                " [REMOVER PEDIDOS] Cancelamento confirmado; lista atualizada.",
                                flush=True,
                            )
                            # itens_mantidos_no_topo não muda: o item cancelado some
                            # da lista e o próximo item assume essa posição.

                        smart_sleep(0.2)

            except BotStoppedException:
                try:
                    pyautogui.mouseUp(button="left")
                except Exception:
                    pass
                print(" [!] Interrupcao instantanea!", flush=True)
                if mode in ("buy", "artefatos"):
                    cycle_resume_state = resolver_estado_ciclo_ao_parar()
                if mode == "shopping":
                    reverter_lista_compras_se_nao_pausado(status_inicial_lista, lista_concluida)
            except Exception as e:
                registrar_erro_fatal(e)
                # Le a decisao de pausa/parar ANTES de pausar_controle(), que
                # sobrescreve o arquivo sem preserve_position -- lendo depois
                # sempre pareceria um PARAR, mesmo se o pedido real tivesse
                # sido pausa.
                if mode in ("buy", "artefatos"):
                    cycle_resume_state = resolver_estado_ciclo_ao_parar()
                if mode == "shopping":
                    reverter_lista_compras_se_nao_pausado(status_inicial_lista, lista_concluida)
                pausar_controle()

        current_run, _current_mode = check_control()
        if not current_run:
            execucao_ativa = False
            protected_pause_scheduler.reset(False)
        if not standby_logged:
            print(">>> Bot em Standby.", flush=True)
            standby_logged = True
        time.sleep(0.2)



if __name__ == "__main__":
    main()
