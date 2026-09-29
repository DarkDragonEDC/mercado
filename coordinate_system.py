"""Sistema unico de coordenadas para a janela do Albion.

Todas as calibragens v2 sao normalizadas em relacao a area cliente da janela
(sem barra de titulo e bordas). Nenhum consumidor deve somar ``win.left`` ou
``win.top`` diretamente; use as funcoes deste modulo.
"""

from __future__ import annotations

import ctypes
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import ImageGrab

from app_paths import user_file


SCHEMA_VERSION = 2
COORDINATE_SPACE = "albion_client_normalized"
META_KEY = "_calibration"
MAX_SETTINGS_FILE_SIZE = 5 * 1024 * 1024

SPATIAL_KEYS = {
    "ancora",
    "area_lista",
    "btn_proxima",
    "nome",
    "venda",
    "compra",
    "compra_topo_cor",
    "preco_final_compra",
    "icone",
    "btn_mais",
    "btn_pedido",
    "btn_criar",
    "btn_sim",
    "btn_nao",
    "drag_start",
    "drag_end",
    "top_start",
    "top_end",
    "btn_abrir",
    "area_fecha_pedidos",
    "cat_clique_principal",
    "sell_buttons_area",
    "sell_button_sample",
    "sell_price_minus",
    "sell_create_button",
    "sell_price_value",
    "sell_close_button",
    "cycle_counter_area",
    "buy_page_number_area",
    "cycle_collect_all",
    "cycle_sell_menu",
    "cycle_buy_menu",
    "busca_mercado",
    "shopping_qtd_valor",
    "preco_medio",
    "remover_pedidos_area_lista",
    "remover_pedidos_btn_editar",
    "remover_pedidos_btn_cancelar",
    "remover_pedidos_topo_cor",
    "remover_pedidos_btn_proxima",
    "remover_pedidos_drag_start",
    "remover_pedidos_drag_end",
    "remover_pedidos_top_start",
    "remover_pedidos_top_end",
}

BUY_REQUIRED_KEYS = {
    "ancora",
    "area_lista",
    "nome",
    "venda",
    "compra",
    "preco_final_compra",
    "icone",
    "btn_mais",
    "btn_pedido",
    "btn_criar",
    "btn_sim",
    "btn_nao",
    "drag_start",
    "drag_end",
    "top_start",
    "top_end",
    "btn_proxima",
}

CYCLE_REQUIRED_KEYS = {
    "cycle_counter_area",
    "buy_page_number_area",
    "cycle_collect_all",
    "cycle_sell_menu",
    "cycle_buy_menu",
}

SELL_REQUIRED_KEYS = {
    "sell_buttons_area",
    "sell_button_sample",
    "sell_price_minus",
    "sell_create_button",
    "sell_price_value",
    "sell_close_button",
}

# Compra Programada reaproveita a leitura/clique de linha do modo Compra
# (mesma area_lista, mesmo btn_pedido) e acrescenta a busca por nome e o
# ajuste de quantidade do pedido.
SHOPPING_REQUIRED_KEYS = set(BUY_REQUIRED_KEYS) | {
    "busca_mercado",
    "shopping_qtd_valor",
}

# Tela "Pedidos de Compra" fica em pixels diferentes da tela de Criar/Editar
# pedido normal -- por isso tem sua própria calibragem completa, mesmo
# reaproveitando a mesma lógica (detectar_botoes_pedido, linha_pedido_e_minha,
# scroll/paginação) parametrizada com essas chaves.
REMOVER_PEDIDOS_REQUIRED_KEYS = {
    "remover_pedidos_area_lista",
    "remover_pedidos_btn_editar",
    "remover_pedidos_btn_cancelar",
    "remover_pedidos_topo_cor",
    "remover_pedidos_btn_proxima",
    "remover_pedidos_drag_start",
    "remover_pedidos_drag_end",
    "remover_pedidos_top_start",
    "remover_pedidos_top_end",
}

# Modo Artefatos (aba dedicada): mesma varredura da Compra, travada na
# categoria Artefato e com quantidade por pedido. Exige a navegação de
# categoria e o campo Quantia (reaproveitado da Compra Programada) mesmo que
# o usuário não use cat_ativo na aba COMPRA.
ARTEFATOS_REQUIRED_KEYS = set(BUY_REQUIRED_KEYS) | {
    "cat_clique_principal",
    "cat_clique_artefato",
    "shopping_qtd_valor",
}


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


@dataclass(frozen=True)
class ClientGeometry:
    left: int
    top: int
    width: int
    height: int
    hwnd: int | None = None

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


def is_spatial_key(key: str) -> bool:
    return key in SPATIAL_KEYS or key.startswith("cat_clique_")


def get_client_geometry(win: Any) -> ClientGeometry:
    """Retorna a area interna real da janela em coordenadas da tela."""
    if win is None:
        raise ValueError("Janela do Albion nao encontrada.")

    hwnd = getattr(win, "_hWnd", None) or getattr(win, "hWnd", None)
    if hwnd:
        rect = RECT()
        origin = POINT(0, 0)
        user32 = ctypes.windll.user32
        user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
        user32.GetClientRect.restype = ctypes.c_bool
        user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(POINT)]
        user32.ClientToScreen.restype = ctypes.c_bool
        hwnd_ptr = ctypes.c_void_p(int(hwnd))
        if user32.GetClientRect(hwnd_ptr, ctypes.byref(rect)) and user32.ClientToScreen(
            hwnd_ptr, ctypes.byref(origin)
        ):
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width > 0 and height > 0:
                return ClientGeometry(int(origin.x), int(origin.y), width, height, int(hwnd))

    # Fallback para testes e ambientes onde o HWND nao esta disponivel.
    width = int(getattr(win, "width", 0))
    height = int(getattr(win, "height", 0))
    if width <= 0 or height <= 0:
        raise ValueError("Nao foi possivel medir a janela do Albion.")
    return ClientGeometry(
        int(getattr(win, "left", 0)),
        int(getattr(win, "top", 0)),
        width,
        height,
        int(hwnd) if hwnd else None,
    )


def capture_region(region: tuple[int, int, int, int]):
    """Captura uma região física, inclusive em monitores com coordenadas negativas."""
    left, top, width, height = (int(value) for value in region)
    if width <= 0 or height <= 0:
        raise ValueError("Região de captura vazia.")
    return ImageGrab.grab(
        bbox=(left, top, left + width, top + height),
        all_screens=True,
    )


def get_window_dpi(geometry: ClientGeometry) -> int:
    if not geometry.hwnd:
        return 96
    try:
        get_dpi = ctypes.windll.user32.GetDpiForWindow
        get_dpi.argtypes = [ctypes.c_void_p]
        get_dpi.restype = ctypes.c_uint
        return int(get_dpi(ctypes.c_void_p(int(geometry.hwnd)))) or 96
    except Exception:
        return 96


def calibration_metadata(geometry: ClientGeometry) -> dict[str, Any]:
    dpi = get_window_dpi(geometry)
    return {
        "schema_version": SCHEMA_VERSION,
        "coordinate_space": COORDINATE_SPACE,
        "client_width": geometry.width,
        "client_height": geometry.height,
        "aspect_ratio": round(geometry.aspect_ratio, 6),
        "dpi": dpi,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def is_v2(data: dict[str, Any]) -> bool:
    meta = data.get(META_KEY, {})
    return bool(
        isinstance(meta, dict)
        and meta.get("schema_version") == SCHEMA_VERSION
        and meta.get("coordinate_space") == COORDINATE_SPACE
    )


def normalize_point(x: float, y: float, geometry: ClientGeometry) -> list[float]:
    if not geometry.contains(x, y):
        raise ValueError("O ponto selecionado esta fora da area interna do Albion.")
    return [
        round((x - geometry.left) / geometry.width, 8),
        round((y - geometry.top) / geometry.height, 8),
    ]


def normalize_rect(
    x: float, y: float, width: float, height: float, geometry: ClientGeometry
) -> list[float]:
    if width <= 0 or height <= 0:
        raise ValueError("A area calibrada precisa ter largura e altura positivas.")
    x2 = x + width
    y2 = y + height
    if not geometry.contains(x, y) or not geometry.contains(x2 - 1, y2 - 1):
        raise ValueError("A area selecionada ultrapassa a area interna do Albion.")
    return [
        round((x - geometry.left) / geometry.width, 8),
        round((y - geometry.top) / geometry.height, 8),
        round(width / geometry.width, 8),
        round(height / geometry.height, 8),
    ]


def resolve_point(
    value: Any, geometry: ClientGeometry, data: dict[str, Any]
) -> tuple[int, int] | None:
    if not isinstance(value, list) or len(value) not in (2, 4):
        return None
    if not is_v2(data):
        return None
    x = float(value[0])
    y = float(value[1])
    if len(value) == 4:
        x += float(value[2]) / 2
        y += float(value[3]) / 2
    return (
        int(round(geometry.left + x * geometry.width)),
        int(round(geometry.top + y * geometry.height)),
    )


def resolve_rect(
    value: Any, geometry: ClientGeometry, data: dict[str, Any]
) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 4 or not is_v2(data):
        return None
    left = int(round(geometry.left + float(value[0]) * geometry.width))
    top = int(round(geometry.top + float(value[1]) * geometry.height))
    width = max(1, int(round(float(value[2]) * geometry.width)))
    height = max(1, int(round(float(value[3]) * geometry.height)))
    width = min(width, geometry.right - left)
    height = min(height, geometry.bottom - top)
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def strip_spatial_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Preserva preferencias, removendo toda calibragem de outra maquina."""
    return {
        key: value
        for key, value in data.items()
        if key != META_KEY and not is_spatial_key(key)
    }


def prepare_for_calibration(
    data: dict[str, Any], geometry: ClientGeometry
) -> tuple[dict[str, Any], bool]:
    """Prepara o documento v2; retorna (dados, calibragem_antiga_descartada)."""
    reset = not is_v2(data)
    if not reset:
        meta = data[META_KEY]
        old_aspect = float(meta.get("aspect_ratio") or 0.0)
        old_width = int(meta.get("client_width") or 0)
        old_height = int(meta.get("client_height") or 0)
        size_changed = (
            old_width <= 0
            or old_height <= 0
            or abs(old_width - geometry.width) / max(old_width, 1) > 0.01
            or abs(old_height - geometry.height) / max(old_height, 1) > 0.01
        )
        reset = old_aspect <= 0 or abs(old_aspect - geometry.aspect_ratio) > 0.015 or size_changed
    prepared = strip_spatial_settings(data) if reset else dict(data)
    prepared[META_KEY] = calibration_metadata(geometry)
    return prepared, reset


def validate_calibration(
    data: dict[str, Any],
    geometry: ClientGeometry,
    mode: str = "buy",
    required_keys: Iterable[str] | None = None,
) -> tuple[bool, str]:
    if not is_v2(data):
        return False, "Calibragem antiga ou ausente. Refaca a calibragem neste computador."

    meta = data[META_KEY]
    old_aspect = float(meta.get("aspect_ratio") or 0.0)
    if old_aspect <= 0 or abs(old_aspect - geometry.aspect_ratio) > 0.015:
        return (
            False,
            "O formato/tamanho proporcional da janela mudou. Refaca a calibragem.",
        )

    old_width = int(meta.get("client_width") or 0)
    old_height = int(meta.get("client_height") or 0)
    if (
        old_width <= 0
        or old_height <= 0
        or abs(old_width - geometry.width) / max(old_width, 1) > 0.01
        or abs(old_height - geometry.height) / max(old_height, 1) > 0.01
    ):
        return False, "O tamanho da área do Albion mudou. Refaca a calibragem."

    saved_dpi = int(meta.get("dpi") or 96)
    current_dpi = get_window_dpi(geometry)
    if saved_dpi != current_dpi:
        return False, "A escala/DPI do monitor mudou. Refaca a calibragem."

    if required_keys is None:
        if mode == "close":
            required = {"area_fecha_pedidos"}
        elif mode == "sell":
            required = set(SELL_REQUIRED_KEYS)
        elif mode == "shopping":
            required = set(SHOPPING_REQUIRED_KEYS)
        elif mode == "remover_pedidos":
            required = set(REMOVER_PEDIDOS_REQUIRED_KEYS)
        elif mode == "artefatos":
            required = set(ARTEFATOS_REQUIRED_KEYS)
        elif mode == "cycle":
            required = (
                set(BUY_REQUIRED_KEYS)
                | set(SELL_REQUIRED_KEYS)
                | set(CYCLE_REQUIRED_KEYS)
            )
        else:
            required = set(BUY_REQUIRED_KEYS)
        if mode in {"buy", "cycle"} and data.get("cat_ativo"):
            required.add("cat_clique_principal")
            enabled = data.get("cat_enabled", {})
            sequence = data.get("cat_sequence", [])
            name_to_key = {
                "ARMAS": "cat_clique_armas",
                "PEITORAL": "cat_clique_peitoral",
                "CAPACETES": "cat_clique_capacetes",
                "BOTAS": "cat_clique_botas",
                "MAO SECUNDARIA": "cat_clique_mao_secundaria",
                "MÃO SECUNDARIA": "cat_clique_mao_secundaria",
                "CAPAS": "cat_clique_capas",
                "BOLSAS": "cat_clique_bolsas",
                "EQUIP COLETA": "cat_clique_equip_coleta",
                "ARTEFATO": "cat_clique_artefato",
            }
            for name in sequence:
                if enabled.get(name, True) and name in name_to_key:
                    required.add(name_to_key[name])
    else:
        required = set(required_keys)

    missing = sorted(key for key in required if not data.get(key))
    if missing:
        return False, "Campos ainda nao calibrados: " + ", ".join(missing)

    for key in required:
        value = data.get(key)
        if not isinstance(value, list) or len(value) not in (2, 4):
            return False, f"Calibragem invalida no campo: {key}"
        if any(not isinstance(item, (int, float)) for item in value):
            return False, f"Calibragem invalida no campo: {key}"
        if any(item < 0 or item > 1 for item in value[:2]):
            return False, f"Calibragem fora da janela no campo: {key}"
        if len(value) == 4:
            if value[2] <= 0 or value[3] <= 0:
                return False, f"Area vazia no campo: {key}"
            if value[0] + value[2] > 1.000001 or value[1] + value[3] > 1.000001:
                return False, f"Area fora da janela no campo: {key}"

    return True, "Calibragem valida."


def _persistent_settings_path(path: str) -> str:
    candidate = Path(path)
    if candidate.name == "offsets.json" and candidate.parent == Path("."):
        return str(user_file("offsets.json"))
    return path


def load_settings(path: str) -> dict[str, Any]:
    path = _persistent_settings_path(path)
    if not os.path.exists(path):
        return {}
    try:
        # Um arquivo de configurações normal tem poucos KB. Não tente carregar
        # arquivos gigantes/corrompidos, pois json.load pode esgotar toda a RAM.
        if os.path.getsize(path) > MAX_SETTINGS_FILE_SIZE:
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(path: str, data: dict[str, Any]) -> None:
    """Gravacao atomica para evitar offsets.json parcial/corrompido.

    O os.replace final pode falhar com PermissionError/WinError 5 no Windows
    quando outro processo (ex.: a interface lendo o mesmo arquivo, ou o
    antivirus) tem o destino aberto no exato instante da troca -- e um erro
    assim, sem repetir, derrubava a automacao inteira por uma disputa
    passageira de arquivo. Tenta algumas vezes com um pequeno intervalo antes
    de desistir.
    """
    path = _persistent_settings_path(path)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=4)
        handle.flush()
        os.fsync(handle.fileno())
    for tentativa in range(5):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError:
            if tentativa == 4:
                raise
            time.sleep(0.05 * (2**tentativa))
