# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'interface.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# irreducible cflow, using cdg fallback
global GLOBAL_MEDALLION_REF
global key_info
# ***<module>: Failure: Compilation Error
import sys
import os
import io
import math
import struct
import wave
try:
    import winsound
except ImportError:
    winsound = None
if getattr(sys, 'frozen', False):
    try:
        torch_lib = os.path.join(sys._MEIPASS, 'torch', 'lib')
        if os.path.exists(torch_lib):
            os.add_dll_directory(torch_lib)
            os.environ['PATH'] = torch_lib + os.pathsep + os.environ.get('PATH', '')
    except:
        pass
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass
import queue
from collections import deque
from ctypes import Structure, c_int, byref, sizeof
import csv
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import json
import os
import time
import threading
import subprocess
import hashlib
import re
import unicodedata
import uuid
import requests
import platform
import multiprocessing
from datetime import datetime, timedelta
from urllib.parse import quote
import pygetwindow as gw
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageChops
from app_paths import (
    cache_dir,
    calibration_assets_dir,
    logs_dir,
    migrate_legacy_calibration_assets,
    migrate_legacy_state,
    user_file,
)
import bot
from purchase_profiles import (
    FINANCIAL_RULE_VERSION,
    PROFILE_AGGRESSIVE,
    PROFILE_BALANCED,
    PROFILE_CONSERVATIVE,
    PROFILE_CUSTOM,
    PROFILE_LABELS,
    format_silver,
    parse_silver,
    resolve_purchase_profile,
    settings_from_legacy_config,
)
from operation_telemetry import BackgroundLogWriter
import numpy as np
from coordinate_system import (
    BUY_REQUIRED_KEYS,
    CYCLE_REQUIRED_KEYS,
    SELL_REQUIRED_KEYS,
    SHOPPING_REQUIRED_KEYS,
    REMOVER_PEDIDOS_REQUIRED_KEYS,
    META_KEY,
    capture_region,
    get_client_geometry,
    is_spatial_key,
    is_v2,
    load_settings,
    normalize_point,
    normalize_rect,
    prepare_for_calibration,
    resolve_point,
    resolve_rect,
    save_settings,
    strip_spatial_settings,
    validate_calibration,
)
from preset_setup_ui import PresetSetupWindow
from startup_update import show_current_release_notes, start_startup_update_check


def stop_automations() -> None:
    try:
        path = user_file('bot_control.json')
        mode = 'buy'
        try:
            current = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(current, dict) and isinstance(current.get('mode'), str):
                mode = current['mode']
        except (OSError, json.JSONDecodeError):
            pass
        path.write_text(
            json.dumps({'run': False, 'mode': mode}, ensure_ascii=False),
            encoding='utf-8',
        )
    except OSError:
        pass

# ─── Caminho base sempre relativo ao .exe ou ao script ───────────────────────
if getattr(sys, 'frozen', False) or '__compiled__' in globals():
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Garante que caminhos relativos (offsets.json, assets/, etc.) funcionem
os.chdir(_BASE_DIR)
migrate_legacy_state()
migrate_legacy_calibration_assets()

OFFSETS_FILE = str(user_file('offsets.json'))
CONTROL_FILE = str(user_file('bot_control.json'))
LISTA_COMPRAS_FILE = str(user_file('lista_compras.json'))
ENCANTAMENTO_OPCOES = ('.0', '.1', '.2', '.3', '.4')
# Mesmas categorias (e mesma grafia) do CATEGORIA_CLIQUE_KEYS em bot.py -- o
# dropdown "Categoria" da Compra Programada reaproveita os pontos calibrados
# do menu de categorias do modo de compra normal, que só cobre essas oito.
CATEGORIA_OPCOES = (
    'ARMAS', 'PEITORAL', 'CAPACETES', 'BOTAS', 'MÃO SECUNDARIA', 'CAPAS',
    'BOLSAS', 'EQUIP COLETA',
)


def _normalizar_categoria_texto(texto):
    """Maiuscula, sem acento e com espaços simples -- pra comparar frouxo."""
    normalizado = unicodedata.normalize('NFKD', str(texto or ''))
    normalizado = normalizado.encode('ascii', 'ignore').decode('ascii').upper()
    return ' '.join(normalizado.split())


# Aceita o nome resumido usado internamente, o singular, e o nome completo
# como aparece no dropdown do jogo (ex.: "Armadura de Capacete") -- não
# precisa digitar a grafia exata do CATEGORIA_OPCOES. As chaves já estão sem
# acento porque são comparadas contra _normalizar_categoria_texto.
CATEGORIA_ALIASES = {
    'ARMA': 'ARMAS',
    'ARMAS': 'ARMAS',
    'PEITORAL': 'PEITORAL',
    'ARMADURA DE PEITORAL': 'PEITORAL',
    'ARMADURA PEITORAL': 'PEITORAL',
    'CAPACETE': 'CAPACETES',
    'CAPACETES': 'CAPACETES',
    'ARMADURA DE CAPACETE': 'CAPACETES',
    'ARMADURA CAPACETE': 'CAPACETES',
    'BOTA': 'BOTAS',
    'BOTAS': 'BOTAS',
    'CALCADO': 'BOTAS',
    'CALCADOS': 'BOTAS',
    'ARMADURA DE CALCADO': 'BOTAS',
    'ARMADURA CALCADO': 'BOTAS',
    'MAO SECUNDARIA': 'MÃO SECUNDARIA',
    'CAPA': 'CAPAS',
    'CAPAS': 'CAPAS',
    'BOLSA': 'BOLSAS',
    'BOLSAS': 'BOLSAS',
    'EQUIP COLETA': 'EQUIP COLETA',
    'EQUIPAMENTO DE COLETA': 'EQUIP COLETA',
    'COLETA': 'EQUIP COLETA',
}
OPPORTUNITIES_FILE = str(user_file('oportunidades.csv'))


def calibration_template_path(filename):
    """Prioriza a amostra gravavel do usuario e preserva o asset distribuido."""
    active = calibration_assets_dir() / filename
    if active.is_file():
        return str(active)
    return os.path.join(_BASE_DIR, 'assets', filename)

GLOBAL_PUFFY_CACHE = {}
GLOBAL_WINDOW_BG_CACHE = {}
GLOBAL_MEDALLION_REF = None

MODULE_PURCHASE = 'purchase_orders'
MODULE_SELL = 'sales_orders'
MODULE_CYCLE = 'auto_cycle'


def build_soft_order_tone():
    """Cria em memoria o som sutil de uma gota caindo em um copo."""
    sample_rate = 22050
    duration = 0.21
    frame_count = int(sample_rate * duration)
    frames = bytearray()
    for index in range(frame_count):
        moment = index / sample_rate
        attack = min(1.0, moment / 0.0035)
        tail = min(1.0, max(0.0, (duration - moment) / 0.035))

        # A queda rápida da frequência produz o pequeno "ploc" líquido.
        base_frequency = 520.0
        frequency_span = 1180.0
        sweep_time = 0.026
        phase = 2 * math.pi * (
            base_frequency * moment
            + frequency_span * sweep_time * (1.0 - math.exp(-moment / sweep_time))
        )
        drop = math.sin(phase) * math.exp(-18.0 * moment)

        # Ressonâncias leves dão a sensação de a gota ter atingido um copo.
        glass = 0.23 * math.sin(2 * math.pi * 1260 * moment + 0.35)
        glass *= math.exp(-31.0 * moment)
        sparkle = 0.08 * math.sin(2 * math.pi * 2380 * moment + 1.1)
        sparkle *= math.exp(-52.0 * moment)

        signal = attack * tail * (drop + glass + sparkle)
        sample = int(32767 * 0.052 * signal)
        frames.extend(struct.pack('<h', sample))
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return buffer.getvalue()


def license_allows_module(key_info, module):
    """Licenças antigas mantêm tudo ativo até a API habilitar módulos."""
    if not isinstance(key_info, dict) or key_info.get('modulesEnforced') is not True:
        return True
    modules = key_info.get('modules')
    if not isinstance(modules, (list, tuple, set)):
        return False
    if module == MODULE_CYCLE:
        return MODULE_PURCHASE in modules and MODULE_SELL in modules
    return module in modules


def build_control_state(run, mode, auto_cycle=False, preserve_position=False):
    """Cria o contrato único enviado da interface para o motor do bot."""
    return {
        'run': bool(run),
        'mode': mode,
        'auto_cycle': bool(auto_cycle),
        'preserve_position': bool(preserve_position),
    }


def build_mini_hud_state(running=False, sell_running=False, cycle_running=False,
                         closing_orders=False, protected_pause=False,
                         intervention_required=False, buy_paused=False,
                         shopping_running=False, shopping_paused=False):
    """Estado textual do controle compacto, independente dos widgets Tk."""
    if intervention_required:
        operation = 'INTERVENÇÃO NECESSÁRIA'
    elif closing_orders:
        operation = 'FECHANDO ORDENS'
    elif cycle_running:
        operation = 'CICLO ATIVO'
    elif sell_running:
        operation = 'VENDA ATIVA'
    elif running:
        operation = 'COMPRA ATIVA'
    elif shopping_running:
        operation = 'COMPRA PROGRAMADA ATIVA'
    elif buy_paused:
        operation = 'COMPRA EM PAUSA'
    elif shopping_paused:
        operation = 'COMPRA PROGRAMADA EM PAUSA'
    else:
        operation = 'AUTOMAÇÃO PARADA'
    return {
        'operation': operation,
        'active': bool(
            running or sell_running or cycle_running or closing_orders or shopping_running
        ),
        'protected_pause': bool(protected_pause),
        'intervention_required': bool(intervention_required),
    }


def format_mini_elapsed(seconds):
    total = max(0, int(seconds or 0))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def aplicar_cantos_arredondados(toplevel):
    """Aplica bordas arredondadas nativas do Windows 11 na janela."""
    # ***<module>.aplicar_cantos_arredondados: Failure detected at line number 10 and instruction offset 22: Different bytecode
    try:
        hwnd = toplevel.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int))
    except:
        return None
def aplicar_efeito_blur_janela(toplevel, alpha_val=0.92, accent_state=3, tint_color=2416446745):
    # irreducible cflow, using cdg fallback
    """Aplica o efeito de vidro fosco (Acrylic/Aero Blur) nativo do Windows 10/11."""
    # ***<module>.aplicar_efeito_blur_janela: Failure: Compilation Error
    toplevel.update()
    hwnd = toplevel.winfo_id()
    class ACCENT_POLICY(Structure):
        # ***<module>.aplicar_efeito_blur_janela.ACCENT_POLICY: Failure: Compilation Error
        __module__ = __name__
        _fields_ = [('AnimationId', c_int), ('AnimationId', c_int)]
    class WINDOWCOMPOSITIONATTRIBDATA(Structure):
        # ***<module>.aplicar_efeito_blur_janela.WINDOWCOMPOSITIONATTRIBDATA: Failure: Compilation Error
        __module__ = __name__
        _fields_ = [('SizeOfData', c_int), ('SizeOfData', c_int)]
    accent = ACCENT_POLICY()
    accent.AccentState = accent_state
    accent.AccentFlags = 2
    accent.GradientColor = tint_color
    accent.AnimationId = 0
    data = WINDOWCOMPOSITIONATTRIBDATA()
    data.Attribute = 19
    try:
        ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, byref(data))
        toplevel.attributes('-alpha', alpha_val)
    except Exception as e:
        toplevel.attributes('-alpha', alpha_val)
def get_window_background_asset(w, h):
    # ***<module>.get_window_background_asset: Failure detected at line number 24 and instruction offset 38: Different bytecode
    key = (w, h)
    if key not in GLOBAL_WINDOW_BG_CACHE:
        scale = 3
        w_s = w * scale
        h_s = h * scale
        im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        r_s = 18 * scale
        draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (0, 3, 10, 255))
        draw_rounded_rectangle(draw, [2 * scale, 2 * scale, w_s - 2 * scale, h_s - 2 * scale], r_s - 2 * scale, (39, 72, 106, 255))
        draw_rounded_rectangle(draw, [4 * scale, 4 * scale, w_s - 4 * scale, h_s - 4 * scale], r_s - 4 * scale, (221, 177, 99, 255))
        draw_rounded_rectangle(draw, [6 * scale, 6 * scale, w_s - 6 * scale, h_s - 6 * scale], r_s - 6 * scale, (6, 16, 31, 255))
        bg_im = Image.new('RGBA', (w_s, h_s), (1, 1, 1, 255))
        bg_im.alpha_composite(im)
        resized = bg_im.resize((w, h), Image.Resampling.LANCZOS)
        GLOBAL_WINDOW_BG_CACHE[key] = ImageTk.PhotoImage(resized)
    return GLOBAL_WINDOW_BG_CACHE[key]
GLOBAL_SPLASH_BG_CACHE = {}
def get_splash_background_asset(w, h):
    # ***<module>.get_splash_background_asset: Failure detected at line number 42 and instruction offset 38: Different bytecode
    key = (w, h)
    if key not in GLOBAL_SPLASH_BG_CACHE:
        scale = 3
        w_s = w * scale
        h_s = h * scale
        im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        r_s = 20 * scale
        draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (0, 3, 10, 255))
        draw_rounded_rectangle(draw, [2 * scale, 2 * scale, w_s - 2 * scale, h_s - 2 * scale], r_s - 2 * scale, (39, 72, 106, 255))
        draw_rounded_rectangle(draw, [4 * scale, 4 * scale, w_s - 4 * scale, h_s - 4 * scale], r_s - 4 * scale, (221, 177, 99, 255))
        draw_rounded_rectangle(draw, [6 * scale, 6 * scale, w_s - 6 * scale, h_s - 6 * scale], r_s - 6 * scale, (2, 9, 22, 255))
        bg_im = Image.new('RGBA', (w_s, h_s), (1, 1, 1, 255))
        bg_im.alpha_composite(im)
        resized = bg_im.resize((w, h), Image.Resampling.LANCZOS)
        GLOBAL_SPLASH_BG_CACHE[key] = ImageTk.PhotoImage(resized)
    return GLOBAL_SPLASH_BG_CACHE[key]
def get_medallion_asset(size=48):
    # irreducible cflow, using cdg fallback
    global GLOBAL_MEDALLION_REF
    # ***<module>.get_medallion_asset: Failure: Compilation Error
    if GLOBAL_MEDALLION_REF is None:
        icon_path = os.path.join('assets', 'icon.png')
        if os.path.exists(icon_path):
            tab_icon = Image.open(icon_path).convert('RGBA')
            bbox = tab_icon.getbbox()
            if bbox:
                tab_icon = tab_icon.crop(bbox)
            resized_icon = tab_icon.resize((size, size), Image.Resampling.LANCZOS)
            bg_im = Image.new('RGBA', (size, size), (1, 1, 1, 255))
            bg_im.alpha_composite(resized_icon)
            GLOBAL_MEDALLION_REF = ImageTk.PhotoImage(bg_im)
        else:
            scale = 3
            s = size * scale
            im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            draw.ellipse([1 * scale, 1 * scale, s - 1 * scale, s - 1 * scale], fill=(2, 9, 22, 255))
            draw.ellipse([3 * scale, 3 * scale, s - 3 * scale, s - 3 * scale], fill=(249, 209, 122, 255))
            draw.ellipse([6 * scale, 6 * scale, s - 6 * scale, s - 6 * scale], fill=(13, 40, 72, 255))
            cx = s / 2
            cy = s / 2
            draw.line([cx - 10 * scale, cy + 10 * scale, cx + 15 * scale, cy - 15 * scale], fill=(220, 220, 220, 255), width=2 * scale)
            draw.line([cx - 10 * scale - 5 * scale, cy + 10 * scale - 5 * scale, cx - 10 * scale + 5 * scale, cy + 10 * scale + 5 * scale], fill=(249, 209, 122, 255), width=2 * scale)
            draw.line([cx - 10 * scale, cy + 10 * scale, cx - 15 * scale, cy + 15 * scale], fill=(2, 9, 22, 255), width=2 * scale)
            draw.ellipse([cx - 17 * scale, cy + 15 * scale, cx - 15 * scale, cy + 17 * scale], fill=(249, 209, 122, 255))
            draw.line([cx + 10 * scale, cy + 10 * scale, cx - 15 * scale, cy - 15 * scale], fill=(220, 220, 220, 255), width=2 * scale)
            draw.line([cx + 10 * scale - 5 * scale, cy + 10 * scale + 5 * scale, cx + 10 * scale + 5 * scale, cy + 10 * scale - 5 * scale], fill=(249, 209, 122, 255), width=2 * scale)
            draw.line([cx + 10 * scale, cy + 10 * scale, cx + 15 * scale, cy + 15 * scale], fill=(2, 9, 22, 255), width=2 * scale)
            draw.ellipse([cx + 15 * scale, cy + 15 * scale, cx + 17 * scale, cy + 17 * scale], fill=(249, 209, 122, 255))
            bg_im = Image.new('RGBA', (s, s), (1, 1, 1, 255))
            bg_im.alpha_composite(im)
            resized = bg_im.resize((size, size), Image.Resampling.LANCZOS)
    return GLOBAL_MEDALLION_REF
def draw_rounded_rectangle(draw, bounds, radius, fill):
    try:
        draw.rounded_rectangle(bounds, radius=radius, fill=fill)
    except AttributeError:
        x0, y0, x1, y1 = bounds
        r = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
        if r <= 0:
            draw.rectangle(bounds, fill=fill)
            return None
        else:
            draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
            draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
            draw.ellipse([x0, y0, x0 + 2 * r, y0 + 2 * r], fill=fill)
            draw.ellipse([x1 - 2 * r, y0, x1, y0 + 2 * r], fill=fill)
            draw.ellipse([x0, y1 - 2 * r, x0 + 2 * r, y1], fill=fill)
            draw.ellipse([x1 - 2 * r, y1 - 2 * r, x1, y1], fill=fill)
def generate_puffy_asset(w, h, asset_type, state='normal', text='', sub_text='', is_checked=False):
    # ***<module>.generate_puffy_asset: Failure: Compilation Error
    w = w
    h = max(1, int(h))
    scale = 3
    w_s = w * scale
    h_s = h * scale
    im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    r_s = int(min(w_s, h_s) * 0.28)
    if asset_type in ['green_btn', 'gold_btn', 'red_btn']:
        if asset_type == 'green_btn':
            if state == 'hover':
                base = (24, 74, 121, 255)
                shadow = (5, 24, 48, 255)
            else:
                if state == 'pressed':
                    base = (8, 42, 78, 255)
                    shadow = (1, 13, 30, 255)
                else:
                    base = (13, 55, 94, 255)
                    shadow = (3, 22, 45, 255)
            text_color = (253, 230, 157, 255)
            text_shadow = (0, 6, 18, 255)
            highlight = (249, 209, 122, 85)
        else:
            if asset_type == 'red_btn':
                if state == 'hover':
                    base = (243, 78, 78, 255)
                    shadow = (146, 35, 35, 255)
                else:
                    if state == 'pressed':
                        base = (171, 39, 39, 255)
                        shadow = (84, 15, 15, 255)
                    else:
                        base = (217, 60, 60, 255)
                        shadow = (116, 24, 24, 255)
                text_color = (255, 255, 255, 255)
                text_shadow = (70, 10, 10, 255)
                highlight = (255, 255, 255, 100)
            else:
                if state == 'hover':
                    base = (249, 209, 122, 255)
                    shadow = (148, 125, 76, 255)
                else:
                    if state == 'pressed':
                        base = (177, 137, 64, 255)
                        shadow = (79, 63, 34, 255)
                    else:
                        base = (221, 177, 99, 255)
                        shadow = (113, 88, 43, 255)
                text_color = (7, 25, 48, 255)
                text_shadow = (253, 230, 157, 120)
                highlight = (255, 255, 255, 120)
        shadow_im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_im)
        s_offset = 2 * scale
        draw_rounded_rectangle(s_draw, [2 * scale, 2 * scale + s_offset, w_s - 2 * scale, h_s - 2 * scale + s_offset], r_s, (0, 0, 0, 70))
        shadow_im = shadow_im.filter(ImageFilter.GaussianBlur(1.2 * scale))
        im.alpha_composite(shadow_im)
        bevel_thick = (5 if state!= 'pressed' else 2) * scale
        draw_rounded_rectangle(draw, [2 * scale, 2 * scale, w_s - 2 * scale, h_s - 2 * scale], r_s, shadow)
        face_rect = [2 * scale, 2 * scale, w_s - 2 * scale, h_s - 2 * scale - bevel_thick]
        draw_rounded_rectangle(draw, face_rect, r_s, base)
        if text == '▲':
            cx = w_s / 2
            cy = (h_s - bevel_thick) / 2
            if state == 'pressed':
                cy += 1.5 * scale
            sz = 4 * scale
            draw.polygon([(cx, cy - sz), (cx - sz * 1.2, cy + sz), (cx + sz * 1.2, cy + sz)], fill=text_color)
        elif text == '▼':
            cx = w_s / 2
            cy = (h_s - bevel_thick) / 2
            if state == 'pressed':
                cy += 1.5 * scale
            sz = 4 * scale
            draw.polygon([(cx, cy + sz), (cx - sz * 1.2, cy - sz), (cx + sz * 1.2, cy - sz)], fill=text_color)
        else:
            font_size = int(h * 0.35)
            try:
                font = ImageFont.truetype('ariblk.ttf', font_size * scale)
            except:
                try:
                    font = ImageFont.truetype('arialbd.ttf', font_size * scale)
                except:
                    font = ImageFont.load_default()
            text_str = str(text)
            draw_play = False
            draw_stop = False
            if text_str.startswith('▶ '):
                text_str = text_str.replace('▶ ', '')
                draw_play = True
            elif text_str.startswith('■ '):
                text_str = text_str.replace('■ ', '')
                draw_stop = True
            try:
                bbox = draw.textbbox((0, 0), text_str, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except:
                text_w, text_h = (len(text_str) * font_size * 0.6 * scale, font_size * scale)
            face_center_x = w_s / 2
            face_center_y = (h_s - bevel_thick) / 2
            extra_w = 10 * scale if draw_play or draw_stop else 0
            text_x = face_center_x - (text_w + extra_w) / 2
            text_y = face_center_y - text_h / 2 - 2 * scale
            if state == 'pressed':
                text_y += 2 * scale
            draw.text((text_x + extra_w + 1 * scale, text_y + 1.5 * scale), text_str, font=font, fill=text_shadow)
            draw.text((text_x + extra_w, text_y), text_str, font=font, fill=text_color)
            if draw_play:
                ix = text_x + 3 * scale
                iy = face_center_y
                if state == 'pressed':
                    iy += 2 * scale
                sz = 3.5 * scale
                draw.polygon([(ix - sz * 0.5 + 1 * scale, iy - sz + 1.5 * scale), (ix - sz * 0.5 + 1 * scale, iy + sz + 1.5 * scale), (ix + sz + 1 * scale, iy + 1.5 * scale)], fill=text_shadow)
                draw.polygon([(ix - sz * 0.5, iy - sz), (ix - sz * 0.5, iy + sz), (ix + sz, iy)], fill=text_color)
            elif draw_stop:
                ix = text_x + 3 * scale
                iy = face_center_y
                if state == 'pressed':
                    iy += 2 * scale
                sz = 3 * scale
                draw.rectangle([ix - sz + 1 * scale, iy - sz + 1.5 * scale, ix + sz + 1 * scale, iy + sz + 1.5 * scale], fill=text_shadow)
                draw.rectangle([ix - sz, iy - sz, ix + sz, iy + sz], fill=text_color)
    else:
        if asset_type == 'header_btn':
            r_s = int(min(w_s, h_s) * 0.2)
            if state == 'hover':
                base = (24, 74, 121, 255)
                shadow = (221, 177, 99, 255)
            else:
                if state == 'pressed':
                    base = (5, 31, 61, 255)
                    shadow = (113, 88, 43, 255)
                else:
                    base = (10, 36, 67, 255)
                    shadow = (39, 72, 106, 255)
            highlight = (255, 255, 255, 120)
            icon_color = (249, 209, 122, 255)
            shadow_im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow_im)
            s_offset = 1.5 * scale
            draw_rounded_rectangle(s_draw, [1 * scale, 1 * scale + s_offset, w_s - 1 * scale, h_s - 1 * scale + s_offset], r_s, (0, 0, 0, 70))
            shadow_im = shadow_im.filter(ImageFilter.GaussianBlur(0.8 * scale))
            im.alpha_composite(shadow_im)
            bevel_thick = (3 if state!= 'pressed' else 1) * scale
            draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w_s - 1 * scale, h_s - 1 * scale], r_s, shadow)
            draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w_s - 1 * scale, h_s - 1 * scale - bevel_thick], r_s, base)
            if state!= 'pressed':
                draw_rounded_rectangle(draw, [2 * scale, 2 * scale, w_s - 2 * scale, int((h_s - bevel_thick) * 0.4)], int(r_s * 0.8), highlight)
            font_size = int(h * 0.42)
            try:
                font = ImageFont.truetype('arialbd.ttf', font_size * scale)
            except:
                font = ImageFont.load_default()
            icon_str = str(text)
            try:
                bbox = draw.textbbox((0, 0), icon_str, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except:
                text_w, text_h = draw.textsize(icon_str, font=font) if hasattr(draw, 'textsize') else (len(icon_str) * font_size * 0.6 * scale, font_size * scale)
            face_center_x = w_s / 2
            face_center_y = (h_s - bevel_thick) / 2
            text_x = face_center_x - text_w / 2
            text_y = face_center_y - text_h / 2 - 1.5 * scale
            if state == 'pressed':
                text_y += 1.5 * scale
            draw.text((text_x, text_y), icon_str, font=font, fill=icon_color)
        else:
            if asset_type == 'checkbox':
                r_s = int(min(w_s, h_s) * 0.25)
                base_color = (4, 16, 32, 255)
                border_color = (39, 72, 106, 255)
                draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, border_color)
                draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w_s - 1 * scale, h_s - 1 * scale], r_s, base_color)
                shadow_im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
                s_draw = ImageDraw.Draw(shadow_im)
                draw_rounded_rectangle(s_draw, [2 * scale, 2 * scale, w_s - 2 * scale, h_s - 2 * scale], r_s, (0, 0, 0, 160))
                shadow_im = shadow_im.filter(ImageFilter.GaussianBlur(1.0 * scale))
                im.alpha_composite(shadow_im)
                if is_checked:
                    tick_color = (249, 209, 122, 255)
                    tick_shadow = (7, 25, 48, 255)
                    font_size = int(h * 0.65)
                    try:
                        font = ImageFont.truetype('ariblk.ttf', font_size * scale)
                    except:
                        try:
                            font = ImageFont.truetype('arialbd.ttf', font_size * scale)
                        except:
                            font = ImageFont.load_default()
                    tick_str = '✔'
                    try:
                        bbox = draw.textbbox((0, 0), tick_str, font=font)
                        t_w = bbox[2] - bbox[0]
                        t_h = bbox[3] - bbox[1]
                    except:
                        t_w, t_h = draw.textsize(tick_str, font=font) if hasattr(draw, 'textsize') else (font_size * 0.7 * scale, font_size * scale)
                    tick_x = (w_s - t_w) / 2
                    tick_y = (h_s - t_h) / 2 - 1.5 * scale
                    draw.text((tick_x + 1 * scale, tick_y + 1.5 * scale), tick_str, font=font, fill=tick_shadow)
                    draw.text((tick_x, tick_y), tick_str, font=font, fill=tick_color)
            else:
                if asset_type == 'status_card':
                    r_s = int(min(w_s, h_s) * 0.15)
                    border_color = (39, 72, 106, 255)
                    inner_bg = (7, 25, 48, 255)
                    draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, border_color)
                    draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w_s - 1 * scale, h_s - 1 * scale], r_s, inner_bg)
                    shadow_im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
                    s_draw = ImageDraw.Draw(shadow_im)
                    draw_rounded_rectangle(s_draw, [2 * scale, 2 * scale, w_s - 2 * scale, h_s - 2 * scale], r_s, (0, 0, 0, 140))
                    shadow_im = shadow_im.filter(ImageFilter.GaussianBlur(1.0 * scale))
                    im.alpha_composite(shadow_im)
                else:
                    if asset_type in ['tab_active', 'tab_inactive']:
                        r_s = int(min(w_s, h_s) * 0.28)
                        if asset_type == 'tab_active':
                            base = (13, 40, 72, 255)
                            shadow = (221, 177, 99, 255)
                            text_color = (249, 209, 122, 255)
                            text_shadow = (0, 0, 0, 160)
                            highlight = (255, 255, 255, 60)
                        else:
                            base = (4, 16, 32, 255)
                            shadow = (0, 9, 24, 255)
                            text_color = (156, 175, 196, 255)
                            text_shadow = (0, 0, 0, 0)
                            highlight = (0, 0, 0, 0)
                        draw.rectangle([0, 0, w_s, h_s], fill=shadow)
                        draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, shadow)
                        draw.rectangle([1 * scale, 1 * scale, w_s - 1 * scale, h_s], fill=base)
                        draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w_s - 1 * scale, h_s - 1 * scale], r_s, base)
                        if highlight[3] > 0:
                            draw_rounded_rectangle(draw, [2 * scale, 2 * scale, w_s - 2 * scale, int(h_s * 0.4)], int(r_s * 0.8), highlight)
                        icon_path = os.path.join('assets', f'icon_{str(text).lower()}.png')
                        icon_loaded = False
                        try:
                            if os.path.exists(icon_path):
                                tab_icon = Image.open(icon_path).convert('RGBA')
                                bbox = tab_icon.getbbox()
                                if bbox:
                                    tab_icon = tab_icon.crop(bbox)
                                max_sz = int(h_s * 0.8)
                                if str(text).lower() == 'edit':
                                    max_sz = int(h_s * 0.6)
                                else:
                                    if str(text).lower() == 'seq':
                                        max_sz = int(h_s * 0.75)
                                iw, ih = tab_icon.size
                                if iw > 0 and ih > 0:
                                        ratio = min(max_sz / iw, max_sz / ih)
                                        new_w, new_h = (int(iw * ratio), int(ih * ratio))
                                        tab_icon = tab_icon.resize((new_w, new_h), Image.Resampling.LANCZOS)
                                        ix = int((w_s - new_w) / 2)
                                        iy = int((h_s - new_h) / 2)
                                        im.paste(tab_icon, (ix, iy), tab_icon)
                                icon_loaded = True
                                icon_loaded = True
                        except:
                            pass
                        if not icon_loaded:
                            font_size = int(h * 0.35)
                            try:
                                font = ImageFont.truetype('ariblk.ttf', font_size * scale)
                            except:
                                font = ImageFont.load_default()
                            text_str = str(text)
                            try:
                                bbox = draw.textbbox((0, 0), text_str, font=font)
                                text_w = bbox[2] - bbox[0]
                                text_h = bbox[3] - bbox[1]
                            except:
                                text_w, text_h = draw.textsize(text_str, font=font) if hasattr(draw, 'textsize') else (len(text_str) * font_size * 0.6 * scale, font_size * scale)
                            face_center_x = w_s / 2
                            face_center_y = h_s / 2
                            text_x = face_center_x - text_w / 2
                            text_y = face_center_y - text_h / 2 - 1.5 * scale
                            if text_shadow[3] > 0:
                                draw.text((text_x + 1 * scale, text_y + 1 * scale), text_str, font=font, fill=text_shadow)
                            draw.text((text_x, text_y), text_str, font=font, fill=text_color)
    resized = im.resize((w, h), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(resized)
def get_puffy_asset(w, h, asset_type, state='normal', text='', sub_text='', is_checked=False):
    key = (w, h, asset_type, state, text, sub_text, is_checked)
    if key not in GLOBAL_PUFFY_CACHE:
        GLOBAL_PUFFY_CACHE[key] = generate_puffy_asset(w, h, asset_type, state, text, sub_text, is_checked)
    return GLOBAL_PUFFY_CACHE[key]
def get_albion_window():
    # irreducible cflow, using cdg fallback
    # ***<module>.get_albion_window: Failure: Compilation Error
    win = gw.getWindowsWithTitle('Albion Online Client')
    if not win:
        win = gw.getWindowsWithTitle('Albion Online')
    if win:
        return win[0]
    return None
# ─── Design system local do MKT ─────────────────────────────────────────────
# A automação não consulta estes tokens. Eles centralizam somente apresentação
# e impedem que novos componentes criem cores, fontes e medidas aleatórias.
UI_COLORS = {
    'background': '#070c14',
    'navigation': '#030812',
    'header': '#0b1725',
    'surface': '#0d1c2e',
    'surface_raised': '#12243a',
    'surface_alt': '#091624',
    'surface_hover': '#17314e',
    'field': '#07111e',
    'border': '#294866',
    'accent': '#e7c36f',
    'accent_muted': '#8e7848',
    'text': '#f4f1e8',
    'text_secondary': '#a4b3c3',
    'text_tertiary': '#70869b',
    'success': '#45b891',
    'success_surface': '#10342e',
    'success_text': '#8fdfc3',
    'warning': '#d8a34a',
    'danger': '#c65a65',
}

UI_SPACING = {
    'xs': 4,
    'sm': 8,
    'md': 12,
    'lg': 16,
    'xl': 20,
    '2xl': 24,
    '3xl': 32,
}

UI_FONTS = {
    'page_title': ('Segoe UI Semibold', 14),
    'section_title': ('Segoe UI Semibold', 10),
    'body': ('Segoe UI', 9),
    'body_strong': ('Segoe UI Semibold', 9),
    'caption': ('Segoe UI', 8),
    'caption_strong': ('Segoe UI Semibold', 8),
    'micro': ('Segoe UI Semibold', 7),
    'mono': ('Consolas', 8),
}

UI_RADII = {'control': 7, 'card': 10, 'window': 18}

COLOR_BG = UI_COLORS['background']
COLOR_CARD = UI_COLORS['surface']
COLOR_ACCENT = UI_COLORS['accent']
COLOR_ACCENT_DIM = UI_COLORS['accent_muted']
COLOR_TEXT = UI_COLORS['text']
COLOR_TEXT_DIM = UI_COLORS['text_secondary']
COLOR_SUCCESS = UI_COLORS['success']
COLOR_ERROR = UI_COLORS['danger']
COLOR_BORDER = UI_COLORS['border']
COLOR_SIDEBAR = UI_COLORS['header']
COLOR_NAV = UI_COLORS['navigation']

# Largura operacional segura. O painel fica ancorado à lateral esquerda do
# Albion; acima deste valor ele invade a área calibrada da loja em 1600x900 e
# a proteção contra janelas sobrepostas bloqueia a automação corretamente.
PANEL_SAFE_WIDTH = 390
MINI_HUD_WIDTH = 318
MINI_HUD_HEIGHT = 140
# Tempo apenas entre recolher a interface e liberar a primeira acao. O atraso
# nao e usado entre itens, paginas, categorias ou etapas do ciclo.
AUTOMATION_START_GUARD_SECONDS = 0.4


def ui_rgba(hex_color, alpha=255):
    value = hex_color.lstrip('#')
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) + (alpha,)


def draw_canvas_rounded_rectangle(canvas, x1, y1, x2, y2, radius, **kwargs):
    """Desenha um retângulo arredondado leve sem alterar a geometria do widget."""
    radius = max(1, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = (
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    )
    return canvas.create_polygon(
        points, smooth=True, splinesteps=24, **kwargs
    )


ITEM_ICON_CACHE_DIR = os.path.join(str(cache_dir()), 'item_icons')
ITEM_ICON_BUNDLED_DIR = os.path.join(_BASE_DIR, 'assets', 'item_cache')


def split_item_name_and_enchantment(item_name):
    """Separa o sufixo visual ``.0``-``.4`` reconhecido pelo bot."""
    clean_name = ' '.join(str(item_name or 'Item').split())
    match = re.search(r'\s+\.([0-4])$', clean_name)
    if not match:
        return clean_name, 0
    return clean_name[:match.start()].strip(), int(match.group(1))


def item_icon_cache_paths(item_name):
    """Gera nomes locais determinísticos sem confiar no texto OCR como caminho."""
    normalized = unicodedata.normalize('NFKD', str(item_name or 'Item'))
    ascii_name = normalized.encode('ascii', 'ignore').decode('ascii').lower()
    slug = re.sub(r'[^a-z0-9]+', '_', ascii_name).strip('_')[:52] or 'item'
    digest = hashlib.sha1(str(item_name or 'Item').encode('utf-8')).hexdigest()[:10]
    stem = f'{slug}_{digest}'
    return (
        os.path.join(ITEM_ICON_CACHE_DIR, f'{stem}_capture.png'),
        os.path.join(ITEM_ICON_CACHE_DIR, f'{stem}_render.png'),
    )


def bundled_item_icon_cache_paths(item_name):
    capture_path, render_path = item_icon_cache_paths(item_name)
    return (
        os.path.join(ITEM_ICON_BUNDLED_DIR, os.path.basename(capture_path)),
        os.path.join(ITEM_ICON_BUNDLED_DIR, os.path.basename(render_path)),
    )


def build_item_render_url(item_name):
    """Monta a URL de render usando o nome localizado em português."""
    base_name, enchantment = split_item_name_and_enchantment(item_name)
    identifier = base_name + (f'@{enchantment}' if enchantment else '')
    encoded = quote(identifier, safe='@')
    return (
        f'https://render.albiononline.com/v1/item/{encoded}.png'
        '?quality=1&size=217&locale=pt'
    )


def prepare_notification_item_icon(item_image, size):
    """Normaliza um recorte ou render para exibição nítida na notificação."""
    if not isinstance(item_image, Image.Image):
        return None
    image = item_image.convert('RGBA')
    alpha_bounds = image.getchannel('A').getbbox()
    if alpha_bounds:
        image = image.crop(alpha_bounds)
    width, height = image.size
    if width <= 0 or height <= 0:
        return None
    side = max(width, height)
    square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    square.alpha_composite(image, ((side - width) // 2, (side - height) // 2))
    return square.resize((size, size), Image.Resampling.LANCZOS)


def get_window_background_asset(w, h):
    """Moldura leve de HUD, sem relevos que lembrem controles antigos."""
    key = ('modern_hud', w, h)
    if key not in GLOBAL_WINDOW_BG_CACHE:
        scale = 3
        ws, hs = w * scale, h * scale
        image = Image.new('RGBA', (ws, hs), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        radius = 18 * scale
        draw_rounded_rectangle(draw, (0, 2 * scale, ws, hs), radius, (0, 0, 0, 170))
        draw_rounded_rectangle(draw, (scale, 0, ws - scale, hs - 2 * scale), radius,
                               ui_rgba(COLOR_BORDER))
        draw_rounded_rectangle(draw, (2 * scale, scale, ws - 2 * scale, hs - 3 * scale),
                               radius - scale, ui_rgba(COLOR_BG))
        draw.line((20 * scale, 2 * scale, ws - 20 * scale, 2 * scale),
                  fill=ui_rgba(COLOR_SIDEBAR, 230), width=scale)
        draw.line((ws // 2 - 34 * scale, 2 * scale, ws // 2 + 34 * scale, 2 * scale),
                  fill=ui_rgba(COLOR_ACCENT, 230), width=scale)
        opaque = Image.new('RGBA', (ws, hs), (1, 1, 1, 255))
        opaque.alpha_composite(image)
        rendered = opaque.resize((w, h), Image.Resampling.LANCZOS)
        GLOBAL_WINDOW_BG_CACHE[key] = ImageTk.PhotoImage(rendered)
    return GLOBAL_WINDOW_BG_CACHE[key]


def get_splash_background_asset(w, h):
    key = ('modern_hud', w, h)
    if key not in GLOBAL_SPLASH_BG_CACHE:
        scale = 3
        ws, hs = w * scale, h * scale
        image = Image.new('RGBA', (ws, hs), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        radius = 18 * scale
        draw_rounded_rectangle(draw, (0, 2 * scale, ws, hs), radius, (0, 0, 0, 170))
        draw_rounded_rectangle(draw, (scale, 0, ws - scale, hs - 2 * scale), radius, ui_rgba(COLOR_BORDER))
        draw_rounded_rectangle(draw, (2 * scale, scale, ws - 2 * scale, hs - 3 * scale),
                               radius - scale, ui_rgba(COLOR_NAV))
        draw.line((18 * scale, 2 * scale, ws - 18 * scale, 2 * scale),
                  fill=ui_rgba(COLOR_ACCENT, 230), width=scale)
        opaque = Image.new('RGBA', (ws, hs), (1, 1, 1, 255))
        opaque.alpha_composite(image)
        GLOBAL_SPLASH_BG_CACHE[key] = ImageTk.PhotoImage(opaque.resize((w, h), Image.Resampling.LANCZOS))
    return GLOBAL_SPLASH_BG_CACHE[key]


def generate_puffy_asset(w, h, asset_type, state='normal', text='', sub_text='', is_checked=False):
    """Componentes de HUD contemporâneo com detalhes discretos de fantasia."""
    w = max(1, int(w))
    h = max(1, int(h))
    scale = 3
    ws, hs = w * scale, h * scale
    image = Image.new('RGBA', (ws, hs), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    parchment = ui_rgba(COLOR_TEXT)
    muted = ui_rgba(COLOR_TEXT_DIM)
    bronze = ui_rgba(COLOR_ACCENT)
    iron = ui_rgba(COLOR_CARD)
    iron_dark = ui_rgba(COLOR_NAV)

    def font_for(size, serif=False):
        candidates = ('bahnschrift.ttf', 'segoeuib.ttf', 'arialbd.ttf')
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, max(7, int(size)) * scale)
            except Exception:
                pass
        return ImageFont.load_default()

    def centered_label(label, color=parchment, offset_y=0, icon=None):
        label = str(label)
        if label in ('▲', '▼'):
            cx, cy = ws / 2, hs / 2 + offset_y
            half = 4 * scale
            points = ((cx, cy - half), (cx - half, cy + half), (cx + half, cy + half))
            if label == '▼':
                points = ((cx - half, cy - half), (cx + half, cy - half), (cx, cy + half))
            draw.polygon(points, fill=color)
            return
        draw_play = label.startswith('▶ ')
        draw_stop = label.startswith('■ ')
        if draw_play or draw_stop:
            label = label[2:]
        font = font_for(h * 0.31, serif=False)
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = len(label) * 6 * scale, 9 * scale
        icon_space = 12 * scale if draw_play or draw_stop or icon else 0
        tx = (ws - tw - icon_space) / 2 + icon_space
        ty = (hs - th) / 2 - 1.5 * scale + offset_y
        draw.text((tx, ty), label, font=font, fill=color)
        if draw_play or draw_stop:
            ix, iy = tx - 8 * scale, hs / 2 + offset_y
            if draw_play:
                draw.polygon(((ix - 2 * scale, iy - 4 * scale),
                              (ix - 2 * scale, iy + 4 * scale),
                              (ix + 4 * scale, iy)), fill=color)
            else:
                draw.rectangle((ix - 3 * scale, iy - 3 * scale,
                                ix + 3 * scale, iy + 3 * scale), fill=color)

    if asset_type in ('green_btn', 'gold_btn', 'red_btn'):
        palettes = {
            # Primary: contraste imediato para a única ação dominante da tela.
            'green_btn': ((20, 91, 70), (13, 66, 51), (27, 116, 88), (69, 184, 145)),
            # Secondary: superfície neutra com acabamento dourado da marca.
            'gold_btn': ((13, 35, 58), (8, 26, 45), (20, 54, 86), (142, 120, 72)),
            # Danger: reservado para parar, zerar ou remover.
            'red_btn': ((82, 36, 46), (61, 27, 35), (105, 45, 57), (173, 75, 88)),
        }
        normal, pressed, hover, border = palettes[asset_type]
        face_rgb = pressed if state == 'pressed' else hover if state == 'hover' else normal
        radius = max(5 * scale, int(min(ws, hs) * 0.24))
        y_shift = scale if state == 'pressed' else 0
        draw_rounded_rectangle(draw, (scale, 2 * scale + y_shift, ws - scale, hs - scale + y_shift),
                               radius, (0, 0, 0, 90))
        draw_rounded_rectangle(draw, (scale, scale + y_shift, ws - scale, hs - 2 * scale + y_shift),
                               radius, (*border, 255))
        draw_rounded_rectangle(draw, (2 * scale, 2 * scale + y_shift, ws - 2 * scale, hs - 3 * scale + y_shift),
                               max(scale, radius - scale), (*face_rgb, 255))
        draw.line((7 * scale, 3 * scale + y_shift, ws - 7 * scale, 3 * scale + y_shift),
                  fill=(255, 255, 255, 20), width=scale)
        button_text = (247, 249, 250, 255) if asset_type == 'green_btn' else parchment
        centered_label(text, button_text, offset_y=y_shift)

    elif asset_type == 'header_btn':
        radius = max(3 * scale, int(min(ws, hs) * 0.22))
        face = ui_rgba(UI_COLORS['surface_hover']) if state == 'hover' else ui_rgba(COLOR_CARD)
        if state == 'pressed':
            face = ui_rgba(UI_COLORS['surface_raised'])
        draw_rounded_rectangle(draw, (0, 0, ws, hs), radius, ui_rgba(COLOR_BORDER))
        draw_rounded_rectangle(draw, (scale, scale, ws - scale, hs - scale), radius - scale, face)
        centered_label(text, parchment)

    elif asset_type == 'checkbox':
        radius = max(3 * scale, int(min(ws, hs) * 0.22))
        border = ui_rgba(COLOR_ACCENT) if is_checked else ui_rgba(COLOR_BORDER)
        draw_rounded_rectangle(draw, (0, 0, ws, hs), radius, border)
        draw_rounded_rectangle(draw, (scale, scale, ws - scale, hs - scale),
                               max(scale, radius - scale), ui_rgba(COLOR_CARD))
        if is_checked:
            font = font_for(h * 0.58)
            mark = '✓'
            try:
                bbox = draw.textbbox((0, 0), mark, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                tw, th = 8 * scale, 10 * scale
            draw.text(((ws - tw) / 2, (hs - th) / 2 - scale), mark, font=font, fill=ui_rgba(COLOR_ACCENT))

    elif asset_type == 'status_card':
        radius = max(4 * scale, int(min(ws, hs) * 0.15))
        draw_rounded_rectangle(draw, (0, 0, ws, hs), radius, ui_rgba(COLOR_BORDER))
        draw_rounded_rectangle(draw, (scale, scale, ws - scale, hs - scale), radius - scale, iron)

    elif asset_type in ('tab_active', 'tab_inactive'):
        active = asset_type == 'tab_active'
        draw.rectangle(
            (0, 0, ws, hs),
            fill=ui_rgba(UI_COLORS['surface_raised']) if active else ui_rgba(COLOR_NAV),
        )
        draw.line((8 * scale, hs - 2 * scale, ws - 8 * scale, hs - 2 * scale),
                  fill=bronze if active else ui_rgba(COLOR_BORDER), width=2 * scale)
        icon_path = os.path.join('assets', f'icon_{str(text).lower()}.png')
        icon_loaded = False
        try:
            if os.path.exists(icon_path):
                icon_image = Image.open(icon_path).convert('RGBA')
                bbox = icon_image.getbbox()
                if bbox:
                    icon_image = icon_image.crop(bbox)
                max_size = int(hs * (0.72 if active else 0.64))
                ratio = min(max_size / icon_image.width, max_size / icon_image.height)
                icon_image = icon_image.resize((max(1, int(icon_image.width * ratio)),
                                                max(1, int(icon_image.height * ratio))),
                                               Image.Resampling.LANCZOS)
                if not active:
                    icon_image = ImageEnhance.Brightness(icon_image).enhance(0.55)
                image.paste(icon_image, ((ws - icon_image.width) // 2, (hs - icon_image.height) // 2), icon_image)
                icon_loaded = True
        except Exception:
            pass
        if not icon_loaded:
            centered_label(text, bronze if active else muted)
    else:
        draw.rectangle((0, 0, ws, hs), fill=iron)
        centered_label(text, parchment)

    return ImageTk.PhotoImage(image.resize((w, h), Image.Resampling.LANCZOS))

OPTIONAL_CALIBRATION_KEYS = (
    ('compra_topo_cor', 'Cor da linha do topo em Pedidos de Compra'),
    ('preco_medio', 'Preço Médio (verificação de média semanal)'),
)

GUIDED_BUY_STEPS = (
    ('LOJA', 'Área da lista de itens', 'area_lista', 'area',
     'Deixe a lista de itens visível e contorne somente a área onde aparecem os produtos.'),
    ('LOJA', 'Amostra do botão Pedido', 'btn_pedido', 'area',
     'Contorne APENAS UM botão Pedido de Compra. Não selecione a coluna inteira.'),
    ('LOJA', 'Próxima página', 'btn_proxima', 'click',
     'Marque o centro da seta usada para avançar a página.'),
    ('ROLAGEM', 'Início do arraste para descer', 'drag_start', 'click',
     'Marque o ponto onde o arraste da barra de rolagem deve começar.'),
    ('ROLAGEM', 'Fim do arraste para descer', 'drag_end', 'click',
     'Marque o ponto final do arraste que revela os próximos itens.'),
    ('ROLAGEM', 'Início do retorno ao topo', 'top_start', 'click',
     'Marque o ponto onde começa o arraste para retornar ao topo.'),
    ('ROLAGEM', 'Fim do retorno ao topo', 'top_end', 'click',
     'Marque o ponto final do arraste que leva a lista ao topo.'),
    ('ITEM', 'Fechar modal / âncora', 'ancora', 'area',
     'Abra um item e contorne de forma justa o X usado para fechar o modal.'),
    ('LEITURA', 'Nome do item', 'nome', 'area',
     'Com o item aberto, contorne somente o texto do nome.'),
    ('LEITURA', 'Preço de venda', 'venda', 'area',
     'Contorne somente o valor de venda usado pelo bot.'),
    ('LEITURA', 'Preço de compra', 'compra', 'area',
     'Contorne somente o valor da ordem de compra.'),
    ('LEITURA', 'Ícone / encantamento', 'icone', 'area',
     'Contorne o ícone do item, incluindo a borda colorida.'),
    ('COMPRA', 'Botão aumentar (+)', 'btn_mais', 'click',
     'Marque o centro do botão + usado para aumentar a quantidade.'),
    ('COMPRA', 'Preço final no modal', 'preco_final_compra', 'area',
     'Depois de clicar no +, contorne SOMENTE o número exibido ao lado de Preço dentro do modal.'),
    ('COMPRA', 'Botão Criar Ordem', 'btn_criar', 'click',
     'Marque o centro do botão que cria a ordem de compra.'),
    ('CONFIRMAÇÃO', 'Botão SIM', 'btn_sim', 'area',
     'Abra a confirmação e contorne de forma justa o botão SIM.'),
    ('CONFIRMAÇÃO', 'Botão NÃO', 'btn_nao', 'area',
     'Com a confirmação aberta, contorne de forma justa o botão NÃO usado para cancelar.'),
)

GUIDED_CYCLE_STEPS = (
    ('CICLO', 'Contador / Transações concluídas', 'cycle_counter_area', 'area',
     'Contorne o botão lateral inteiro que mostra a quantidade de transações concluídas.'),
    ('CICLO', 'Número da página de compra', 'buy_page_number_area', 'area',
     'Na tela Criar Pedido de Compra, contorne somente o número entre as setas de página.'),
    ('CICLO', 'Botão Pegar todos', 'cycle_collect_all', 'click',
     'Abra Transações Concluídas e marque o centro do botão Pegar todos.'),
    ('CICLO', 'Abrir tela de venda', 'cycle_sell_menu', 'click',
     'Marque o centro do botão lateral que abre a tela Vender do Inventário.'),
    ('CICLO', 'Abrir ordem de compra', 'cycle_buy_menu', 'click',
     'Marque o centro do botão lateral que abre a tela Criar Pedido de Compra.'),
)

GUIDED_SELL_STEPS = (
    ('LISTA', 'Área dos botões Vender', 'sell_buttons_area', 'area',
     'Contorne a coluna onde podem aparecer todos os botões Vender visíveis na lista.'),
    ('LISTA', 'Amostra do botão Vender', 'sell_button_sample', 'area',
     'Contorne somente um botão Vender, de forma justa, para servir como referência visual.'),
    ('PREÇO', 'Botão diminuir (-)', 'sell_price_minus', 'click',
     'Com o item aberto para venda, marque o centro do botão menos usado para diminuir o preço.'),
    ('PREÇO', 'Área do valor da venda', 'sell_price_value', 'area',
     'Contorne somente o valor numérico exibido na barra de preço do pedido de venda.'),
    ('ITEM', 'Fechar item (X)', 'sell_close_button', 'click',
     'Marque o centro do X que fecha o item aberto e retorna para a lista de vendas.'),
    ('VENDA', 'Botão Criar', 'sell_create_button', 'click',
     'Marque o centro do botão Criar que confirma o pedido de venda.'),
)
class InstallerModal:
    def __init__(self, parent_root, log_callback):
        # ***<module>.InstallerModal.__init__: Failure detected at line number 85 and instruction offset 14: Different bytecode
        self.parent = parent_root
        self.log_callback = log_callback
        self.window = tk.Toplevel(parent_root)
        self.window.title('Instalador do Sistema')
        self.window.geometry('500x350')
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.config(bg=COLOR_BG)
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        w = 500
        h = 350
        self.window.geometry(f'{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}')
        self.container = tk.Frame(self.window, bg=COLOR_BG, highlightthickness=2, highlightbackground=COLOR_ACCENT)
        self.container.pack(fill='both', expand=True)
        self.header = tk.Frame(self.container, bg=COLOR_SIDEBAR, height=35)
        self.header.pack(fill='x')
        tk.Label(self.header, text='INSTALADOR DO SISTEMA', fg=COLOR_ACCENT, bg=COLOR_SIDEBAR, font=('Segoe UI Semibold', 9)).pack(side='left', padx=15)
        self.close_btn = tk.Button(self.header, text='✕', bg=COLOR_SIDEBAR, fg=COLOR_TEXT_DIM, font=('Arial', 11, 'bold'), relief='flat', bd=0, cursor='hand2', command=self.window.destroy)
        self.close_btn.pack(side='right', padx=10)
        self.console = scrolledtext.ScrolledText(self.container, bg='#010713', fg=COLOR_ACCENT, font=('Consolas', 8), height=12, relief='flat', padx=10, pady=10)
        self.console.pack(fill='both', expand=True, padx=15, pady=10)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.container, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill='x', padx=15, pady=(5, 0))
        self.progress_label = tk.Label(self.container, text='0%', bg=COLOR_BG, fg=COLOR_ACCENT, font=('Segoe UI Semibold', 8))
        self.progress_label.pack(pady=(0, 5))
        def update_progress_label(*args):
            self.progress_label.config(text=f'{int(self.progress_var.get())}%')
        self.progress_var.trace_add('write', update_progress_label)
        self.start_btn = tk.Button(self.container, text='INICIAR INSTALAÇÃO', bg=COLOR_ACCENT, fg=COLOR_NAV, font=('Segoe UI Semibold', 8), relief='flat', cursor='hand2', command=self.start_installation)
        self.start_btn.pack(pady=5)
        self.header.bind('<Button-1>', self.start_move)
        self.header.bind('<B1-Motion>', self.do_move)
    def start_move(self, event):
        self.x = event.x
        self.y = event.y
    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.window.winfo_x() + deltax
        y = self.window.winfo_y() + deltay
        self.window.geometry(f'+{x}+{y}')
    def log(self, msg):
        self._installer_log_queue.put(msg)
    def _poll_installer_log(self):
        # ***<module>.InstallerModal._poll_installer_log: Failure detected at line number 132 and instruction offset 22: Different bytecode
        try:
            while True:
                msg = self._installer_log_queue.get_nowait()
                self.console.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
                self.console.see('end')
                self.log_callback(f'[INSTALLER] {msg}')
                self.window.update_idletasks()
        except queue.Empty:
            pass
        self.window.after(100, self._poll_installer_log)
    def start_installation(self):
        # ***<module>.InstallerModal.start_installation: Failure detected at line number 141 and instruction offset 16: Different bytecode
        self.start_btn.config(state='disabled')
        threading.Thread(target=self.run_installation, daemon=True).start()
    def run_installation(self):
        try:
            self.log('Iniciando processo de instalação do zero...')
            self.progress_var.set(10)
            installer_path = os.path.join(os.getcwd(), 'python_installer.exe')
            creation_flags = 134217728
            self.log('Verificando Python...')
            has_python = False
            try:
                subprocess.run(['python', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
                has_python = True
            except:
                pass
            if not has_python:
                self.log('Python não encontrado. Baixando instalador do Python 3.11.9...')
                import urllib.request
                url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
                urllib.request.urlretrieve(url, installer_path)
                self.progress_var.set(30)
                self.log('Instalando Python 3.11.9 (silencioso). Por favor, aguarde...')
                cmd = f'\"{installer_path}\" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0'
                subprocess.run(cmd, shell=True, creationflags=creation_flags)
                self.log('Python instalado com sucesso!')
                os.environ['PATH'] += os.pathsep + 'C:\\Program Files\\Python311' + os.pathsep + 'C:\\Program Files\\Python311\\Scripts'
            else:
                self.log('Python já está instalado.')
            self.progress_var.set(50)
            def run_and_log(cmd_list):
                process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creation_flags)
                for line in iter(process.stdout.readline, ''):
                    self.log(line.strip()) if line else None
                process.stdout.close()
                process.wait()
                return process.returncode
            self.log('Atualizando o PIP...')
            run_and_log(['python', '-m', 'pip', 'install', '--upgrade', 'pip'])
            self.progress_var.set(60)
            self.log('Instalando todas as bibliotecas e dependências (pode demorar alguns minutos)...')
            all_deps = [
                'opencv-python',
                'pillow',
                'pyautogui',
                'keyboard',
                'pygetwindow',
                'easyocr',
                'torch',
                'torchvision',
                'numpy',
                'requests',
            ]
            for i, dep in enumerate(all_deps):
                self.log(f'[{i+1}/{len(all_deps)}] Instalando {dep}...')
                rc = run_and_log(['python', '-m', 'pip', 'install', dep])
                if rc == 0:
                    self.log(f'  OK: {dep} instalado com sucesso.')
                else:
                    self.log(f'  AVISO: {dep} pode ter tido um problema (codigo {rc}).')
                self.progress_var.set(60 + 30 * (i + 1) / len(all_deps))
            self.progress_var.set(90)
            self.log('Criando pastas de sistema...')
            if not os.path.exists('assets'):
                os.makedirs('assets')
            self.progress_var.set(100)
            if os.path.exists(installer_path):
                os.remove(installer_path)
            self.log('[OK] INSTALAÇÃO CONCLUÍDA COM SUCESSO!')
            self.start_btn.config(text='FECHAR', state='normal', command=self.window.destroy)
        except Exception as e:
            self.log(f'ERRO FATAL: {str(e)}')
            self.start_btn.config(text='FECHAR', state='normal', command=self.window.destroy)
_log_queue = queue.Queue()
class StdoutRedirector:
    def __init__(self, callback):
        self.callback = callback
    def write(self, string):
        if string.strip():
            _log_queue.put(string.strip())
    def flush(self):
        return None


def classify_operation_message(message):
    """Converte tokens existentes em telemetria sem alterar o protocolo legado."""
    line = str(message).strip()
    normalized = ''.join(
        char for char in unicodedata.normalize('NFKD', line.casefold())
        if not unicodedata.combining(char)
    )
    event = {'event': 'log', 'module': 'system', 'result': 'info'}
    if line.startswith('[DATA]'):
        parts = line.replace('[DATA] ', '', 1).split('|')
        event.update(event='opportunity_evaluated', module='purchase')
        if len(parts) >= 5:
            event['item'] = parts[0][:120]
            for key, value in (('sale_price', parts[1]), ('purchase_price', parts[2])):
                try:
                    event[key] = int(float(value))
                except (TypeError, ValueError):
                    pass
            event['approved'] = parts[4].strip() == '1'
            event['result'] = 'approved' if event['approved'] else 'skipped'
    elif line.startswith('[OCR_DIAG] '):
        event.update(module='purchase', diagnostic_type='item_ocr')
        try:
            diagnostic = json.loads(line.replace('[OCR_DIAG] ', '', 1))
            if isinstance(diagnostic, dict):
                event['diagnostic'] = diagnostic
        except (TypeError, ValueError, json.JSONDecodeError):
            event['diagnostic_parse_error'] = True
    elif line.startswith('[BUY]'):
        event.update(event='purchase_confirmed', module='purchase', result='success')
        try:
            event['estimated_margin'] = float(line.replace('[BUY] ', '', 1))
        except (TypeError, ValueError):
            pass
    elif line.startswith('[BUY_DETAIL] '):
        event.update(event='purchase_detail', module='purchase', result='success')
        try:
            detail = json.loads(line.replace('[BUY_DETAIL] ', '', 1))
            if isinstance(detail, dict):
                event['detail'] = detail
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    elif line.startswith('[VENDA] Pedido de venda criado com sucesso.'):
        event.update(event='sale_confirmed', module='sale', result='success')
    elif line.startswith('[CICLO]'):
        event.update(event='cycle_activity', module='cycle')
        if 'Coletando e abrindo vendas' in line or 'Aguardando 10 segundos' in line:
            event.update(event='cycle_transition', stage='collect')
        elif 'Coleta concluida e tela de venda confirmada' in line:
            event.update(event='cycle_transition', stage='sale')
        elif 'Tela de compra confirmada' in line:
            event.update(event='cycle_transition', stage='purchase')
    elif normalized.startswith('[!] pulando:'):
        # O resultado ja foi contabilizado pelo [DATA] imediatamente anterior.
        # Mantemos a explicacao apenas no diagnostico bruto, sem duplicar a
        # linha na lista de eventos.
        event.update(module='purchase', result='skipped')
    elif 'interrupcao instantanea' in normalized:
        event.update(event='automation_interrupted', result='info')
    elif (
        '[bloqueado]' in normalized
        or 'parada segura' in normalized
        or 'bloqueio financeiro' in normalized
        or 'operacao bloqueada' in normalized
        or 'calibragem bloqueada' in normalized
        or 'venda bloqueada' in normalized
        or 'clique fora da janela' in normalized
    ):
        event.update(event='safety_protection', result='protected')
    elif (
        'erro fatal' in normalized
        or 'erro na ' in normalized
        or 'erro ao ' in normalized
        or 'falha ao ' in normalized
        or 'nao foi possivel' in normalized
    ):
        event.update(event='operation_error', result='error')
    elif line.startswith('[!]'):
        # O nucleo usa [!] tambem para recuperacoes e avisos normais. O
        # prefixo sozinho nunca deve transformar a mensagem em erro.
        event.update(event='operational_notice', result='info')
    elif 'BOT INICIADO' in line or 'Bot de VENDA iniciado' in line or 'CICLO AUTOM' in line and 'iniciado' in line:
        event.update(event='automation_started', result='success')
    elif 'PAUSADO' in line or 'Standby' in line:
        event.update(event='automation_stopped')
    return event


class LogWindow:
    def __init__(self, parent):
        self.parent = parent
        log_root = str(logs_dir())
        try:
            os.makedirs(log_root, exist_ok=True)
            self.log_path = os.path.join(log_root, f"operacoes-{datetime.now():%Y-%m-%d}.log")
        except OSError:
            log_root = _BASE_DIR
            self.log_path = os.path.join(_BASE_DIR, f"operacoes-{datetime.now():%Y-%m-%d}.log")
        try:
            self.writer = BackgroundLogWriter(log_root)
            self.log_path = self.writer.raw_path_for()
        except OSError:
            self.writer = None

        self.visible = False
        self.current_view = 'summary'
        self.current_filter = 'all'
        self._refresh_pending = False
        self.events = deque(maxlen=500)
        self.metrics = {
            'analyzed': 0,
            'approved': 0,
            'purchases': 0,
            'sales': 0,
            'skipped': 0,
        }
        self.purchase_details = []
        self.total_gasto_pedidos = 0
        self.total_taxa_pedidos = 0
        self.window = tk.Toplevel(parent)
        self.window.title('MKT - Monitor de Operacoes')
        self.window.geometry('620x470')
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', False)
        self.window.config(bg=COLOR_BG)
        self.container = tk.Frame(
            self.window, bg=COLOR_BG, highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        self.container.pack(fill='both', expand=True)
        self.header = tk.Frame(self.container, bg=COLOR_SIDEBAR, height=42)
        self.header.pack(fill='x')
        title_box = tk.Frame(self.header, bg=COLOR_SIDEBAR)
        title_box.pack(side='left', padx=14, pady=7)
        tk.Label(title_box, text='MONITOR DE OPERACOES', fg=COLOR_ACCENT,
                 bg=COLOR_SIDEBAR, font=('Segoe UI Semibold', 9)).pack(anchor='w')
        self.session_label = tk.Label(
            title_box, text='SESSAO ATUAL - REGISTRO LOCAL', fg=COLOR_TEXT_DIM,
            bg=COLOR_SIDEBAR, font=('Segoe UI', 7),
        )
        self.session_label.pack(anchor='w')
        self.close_btn = tk.Button(
            self.header, text='X', bg=COLOR_SIDEBAR, fg=COLOR_TEXT_DIM,
            font=('Segoe UI Semibold', 9), relief='flat', bd=0,
            cursor='hand2', command=self.hide,
        )
        self.close_btn.pack(side='right', padx=12)
        self.close_btn.bind('<Enter>', lambda e: self.close_btn.config(fg=COLOR_ERROR))
        self.close_btn.bind('<Leave>', lambda e: self.close_btn.config(fg=COLOR_TEXT_DIM))

        self.nav = tk.Frame(self.container, bg=COLOR_NAV)
        self.nav.pack(fill='x')
        self.nav_buttons = {}
        for key, label in (('summary', 'RESUMO'), ('events', 'EVENTOS'), ('purchases', 'PEDIDOS'), ('diagnostics', 'DIAGNOSTICO')):
            button = tk.Button(
                self.nav, text=label, bg=COLOR_NAV, fg=COLOR_TEXT_DIM,
                activebackground=COLOR_CARD, activeforeground=COLOR_ACCENT,
                font=('Segoe UI Semibold', 8), relief='flat', bd=0,
                cursor='hand2', command=lambda selected=key: self.show_view(selected),
            )
            button.pack(side='left', expand=True, fill='x', padx=1, pady=(2, 0), ipady=7)
            self.nav_buttons[key] = button

        self.body = tk.Frame(self.container, bg=COLOR_BG)
        self.body.pack(fill='both', expand=True, padx=12, pady=10)
        self.views = {
            'summary': tk.Frame(self.body, bg=COLOR_BG),
            'events': tk.Frame(self.body, bg=COLOR_BG),
            'purchases': tk.Frame(self.body, bg=COLOR_BG),
            'diagnostics': tk.Frame(self.body, bg=COLOR_BG),
        }
        self._build_summary_view()
        self._build_events_view()
        self._build_purchases_view()
        self._build_diagnostics_view()
        self.set_filter('all')

        footer = tk.Frame(self.container, bg=COLOR_SIDEBAR)
        footer.pack(fill='x', side='bottom')
        tk.Button(
            footer, text='ABRIR PASTA DE REGISTROS', command=self.open_log_folder,
            bg=COLOR_SIDEBAR, fg=COLOR_TEXT_DIM, activebackground=COLOR_CARD,
            activeforeground=COLOR_TEXT, relief='flat', bd=0,
            font=('Segoe UI Semibold', 7), cursor='hand2',
        ).pack(side='left', padx=10, pady=6)
        tk.Button(
            footer, text='EXPORTAR RESUMO', command=self.export_report,
            bg=COLOR_SIDEBAR, fg=COLOR_TEXT_DIM, activebackground=COLOR_CARD,
            activeforeground=COLOR_TEXT, relief='flat', bd=0,
            font=('Segoe UI Semibold', 7), cursor='hand2',
        ).pack(side='left', padx=(0, 8), pady=6)
        tk.Label(
            footer, text='O monitor e ocultado automaticamente durante a execucao.',
            bg=COLOR_SIDEBAR, fg=COLOR_TEXT_DIM, font=('Segoe UI', 7),
        ).pack(side='right', padx=10)

        self.header.bind('<Button-1>', self.start_move)
        self.header.bind('<B1-Motion>', self.do_move)
        title_box.bind('<Button-1>', self.start_move)
        title_box.bind('<B1-Motion>', self.do_move)
        self.show_view('summary')
        self.window.withdraw()

    def _build_summary_view(self):
        view = self.views['summary']
        intro = tk.Frame(view, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        intro.pack(fill='x', pady=(0, 10))
        tk.Label(intro, text='Resumo da sessao', bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=('Segoe UI Semibold', 12)).pack(anchor='w', padx=14, pady=(12, 2))
        tk.Label(intro, text='Indicadores operacionais. O historico completo permanece salvo em disco.',
                 bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=('Segoe UI', 8)).pack(anchor='w', padx=14, pady=(0, 12))

        cards = tk.Frame(view, bg=COLOR_BG)
        cards.pack(fill='x')
        self.metric_labels = {}
        definitions = (
            ('analyzed', 'ANALISADOS'), ('approved', 'APROVADOS'),
            ('purchases', 'COMPRAS'), ('sales', 'VENDAS'), ('skipped', 'IGNORADOS'),
        )
        for column, (key, label) in enumerate(definitions):
            card = tk.Frame(cards, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
            card.grid(row=0, column=column, sticky='nsew', padx=3)
            cards.grid_columnconfigure(column, weight=1)
            tk.Label(card, text=label, bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
                     font=('Segoe UI Semibold', 7)).pack(pady=(10, 3))
            value = tk.Label(card, text='0', bg=COLOR_CARD, fg=COLOR_ACCENT,
                             font=('Segoe UI Semibold', 14))
            value.pack(pady=(0, 10))
            self.metric_labels[key] = value

        self.success_label = tk.Label(
            view, text='APROVEITAMENTO DAS OPORTUNIDADES: --', bg=COLOR_BG,
            fg=COLOR_SUCCESS, font=('Segoe UI Semibold', 9),
        )
        self.success_label.pack(anchor='w', padx=4, pady=(14, 5))
        tk.Label(
            view,
            text='Ignorados = itens fora dos seus limites ou sem preco legivel. Nao sao erros.',
            bg=COLOR_BG, fg=COLOR_TEXT_DIM, font=('Segoe UI', 8),
        ).pack(anchor='w', padx=4, pady=(0, 5))
        self.recent_summary = tk.Label(
            view, text='Aguardando eventos da sessao...', bg=COLOR_BG,
            fg=COLOR_TEXT_DIM, justify='left', anchor='nw', font=('Segoe UI', 8),
        )
        self.recent_summary.pack(fill='both', expand=True, padx=4, pady=5)

    def _build_events_view(self):
        view = self.views['events']
        filters = tk.Frame(view, bg=COLOR_BG)
        filters.pack(fill='x', pady=(0, 8))
        self.filter_buttons = {}
        for key, label in (('all', 'TODOS'), ('purchase', 'COMPRA'), ('sale', 'VENDA'), ('cycle', 'CICLO'), ('alerts', 'SEGURANCA')):
            button = tk.Button(
                filters, text=label, relief='flat', bd=0, cursor='hand2',
                bg=COLOR_CARD, fg=COLOR_TEXT_DIM, activebackground=COLOR_ACCENT_DIM,
                activeforeground=COLOR_TEXT, font=('Segoe UI Semibold', 7),
                command=lambda selected=key: self.set_filter(selected),
            )
            button.pack(side='left', padx=(0, 5), ipady=4, ipadx=7)
            self.filter_buttons[key] = button
        style = ttk.Style(self.window)
        style.configure('MKT.Treeview', background=COLOR_CARD, fieldbackground=COLOR_CARD,
                        foreground=COLOR_TEXT, rowheight=25, borderwidth=0,
                        font=('Segoe UI', 8))
        style.configure('MKT.Treeview.Heading', background=COLOR_NAV, foreground=COLOR_ACCENT,
                        relief='flat', font=('Segoe UI Semibold', 7))
        self.event_tree = ttk.Treeview(
            view, columns=('time', 'module', 'event', 'result'), show='headings',
            style='MKT.Treeview', selectmode='browse',
        )
        headings = (('time', 'HORA', 75), ('module', 'MODULO', 90),
                    ('event', 'EVENTO', 300), ('result', 'RESULTADO', 90))
        for key, label, width in headings:
            self.event_tree.heading(key, text=label)
            self.event_tree.column(key, width=width, anchor='w', stretch=key == 'event')
        self.event_tree.pack(fill='both', expand=True)

    def _build_purchases_view(self):
        view = self.views['purchases']
        header = tk.Frame(view, bg=COLOR_BG)
        header.pack(fill='x', pady=(0, 8))
        tk.Label(
            header, text='PEDIDOS DE COMPRA CRIADOS NESTA SESSAO', bg=COLOR_BG,
            fg=COLOR_ACCENT, font=('Segoe UI Semibold', 8),
        ).pack(side='left')
        totals_box = tk.Frame(header, bg=COLOR_BG)
        totals_box.pack(side='right')
        self.purchases_total_lbl = tk.Label(
            totals_box, text='TOTAL GASTO EM PEDIDOS: 0', bg=COLOR_BG,
            fg=COLOR_TEXT, font=('Segoe UI Semibold', 8),
        )
        self.purchases_total_lbl.pack(anchor='e')
        self.purchases_taxa_lbl = tk.Label(
            totals_box, text='TOTAL EM TAXAS (NÃO RETORNA): 0', bg=COLOR_BG,
            fg=COLOR_TEXT_DIM, font=('Segoe UI', 7),
        )
        self.purchases_taxa_lbl.pack(anchor='e')
        style = ttk.Style(self.window)
        style.configure('MKT.Treeview', background=COLOR_CARD, fieldbackground=COLOR_CARD,
                        foreground=COLOR_TEXT, rowheight=25, borderwidth=0,
                        font=('Segoe UI', 8))
        style.configure('MKT.Treeview.Heading', background=COLOR_NAV, foreground=COLOR_ACCENT,
                        relief='flat', font=('Segoe UI Semibold', 7))
        self.purchases_tree = ttk.Treeview(
            view,
            columns=('time', 'nome', 'tier', 'encantamento', 'quantidade', 'venda', 'compra', 'taxa', 'lucro'),
            show='headings', style='MKT.Treeview', selectmode='browse',
        )
        headings = (
            ('time', 'HORA', 65),
            ('nome', 'ITEM', 200),
            ('tier', 'TIER', 40),
            ('encantamento', 'ENCANT.', 55),
            ('quantidade', 'QTD', 45),
            ('venda', 'VENDA', 70),
            ('compra', 'PEDIDO', 70),
            ('taxa', 'TAXA', 60),
            ('lucro', 'LUCRO EST.', 80),
        )
        for key, label, width in headings:
            self.purchases_tree.heading(key, text=label)
            self.purchases_tree.column(key, width=width, anchor='w', stretch=key == 'nome')
        self.purchases_tree.pack(fill='both', expand=True)

    def _build_diagnostics_view(self):
        view = self.views['diagnostics']
        tk.Label(
            view, text='LOG TECNICO RECENTE', bg=COLOR_BG, fg=COLOR_ACCENT,
            font=('Segoe UI Semibold', 8),
        ).pack(anchor='w', pady=(0, 6))
        self.console = scrolledtext.ScrolledText(
            view, bg='#010713', fg=COLOR_TEXT_DIM, insertbackground=COLOR_ACCENT,
            font=('Consolas', 8), relief='flat', padx=10, pady=10, wrap='word',
        )
        self.console.pack(fill='both', expand=True)
        self.console.configure(state='disabled')

    def start_move(self, event):
        self.x = event.x
        self.y = event.y
    def do_move(self, event):
        deltax, deltay = (event.x - self.x, event.y - self.y)
        self.window.geometry(f'+{self.window.winfo_x() + deltax}+{self.window.winfo_y() + deltay}')

    def log(self, message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{timestamp}] {message}\n"
        event = classify_operation_message(message)
        writer = getattr(self, 'writer', None)
        if writer is not None:
            writer.submit(message, event)
        else:
            # Compatibilidade com testes e ambientes onde a thread nao iniciou.
            try:
                with open(self.log_path, 'a', encoding='utf-8') as handle:
                    handle.write(line)
            except OSError:
                pass
        self._record_event(message, event)
        # Diagnostico detalhado permanece nos arquivos locais, mas nao ocupa a
        # janela tecnica do cliente com uma linha JSON extensa por item.
        if str(message).startswith('[OCR_DIAG] '):
            return None
        try:
            self.console.configure(state='normal')
            self.console.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
            line_count = int(self.console.index('end-1c').split('.')[0])
            if line_count > 1200:
                self.console.delete('1.0', f'{line_count - 1000}.0')
            self.console.see('end')
            self.console.configure(state='disabled')
        except Exception:
            return None

    def _record_event(self, message, event):
        if not hasattr(self, 'metrics'):
            self.metrics = {
                'analyzed': 0, 'approved': 0, 'purchases': 0,
                'sales': 0, 'skipped': 0,
            }
        if not hasattr(self, 'events'):
            self.events = deque(maxlen=500)
        if not hasattr(self, 'purchase_details'):
            self.purchase_details = []
        if not hasattr(self, 'total_gasto_pedidos'):
            self.total_gasto_pedidos = 0
        if not hasattr(self, 'total_taxa_pedidos'):
            self.total_taxa_pedidos = 0
        event_type = event.get('event', 'log')
        if event_type == 'opportunity_evaluated':
            self.metrics['analyzed'] += 1
            if event.get('approved'):
                self.metrics['approved'] += 1
            else:
                self.metrics['skipped'] += 1
        elif event_type == 'purchase_confirmed':
            self.metrics['purchases'] += 1
        elif event_type == 'sale_confirmed':
            self.metrics['sales'] += 1
        elif event_type == 'purchase_detail':
            detail = event.get('detail')
            if isinstance(detail, dict):
                preco_pedido = detail.get('preco_pedido')
                taxa_pedido = detail.get('taxa_pedido')
                self.purchase_details.append({
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'nome': detail.get('nome') or '',
                    'tier': detail.get('tier'),
                    'encantamento': detail.get('encantamento') or '',
                    'quantidade': detail.get('quantidade') or 1,
                    'venda': detail.get('venda'),
                    'compra': detail.get('compra'),
                    'preco_pedido': preco_pedido,
                    'taxa_pedido': taxa_pedido,
                    'lucro_estimado': detail.get('lucro_estimado'),
                })
                if isinstance(preco_pedido, (int, float)):
                    self.total_gasto_pedidos += preco_pedido
                if isinstance(taxa_pedido, (int, float)):
                    self.total_taxa_pedidos += taxa_pedido

        if event_type != 'log':
            self.events.append({
                'time': datetime.now().strftime('%H:%M:%S'),
                'module': event.get('module', 'system'),
                'event': event_type,
                'result': event.get('result', 'info'),
                'message': str(message)[:240],
            })
        if getattr(self, 'visible', False):
            self._schedule_refresh()

    def _schedule_refresh(self):
        """Agrupa atualizacoes visuais sem atrasar ou bloquear os eventos."""
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self.parent.after(250, self._flush_visual_refresh)

    def _flush_visual_refresh(self):
        self._refresh_pending = False
        if not self.visible:
            return
        self._refresh_summary()
        if self.current_view == 'events':
            self._render_events()
        elif self.current_view == 'purchases':
            self._render_purchases()

    def _refresh_summary(self):
        for key, label in self.metric_labels.items():
            label.config(text=str(self.metrics[key]))
        approved = self.metrics['approved']
        purchases = self.metrics['purchases']
        rate = purchases / approved * 100 if approved else 0.0
        rate_text = f'{rate:.1f}%' if approved else '--'
        self.success_label.config(text=f'APROVEITAMENTO DAS OPORTUNIDADES: {rate_text}')
        if self.events:
            last = self.events[-1]
            self.recent_summary.config(
                text=f"Ultimo evento: {last['time']}  |  {last['module'].upper()}\n{last['message']}"
            )

    def show_view(self, selected):
        self.current_view = selected
        for key, frame in self.views.items():
            frame.pack_forget()
            self.nav_buttons[key].config(
                bg=COLOR_CARD if key == selected else COLOR_NAV,
                fg=COLOR_ACCENT if key == selected else COLOR_TEXT_DIM,
            )
        self.views[selected].pack(fill='both', expand=True)
        if selected == 'summary':
            self._refresh_summary()
        elif selected == 'events':
            self._render_events()
        elif selected == 'purchases':
            self._render_purchases()

    def set_filter(self, selected):
        self.current_filter = selected
        for key, button in self.filter_buttons.items():
            button.config(
                bg=COLOR_ACCENT_DIM if key == selected else COLOR_CARD,
                fg=COLOR_TEXT if key == selected else COLOR_TEXT_DIM,
            )
        self._render_events()

    def _event_matches_filter(self, event):
        selected = self.current_filter
        if selected == 'all':
            return True
        if selected == 'alerts':
            return event['result'] in {'protected', 'warning', 'error'}
        return event['module'] == selected

    def _render_events(self):
        self.event_tree.delete(*self.event_tree.get_children())
        labels = {
            'opportunity_evaluated': 'Oportunidade analisada',
            'purchase_confirmed': 'Ordem de compra confirmada',
            'sale_confirmed': 'Pedido de venda confirmado',
            'cycle_transition': 'Mudanca de etapa do ciclo',
            'cycle_activity': 'Atividade do ciclo',
            'safety_protection': 'Protecao de seguranca acionada',
            'operation_error': 'Erro real de execucao',
            'operational_notice': 'Aviso operacional',
            'automation_started': 'Automacao iniciada',
            'automation_stopped': 'Automacao encerrada',
            'automation_interrupted': 'Parada solicitada pelo usuario',
        }
        module_labels = {
            'purchase': 'COMPRA', 'sale': 'VENDA',
            'cycle': 'CICLO', 'system': 'SISTEMA',
        }
        result_labels = {
            'info': 'INFO', 'success': 'SUCESSO', 'approved': 'APROVADO',
            'skipped': 'IGNORADO',
            'protected': 'PROTEGIDO', 'warning': 'ATENCAO', 'error': 'ERRO',
        }
        for event in reversed(self.events):
            if not self._event_matches_filter(event):
                continue
            self.event_tree.insert('', 'end', values=(
                event['time'], module_labels.get(event['module'], event['module'].upper()),
                labels.get(event['event'], event['event']),
                result_labels.get(event['result'], event['result'].upper()),
            ))

    def _render_purchases(self):
        self.purchases_tree.delete(*self.purchases_tree.get_children())
        for compra in reversed(self.purchase_details):
            tier = compra.get('tier')
            self.purchases_tree.insert('', 'end', values=(
                compra['time'],
                compra['nome'],
                f"T{tier}" if tier else '-',
                compra.get('encantamento') or '-',
                compra.get('quantidade') or 1,
                compra.get('venda') if compra.get('venda') is not None else '-',
                compra.get('preco_pedido') if compra.get('preco_pedido') is not None else '-',
                compra.get('taxa_pedido') if compra.get('taxa_pedido') is not None else '-',
                compra.get('lucro_estimado') if compra.get('lucro_estimado') is not None else '-',
            ))
        total_fmt = f"{int(self.total_gasto_pedidos):,}".replace(',', '.')
        taxa_fmt = f"{int(self.total_taxa_pedidos):,}".replace(',', '.')
        self.purchases_total_lbl.config(text=f'TOTAL GASTO EM PEDIDOS: {total_fmt}')
        self.purchases_taxa_lbl.config(text=f'TOTAL EM TAXAS (NÃO RETORNA): {taxa_fmt}')

    def open_log_folder(self):
        folder = os.path.dirname(self.log_path)
        try:
            os.startfile(folder)
        except (AttributeError, OSError):
            return

    def export_report(self):
        target = filedialog.asksaveasfilename(
            parent=self.window,
            title='Exportar resumo da sessao',
            defaultextension='.csv',
            filetypes=[('Relatorio CSV', '*.csv')],
            initialfile=f"relatorio-mkt-{datetime.now():%Y-%m-%d-%H%M}.csv",
        )
        if not target:
            return
        try:
            with open(target, 'w', newline='', encoding='utf-8-sig') as handle:
                output = csv.writer(handle, delimiter=';')
                output.writerow(['RESUMO DA SESSAO'])
                output.writerow(['Analisados', self.metrics['analyzed']])
                output.writerow(['Aprovados', self.metrics['approved']])
                output.writerow(['Compras confirmadas', self.metrics['purchases']])
                output.writerow(['Vendas confirmadas', self.metrics['sales']])
                output.writerow(['Itens ignorados normalmente', self.metrics['skipped']])
                output.writerow(['Total gasto em pedidos', int(self.total_gasto_pedidos)])
                output.writerow(['Total em taxas (nao retorna)', int(self.total_taxa_pedidos)])
                output.writerow([])
                output.writerow(['PEDIDOS DE COMPRA CRIADOS NESTA SESSAO'])
                output.writerow(['Hora', 'Item', 'Tier', 'Encantamento', 'Quantidade', 'Venda', 'Preco do Pedido', 'Taxa', 'Lucro Estimado'])
                for compra in self.purchase_details:
                    tier = compra.get('tier')
                    output.writerow([
                        compra['time'], compra['nome'], f"T{tier}" if tier else '',
                        compra.get('encantamento') or '', compra.get('quantidade') or 1,
                        compra.get('venda'), compra.get('preco_pedido'),
                        compra.get('taxa_pedido'), compra.get('lucro_estimado'),
                    ])
                output.writerow([])
                output.writerow(['Hora', 'Modulo', 'Evento', 'Resultado', 'Detalhe'])
                for event in self.events:
                    output.writerow([
                        event['time'], event['module'], event['event'],
                        event['result'], event['message'],
                    ])
            messagebox.showinfo('Monitor de operacoes', 'Resumo exportado com sucesso.', parent=self.window)
        except OSError as exc:
            messagebox.showerror('Monitor de operacoes', f'Nao foi possivel exportar:\n{exc}', parent=self.window)

    def toggle(self):
        if self.window.winfo_viewable():
            self.hide()
        else:
            self._position_safely()
            self.window.deiconify()
            self.window.lift()
            self.visible = True
            self.show_view(self.current_view)

    def _position_safely(self):
        self.window.update_idletasks()
        width = max(620, self.window.winfo_reqwidth())
        height = max(470, self.window.winfo_reqheight())
        screen_w = self.parent.winfo_screenwidth()
        screen_h = self.parent.winfo_screenheight()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_w = self.parent.winfo_width()
        gap = 10
        if parent_x + parent_w + gap + width <= screen_w:
            x = parent_x + parent_w + gap
        elif parent_x - gap - width >= 0:
            x = parent_x - gap - width
        else:
            x = max(0, (screen_w - width) // 2)
        y = max(0, min(parent_y, screen_h - height))
        self.window.geometry(f'{width}x{height}+{x}+{y}')

    def hide(self):
        self.window.withdraw()
        self.visible = False

class SplashScreen:
    def __init__(self, parent_root, on_finish=None):
        self.root = tk.Toplevel(parent_root)
        self.on_finish = on_finish
        self._finished = False
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        w, h = (320, 90)
        sw, sh = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.root.geometry(f'{w}x{h}+{int((sw - w) / 2)}+{int(sh * 0.72)}')
        self.root.config(bg='#010101')
        try:
            self.root.attributes('-transparentcolor', '#010101')
        except:
            pass
        self.canvas = tk.Canvas(self.root, bg='#010101', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.step = 0
        # A animação é somente visual. A abertura do MKT jamais pode depender
        # de PIL/Canvas conseguir desenhar todos os quadros.
        self.root.after(1500, self.finish)
        self.animate()

    def finish(self):
        """Encerra a tela de abertura uma única vez, mesmo após falha visual."""
        if self._finished:
            return
        self._finished = True
        try:
            if self.on_finish:
                self.on_finish()
        finally:
            try:
                if self.root.winfo_exists():
                    self.root.destroy()
            except tk.TclError:
                pass

    def animate(self):
        if self._finished:
            return
        try:
            self.draw_hud_frame(self.step)
        except Exception:
            # Não interrompe a inicialização por um problema puramente estético.
            return
        self.step += 1.6
        if self.step <= 100:
            self.root.after(20, self.animate)
    def draw_hud_frame(self, progress):
        # ***<module>.SplashScreen.draw_hud_frame: Failure: Different bytecode
        w, h = (320, 90)
        w_draw, h_draw = (320, 90)
        scale = 3
        w_s = w_draw * scale
        h_s = h_draw * scale
        im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        r_s = 15 * scale
        draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (2, 9, 22, 255))
        draw_rounded_rectangle(draw, [0, 0, w_s, int(h_s * 0.4)], r_s, (13, 40, 72, 255))
        border_thickness = int(1.5 * scale)
        b_draw = ImageDraw.Draw(im)
        draw_rounded_rectangle(b_draw, [0, 0, w_s, h_s], r_s, (249, 209, 122, 255))
        draw_rounded_rectangle(b_draw, [border_thickness, border_thickness, w_s - border_thickness, h_s - border_thickness], r_s - border_thickness, (2, 9, 22, 255))
        draw_rounded_rectangle(b_draw, [border_thickness * 2, border_thickness * 2, w_s - border_thickness * 2, int(h_s * 0.5)], r_s - border_thickness * 2, (13, 40, 72, 255))
        title = 'MKT'
        try:
            from PIL import ImageFont
            fnt = ImageFont.truetype('bahnschrift.ttf', 40)
        except:
            fnt = ImageFont.load_default()
        tx_center = w_s // 2
        ty_center = 40 * scale
        draw.text((tx_center + 4, ty_center + 4), title, font=fnt, fill=(0, 0, 0, 200), anchor='mm')
        draw.text((tx_center, ty_center), title, font=fnt, fill=(148, 125, 76, 255), anchor='mm')
        draw.text((tx_center, ty_center - 3), title, font=fnt, fill=(253, 230, 157, 255), anchor='mm')
        sub_title = 'CARREGANDO SISTEMAS...'
        try:
            fnt_sub = ImageFont.truetype('segoeui.ttf', 16)
        except:
            fnt_sub = ImageFont.load_default()
        draw.text((tx_center, ty_center + 50), sub_title, font=fnt_sub, fill=(156, 175, 196, 255), anchor='mm')
        bar_w = 260 * scale
        bar_h = 6 * scale
        bar_x1 = (w_s - bar_w) // 2
        bar_x2 = bar_x1 + bar_w
        bar_y1 = h_s - 22 * scale
        bar_y2 = bar_y1 + bar_h
        draw_rounded_rectangle(draw, [bar_x1, bar_y1, bar_x2, bar_y2], bar_h // 2, (0, 3, 10, 255))
        if progress > 0:
            p_w = int(bar_w * (progress / 100.0))
            for gw in range(4, 0, (-1)):
                g_alpha = int(40 / gw)
                draw_rounded_rectangle(draw, [bar_x1, bar_y1 - gw * 2, bar_x1 + p_w, bar_y2 + gw * 2], bar_h // 2, (249, 209, 122, g_alpha))
            draw_rounded_rectangle(draw, [bar_x1, bar_y1, bar_x1 + p_w, bar_y2], bar_h // 2, (148, 125, 76, 255))
            draw_rounded_rectangle(draw, [bar_x1, bar_y1, bar_x1 + p_w, bar_y1 + bar_h // 2], bar_h // 2, (249, 209, 122, 255))
            glow_r = 8 * scale
            draw.ellipse([bar_x1 + p_w - glow_r, bar_y1 + bar_h // 2 - glow_r, bar_x1 + p_w + glow_r, bar_y1 + bar_h // 2 + glow_r], fill=(253, 230, 157, 120))
        r, g, b, a = im.split()
        bg_im = Image.new('RGB', (w_s, h_s), (1, 1, 1))
        bg_im.paste(im.convert('RGB'), mask=a)
        resized = bg_im.resize((w, h), Image.Resampling.LANCZOS)
        self.hud_tk = ImageTk.PhotoImage(resized)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.hud_tk, anchor='nw')
DEFAULT_CATEGORIES = [
    {'name': 'ARMAS', 'key': 'cat_clique_armas', 'enabled': True},
    {'name': 'PEITORAL', 'key': 'cat_clique_peitoral', 'enabled': True},
    {'name': 'CAPACETES', 'key': 'cat_clique_capacetes', 'enabled': True},
    {'name': 'BOTAS', 'key': 'cat_clique_botas', 'enabled': True},
    {'name': 'MÃO SECUNDARIA', 'key': 'cat_clique_mao_secundaria', 'enabled': True},
    {'name': 'CAPAS', 'key': 'cat_clique_capas', 'enabled': True},
    {'name': 'BOLSAS', 'key': 'cat_clique_bolsas', 'enabled': True},
    {'name': 'EQUIP COLETA', 'key': 'cat_clique_equip_coleta', 'enabled': True},
    {'name': 'ARTEFATO', 'key': 'cat_clique_artefato', 'enabled': True},
]
class AlbionBotGUI:
    def __init__(self, root, **kwargs):
        # ***<module>.AlbionBotGUI.__init__: Failure detected at line number 305 and instruction offset 308: Different bytecode
        self.root = root
        self.root.title('MKT')
        try:
            self.root.iconbitmap('assets/icon.ico')
        except:
            pass
        self.width = PANEL_SAFE_WIDTH
        self.height = min(760, max(680, self.root.winfo_screenheight() - 58))
        self.root.geometry(f'{self.width}x{self.height}')
        self.root.config(bg='#010101')
        try:
            self.root.attributes('-transparentcolor', '#010101')
        except:
            pass
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.running = False
        self.sell_running = False
        self.cycle_running = False
        self.hotkey_handles = []
        self.bot_process = None
        self.installing = False
        self.minimized = False
        self._mini_refresh_job = None
        self._mini_started_at = None
        self._mini_was_active = False
        self._mini_user_dragged = False
        self._mini_intervention_required = False
        self.current_tab = 'BOT'
        self.offsets = self.carregar_offsets()
        self.order_sound_enabled = bool(self.offsets.get('order_sound_enabled', True))
        self._order_sound_payload = build_soft_order_tone()
        self._sound_button_hover = False
        self.carregar_sequencia_categorias()
        self.key_info = kwargs.get('key_info', {})
        self.log_window = LogWindow(self.root)
        import sys
        sys.stdout = StdoutRedirector(self.log)
        sys.stderr = StdoutRedirector(self.log)
        self.total_orders = 0
        self.total_profit = 0
        self.total_gasto = 0
        self.total_taxa = 0
        self.cycle_orders_completed = 0
        self.cycle_items_sold = 0
        self.cycle_stage = None
        self.last_item_name = 'Item'
        self.active_notification = None
        self.notif_queue = []
        self._item_icon_cache_queue = queue.Queue()
        self._item_icon_fetch_attempted = set()
        threading.Thread(target=self._item_icon_cache_worker, daemon=True).start()
        bot.buy_callback = self.enqueue_notification
        bot.item_icon_prefetch_callback = self.prefetch_item_icon
        self._poll_log_queue()
        self.main_container = tk.Canvas(self.root, bg='#010101', highlightthickness=0)
        self.main_container.pack(fill='both', expand=True)
        self.window_bg_ref = None
        def draw_window_bg(e=None):
            w = self.main_container.winfo_width()
            h = self.main_container.winfo_height()
            if w <= 1 or h <= 1:
                w, h = (280, 640)
            self.window_bg_ref = get_window_background_asset(w, h)
            self.main_container.delete('all')
            self.main_container.create_image(0, 0, image=self.window_bg_ref, anchor='nw')
        self.main_container.bind('<Configure>', draw_window_bg)
        self.inner_frame = tk.Frame(self.main_container, bg=COLOR_BG)
        self.inner_frame.pack(fill='both', expand=True, padx=3, pady=3)
        self.setup_ui()
        self.setup_custom_titlebar()
        self.carregar_dados_iniciais()
        self.carregar_ajustes_financeiros()
        self.running = False
        self.buy_paused = False
        self.cycle_running = False
        self.bot_process = None
        self.iniciar_processo_background()
        self.monitor_game_position()
        self.registrar_atalhos_globais()
    def setup_ui(self):
        self.setup_styles()
        self.create_widgets()
    def setup_custom_titlebar(self):
        self.header.bind('<Button-1>', self.start_move)
        self.header.bind('<B1-Motion>', self.do_move)
        for child in self.header.winfo_children():
            if isinstance(child, tk.Label):
                child.bind('<Button-1>', self.start_move)
                child.bind('<B1-Motion>', self.do_move)

    def _draw_sound_toggle(self):
        canvas = getattr(self, 'sound_btn', None)
        if canvas is None:
            return
        w, h, scale = (22, 22, 3)
        image = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        active = bool(getattr(self, 'order_sound_enabled', True))
        hover = bool(getattr(self, '_sound_button_hover', False))
        border = ui_rgba(COLOR_ACCENT) if hover else ui_rgba(COLOR_BORDER)
        inner = ui_rgba(UI_COLORS['surface_hover']) if active else ui_rgba(COLOR_CARD)
        draw_rounded_rectangle(draw, [0, 0, w * scale, h * scale], 6 * scale, border)
        draw_rounded_rectangle(
            draw,
            [scale, scale, (w - 1) * scale, (h - 1) * scale],
            5 * scale,
            inner,
        )
        color = ui_rgba(COLOR_ACCENT) if active else ui_rgba(UI_COLORS['text_tertiary'])
        draw.rectangle([5 * scale, 9 * scale, 8 * scale, 13 * scale], fill=color)
        draw.polygon(
            [(8 * scale, 9 * scale), (12 * scale, 6 * scale),
             (12 * scale, 16 * scale), (8 * scale, 13 * scale)],
            fill=color,
        )
        if active:
            draw.arc([9 * scale, 6 * scale, 17 * scale, 16 * scale], -55, 55,
                     fill=color, width=max(1, scale))
            draw.arc([10 * scale, 4 * scale, 20 * scale, 18 * scale], -55, 55,
                     fill=color, width=max(1, scale))
        else:
            draw.line([(5 * scale, 5 * scale), (17 * scale, 17 * scale)],
                      fill=(208, 92, 92, 255), width=2 * scale)
        resized = image.resize((w, h), Image.Resampling.LANCZOS)
        self._sound_btn_image = ImageTk.PhotoImage(resized)
        canvas.delete('all')
        canvas.create_image(0, 0, image=self._sound_btn_image, anchor='nw')

    def create_sound_toggle_button(self, parent):
        self.sound_btn = tk.Canvas(
            parent, width=22, height=22, bg=COLOR_SIDEBAR,
            highlightthickness=0, cursor='hand2', takefocus=1,
        )
        self.sound_btn.bind('<Button-1>', lambda _event: self.toggle_order_sound())
        self.sound_btn.bind('<Return>', lambda _event: self.toggle_order_sound())
        self.sound_btn.bind('<space>', lambda _event: self.toggle_order_sound())

        def on_enter(_event):
            self._sound_button_hover = True
            self._draw_sound_toggle()

        def on_leave(_event):
            self._sound_button_hover = False
            self._draw_sound_toggle()

        self.sound_btn.bind('<Enter>', on_enter)
        self.sound_btn.bind('<Leave>', on_leave)
        self._draw_sound_toggle()
        return self.sound_btn

    def toggle_order_sound(self):
        self.order_sound_enabled = not bool(getattr(self, 'order_sound_enabled', True))
        try:
            data = load_settings('offsets.json')
            data['order_sound_enabled'] = self.order_sound_enabled
            save_settings('offsets.json', data)
            self.offsets = data
        except Exception as exc:
            self.log(f'[AVISO] Nao foi possivel salvar a preferencia de som: {exc}')
        self._draw_sound_toggle()
        estado = 'LIGADO' if self.order_sound_enabled else 'DESLIGADO'
        self.log(f'>>> Som de ordem realizada: {estado}.')
        if self.order_sound_enabled:
            self.play_order_sound()

    def play_order_sound(self):
        """Toca fora da thread da interface e nunca interfere no fluxo do bot."""
        if not bool(getattr(self, 'order_sound_enabled', True)) or winsound is None:
            return
        payload = getattr(self, '_order_sound_payload', None)
        if not payload:
            return

        def play():
            try:
                winsound.PlaySound(payload, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            except Exception:
                pass

        threading.Thread(target=play, daemon=True).start()

    def registrar_atalhos_globais(self):
        """Registra os atalhos uma única vez e guarda seus identificadores."""
        try:
            import keyboard
            callbacks = {
                'f6': self._mini_toggle_pause_resume,
                'f7': self.iniciar_via_atalho,
                'f8': self.pause_bot,
                'f9': self.alternar_pausa_protegida_via_atalho,
                'insert': self.pause_bot,
            }
            for tecla, callback in callbacks.items():
                handle = keyboard.add_hotkey(
                    tecla,
                    lambda action=callback: self.root.after(0, action),
                )
                self.hotkey_handles.append(handle)
            self.log('>>> Atalhos ativos: F6 pausar/continuar | F7 iniciar | F8 parar | F9 Pausa protegida.')
        except Exception as exc:
            self.log(f'[AVISO] Atalhos F6/F7/F8/F9 não registrados: {exc}')

    def iniciar_via_atalho(self):
        """Inicia somente; nunca transforma F7 em um botão de alternância."""
        if self.automacao_em_execucao():
            return
        if self.current_tab == 'SELL':
            self.iniciar_bot_venda()
        elif self.current_tab == 'CYCLE':
            self.toggle_cycle_bot()
        else:
            self.toggle_bot()

    def alternar_pausa_protegida_via_atalho(self):
        """Usa F9 apenas para ligar/desligar a Pausa protegida."""
        novo_estado = not bool(getattr(self, 'protected_pause_enabled', False))
        self.alternar_pausa_protegida(novo_estado)
        estado = 'ATIVADA' if novo_estado else 'DESATIVADA'
        self.show_notification(f'PAUSA PROTEGIDA {estado}')

    def automacao_em_execucao(self):
        return bool(
            self.running
            or self.sell_running
            or self.cycle_running
            or getattr(self, 'fechando_ordens', False)
            or getattr(self, 'shopping_running', False)
            or getattr(self, 'remover_pedidos_running', False)
        )

    def modulo_liberado(self, module, titulo):
        if license_allows_module(self.key_info, module):
            return True
        messagebox.showwarning(
            'Módulo não incluído',
            f'Sua licença não inclui {titulo}. Entre em contato para liberar este módulo.',
        )
        return False

    def encerrar_aplicativo(self):
        try:
            import keyboard
            for handle in self.hotkey_handles:
                keyboard.remove_hotkey(handle)
        except Exception:
            pass
        self.hotkey_handles.clear()
        self.root.quit()
    def start_move(self, event):
        self.x = event.x
        self.y = event.y
        self.user_dragged = True

    def do_move(self, event):
        self.user_dragged = True
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f'+{x}+{y}')

    def monitor_game_position(self):
        try:
            if getattr(self, 'calibration_active', False):
                overlay = getattr(self, 'calib_win', None)
                if overlay is not None and overlay.winfo_exists():
                    overlay.attributes('-topmost', True)
                    overlay.lift()
                return
            hwnd_foreground = ctypes.windll.user32.GetForegroundWindow()
            win = get_albion_window()
            if win and (not win.isMinimized):
                target_x = win.left
                target_y = win.top
                if not self.minimized and not getattr(self, 'user_dragged', False):
                    self.root.geometry(f'{self.width}x{self.height}+{target_x}+{target_y}')
                elif (
                    self.minimized
                    and hasattr(self, '_mini_win')
                    and self._mini_win
                    and not getattr(self, '_mini_user_dragged', False)
                ):
                    self._mini_win.geometry(
                        f'{MINI_HUD_WIDTH}x{MINI_HUD_HEIGHT}+{target_x + 8}+{target_y + 34}'
                    )

                # Garante que o bot e todos os overlays fiquem SEMPRE NO TOPO em cima do jogo!
                if not self.minimized:
                    self.root.attributes('-topmost', True)
                    self.root.lift()
                    help_window = getattr(self, '_cost_help_window', None)
                    if help_window is not None and help_window.winfo_exists():
                        help_window.attributes('-topmost', True)
                        help_window.lift()
                elif hasattr(self, '_mini_win') and self._mini_win:
                    self._mini_win.attributes('-topmost', True)
                    self._mini_win.lift()

                if hasattr(self, 'log_window') and getattr(self.log_window, 'visible', False):
                    self.log_window.window.attributes('-topmost', True)
        except Exception:
            pass
        finally:
            self.root.after(500, self.monitor_game_position)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', background=COLOR_NAV, foreground=COLOR_TEXT, fieldbackground=COLOR_NAV,
                        rowheight=30, font=UI_FONTS['body'], borderwidth=0, relief='flat')
        style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
        style.map('Treeview', background=[('selected', COLOR_ACCENT_DIM)], foreground=[('selected', COLOR_TEXT)])
        style.configure('Treeview.Heading', background=UI_COLORS['surface_raised'], foreground=COLOR_ACCENT,
                        font=UI_FONTS['caption_strong'], relief='flat', padding=(4, 8))
        style.configure('TProgressbar', thickness=8, troughcolor=COLOR_NAV, background=COLOR_SUCCESS,
                        borderwidth=0, bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER)
        style.configure('Dark.Vertical.TScrollbar', troughcolor=COLOR_NAV, background=UI_COLORS['surface_raised'],
                        bordercolor=COLOR_NAV, arrowcolor=COLOR_TEXT_DIM, relief='flat', width=8)
        style.map('Dark.Vertical.TScrollbar', background=[('active', UI_COLORS['surface_hover'])])
    def hex_to_rgb(self, hex_str):
        hex_str = hex_str.lstrip('#')
        return tuple((int(hex_str[i:i + 2], 16) for i in [0, 2, 4]))
    def create_rounded_frame(self, parent, bg_color=COLOR_CARD, border_color=COLOR_BORDER, radius=10):
        # ***<module>.AlbionBotGUI.create_rounded_frame: Failure detected at line number 360 and instruction offset 12: Different bytecode
        parent_bg = parent.cget('bg')
        container = tk.Canvas(parent, highlightthickness=0, bg=parent_bg)
        inner = tk.Frame(container, bg=bg_color)
        inner.pack(fill='both', expand=True, padx=4, pady=4)
        state = {'img': None}
        def redraw_frame(e=None):
            # ***<module>.AlbionBotGUI.create_rounded_frame.redraw_frame: Failure detected at line number 371 and instruction offset 42: Different bytecode
            w = container.winfo_width()
            h = container.winfo_height()
            if w <= 1 or h <= 1:
                return None
            else:
                scale = 3
                im = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
                draw = ImageDraw.Draw(im)
                r_s = radius * scale
                border_rgb = self.hex_to_rgb(border_color)
                bg_rgb = self.hex_to_rgb(bg_color)
                draw_rounded_rectangle(draw, [0, 0, w * scale, h * scale], r_s, border_rgb + (255,))
                draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w * scale - 1 * scale, h * scale - 1 * scale], r_s - 1 * scale, bg_rgb + (255,))
                shadow_im = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
                s_draw = ImageDraw.Draw(shadow_im)
                draw_rounded_rectangle(s_draw, [2 * scale, 2 * scale, w * scale - 2 * scale, h * scale - 2 * scale], r_s - 2 * scale, (0, 0, 0, 80))
                shadow_im = shadow_im.filter(ImageFilter.GaussianBlur(1.0 * scale))
                im.alpha_composite(shadow_im)
                resized = im.resize((w, h), Image.Resampling.LANCZOS)
                state['img'] = ImageTk.PhotoImage(resized)
                container.delete('all')
                container.create_image(0, 0, image=state['img'], anchor='nw')
                container.tag_lower('all')
        container.bind('<Configure>', redraw_frame)
        return (container, inner)
    def create_3d_button(self, parent, text, type_color='gold', command=None):
        # ***<module>.AlbionBotGUI.create_3d_button: Failure detected at line number 400 and instruction offset 106: Different bytecode
        asset_type = 'gold_btn'
        if type_color == 'green':
            asset_type = 'green_btn'
        else:
            if type_color == 'red':
                asset_type = 'red_btn'
        parent_bg = parent.cget('bg')
        w_init = 28 if text in ['▲', '▼'] else 106 if text in ['CONFIRMAR', 'CANCELAR'] else 84 if text in ['SET', 'MARCAR', 'EDITAR'] else 250
        h_init = 28 if text in ['▲', '▼'] else 36
        canv = tk.Canvas(
            parent, highlightthickness=0, bg=parent_bg, cursor='hand2',
            width=w_init, height=h_init, takefocus=1,
        )
        state = {'current': 'normal', 'img': None}
        def update_image(e=None):
            w = canv.winfo_width()
            h = canv.winfo_height()
            if w <= 1 or h <= 1:
                w, h = (w_init, h_init)
            state['img'] = get_puffy_asset(w, h, asset_type, state['current'], text)
            canv.delete('all')
            canv.create_image(0, 0, image=state['img'], anchor='nw')
        canv.bind('<Configure>', update_image)
        def on_enter(e):
            state['current'] = 'hover'
            update_image()
        def on_leave(e):
            state['current'] = 'normal'
            update_image()
        def on_press(e):
            state['current'] = 'pressed'
            update_image()
        def on_release(e):
            state['current'] = 'hover'
            update_image()
            if command:
                command()
        canv.bind('<Enter>', on_enter)
        canv.bind('<Leave>', on_leave)
        canv.bind('<ButtonPress-1>', on_press)
        canv.bind('<ButtonRelease-1>', on_release)
        canv.bind('<FocusIn>', lambda _event: (state.update(current='hover'), update_image()))
        canv.bind('<FocusOut>', lambda _event: (state.update(current='normal'), update_image()))
        canv.bind('<Return>', lambda _event: command() if command else None)
        canv.bind('<space>', lambda _event: command() if command else None)
        return canv
    def create_tab_button(self, parent, key, text, command, height=42):
        # ***<module>.AlbionBotGUI.create_tab_button: Failure detected at line number 431 and instruction offset 2: Different bytecode
        container = tk.Frame(parent, bg=parent.cget('bg'), height=height)
        container.pack_propagate(False)
        canv = tk.Canvas(
            container, highlightthickness=0, bg=parent.cget('bg'),
            name='canv', cursor='hand2', takefocus=1,
        )
        canv.pack(fill='both', expand=True)
        canv.tab_text = text
        canv.tab_height = height
        state = {'img': None}
        def update_tab(e=None):
            w = canv.winfo_width()
            h = canv.winfo_height()
            if w <= 1 or h <= 1:
                w = 52
                h = height
            asset_type = 'tab_active' if self.current_tab == key else 'tab_inactive'
            state['img'] = get_puffy_asset(w, h, asset_type, text=text)
            canv.delete('all')
            canv.create_image(0, 0, image=state['img'], anchor='nw')
        canv.bind('<Configure>', update_tab)
        def on_click(e):
            command()
        canv.bind('<Button-1>', on_click)
        canv.bind('<Return>', lambda _event: command())
        canv.bind('<space>', lambda _event: command())
        return container
    def update_tab_visual(self, tab_frame, active):
        try:
            canv = tab_frame.nametowidget('canv')
            w = canv.winfo_width()
            h = canv.winfo_height()
            if w <= 1 or h <= 1:
                w, h = (52, getattr(canv, 'tab_height', 42))
            text = canv.tab_text
            asset_type = 'tab_active' if active else 'tab_inactive'
            canv.img_ref = get_puffy_asset(w, h, asset_type, text=text)
            canv.delete('all')
            canv.create_image(0, 0, image=canv.img_ref, anchor='nw')
        except Exception as e:
            return None
    def create_puffy_checkbox(self, parent, text, initial_value, on_change_callback, bg_color=None):
        # ***<module>.AlbionBotGUI.create_puffy_checkbox: Failure detected at line number 469 and instruction offset 10: Different bytecode
        if bg_color is None:
            bg_color = COLOR_BG
        frame = tk.Frame(parent, bg=bg_color)
        chk_box = tk.Canvas(frame, width=22, height=22, bg=bg_color, highlightthickness=0, cursor='hand2')
        chk_box.pack(side='left', padx=(0, 8))
        lbl = tk.Label(frame, text=text, bg=bg_color, fg=COLOR_TEXT, font=('Segoe UI Semibold', 9), cursor='hand2')
        lbl.pack(side='left')
        state = {'active': initial_value, 'img': None}
        def redraw_chk():
            # ***<module>.AlbionBotGUI.create_puffy_checkbox.redraw_chk: Failure detected at line number 478 and instruction offset 22: Different bytecode
            scale = 3
            w_s, h_s = (22 * scale, 22 * scale)
            im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            r_s = 6 * scale
            if state['active']:
                draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (221, 177, 99, 255))
                draw_rounded_rectangle(draw, [scale, scale, w_s - scale, h_s - scale], r_s - scale, (13, 40, 72, 255))
                draw.line([(5 * scale, 11 * scale), (9 * scale, 15 * scale)], fill=(253, 230, 157, 255), width=2 * scale)
                draw.line([(9 * scale, 15 * scale), (16 * scale, 6 * scale)], fill=(253, 230, 157, 255), width=2 * scale)
            else:
                draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (39, 72, 106, 255))
                draw_rounded_rectangle(draw, [scale, scale, w_s - scale, h_s - scale], r_s - scale, (4, 16, 32, 255))
            resized = im.resize((22, 22), Image.Resampling.LANCZOS)
            state['img'] = ImageTk.PhotoImage(resized)
            chk_box.delete('all')
            chk_box.create_image(0, 0, image=state['img'], anchor='nw')
        def toggle(e):
            state['active'] = not state['active']
            redraw_chk()
            on_change_callback(state['active'])
        def set_active(value):
            state['active'] = bool(value)
            redraw_chk()
        chk_box.bind('<Button-1>', toggle)
        lbl.bind('<Button-1>', toggle)
        frame.set_active = set_active
        redraw_chk()
        return frame
    def create_puffy_toggle_switch(self, parent, text, initial_value, on_change_callback, bg_color=None):
        # ***<module>.AlbionBotGUI.create_puffy_toggle_switch: Failure detected at line number 504 and instruction offset 10: Different bytecode
        if bg_color is None:
            bg_color = COLOR_BG
        frame = tk.Frame(parent, bg=bg_color)
        sw_width = 48
        sw_height = 24
        sw_canvas = tk.Canvas(frame, width=sw_width, height=sw_height, bg=bg_color, highlightthickness=0, cursor='hand2')
        sw_canvas.pack(side='left', padx=(0, 10))
        lbl = tk.Label(frame, text=text, bg=bg_color, fg=COLOR_TEXT, font=('Segoe UI Semibold', 9), cursor='hand2')
        lbl.pack(side='left')
        state = {'active': initial_value, 'img': None}
        def redraw_switch():
            # ***<module>.AlbionBotGUI.create_puffy_toggle_switch.redraw_switch: Failure detected at line number 515 and instruction offset 22: Different bytecode
            scale = 3
            w_s, h_s = (sw_width * scale, sw_height * scale)
            im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            r_track = 12 * scale
            border = (221, 177, 99, 255) if state['active'] else (39, 72, 106, 255)
            track = (13, 55, 94, 255) if state['active'] else (4, 16, 32, 255)
            draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_track, border)
            draw_rounded_rectangle(draw, [scale, scale, w_s - scale, h_s - scale], r_track - scale, track)
            diameter = 18 * scale
            hx1 = (27 if state['active'] else 3) * scale
            hy1 = 3 * scale
            draw.ellipse([hx1, hy1, hx1 + diameter, hy1 + diameter],
                         fill=(249, 209, 122, 255), outline=(253, 230, 157, 80), width=scale)
            resized = im.resize((sw_width, sw_height), Image.Resampling.LANCZOS)
            state['img'] = ImageTk.PhotoImage(resized)
            sw_canvas.delete('all')
            sw_canvas.create_image(0, 0, image=state['img'], anchor='nw')
        def toggle(e):
            state['active'] = not state['active']
            redraw_switch()
            on_change_callback(state['active'])
        sw_canvas.bind('<Button-1>', toggle)
        lbl.bind('<Button-1>', toggle)
        redraw_switch()
        return frame
    def get_custom_config_field_bg(self, is_vmax, value, width=228, height=50):
        # ***<module>.AlbionBotGUI.get_custom_config_field_bg: Failure: Different control flow
        scale = 3
        w_s = width * scale
        h_s = height * scale
        im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        cy = h_s / 2
        ty1 = cy - 14 * scale
        ty2 = cy + 6 * scale
        tx1 = 36 * scale
        tx2 = w_s - 15 * scale
        r_track = 10 * scale
        draw_rounded_rectangle(draw, [tx1, ty1, tx2, ty2], r_track, (143, 83, 51, 255))
        draw_rounded_rectangle(draw, [tx1 + 1.5 * scale, ty1 + 1.5 * scale, tx2 - 1.5 * scale, ty2 - 1.5 * scale], r_track - 1.5 * scale, (30, 10, 48, 255))
        if not is_vmax:
            try:
                val = float(value)
            except:
                val = 0.0
            ratio = max(0.0, min(100.0, val)) / 100.0
        else:
            try:
                val = float(value)
            except:
                val = 0.0
            ratio = max(0.0, min(100000.0, val)) / 100000.0
        fx1 = tx1 + 1.5 * scale
        if ratio > 0.0:
            fx2 = fx1 + max(12, int(522 * ratio))
            if not is_vmax:
                draw_rounded_rectangle(draw, [fx1, ty1 + 1.5 * scale, fx2, ty2 - 1.5 * scale], r_track - 1.5 * scale, (170, 45, 10, 255))
                draw_rounded_rectangle(draw, [fx1, ty1 + 1.5 * scale, fx2, ty2 - 3.5 * scale], r_track - 1.5 * scale, (220, 75, 20, 255))
                draw_rounded_rectangle(draw, [fx1, ty1 + 2 * scale, fx2, ty1 + 5 * scale], 1.5 * scale, (255, 150, 100, 255))
            else:
                draw_rounded_rectangle(draw, [fx1, ty1 + 1.5 * scale, fx2, ty2 - 1.5 * scale], r_track - 1.5 * scale, (34, 96, 6, 255))
                draw_rounded_rectangle(draw, [fx1, ty1 + 1.5 * scale, fx2, ty2 - 3.5 * scale], r_track - 1.5 * scale, (92, 196, 37, 255))
                draw_rounded_rectangle(draw, [fx1, ty1 + 2 * scale, fx2, ty1 + 5 * scale], 1.5 * scale, (188, 250, 140, 255))
        def draw_star(draw, cx, cy, r):
            pts = [(cx, cy - r), (cx + r * 0.3, cy - r * 0.3), (cx + r, cy), (cx + r * 0.3, cy + r * 0.3), (cx, cy + r), (cx - r * 0.3, cy + r * 0.3), (cx - r, cy), (cx - r * 0.3, cy - r * 0.3)]
            draw.polygon(pts, fill=(255, 255, 255, 255))
        if ratio > 0.1:
            draw_star(draw, fx1 + int(522 * ratio) - 12 * scale, ty1 + 4 * scale, 4 * scale)
            draw_star(draw, tx1 + 32 * scale, ty2 - 4 * scale, 3 * scale)
        cx_coin = 20 * scale
        cy_coin = h_s / 2
        r_coin = 20 * scale
        if not is_vmax:
            img_loaded = False
            try:
                img_path = os.path.join('assets', 'icon_custo.png')
                if os.path.exists(img_path):
                    custom_icon = Image.open(img_path).convert('RGBA')
                    icon_sz = int(r_coin * 2.4)
                    custom_icon = custom_icon.resize((icon_sz, icon_sz), Image.Resampling.LANCZOS)
                    im.paste(custom_icon, (int(cx_coin - icon_sz / 2), int(cy_coin - icon_sz / 2)), custom_icon)
                    img_loaded = True
            except:
                pass
            if not img_loaded:
                draw.ellipse([cx_coin - r_coin, cy_coin - r_coin, cx_coin + r_coin, cy_coin + r_coin], fill=(143, 83, 51, 255))
                draw.ellipse([cx_coin - r_coin + 1.5 * scale, cy_coin - r_coin + 1.5 * scale, cx_coin + r_coin - 1.5 * scale, cy_coin + r_coin - 1.5 * scale], fill=(180, 130, 40, 255))
                draw.ellipse([cx_coin - r_coin + 3 * scale, cy_coin - r_coin + 3 * scale, cx_coin + r_coin - 3 * scale, cy_coin + r_coin - 3 * scale], fill=(245, 195, 55, 255))
                draw.ellipse([cx_coin - r_coin + 4.5 * scale, cy_coin - r_coin + 4.5 * scale, cx_coin + r_coin - 4.5 * scale, cy_coin + r_coin - 4.5 * scale], fill=(215, 155, 30, 255))
                for offset_x, offset_y, color in [(1.5 * scale, 1.5 * scale, (90, 50, 10, 255)), (0, 0, (255, 245, 190, 255))]:
                    draw.line([cx_coin + 6 * scale + offset_x, cy_coin - 7 * scale + offset_y, cx_coin - 6 * scale + offset_x, cy_coin + 7 * scale + offset_y], fill=color, width=int(2 * scale))
                    draw.ellipse([cx_coin - 7 * scale + offset_x, cy_coin - 7 * scale + offset_y, cx_coin - 2 * scale + offset_x, cy_coin - 2 * scale + offset_y], outline=color, width=int(1.5 * scale))
                    draw.ellipse([cx_coin + 2 * scale + offset_x, cy_coin + 2 * scale + offset_y, cx_coin + 7 * scale + offset_x, cy_coin + 7 * scale + offset_y], outline=color, width=int(1.5 * scale))
        else:
            img_loaded = False
            try:
                img_path = os.path.join('assets', 'icon_valor.png')
                if os.path.exists(img_path):
                    custom_icon = Image.open(img_path).convert('RGBA')
                    icon_sz = int(r_coin * 2.4)
                    custom_icon = custom_icon.resize((icon_sz, icon_sz), Image.Resampling.LANCZOS)
                    im.paste(custom_icon, (int(cx_coin - icon_sz / 2), int(cy_coin - icon_sz / 2)), custom_icon)
                    img_loaded = True
            except:
                pass
            if not img_loaded:
                draw.ellipse([cx_coin - r_coin, cy_coin - r_coin, cx_coin + r_coin, cy_coin + r_coin], fill=(143, 83, 51, 255))
                draw.ellipse([cx_coin - r_coin + 1.5 * scale, cy_coin - r_coin + 1.5 * scale, cx_coin + r_coin - 1.5 * scale, cy_coin + r_coin - 1.5 * scale], fill=(180, 130, 40, 255))
                draw.ellipse([cx_coin - r_coin + 3 * scale, cy_coin - r_coin + 3 * scale, cx_coin + r_coin - 3 * scale, cy_coin + r_coin - 3 * scale], fill=(245, 195, 55, 255))
                dp_top_left = (cx_coin - 11 * scale, cy_coin - 6 * scale)
                dp_top_right = (cx_coin + 11 * scale, cy_coin - 6 * scale)
                dp_bottom = (cx_coin, cy_coin + 11 * scale)
                dp_mid = (cx_coin, cy_coin - 6 * scale)
                draw.polygon([dp_top_left, dp_mid, dp_bottom], fill=(45, 105, 235, 255))
                draw.polygon([dp_top_right, dp_mid, dp_bottom], fill=(15, 45, 155, 255))
                draw.polygon([dp_top_left, dp_top_right, dp_mid], fill=(145, 195, 255, 255))
                draw.ellipse([cx_coin - 5 * scale, cy_coin - 3 * scale, cx_coin - 3 * scale, cy_coin - 1 * scale], fill=(255, 255, 255, 255))
        px1 = w_s - 85 * scale
        px2 = w_s - 20 * scale
        py1 = ty2
        py2 = ty2 + 15 * scale
        r_plaque = 3 * scale
        draw_rounded_rectangle(draw, [px1, py1, px2, py2], r_plaque, (143, 83, 51, 255))
        draw_rounded_rectangle(draw, [px1 + 1 * scale, py1 + 1 * scale, px2 - 1 * scale, py2 - 1 * scale], r_plaque - 1 * scale, (255, 218, 59, 255))
        mid_x = (px1 + px2) / 2
        draw.line([mid_x, py1 + 1.5 * scale, mid_x, py2 - 1.5 * scale], fill=(143, 83, 51, 255), width=int(1 * scale))
        lay = (py1 + py2) / 2
        lax1 = px1 + 15 * scale
        draw.polygon([(lax1 - 3.5 * scale, lay), (lax1 + 1.5 * scale, lay - 3.5 * scale), (lax1 + 1.5 * scale, lay + 3.5 * scale)], fill=(207, 96, 29, 255))
        lax2 = px1 + 22 * scale
        draw.polygon([(lax2 - 3.5 * scale, lay), (lax2 + 1.5 * scale, lay - 3.5 * scale), (lax2 + 1.5 * scale, lay + 3.5 * scale)], fill=(207, 96, 29, 255))
        rax1 = px2 - 22 * scale
        draw.polygon([(rax1 + 3.5 * scale, lay), (rax1 - 1.5 * scale, lay - 3.5 * scale), (rax1 - 1.5 * scale, lay + 3.5 * scale)], fill=(207, 96, 29, 255))
        rax2 = px2 - 15 * scale
        draw.polygon([(rax2 + 3.5 * scale, lay), (rax2 - 1.5 * scale, lay - 3.5 * scale), (rax2 - 1.5 * scale, lay + 3.5 * scale)], fill=(207, 96, 29, 255))
        resized = im.resize((width, height), Image.Resampling.LANCZOS)
        return resized

    def get_custom_config_field_bg(self, is_vmax, value, width=228, height=50):
        """Campo de configuração com aparência de placa medieval, sem ícones cartunescos."""
        scale = 3
        ws, hs = width * scale, height * scale
        image = Image.new('RGBA', (ws, hs), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        center_y = 20 * scale
        track_left, track_right = 40 * scale, (width - 14) * scale
        track_top, track_bottom = 8 * scale, 31 * scale
        radius = 8 * scale
        draw_rounded_rectangle(draw, (track_left, track_top, track_right, track_bottom),
                               radius, (39, 72, 106, 255))
        draw_rounded_rectangle(draw, (track_left + 2 * scale, track_top + 2 * scale,
                                      track_right - 2 * scale, track_bottom - 2 * scale),
                               radius - 2 * scale, (2, 9, 22, 255))
        try:
            number = float(value)
        except Exception:
            number = 0.0
        limit = 100000.0 if is_vmax else 100.0
        ratio = max(0.0, min(limit, number)) / limit
        if ratio > 0:
            fill_right = track_left + 2 * scale + int((track_right - track_left - 4 * scale) * ratio)
            fill_color = (13, 63, 108, 255) if is_vmax else (148, 125, 76, 255)
            draw_rounded_rectangle(draw, (track_left + 2 * scale, track_top + 2 * scale,
                                          max(track_left + 8 * scale, fill_right), track_bottom - 2 * scale),
                                   radius - 2 * scale, fill_color)
            draw.line((track_left + 6 * scale, track_top + 4 * scale,
                       max(track_left + 6 * scale, fill_right - 4 * scale), track_top + 4 * scale),
                      fill=(253, 230, 157, 110), width=scale)

        emblem_x, emblem_y = 20 * scale, center_y
        draw.ellipse((emblem_x - 14 * scale, emblem_y - 14 * scale,
                      emblem_x + 14 * scale, emblem_y + 14 * scale),
                     fill=(2, 9, 22, 255), outline=(221, 177, 99, 255), width=2 * scale)
        draw.ellipse((emblem_x - 10 * scale, emblem_y - 10 * scale,
                      emblem_x + 10 * scale, emblem_y + 10 * scale),
                     outline=(39, 72, 106, 255), width=scale)
        symbol = '◆' if is_vmax else '%'
        try:
            font = ImageFont.truetype('segoeuib.ttf', 10 * scale)
        except Exception:
            font = ImageFont.load_default()
        try:
            bbox = draw.textbbox((0, 0), symbol, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = 8 * scale, 10 * scale
        draw.text((emblem_x - tw / 2, emblem_y - th / 2 - scale), symbol,
                  font=font, fill=(249, 209, 122, 255))

        plaque = (143 * scale, 34 * scale, 208 * scale, 48 * scale)
        draw_rounded_rectangle(draw, plaque, 3 * scale, (39, 72, 106, 255))
        draw_rounded_rectangle(draw, (plaque[0] + scale, plaque[1] + scale,
                                      plaque[2] - scale, plaque[3] - scale),
                               2 * scale, (4, 16, 32, 255))
        middle = (plaque[0] + plaque[2]) / 2
        draw.line((middle, plaque[1] + scale, middle, plaque[3] - scale),
                  fill=(39, 72, 106, 255), width=scale)
        cy = (plaque[1] + plaque[3]) / 2
        draw.polygon(((159 * scale, cy), (166 * scale, cy - 4 * scale), (166 * scale, cy + 4 * scale)),
                     fill=(249, 209, 122, 255))
        draw.polygon(((192 * scale, cy), (185 * scale, cy - 4 * scale), (185 * scale, cy + 4 * scale)),
                     fill=(249, 209, 122, 255))
        return image.resize((width, height), Image.Resampling.LANCZOS)

    def create_header_button(self, parent, text, command):
        # ***<module>.AlbionBotGUI.create_header_button: Failure detected at line number 679 and instruction offset 2: Different bytecode
        btn = tk.Canvas(
            parent, width=22, height=22, bg=COLOR_SIDEBAR,
            highlightthickness=0, cursor='hand2', takefocus=1,
        )
        state = {'current': 'normal', 'img': None}
        def draw_btn():
            # ***<module>.AlbionBotGUI.create_header_button.draw_btn: Failure detected at line number 685 and instruction offset 30: Different bytecode
            w, h = (22, 22)
            scale = 3
            w_s, h_s = (w * scale, h * scale)
            im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            r_s = 6 * scale
            if state['current'] == 'pressed':
                draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (148, 125, 76, 255))
                draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w_s - 1 * scale, h_s - 1 * scale], r_s - 1 * scale, (5, 31, 61, 255))
                y_offset = 1.0 * scale
            else:
                if state['current'] == 'hover':
                    draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (221, 177, 99, 255))
                    draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w_s - 1 * scale, h_s - 1 * scale], r_s - 1 * scale, (13, 40, 72, 255))
                    y_offset = 0.0
                else:
                    draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (39, 72, 106, 255))
                    draw_rounded_rectangle(draw, [1 * scale, 1 * scale, w_s - 1 * scale, h_s - 1 * scale], r_s - 1 * scale, (7, 25, 48, 255))
                    y_offset = 0.0
            if text == '✕':
                cx = w_s / 2
                cy = h_s / 2 + y_offset
                sz = 3.5 * scale
                draw.line([(cx - sz, cy - sz), (cx + sz, cy + sz)], fill=(249, 209, 122, 255), width=2 * scale)
                draw.line([(cx + sz, cy - sz), (cx - sz, cy + sz)], fill=(249, 209, 122, 255), width=2 * scale)
            else:
                if text == '—':
                    cx = w_s / 2
                    cy = h_s / 2 + y_offset
                    sz = 4 * scale
                    draw.line([(cx - sz, cy), (cx + sz, cy)], fill=(249, 209, 122, 255), width=2 * scale)
                else:
                    if text == '📋':
                        cx = w_s / 2
                        cy = h_s / 2 + y_offset
                        sz_w = 3.5 * scale
                        sz_h = 4.5 * scale
                        draw.rectangle([cx - sz_w, cy - sz_h, cx + sz_w, cy + sz_h], fill=(221, 208, 179, 255))
                        draw.rectangle([cx - sz_w + 1.2 * scale, cy - sz_h + 2 * scale, cx + sz_w - 1.2 * scale, cy + sz_h - 1 * scale], fill=(44, 38, 29, 255))
                        draw.rectangle([cx - 1.5 * scale, cy - sz_h - 0.5 * scale, cx + 1.5 * scale, cy - sz_h + 1 * scale], fill=(178, 141, 77, 255))
                    else:
                        try:
                            font = ImageFont.truetype('ariblk.ttf', 9 * scale)
                        except:
                            font = ImageFont.load_default()
                        tx, ty = ((w_s - 9 * scale) / 2, (h_s - 9 * scale) / 2 - 1.5 * scale + y_offset)
                        draw.text((tx, ty), text, font=font, fill=(230, 219, 192, 255))
            resized = im.resize((w, h), Image.Resampling.LANCZOS)
            state['img'] = ImageTk.PhotoImage(resized)
            btn.delete('all')
            btn.create_image(0, 0, image=state['img'], anchor='nw')
        def on_press(e):
            state['current'] = 'pressed'
            draw_btn()
        def on_release(e):
            state['current'] = 'hover'
            draw_btn()
            command()
        def on_enter(e):
            state['current'] = 'hover'
            draw_btn()
        def on_leave(e):
            state['current'] = 'normal'
            draw_btn()
        btn.bind('<ButtonPress-1>', on_press)
        btn.bind('<ButtonRelease-1>', on_release)
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        btn.bind('<FocusIn>', on_enter)
        btn.bind('<FocusOut>', on_leave)
        btn.bind('<Return>', lambda _event: command())
        btn.bind('<space>', lambda _event: command())
        draw_btn()
        return btn
    def create_engraved_separator(self, parent):
        # ***<module>.AlbionBotGUI.create_engraved_separator: Failure detected at line number 753 and instruction offset 2: Different bytecode
        sep_frame = tk.Frame(parent, bg=COLOR_BG, height=6)
        sep_frame.pack(fill='x', pady=4)
        tk.Frame(sep_frame, bg=COLOR_NAV, height=2).pack(fill='x')
        tk.Frame(sep_frame, bg=COLOR_BORDER, height=1).pack(fill='x')

    def create_page_header(self, parent, eyebrow, title, description=''):
        """Cabecalho consistente para separar contexto, titulo e orientacao."""
        wrapper = tk.Frame(parent, bg=COLOR_BG)
        wrapper.pack(fill='x', padx=16, pady=(14, 9))
        tk.Label(
            wrapper, text=eyebrow.upper(), bg=COLOR_BG, fg=COLOR_ACCENT,
            font=UI_FONTS['caption_strong'],
        ).pack(anchor='w')
        tk.Label(
            wrapper, text=title, bg=COLOR_BG, fg=COLOR_TEXT,
            font=UI_FONTS['page_title'],
        ).pack(anchor='w', pady=(2, 0))
        if description:
            tk.Label(
                wrapper, text=description, bg=COLOR_BG, fg=COLOR_TEXT_DIM,
                font=UI_FONTS['body'], justify='left', wraplength=350,
            ).pack(anchor='w', pady=(3, 7))
        tk.Frame(wrapper, bg=COLOR_BORDER, height=1).pack(fill='x', pady=(5, 0))
        return wrapper

    def create_section_divider(self, parent, text):
        row = tk.Frame(parent, bg=COLOR_BG)
        row.pack(fill='x', padx=18, pady=(13, 6))
        tk.Label(
            row, text=text.upper(), bg=COLOR_BG, fg=COLOR_ACCENT,
            font=UI_FONTS['caption_strong'],
        ).pack(side='left')
        tk.Frame(row, bg=COLOR_BORDER, height=1).pack(
            side='left', fill='x', expand=True, padx=(10, 0), pady=7,
        )
        return row

    def create_tooltip(self, widget, text):
        """Ajuda contextual no rodapé, sem criar janela sobre a área do jogo."""
        state = {'after': None}

        def hide(_event=None):
            after_id = state.get('after')
            if after_id:
                try:
                    widget.after_cancel(after_id)
                except Exception:
                    pass
                state['after'] = None
            footer = getattr(self, 'footer', None)
            if footer is not None:
                try:
                    footer.config(text='produzido por: S e M', fg=COLOR_TEXT_DIM)
                except Exception:
                    pass

        def show():
            state['after'] = None
            try:
                if self.automacao_em_execucao() or not widget.winfo_exists():
                    return
                footer = getattr(self, 'footer', None)
                if footer is not None:
                    footer.config(text=text, fg=COLOR_ACCENT)
            except Exception:
                hide()

        def schedule(_event=None):
            hide()
            try:
                state['after'] = widget.after(550, show)
            except Exception:
                pass

        widget.bind('<Enter>', schedule, add='+')
        widget.bind('<Leave>', hide, add='+')
        widget.bind('<ButtonPress-1>', hide, add='+')
        widget.bind('<Destroy>', hide, add='+')
        widget._mkt_tooltip_state = state
        return widget
    def atualizar_botao_inicial(self):
        for child in self.start_btn_container.winfo_children():
            child.destroy()
        if self.running:
            row = tk.Frame(self.start_btn_container, bg=COLOR_BG)
            row.pack(fill='x')
            pausar_btn = self.create_3d_button(row, '⏸ PAUSAR', type_color='gold', command=self.pausar_bot)
            pausar_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
            parar_btn = self.create_3d_button(row, '■ PARAR BOT', type_color='red', command=self.toggle_bot)
            parar_btn.pack(side='left', fill='x', expand=True)
        elif getattr(self, 'buy_paused', False):
            row = tk.Frame(self.start_btn_container, bg=COLOR_BG)
            row.pack(fill='x')
            continuar_btn = self.create_3d_button(row, '▶ CONTINUAR', type_color='green', command=self.continuar_bot)
            continuar_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
            parar_btn = self.create_3d_button(row, '■ PARAR', type_color='red', command=self.pause_bot)
            parar_btn.pack(side='left', fill='x', expand=True)
        else:
            btn = self.create_3d_button(self.start_btn_container, '▶ INICIAR BOT', type_color='green', command=self.toggle_bot)
            btn.pack(fill='x')
    def create_widgets(self):
        # ***<module>.AlbionBotGUI.create_widgets: Failure: Compilation Error
        self.header = tk.Frame(self.inner_frame, bg=COLOR_SIDEBAR, height=46)
        self.header.pack(fill='x')
        self.header.pack_propagate(False)
        rem = 'MKT'
        def create_key_badge(text):
            # ***<module>.AlbionBotGUI.create_widgets.create_key_badge: Failure detected at line number 771 and instruction offset 30: Different bytecode
            w, h = (64, 24)
            scale = 3
            w_s, h_s = (w * scale, h * scale)
            im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)
            r_s = 12 * scale
            draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, ui_rgba(COLOR_BORDER))
            draw_rounded_rectangle(draw, [scale, scale, w_s - scale, h_s - scale], r_s - scale, ui_rgba(COLOR_NAV))
            try:
                font = ImageFont.truetype('segoeuib.ttf', 9 * scale)
            except:
                font = ImageFont.load_default()
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
            except:
                tw, th = (len(text) * 6 * scale, 10 * scale)
            tx = (w_s - tw) / 2
            ty = (h_s - th) / 2 - 1.5 * scale
            draw.text((tx, ty), text, font=font, fill=ui_rgba(COLOR_ACCENT))
            resized = im.resize((w, h), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(resized)
        self.key_canvas = tk.Canvas(self.header, width=64, height=24, bg=COLOR_SIDEBAR, highlightthickness=0, cursor='hand2')
        self.key_canvas.pack(side='left', padx=(10, 3), pady=9)
        self.key_img = create_key_badge(rem)
        self.key_canvas.create_image(0, 0, image=self.key_img, anchor='nw')
        self.key_canvas.bind('<Button-1>', self.start_move)
        self.key_canvas.bind('<B1-Motion>', self.do_move)
        self.close_lbl = self.create_header_button(self.header, '✕', self.encerrar_aplicativo)
        self.close_lbl.pack(side='right', padx=(3, 9), pady=10)
        self.min_lbl = self.create_header_button(self.header, '—', self.toggle_minimize)
        self.min_lbl.pack(side='right', padx=3, pady=10)
        self.log_lbl = self.create_header_button(self.header, '📋', self.log_window.toggle)
        self.log_lbl.pack(side='right', padx=3, pady=10)
        self.sound_btn = self.create_sound_toggle_button(self.header)
        self.sound_btn.pack(side='right', padx=3, pady=10)
        self.create_tooltip(self.sound_btn, 'Som das ordens confirmadas')
        self.create_tooltip(self.log_lbl, 'Abrir console de operações')
        self.create_tooltip(self.min_lbl, 'Minimizar para o controle compacto')
        self.create_tooltip(self.close_lbl, 'Fechar o MKT')
        self.title_lbl = tk.Label(self.header, text='MKT', fg=COLOR_TEXT, bg=COLOR_SIDEBAR, font=('Bahnschrift SemiBold', 12))
        self.title_lbl.pack(side='left', fill='both', expand=True, padx=5)
        self.nav_bar = tk.Frame(self.inner_frame, bg=COLOR_NAV, height=44)
        self.nav_bar.pack(fill='x')
        self.tab_btns = {}
        primary_tabs = [
            ('BOT', 'COMPRA', self.show_bot_tab),
            ('SELL', 'VENDA', self.show_sell_tab),
            ('CYCLE', 'CICLO', self.show_cycle_tab),
            ('SHOPPING', 'LISTA', self.show_shopping_tab),
            ('REMOVER', 'REMOVER PEDIDOS', self.show_remover_pedidos_tab),
        ]
        for key, display_name, cmd in primary_tabs:
            btn_3d = self.create_tab_button(self.nav_bar, key, display_name, cmd)
            btn_3d.pack(side='left', fill='both', expand=True, padx=1)
            self.tab_btns[key] = btn_3d

        self.tool_nav_bar = tk.Frame(self.inner_frame, bg=COLOR_NAV, height=36)
        self.tool_nav_bar.pack(fill='x')
        tool_tabs = [
            ('SEQ', 'CATEGORIAS', self.show_seq_tab),
            ('EDIT', 'ORDENS', self.show_edit_tab),
            ('CFG', 'AJUSTES', self.show_config_tab),
            ('SYS', 'SISTEMA', self.show_sys_tab),
        ]
        for key, display_name, cmd in tool_tabs:
            btn_3d = self.create_tab_button(
                self.tool_nav_bar, key, display_name, cmd, height=36,
            )
            btn_3d.pack(side='left', fill='both', expand=True, padx=1)
            self.tab_btns[key] = btn_3d
        self.footer = tk.Label(
            self.inner_frame,
            text='produzido por: S e M',
            bg=COLOR_NAV,
            fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption'],
            pady=6,
        )
        self.footer.pack(side='bottom', fill='x')
        self.canvas_container = tk.Frame(self.inner_frame, bg=COLOR_BG)
        self.canvas_container.pack(fill='both', expand=True)
        self.canvas_main = tk.Canvas(self.canvas_container, bg=COLOR_BG, highlightthickness=0)
        self.scrollbar_main = ttk.Scrollbar(self.canvas_container, orient='vertical', command=self.canvas_main.yview,
                                            style='Dark.Vertical.TScrollbar')
        self.content_area = tk.Frame(self.canvas_main, bg=COLOR_BG)
        self.content_area.bind('<Configure>', lambda e: self.canvas_main.configure(scrollregion=self.canvas_main.bbox('all')))
        self.canvas_window_id = self.canvas_main.create_window((0, 0), window=self.content_area, anchor='nw', width=self.width - 12)
        self.canvas_main.bind('<Configure>', lambda e: self.canvas_main.itemconfig(self.canvas_window_id, width=e.width))
        self.canvas_main.configure(yscrollcommand=self.scrollbar_main.set)
        self.canvas_main.pack(side='left', fill='both', expand=True)
        self.scrollbar_main.pack(side='right', fill='y')
        self.content_area.bind_all('<MouseWheel>', lambda e: self.canvas_main.yview_scroll(int((-1) * (e.delta / 120)), 'units'))
        self.bot_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.create_page_header(
            self.bot_tab,
            'Automação principal',
            'Central de compra',
            'Analisa o mercado e cria ordens somente dentro dos seus limites.',
        )
        stats_grid = tk.Frame(self.bot_tab, bg=COLOR_BG)
        stats_grid.pack(fill='x', padx=12, pady=(0, 6))
        self.card_status = self.create_compact_stat_card(stats_grid, 'STATUS', 'PARADO', 0)
        self.card_orders = self.create_compact_stat_card(stats_grid, 'ORDENS', '0', 1)
        self.card_profit = self.create_compact_stat_card(stats_grid, 'LUCRO ESTIMADO', '0', 2)
        self.cat_active_var = tk.BooleanVar(value=self.offsets.get('cat_ativo', False))
        def toggle_chk(new_val):
            self.cat_active_var.set(new_val)
            self.salvar_calibração('cat_ativo', new_val)
            self.log(f">>> Troca Automática de Categoria: {('ATIVADA' if new_val else 'DESATIVADA')}")
        self.chk_frame = self.create_puffy_toggle_switch(self.bot_tab, 'Troca Automática de Categoria', self.cat_active_var.get(), toggle_chk)
        self.chk_frame.pack(fill='x', padx=16, pady=5)
        calibration_bar = tk.Frame(
            self.bot_tab,
            bg=COLOR_CARD,
            padx=12,
            pady=8,
            cursor='hand2',
        )
        calibration_bar.pack(fill='x', padx=14, pady=(4, 6))
        tk.Label(calibration_bar, text='CALIBRAGEM', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
                 font=('Segoe UI Semibold', 8)).pack(side='left')
        self.bot_calibration_lbl = tk.Label(calibration_bar, text='VERIFICANDO', bg=COLOR_CARD,
                                            fg=COLOR_ACCENT, font=('Segoe UI Semibold', 8))
        self.bot_calibration_lbl.pack(side='right')
        for calibration_widget in (calibration_bar, *calibration_bar.winfo_children()):
            calibration_widget.bind('<Button-1>', lambda _event: self.show_calib_tab())
        self.optional_calibration_notice = tk.Frame(
            self.bot_tab,
            bg=UI_COLORS['warning'],
            padx=12,
            pady=6,
            cursor='hand2',
        )
        self.optional_calibration_notice_lbl = tk.Label(
            self.optional_calibration_notice,
            text='',
            bg=UI_COLORS['warning'],
            fg=COLOR_BG,
            font=('Segoe UI Semibold', 8),
            justify='left',
            wraplength=340,
            anchor='w',
        )
        self.optional_calibration_notice_lbl.pack(fill='x')
        for notice_widget in (self.optional_calibration_notice, self.optional_calibration_notice_lbl):
            notice_widget.bind('<Button-1>', lambda _event: self.show_calib_tab())
        self.start_btn_container = tk.Frame(self.bot_tab, bg=COLOR_BG)
        self.start_btn_container.pack(fill='x', padx=12, pady=6)
        self.atualizar_botao_inicial()
        self._criar_toggle_media_semanal(self.bot_tab).pack(
            fill='x', padx=12, pady=(0, 6)
        )
        self.tree_border = tk.Frame(self.bot_tab, bg=COLOR_NAV, highlightthickness=0)
        self.tree_border.pack(fill='x', padx=12, pady=6)
        self.tree = ttk.Treeview(self.tree_border, columns=('Item', 'V', 'C', 'ROI'), show='headings', height=11)
        self.tree.heading('Item', text='ITEM')
        self.tree.heading('V', text='VENDA')
        self.tree.heading('C', text='COMPRA')
        self.tree.heading('ROI', text='CUSTO')
        w_item = self.offsets.get('col_w_item', 95)
        w_v = self.offsets.get('col_w_v', 55)
        w_c = self.offsets.get('col_w_c', 55)
        w_roi = self.offsets.get('col_w_roi', 43)
        self.tree.column('Item', width=max(145, int(w_item)), minwidth=125, stretch=True)
        self.tree.column('V', width=max(66, int(w_v)), minwidth=60, stretch=False, anchor='e')
        self.tree.column('C', width=max(66, int(w_c)), minwidth=60, stretch=False, anchor='e')
        self.tree.column('ROI', width=max(58, int(w_roi)), minwidth=54, stretch=False, anchor='center')
        self.tree.pack(fill='x')
        self.tree_empty_state = tk.Frame(self.tree_border, bg=COLOR_NAV, padx=18, pady=12)
        tk.Label(
            self.tree_empty_state, text='◇', bg=COLOR_NAV,
            fg=COLOR_ACCENT_DIM, font=('Segoe UI Semibold', 15),
        ).pack()
        tk.Label(
            self.tree_empty_state, text='Nenhuma análise nesta sessão',
            bg=COLOR_NAV, fg=COLOR_TEXT, font=UI_FONTS['body_strong'],
        ).pack(pady=(2, 0))
        tk.Label(
            self.tree_empty_state, text='Inicie a Compra para acompanhar as oportunidades.',
            bg=COLOR_NAV, fg=COLOR_TEXT_DIM, font=UI_FONTS['caption'],
        ).pack(pady=(2, 0))
        self.tree_empty_state.place(relx=0.5, rely=0.56, anchor='center')
        self.tree.bind('<ButtonRelease-1>', self.on_tree_resize)
        self.tree.tag_configure(
            'opp', background=UI_COLORS['success_surface'],
            foreground=UI_COLORS['success_text'],
        )
        self.tree.tag_configure('even', background=COLOR_CARD, foreground=COLOR_TEXT)
        self.tree.tag_configure('odd', background=UI_COLORS['surface_alt'], foreground=COLOR_TEXT)
        btn_reset = self.create_3d_button(self.bot_tab, 'ZERAR CONTADORES', type_color='red', command=self.resetar_contadores)
        btn_reset.pack(fill='x', padx=12, pady=(5, 10))

        # Tela reservada para o futuro bot de pedidos de venda.
        # Nenhuma acao desta aba chama ou altera a logica atual do bot de compra.
        self.sell_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.create_page_header(
            self.sell_tab,
            'Automação de inventário',
            'Venda automática',
            'Cria pedidos de venda item por item e ignora preços indisponíveis.',
        )

        self.sell_start_btn_container = tk.Frame(self.sell_tab, bg=COLOR_BG)
        self.sell_start_btn_container.pack(fill='x', padx=12, pady=(8, 4))
        self.atualizar_botao_venda()

        sell_status_card = tk.Frame(
            self.sell_tab,
            bg=COLOR_CARD,
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        sell_status_card.pack(fill='x', padx=12, pady=(8, 6))
        tk.Label(
            sell_status_card,
            text='STATUS DO MODULO',
            bg=COLOR_CARD,
            fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption_strong'],
        ).pack(anchor='w')
        self.sell_module_status_lbl = tk.Label(
            sell_status_card,
            text='VERIFICANDO CALIBRAGEM',
            bg=COLOR_CARD,
            fg=COLOR_ACCENT,
            font=UI_FONTS['section_title'],
        )
        self.sell_module_status_lbl.pack(anchor='w', pady=(3, 0))

        sell_prepare_card = tk.Frame(
            self.sell_tab,
            bg=COLOR_CARD,
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        sell_prepare_card.pack(fill='x', padx=12, pady=6)
        tk.Label(
            sell_prepare_card,
            text='COMO A VENDA FUNCIONA',
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            font=UI_FONTS['body_strong'],
        ).pack(anchor='w')
        tk.Label(
            sell_prepare_card,
            text='Abre o item, valida o preço, reduz 1 prata e cria a venda. Depois avança pela lista automaticamente.',
            bg=COLOR_CARD,
            fg=COLOR_TEXT_DIM,
            font=UI_FONTS['body'],
            justify='left',
            wraplength=320,
        ).pack(anchor='w', pady=(5, 10))

        for item_text, item_status, item_color in (
            ('Motor de venda', 'PRONTO', COLOR_SUCCESS),
            ('Calibragem da venda', 'VERIFICANDO', COLOR_ACCENT),
        ):
            sell_row = tk.Frame(sell_prepare_card, bg=COLOR_CARD)
            sell_row.pack(fill='x', pady=3)
            tk.Label(
                sell_row,
                text=item_text,
                bg=COLOR_CARD,
                fg=COLOR_TEXT,
                font=UI_FONTS['body'],
            ).pack(side='left')
            status_label = tk.Label(
                sell_row,
                text=item_status,
                bg=COLOR_CARD,
                fg=item_color,
                font=UI_FONTS['caption_strong'],
            )
            status_label.pack(side='right')
            if item_text == 'Calibragem da venda':
                self.sell_prepare_calibration_lbl = status_label

        tk.Label(
            self.sell_tab,
            text='F7 inicia • F8 ou Insert interrompe • F9 alterna Pausa protegida.',
            bg=COLOR_BG,
            fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption'],
            pady=10,
        ).pack()

        sell_config_btn = self.create_3d_button(
            self.sell_tab, 'CONFIGURAR VENDA',
            type_color='gold', command=self.show_calib_tab,
        )
        sell_config_btn.pack(fill='x', padx=12, pady=(4, 8))

        self._create_cycle_tab()
        self._create_shopping_tab()
        self._create_remover_pedidos_tab()

        self.calib_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        back_btn_calib = tk.Label(self.calib_tab, text='←  CONFIGURAÇÕES', fg=COLOR_TEXT_DIM, bg=COLOR_BG, font=('Segoe UI Semibold', 8), cursor='hand2')
        back_btn_calib.pack(anchor='w', padx=16, pady=(14, 2))
        back_btn_calib.bind('<Button-1>', lambda e: self.show_config_tab())
        self.calib_status_labels = {}
        health_card = tk.Frame(
            self.calib_tab,
            bg=COLOR_CARD,
            padx=14,
            pady=13,
        )
        health_card.pack(fill='x', padx=12, pady=(8, 8))
        tk.Label(
            health_card,
            text='CALIBRAGEM DO BOT',
            bg=COLOR_CARD,
            fg=COLOR_TEXT_DIM,
            font=('Segoe UI Semibold', 8),
        ).pack(anchor='w')
        tk.Label(
            health_card,
            text='Configure onde o bot deve agir',
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            font=('Bahnschrift SemiBold', 13),
        ).pack(anchor='w', pady=(3, 0))
        self.calib_health_lbl = tk.Label(
            health_card,
            text='Verificando configuração...',
            bg=COLOR_CARD,
            fg=COLOR_TEXT_DIM,
            font=('Segoe UI', 8),
        )
        self.calib_health_lbl.pack(anchor='w', pady=(3, 11))
        guide_btn = self.create_3d_button(
            health_card,
            'INICIAR CALIBRAGEM GUIADA DE COMPRA',
            type_color='green',
            command=lambda: self.abrir_calibragem_guiada('buy'),
        )
        guide_btn.pack(fill='x')
        sell_health_card = tk.Frame(
            self.calib_tab, bg=COLOR_CARD, padx=14, pady=13,
            highlightthickness=1, highlightbackground=COLOR_BORDER,
        )
        sell_health_card.pack(fill='x', padx=12, pady=(4, 8))
        tk.Label(
            sell_health_card, text='CALIBRAGEM DA VENDA', bg=COLOR_CARD,
            fg=COLOR_TEXT_DIM, font=('Segoe UI Semibold', 8),
        ).pack(anchor='w')
        self.sell_calibration_lbl = tk.Label(
            sell_health_card, text='CALIBRAGEM PENDENTE', bg=COLOR_CARD,
            fg=COLOR_ACCENT, font=('Segoe UI Semibold', 9),
        )
        self.sell_calibration_lbl.pack(anchor='w', pady=(3, 8))
        sell_guide_btn = self.create_3d_button(
            sell_health_card, 'INICIAR CALIBRAGEM GUIADA DE VENDA',
            type_color='green', command=lambda: self.abrir_calibragem_guiada('sell'),
        )
        sell_guide_btn.pack(fill='x', pady=(0, 3))
        sell_test_btn = self.create_3d_button(
            sell_health_card, 'VALIDAR CALIBRAGEM DE VENDA',
            type_color='gold', command=self.testar_calibragem_venda,
        )
        sell_test_btn.pack(fill='x')
        cycle_health_card = tk.Frame(
            self.calib_tab, bg=COLOR_CARD, padx=14, pady=13,
            highlightthickness=1, highlightbackground=COLOR_BORDER,
        )
        cycle_health_card.pack(fill='x', padx=12, pady=(4, 8))
        tk.Label(
            cycle_health_card, text='CALIBRAGEM DO CICLO AUTOMÁTICO',
            bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
            font=('Segoe UI Semibold', 8),
        ).pack(anchor='w')
        self.cycle_calibration_lbl = tk.Label(
            cycle_health_card, text='CALIBRAGEM PENDENTE', bg=COLOR_CARD,
            fg=COLOR_ACCENT, font=('Segoe UI Semibold', 9),
        )
        self.cycle_calibration_lbl.pack(anchor='w', pady=(3, 8))
        cycle_guide_btn = self.create_3d_button(
            cycle_health_card, 'INICIAR CALIBRAGEM GUIADA DO CICLO',
            type_color='green', command=lambda: self.abrir_calibragem_guiada('cycle'),
        )
        cycle_guide_btn.pack(fill='x', pady=(0, 3))
        cycle_test_btn = self.create_3d_button(
            cycle_health_card, 'VALIDAR CALIBRAGEM DO CICLO',
            type_color='gold', command=self.testar_calibragem_ciclo,
        )
        cycle_test_btn.pack(fill='x')
        calib_groups = [
            ('Navegação', [('Âncora (X do Modal)', 'ancora', 'area'), ('Área da Lista (Itens)', 'area_lista', 'area'), ('Próxima Página (>)', 'btn_proxima', 'click')]),
            ('Leitura (OCR)', [('Área Nome Item', 'nome', 'area'), ('Área Preço Venda', 'venda', 'area'), ('Área Preço Compra', 'compra', 'area'), ('Cor da Linha do Topo (opcional)', 'compra_topo_cor', 'area'), ('Área Ícone (Brilho)', 'icone', 'area'), ('Preço Médio • opcional, só p/ verificar liquidez semanal', 'preco_medio', 'area')]),
            ('Ações de Compra', [('Amostra Pedido (somente 1 botão)', 'btn_pedido', 'area'), ('Botão (+)', 'btn_mais', 'click'), ('Preço Final no Modal', 'preco_final_compra', 'area'), ('Criar Ordem', 'btn_criar', 'click'), ('Botão SIM (Confirmar)', 'btn_sim', 'area'), ('Botão NÃO (Cancelar)', 'btn_nao', 'area')]),
            ('Rolagem / Arraste', [('Início Arraste', 'drag_start', 'click'), ('Fim Arraste', 'drag_end', 'click'), ('Reset Topo (Início)', 'top_start', 'click'), ('Reset Topo (Fim)', 'top_end', 'click')]),
            ('Venda', [('Área Botões Vender', 'sell_buttons_area', 'area'), ('Amostra Botão Vender', 'sell_button_sample', 'area'), ('Diminuir Preço (-)', 'sell_price_minus', 'click'), ('Área Valor Venda', 'sell_price_value', 'area'), ('Fechar Item (X)', 'sell_close_button', 'click'), ('Criar Venda', 'sell_create_button', 'click')]),
            ('Ciclo Compra / Venda', [('Contador de Transações', 'cycle_counter_area', 'area'), ('Número da Página de Compra', 'buy_page_number_area', 'area'), ('Pegar todos', 'cycle_collect_all', 'click'), ('Abrir Venda', 'cycle_sell_menu', 'click'), ('Abrir Ordem de Compra', 'cycle_buy_menu', 'click')]),
            ('Compra Programada', [('Campo de Busca do Mercado', 'busca_mercado', 'click'), ('Valor da Quantia (contorne largo, até 5 dígitos)', 'shopping_qtd_valor', 'area')]),
            ('Fechamento de ordens • opcional', [("Área dos botões de fechar (X)", 'area_fecha_pedidos', 'area')]),
            ('Remover Pedidos', [
                ('Área da Lista (Pedidos de Compra)', 'remover_pedidos_area_lista', 'area'),
                ('Amostra do botão EDITAR (somente 1)', 'remover_pedidos_btn_editar', 'area'),
                ('Amostra do X de cancelar (somente 1)', 'remover_pedidos_btn_cancelar', 'area'),
                ('Cor do topo em "Editar pedido de compra"', 'remover_pedidos_topo_cor', 'area'),
                ('Próxima Página (>)', 'remover_pedidos_btn_proxima', 'click'),
                ('Início Arraste (Rolagem)', 'remover_pedidos_drag_start', 'click'),
                ('Fim Arraste (Rolagem)', 'remover_pedidos_drag_end', 'click'),
                ('Reset Topo (Início)', 'remover_pedidos_top_start', 'click'),
                ('Reset Topo (Fim)', 'remover_pedidos_top_end', 'click'),
            ])
        ]
        for group_name, fields in calib_groups:
            header_frame = tk.Frame(self.calib_tab, bg=COLOR_BG)
            header_frame.pack(fill='x', padx=16, pady=(15, 6))
            tk.Label(header_frame, text=group_name.upper(), bg=COLOR_BG, fg=COLOR_ACCENT,
                     font=('Bahnschrift SemiBold', 8)).pack(side='left')
            tk.Frame(header_frame, bg=COLOR_BORDER, height=1).pack(side='left', fill='x', expand=True, padx=(10, 0), pady=8)
            for label, key, mode in fields:
                row_bg = COLOR_CARD
                f = tk.Frame(self.calib_tab, bg=row_bg, padx=12, pady=7)
                f.pack(fill='x', padx=12, pady=3)
                status_lbl = tk.Label(
                    f, text='●', bg=row_bg, fg=UI_COLORS['text_tertiary'],
                    font=UI_FONTS['caption'],
                )
                status_lbl.pack(side='left', padx=(0, 9))
                tk.Label(
                    f, text=label, bg=row_bg, fg=COLOR_TEXT, font=('Segoe UI Semibold', 9),
                    wraplength=190, justify='left',
                ).pack(side='left', fill='x')
                btn = self.create_3d_button(f, 'MARCAR', type_color='gold', command=lambda k=key, m=mode: self.iniciar_calibragem_campo(k, m))
                btn.pack(side='right')
                self.calib_status_labels[key] = status_lbl
        self.test_calib_btn = self.create_3d_button(self.calib_tab, 'VALIDAR SEM CLIQUES', type_color='gold', command=self.testar_calibragem)
        self.test_calib_btn.pack(fill='x', padx=12, pady=(16, 5))
        self.reset_btn = self.create_3d_button(self.calib_tab, 'REFAZER TODA A CALIBRAGEM', type_color='red', command=self.resetar_calibragens)
        self.reset_btn.pack(fill='x', padx=12, pady=(3, 14))
        self.root.after(200, self.atualizar_status_calibragem)
        self.config_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.create_page_header(
            self.config_tab,
            'Controles do bot',
            'Ajustes',
            'Defina os limites de compra e o ritmo dos cliques.',
        )
        self.create_section_divider(self.config_tab, 'Limites financeiros')
        def create_config_field(parent, label, attr_name, is_vmax):
            # ***<module>.AlbionBotGUI.create_widgets.create_config_field: Failure: Compilation Error
            f = tk.Frame(parent, bg=COLOR_BG, pady=5)
            f.pack(fill='x', padx=15)
            title_row = tk.Frame(f, bg=COLOR_BG)
            title_row.pack(fill='x', pady=(0, 2))
            tk.Label(title_row, text=label, bg=COLOR_BG, fg=COLOR_TEXT,
                     font=('Segoe UI Semibold', 8)).pack(side='left')
            if attr_name == 'config_lucro_ent':
                help_btn = tk.Button(
                    title_row,
                    text='?',
                    command=self.mostrar_ajuda_custo_maximo,
                    width=2,
                    height=1,
                    bg=UI_COLORS['surface_raised'],
                    fg=COLOR_ACCENT,
                    activebackground=UI_COLORS['surface_hover'],
                    activeforeground=COLOR_TEXT,
                    relief='flat',
                    bd=0,
                    cursor='hand2',
                    font=('Segoe UI Semibold', 8),
                    padx=0,
                    pady=0,
                )
                help_btn.pack(side='left', padx=(6, 0))
                self.cost_help_btn = help_btn
            field_descriptions = {
                'config_lucro_ent': 'Percentual mínimo de lucro desejado sobre o preço de venda de cada item.',
                'config_vmax_ent': 'Máximo de prata que uma única Buy Order pode utilizar.',
            }
            if attr_name in field_descriptions:
                tk.Label(
                    f,
                    text=field_descriptions[attr_name],
                    bg=COLOR_BG,
                    fg=COLOR_TEXT_DIM,
                    font=('Segoe UI', 7),
                ).pack(anchor='w', pady=(0, 1))
            width = 228
            height = 50
            canv = tk.Canvas(f, width=width, height=height, bg=COLOR_BG, highlightthickness=0)
            canv.pack()
            val_holder = ['1.0' if not is_vmax else '100000']
            editable_holder = [True]
            def update_canv_bg():
                # ***<module>.AlbionBotGUI.create_widgets.create_config_field.update_canv_bg: Failure: Different bytecode
                val_str = val_holder[0]
                bg_img = self.get_custom_config_field_bg(is_vmax, val_str, width, height)
                canv.bg_ref = ImageTk.PhotoImage(bg_img)
                canv.delete('bg_img')
                canv.create_image(0, 0, image=canv.bg_ref, anchor='nw', tags='bg_img')
                canv.tag_lower('bg_img')
                canv.delete('text_val')
                value_color = COLOR_TEXT if editable_holder[0] else COLOR_TEXT_DIM
                canv.create_text(125, 22, text=val_str, fill=COLOR_NAV, font=('Segoe UI Semibold', 9), tags='text_val')
                canv.create_text(124, 21, text=val_str, fill=value_color, font=('Segoe UI Semibold', 9), tags='text_val')
                if attr_name in ('config_lucro_ent', 'config_vmax_ent') and hasattr(self, 'financial_rule_summary'):
                    self.atualizar_resumo_limites()
                    self._atualizar_resultado_personalizado()
            entry_bg = UI_COLORS['surface_hover'] if not is_vmax else UI_COLORS['surface_raised']
            ent = tk.Entry(canv, bg=entry_bg, fg=COLOR_TEXT, font=('Segoe UI Semibold', 9), justify='center', relief='flat', highlightthickness=0, insertbackground=COLOR_TEXT)
            def finish_edit(event=None):
                # ***<module>.AlbionBotGUI.create_widgets.create_config_field.finish_edit: Failure: Different bytecode
                typed = ent.get()
                if not is_vmax:
                    try:
                        val = float(typed)
                        val = max(0.0, min(100.0, val))
                        val_holder[0] = f'{val:.1f}'
                    except:
                        val_holder[0] = typed
                else:
                    try:
                        val = float(typed)
                        val = max(0.0, val)
                        val_holder[0] = f'{int(val)}'
                    except:
                        val_holder[0] = typed
                canv.delete('entry_window')
                update_canv_bg()
            ent.bind('<Return>', finish_edit)
            ent.bind('<FocusOut>', finish_edit)
            def start_edit(event=None):
                # ***<module>.AlbionBotGUI.create_widgets.create_config_field.start_edit: Failure: Different bytecode
                if not editable_holder[0]:
                    return
                ent.delete(0, 'end')
                ent.insert(0, val_holder[0])
                canv.create_window(124, 21, window=ent, width=90 if not is_vmax else 105, height=18, tags='entry_window')
                ent.focus_set()
                ent.select_range(0, 'end')
            def on_canv_click(event):
                # ***<module>.AlbionBotGUI.create_widgets.create_config_field.on_canv_click: Failure: Different control flow
                if not editable_holder[0]:
                    return
                x, y = (event.x, event.y)
                if 31 <= y <= 48 and 143 <= x <= 208:
                                try:
                                    curr_val = float(val_holder[0])
                                except:
                                    curr_val = 0.0
                                if x < 176:
                                    if not is_vmax:
                                        new_val = max(0.0, curr_val - 1.0)
                                    else:
                                        new_val = max(0, curr_val - 5000)
                                else:
                                    if not is_vmax:
                                        new_val = min(100.0, curr_val + 1.0)
                                    else:
                                        new_val = curr_val + 5000
                                if not is_vmax:
                                    val_holder[0] = f'{new_val:.1f}'
                                else:
                                    val_holder[0] = f'{int(new_val)}'
                                update_canv_bg()
                start_edit(event)
            canv.bind('<Button-1>', on_canv_click)
            class EntryWrapper:
                def __init__(self, val_h, editable_h, update_fn, ent_widget, canvas_widget):
                    self.val_h = val_h
                    self.editable_h = editable_h
                    self.update_fn = update_fn
                    self.ent_widget = ent_widget
                    self.master = canvas_widget
                def get(self):
                    return self.val_h[0]
                def delete(self, first, last=None):
                    self.val_h[0] = ''
                    self.ent_widget.delete(first, last)
                def insert(self, index, string):
                    self.val_h[0] = string
                    self.ent_widget.delete(0, 'end')
                    self.ent_widget.insert(0, string)
                    self.update_fn()
                def set_editable(self, editable):
                    self.editable_h[0] = bool(editable)
                    self.master.config(cursor='xterm' if editable else 'arrow')
                    self.update_fn()
            wrapped_ent = EntryWrapper(val_holder, editable_holder, update_canv_bg, ent, canv)
            setattr(self, attr_name, wrapped_ent)
            canv.update_bg = update_canv_bg
            update_canv_bg()
            return wrapped_ent

        bank_card = tk.Frame(
            self.config_tab,
            bg=COLOR_CARD,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        bank_card.pack(fill='x', padx=15, pady=(4, 8))
        tk.Label(
            bank_card,
            text='BANCA OPERACIONAL',
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            font=('Segoe UI Semibold', 8),
        ).pack(anchor='w')
        tk.Label(
            bank_card,
            text='Orçamento máximo que o bot poderá comprometer nesta execução. Use 0 para não limitar o total.',
            bg=COLOR_CARD,
            fg=COLOR_TEXT_DIM,
            wraplength=315,
            justify='left',
            font=('Segoe UI', 7),
        ).pack(anchor='w', pady=(2, 6))
        self.operational_bank_entry = tk.Entry(
            bank_card,
            bg=UI_COLORS['field'],
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            justify='center',
            relief='flat',
            highlightthickness=1,
            highlightbackground=COLOR_ACCENT_DIM,
            font=('Segoe UI Semibold', 10),
        )
        self.operational_bank_entry.pack(fill='x', ipady=6)
        self.operational_bank_entry.insert(0, '0')
        self.operational_bank_entry.bind('<KeyRelease>', self._on_operational_bank_change)
        self.operational_bank_entry.bind('<FocusOut>', self._format_operational_bank)
        self.operational_bank_entry.bind('<Return>', self._format_operational_bank)

        tk.Label(
            bank_card,
            text='PERFIL DE OPERAÇÃO',
            bg=COLOR_CARD,
            fg=COLOR_TEXT_DIM,
            font=('Segoe UI Semibold', 8),
        ).pack(anchor='w', pady=(10, 5))
        profile_grid = tk.Frame(bank_card, bg=COLOR_CARD)
        profile_grid.pack(fill='x')
        self.purchase_profile = PROFILE_CUSTOM
        self.purchase_profile_buttons = {}
        for index, profile in enumerate((
            PROFILE_CONSERVATIVE,
            PROFILE_BALANCED,
            PROFILE_AGGRESSIVE,
            PROFILE_CUSTOM,
        )):
            button = tk.Button(
                profile_grid,
                text=PROFILE_LABELS[profile].upper(),
                command=lambda selected=profile: self.selecionar_perfil_compra(selected),
                bg=COLOR_CARD,
                fg=COLOR_TEXT_DIM,
                activebackground=COLOR_ACCENT_DIM,
                activeforeground=COLOR_TEXT,
                relief='flat',
                bd=0,
                cursor='hand2',
                font=('Segoe UI Semibold', 7),
                padx=4,
                pady=5,
            )
            button.grid(row=index // 2, column=index % 2, sticky='ew', padx=2, pady=2)
            self.purchase_profile_buttons[profile] = button
        profile_grid.grid_columnconfigure(0, weight=1)
        profile_grid.grid_columnconfigure(1, weight=1)

        create_config_field(self.config_tab, '1. LUCRO MÍNIMO POR VENDA (%)', 'config_lucro_ent', False)
        tk.Frame(self.config_tab, bg=COLOR_BG, height=5).pack()
        create_config_field(self.config_tab, '2. LIMITE POR ORDEM (PRATA)', 'config_vmax_ent', True)
        self.create_section_divider(self.config_tab, 'Velocidade da automação')
        create_config_field(self.config_tab, 'INTERVALO ENTRE CLIQUES (SEGUNDOS)', 'config_delay_clique_ent', False)
        tk.Frame(self.config_tab, bg=COLOR_BG, height=5).pack()
        create_config_field(self.config_tab, 'ESPERA APÓS TROCAR DE PÁGINA (SEGUNDOS)', 'config_delay_pagina_ent', False)
        self.create_section_divider(self.config_tab, 'Proteção de execução')
        protected_pause_card = tk.Frame(
            self.config_tab,
            bg=COLOR_CARD,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
        )
        protected_pause_card.pack(fill='x', padx=20, pady=(2, 5))
        self.protected_pause_enabled = bool(
            self.offsets.get(bot.PROTECTED_PAUSE_ENABLED_KEY, False)
        )
        protected_pause_checkbox = self.create_puffy_checkbox(
            protected_pause_card,
            'PAUSA PROTEGIDA',
            self.protected_pause_enabled,
            self.alternar_pausa_protegida,
            bg_color=COLOR_CARD,
        )
        self.protected_pause_checkbox = protected_pause_checkbox
        protected_pause_checkbox.pack(anchor='w')
        tk.Label(
            protected_pause_card,
            text='Pausas de 3–7 minutos, sorteadas a cada 45–90 minutos.\n'
                 'A pausa começa somente entre operações concluídas. F9 ativa ou desativa.',
            bg=COLOR_CARD,
            fg=COLOR_TEXT_DIM,
            justify='left',
            wraplength=315,
            font=('Segoe UI', 7),
        ).pack(anchor='w', padx=(30, 0), pady=(4, 0))
        self.save_cfg_btn = self.create_3d_button(self.config_tab, 'SALVAR CONFIGURAÇÕES', type_color='green', command=self.salvar_ajustes_financeiros)
        self.save_cfg_btn.pack(fill='x', padx=20, pady=(20, 10))
        self.create_section_divider(self.config_tab, 'Calibragem')
        self.calib_sub_btn = self.create_3d_button(self.config_tab, 'CALIBRAR TELA', type_color='yellow', command=self.show_calib_tab)
        self.calib_sub_btn.pack(fill='x', padx=20, pady=5)
        self.cliq_sub_btn = self.create_3d_button(self.config_tab, 'CALIBRAR CLIQUES', type_color='yellow', command=self.show_cliq_tab)
        self.cliq_sub_btn.pack(fill='x', padx=20, pady=5)
        self.seq_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.seq_list_frame = tk.Frame(self.seq_tab, bg=COLOR_BG)
        self.seq_list_frame.pack(fill='both', expand=True)
        self.render_seq_tab()
        self.cliq_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.render_cliq_tab()
        self.edit_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.create_page_header(
            self.edit_tab,
            'Gerenciamento',
            'Fechamento de ordens',
            'Encerra pedidos existentes usando a calibragem configurada.',
        )
        edit_cnt = tk.Frame(self.edit_tab, bg=COLOR_BG)
        edit_cnt.pack(fill='both', expand=True, pady=18)
        self.edit_gif_lbl = tk.Label(edit_cnt, bg=COLOR_BG)
        self.edit_gif_lbl.pack(pady=(0, 10))
        try:
            from PIL import ImageSequence
            gif_img = Image.open('assets/operando.gif')
            self.fechamento_frames = [ImageTk.PhotoImage(img.copy().convert('RGBA')) for img in ImageSequence.Iterator(gif_img)]
        except Exception as e:
            self.fechamento_frames = []
        self.fechamento_frame_idx = 0
        self.edit_status_lbl = tk.Label(edit_cnt, text='STATUS: PAUSADO', fg=COLOR_TEXT_DIM, bg=COLOR_BG, font=('Segoe UI Semibold', 8))
        self.edit_status_lbl.pack(pady=(0, 20))
        self.edit_btn = self.create_3d_button(edit_cnt, 'INICIAR FECHAMENTO', type_color='gold', command=self.toggle_fechamento)
        self.edit_btn.pack(fill='x', padx=20)
        self.edit_guide_btn = self.create_3d_button(
            edit_cnt,
            'CALIBRAR FECHAMENTO',
            type_color='gold',
            command=lambda: self.abrir_calibragem_guiada('close'),
        )
        self.edit_guide_btn.pack(fill='x', padx=20, pady=(8, 0))
        self.sys_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.create_page_header(
            self.sys_tab,
            'Diagnóstico',
            'Sistema e dependências',
            'Verifique ou reinstale os componentes necessários para executar o MKT.',
        )
        self.btn_install_sys = self.create_3d_button(self.sys_tab, 'INICIAR INSTALAÇÃO', type_color='gold', command=self.iniciar_instalacao_sistema)
        self.btn_install_sys.pack(pady=(8, 4), padx=25, fill='x')
        self.create_section_divider(self.sys_tab, 'Status do sistema')
        _SYS_DEPS = [
            ('pyautogui',   'pyautogui',    'Bot - Cliques'),
            ('pygetwindow', 'pygetwindow',  'Bot - Janela Albion'),
            ('cv2',         'opencv-python','Bot - Visão Computacional'),
            ('numpy',       'numpy',        'Bot - Cálculos'),
            ('PIL',         'pillow',       'Interface - Imagens'),
            ('easyocr',     'easyocr',      'Bot - OCR de Preços'),
            ('torch',       'torch',        'Bot - Motor OCR'),
            ('torchvision', 'torchvision',  'Bot - Visão OCR'),
            ('requests',    'requests',     'Licença - API'),
        ]
        self._sys_dep_labels = {}
        deps_frame = tk.Frame(self.sys_tab, bg=COLOR_BG)
        deps_frame.pack(fill='x', padx=10)
        missing_components = 0
        for mod, _pip_name, _desc in _SYS_DEPS:
            try:
                __import__(mod)
            except Exception:
                missing_components += 1
        ready = missing_components == 0
        status_card = tk.Frame(deps_frame, bg=COLOR_CARD, padx=12, pady=12)
        status_card.pack(fill='x', pady=2)
        tk.Label(
            status_card,
            text='●' if ready else '!',
            bg=COLOR_CARD,
            fg=COLOR_SUCCESS if ready else COLOR_ERROR,
            font=('Segoe UI Semibold', 10),
            width=3,
        ).pack(side='left')
        tk.Label(
            status_card,
            text='MKT pronto para executar' if ready else 'Reparo do sistema necessário',
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            font=('Segoe UI Semibold', 9),
            anchor='w',
        ).pack(side='left', padx=5)
        self.show_bot_tab()
    def iniciar_instalacao_sistema(self):
        InstallerModal(self.root, self.log)
    def toggle_minimize(self, event=None):
        if not self.minimized:
            if hasattr(self, 'log_window'):
                self.log_window.hide()
            self.root.withdraw()
            self.minimized = True
            self._mini_win = tk.Toplevel(self.root)
            self._mini_win.title('MKT - Controle compacto')
            self._mini_win.overrideredirect(True)
            self._mini_win.attributes('-topmost', True)
            self._mini_win.resizable(False, False)
            self._mini_win.config(bg=COLOR_ACCENT)
            self._mini_win.geometry(f'{MINI_HUD_WIDTH}x{MINI_HUD_HEIGHT}')
            aplicar_cantos_arredondados(self._mini_win)

            border = tk.Frame(self._mini_win, bg=COLOR_ACCENT, padx=1, pady=1)
            border.pack(fill='both', expand=True)
            hud = tk.Frame(border, bg=COLOR_SIDEBAR)
            hud.pack(fill='both', expand=True)

            hint_box = tk.Frame(hud, bg=COLOR_NAV)
            hint_box.pack(side='bottom', fill='x')
            tk.Label(
                hint_box, text='F6 pausar/continuar  •  F7 iniciar  •  F8 parar',
                bg=COLOR_NAV, fg=COLOR_TEXT_DIM, font=('Segoe UI', 7), pady=3,
            ).pack()

            icon_box = tk.Frame(hud, bg=COLOR_SIDEBAR, width=54)
            icon_box.pack(side='left', fill='y', padx=(7, 3), pady=6)
            icon_box.pack_propagate(False)
            try:
                import sys
                try:
                    base_path = sys._MEIPASS
                except Exception:
                    base_path = os.path.abspath('.')
                icon_path = os.path.join(base_path, 'assets', 'icon_minimizado.png')
                if not os.path.exists(icon_path):
                    icon_path = os.path.abspath(os.path.join('assets', 'icon_minimizado.png'))
                if not os.path.exists(icon_path):
                    icon_path = os.path.join(base_path, 'assets', 'icon.png')
                img = Image.open(icon_path).convert('RGBA')
                img.thumbnail((48, 48), Image.Resampling.LANCZOS)
                self._mini_icon_img = ImageTk.PhotoImage(img)
                icon_label = tk.Label(icon_box, image=self._mini_icon_img, bg=COLOR_SIDEBAR, cursor='fleur')
            except Exception as e:
                self.log(f'Erro ao carregar icone: {e}')
                icon_label = tk.Label(
                    icon_box, text='MKT', bg=COLOR_SIDEBAR, fg=COLOR_ACCENT,
                    font=('Segoe UI Semibold', 10), cursor='fleur',
                )
            icon_label.pack(fill='both', expand=True)

            status_box = tk.Frame(hud, bg=COLOR_SIDEBAR, cursor='fleur')
            status_box.pack(side='left', fill='both', expand=True, padx=(2, 5), pady=7)
            self._mini_status_lbl = tk.Label(
                status_box, text='AUTOMAÇÃO PARADA', bg=COLOR_SIDEBAR,
                fg=COLOR_TEXT_DIM, font=('Segoe UI Semibold', 8), anchor='w', cursor='fleur',
            )
            self._mini_status_lbl.pack(fill='x')
            self._mini_elapsed_lbl = tk.Label(
                status_box, text='F8/Insert para parar', bg=COLOR_SIDEBAR,
                fg=COLOR_TEXT_DIM, font=('Segoe UI', 7), anchor='w', cursor='fleur',
            )
            self._mini_elapsed_lbl.pack(fill='x', pady=(3, 0))
            self._mini_totals_lbl = tk.Label(
                status_box, text='Gasto: 0  •  Lucro total: 0', bg=COLOR_SIDEBAR,
                fg=COLOR_TEXT_DIM, font=('Segoe UI', 7), anchor='w', cursor='fleur',
            )
            self._mini_totals_lbl.pack(fill='x', pady=(2, 0))
            self._mini_taxa_lbl = tk.Label(
                status_box, text='Taxa (não retorna): 0', bg=COLOR_SIDEBAR,
                fg=COLOR_TEXT_DIM, font=('Segoe UI', 7), anchor='w', cursor='fleur',
            )
            self._mini_taxa_lbl.pack(fill='x', pady=(2, 0))
            self._mini_pause_btn = tk.Button(
                status_box, text='F9  PAUSA OFF', command=self.alternar_pausa_protegida_via_atalho,
                bg=COLOR_NAV, fg=COLOR_TEXT_DIM, activebackground=COLOR_ACCENT_DIM,
                activeforeground=COLOR_TEXT, relief='flat', bd=0, cursor='hand2',
                font=('Segoe UI Semibold', 7), pady=2,
            )
            self._mini_pause_btn.pack(fill='x', pady=(3, 0))

            actions = tk.Frame(hud, bg=COLOR_SIDEBAR)
            actions.pack(side='right', fill='y', padx=(2, 7), pady=7)
            self._mini_pauseresume_btn = tk.Button(
                actions, text='⏸ PAUSAR', command=self._mini_toggle_pause_resume,
                bg=COLOR_ACCENT_DIM, fg=COLOR_TEXT, activebackground=COLOR_ACCENT,
                activeforeground=COLOR_TEXT, relief='flat', bd=0, cursor='hand2',
                font=('Segoe UI Semibold', 8), width=9, pady=4,
            )
            self._mini_pauseresume_btn.pack(fill='x', pady=(0, 4))
            self._mini_stop_btn = tk.Button(
                actions, text='■ PARAR', command=self.pause_bot,
                bg=COLOR_ERROR, fg='#FFFFFF', activebackground='#A82C38',
                activeforeground='#FFFFFF', relief='flat', bd=0, cursor='hand2',
                font=('Segoe UI Semibold', 8), width=9, pady=4,
            )
            self._mini_stop_btn.pack(fill='x')
            tk.Button(
                actions, text='ABRIR MKT', command=self.toggle_minimize,
                bg=COLOR_CARD, fg=COLOR_TEXT, activebackground=COLOR_ACCENT_DIM,
                activeforeground=COLOR_TEXT, relief='flat', bd=0, cursor='hand2',
                font=('Segoe UI Semibold', 7), width=9, pady=3,
            ).pack(fill='x', pady=(4, 0))

            for draggable in (hud, icon_box, icon_label, status_box,
                              self._mini_status_lbl, self._mini_elapsed_lbl):
                draggable.bind('<Button-1>', self._mini_start_move)
                draggable.bind('<B1-Motion>', self._mini_do_move)
                draggable.bind('<ButtonRelease-1>', self._mini_finish_move)
                draggable.bind('<Double-Button-1>', lambda _event: self.toggle_minimize())
            self._position_mini_hud()
            self._refresh_mini_hud()
        else:
            if self._mini_refresh_job is not None:
                try:
                    self.root.after_cancel(self._mini_refresh_job)
                except Exception:
                    pass
                self._mini_refresh_job = None
            if hasattr(self, '_mini_win') and self._mini_win:
                try:
                    self._mini_win.destroy()
                except Exception:
                    pass
                self._mini_win = None
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.minimized = False

    def _position_mini_hud(self):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        saved_x = self.offsets.get('mini_hud_x')
        saved_y = self.offsets.get('mini_hud_y')
        if isinstance(saved_x, int) and isinstance(saved_y, int):
            x, y = saved_x, saved_y
            self._mini_user_dragged = True
        else:
            win = get_albion_window()
            x = (win.left + 8) if win else 12
            y = (win.top + 34) if win else 42
            self._mini_user_dragged = False
        x = max(0, min(x, screen_w - MINI_HUD_WIDTH))
        y = max(0, min(y, screen_h - MINI_HUD_HEIGHT))
        self._mini_win.geometry(f'{MINI_HUD_WIDTH}x{MINI_HUD_HEIGHT}+{x}+{y}')

    def _mini_start_move(self, event):
        self._mini_drag_x = event.x_root - self._mini_win.winfo_x()
        self._mini_drag_y = event.y_root - self._mini_win.winfo_y()

    def _mini_do_move(self, event):
        self._mini_user_dragged = True
        x = event.x_root - self._mini_drag_x
        y = event.y_root - self._mini_drag_y
        self._mini_win.geometry(f'+{x}+{y}')

    def _mini_finish_move(self, _event=None):
        if not getattr(self, '_mini_user_dragged', False):
            return
        try:
            data = load_settings('offsets.json')
            data['mini_hud_x'] = self._mini_win.winfo_x()
            data['mini_hud_y'] = self._mini_win.winfo_y()
            save_settings('offsets.json', data)
            self.offsets = data
        except Exception as exc:
            self.log(f'[AVISO] Posição do controle compacto não foi salva: {exc}')

    def _mini_toggle_pause_resume(self):
        if getattr(self, 'buy_paused', False):
            self.continuar_bot()
        elif getattr(self, 'running', False):
            self.pausar_bot()
        elif getattr(self, 'shopping_paused', False):
            self.continuar_shopping()
        elif getattr(self, 'shopping_running', False):
            self.pausar_shopping()

    def _refresh_mini_hud(self):
        if not getattr(self, 'minimized', False) or not getattr(self, '_mini_win', None):
            self._mini_refresh_job = None
            return
        state = build_mini_hud_state(
            running=getattr(self, 'running', False),
            sell_running=getattr(self, 'sell_running', False),
            cycle_running=getattr(self, 'cycle_running', False),
            closing_orders=getattr(self, 'fechando_ordens', False),
            protected_pause=getattr(self, 'protected_pause_enabled', False),
            intervention_required=getattr(self, '_mini_intervention_required', False),
            buy_paused=getattr(self, 'buy_paused', False),
            shopping_running=getattr(self, 'shopping_running', False),
            shopping_paused=getattr(self, 'shopping_paused', False),
        )
        now = time.monotonic()
        if state['active'] and not self._mini_was_active:
            self._mini_started_at = now
        elif not state['active']:
            self._mini_started_at = None
        self._mini_was_active = state['active']
        elapsed = format_mini_elapsed(now - self._mini_started_at) if self._mini_started_at else '00:00:00'
        order_count = max(0, int(getattr(self, 'total_orders', 0)))
        order_label = 'ordem' if order_count == 1 else 'ordens'
        self._mini_status_lbl.config(
            text=state['operation'],
            fg=(
                COLOR_ERROR if state['intervention_required']
                else COLOR_SUCCESS if state['active']
                else COLOR_TEXT_DIM
            ),
        )
        self._mini_elapsed_lbl.config(
            text=f'{elapsed}  •  {order_count} {order_label}',
        )
        total_gasto = max(0, int(getattr(self, 'total_gasto', 0)))
        total_profit = int(getattr(self, 'total_profit', 0))
        total_taxa = max(0, int(getattr(self, 'total_taxa', 0)))
        gasto_fmt = f'{total_gasto:,}'.replace(',', '.')
        lucro_total_fmt = f'{total_profit:,}'.replace(',', '.')
        taxa_fmt = f'{total_taxa:,}'.replace(',', '.')
        self._mini_totals_lbl.config(
            text=f'Gasto: {gasto_fmt}  •  Lucro total: {lucro_total_fmt}',
        )
        self._mini_taxa_lbl.config(
            text=f'Taxa (não retorna): {taxa_fmt}',
        )
        self._mini_pause_btn.config(
            text='F9  PAUSA ON' if state['protected_pause'] else 'F9  PAUSA OFF',
            bg=COLOR_ACCENT_DIM if state['protected_pause'] else COLOR_NAV,
            fg=COLOR_TEXT if state['protected_pause'] else COLOR_TEXT_DIM,
        )
        self._mini_stop_btn.config(
            state='normal',
        )
        self._mini_pauseresume_btn.config(
            text='▶ CONTINUAR' if getattr(self, 'buy_paused', False) else '⏸ PAUSAR',
        )
        self._mini_refresh_job = self.root.after(250, self._refresh_mini_hud)
    def _create_cycle_tab(self):
        self.cycle_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.create_page_header(
            self.cycle_tab,
            'Automação completa',
            'Ciclo automático',
            'Compra, coleta e vende continuamente até você interromper.',
        )
        tk.Label(
            self.cycle_tab,
            text='Compra → coleta → vende → volta a comprar',
            bg=COLOR_BG, fg=COLOR_TEXT, font=UI_FONTS['section_title'],
        ).pack(pady=(0, 10))

        flow = tk.Frame(self.cycle_tab, bg=COLOR_BG)
        flow.pack(fill='x', padx=12, pady=(2, 10))
        self.cycle_stage_labels = {}
        for index, (stage_key, label) in enumerate((
            ('buy', 'COMPRANDO'),
            ('collect', 'COLETANDO'),
            ('sell', 'VENDENDO'),
        )):
            stage = tk.Canvas(
                flow, width=96, height=38, bg=COLOR_BG,
                highlightthickness=0, bd=0,
            )
            stage.pack(side='left', fill='x', expand=True)
            stage._mkt_stage_text = label
            stage._mkt_stage_active = False
            stage.bind(
                '<Configure>',
                lambda _event, widget=stage: self._render_cycle_stage(widget),
            )
            self.cycle_stage_labels[stage_key] = stage
            if index < 2:
                tk.Label(flow, text='›', bg=COLOR_BG, fg=COLOR_ACCENT,
                         font=('Segoe UI Semibold', 12), width=2).pack(side='left')

        metrics = tk.Frame(self.cycle_tab, bg=COLOR_BG)
        metrics.pack(fill='x', padx=12, pady=(0, 6))
        for index, (label, attr_name) in enumerate((
            ('ORDENS REALIZADAS', 'cycle_orders_count_lbl'),
            ('ITENS VENDIDOS', 'cycle_sold_count_lbl'),
        )):
            metric = tk.Frame(
                metrics, bg=COLOR_BG, padx=10, pady=8,
            )
            metric.grid(row=0, column=index, sticky='ew', padx=(0, 4) if index == 0 else (4, 0))
            metrics.grid_columnconfigure(index, weight=1)
            self._add_rounded_block_background(metric)
            tk.Label(
                metric, text=label, bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
                font=UI_FONTS['micro'],
            ).pack()
            value_label = tk.Label(
                metric, text='0', bg=COLOR_CARD, fg=COLOR_TEXT,
                font=UI_FONTS['section_title'],
            )
            value_label.pack(pady=(3, 0))
            setattr(self, attr_name, value_label)

        limit_card = tk.Frame(
            self.cycle_tab, bg=COLOR_BG, padx=14, pady=12,
        )
        limit_card.pack(fill='x', padx=12, pady=6)
        self._add_rounded_block_background(limit_card)
        tk.Label(
            limit_card, text='QUANDO INICIAR A COLETA', bg=COLOR_CARD,
            fg=COLOR_TEXT, font=UI_FONTS['body_strong'],
        ).pack(anchor='w')
        tk.Label(
            limit_card, text='Ao atingir esta quantidade de itens prontos:',
            bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=UI_FONTS['body'],
        ).pack(anchor='w', pady=(4, 8))
        entry_row = tk.Frame(limit_card, bg=COLOR_CARD)
        entry_row.pack(fill='x')
        self.cycle_limit_entry = tk.Entry(
            entry_row, bg=UI_COLORS['field'], fg=COLOR_TEXT, insertbackground=COLOR_ACCENT,
            justify='center', relief='flat', font=('Segoe UI Semibold', 10),
            highlightthickness=1, highlightbackground=COLOR_BORDER,
        )
        self.cycle_limit_entry.pack(side='left', fill='x', expand=True, ipady=7)
        self.cycle_limit_entry.insert(0, str(self.offsets.get('cycle_order_limit', 48)))
        tk.Label(entry_row, text='ITENS PRONTOS', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
                 font=('Segoe UI Semibold', 8), padx=10).pack(side='right')

        status_card = tk.Frame(
            self.cycle_tab, bg=COLOR_BG, padx=14, pady=12,
        )
        status_card.pack(fill='x', padx=12, pady=6)
        self._add_rounded_block_background(status_card)
        tk.Label(status_card, text='STATUS DO CICLO', bg=COLOR_CARD,
                 fg=COLOR_TEXT_DIM, font=UI_FONTS['caption_strong']).pack(anchor='w')
        self.cycle_module_status_lbl = tk.Label(
            status_card, text='PRONTO PARA VALIDAR', bg=COLOR_CARD,
            fg=COLOR_ACCENT, font=UI_FONTS['section_title'],
        )
        self.cycle_module_status_lbl.pack(anchor='w', pady=(3, 5))
        tk.Label(
            status_card, text='Exige as calibragens de Compra e Venda.',
            bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=UI_FONTS['body'],
        ).pack(anchor='w')

        self.cycle_start_btn_container = tk.Frame(self.cycle_tab, bg=COLOR_BG)
        self.cycle_start_btn_container.pack(fill='x', padx=12, pady=(10, 5))
        self.atualizar_botao_ciclo()
        self._criar_toggle_media_semanal(self.cycle_tab).pack(
            fill='x', padx=12, pady=(0, 6)
        )
        tk.Label(
            self.cycle_tab, text='F7 inicia • F8 ou Insert interrompe • F9 alterna Pausa protegida.',
            bg=COLOR_BG, fg=COLOR_TEXT_DIM, font=UI_FONTS['caption'], pady=8,
        ).pack()

    def _create_shopping_tab(self):
        self.shopping_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.create_page_header(
            self.shopping_tab,
            'Lista de compras específica',
            'Compra Programada',
            'Procura itens pelo nome, ajusta a quantidade e cria o pedido a 1 '
            'moeda acima do preço atual — sem respeitar banca operacional '
            'nem valor máximo.',
        )

        self.shopping_start_btn_container = tk.Frame(self.shopping_tab, bg=COLOR_BG)
        self.shopping_start_btn_container.pack(fill='x', padx=12, pady=(8, 4))
        self.shopping_running = False
        self.shopping_paused = False
        self._shopping_poll_job = None
        self.atualizar_botao_shopping()
        self._criar_toggle_media_semanal(self.shopping_tab).pack(
            fill='x', padx=12, pady=(0, 6)
        )

        status_card = tk.Frame(
            self.shopping_tab, bg=COLOR_CARD, padx=14, pady=12,
            highlightthickness=1, highlightbackground=COLOR_BORDER,
        )
        status_card.pack(fill='x', padx=12, pady=(8, 6))
        tk.Label(
            status_card, text='STATUS DO MÓDULO', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption_strong'],
        ).pack(anchor='w')
        self.shopping_module_status_lbl = tk.Label(
            status_card, text='VERIFICANDO CALIBRAGEM', bg=COLOR_CARD,
            fg=COLOR_ACCENT, font=UI_FONTS['section_title'],
        )
        self.shopping_module_status_lbl.pack(anchor='w', pady=(3, 0))
        tk.Label(
            status_card,
            text=(
                'Ignora banca operacional e lucro mínimo. O único limite '
                'financeiro é o valor máximo por pedido abaixo (opcional).'
            ),
            bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=UI_FONTS['body'],
            justify='left', wraplength=320,
        ).pack(anchor='w', pady=(4, 8))

        tk.Label(
            status_card, text='Valor máximo por pedido (prata, 0 = sem limite)',
            bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=UI_FONTS['caption_strong'],
        ).pack(anchor='w')
        self.shopping_valor_maximo_entry = tk.Entry(
            status_card, bg=UI_COLORS['field'], fg=COLOR_TEXT, relief='flat',
            insertbackground=COLOR_TEXT,
        )
        self.shopping_valor_maximo_entry.insert(0, '0')
        self.shopping_valor_maximo_entry.pack(fill='x', pady=(2, 0))
        self.carregar_valor_maximo_shopping_ui()

        form_card = tk.Frame(
            self.shopping_tab, bg=COLOR_CARD, padx=14, pady=12,
            highlightthickness=1, highlightbackground=COLOR_BORDER,
        )
        form_card.pack(fill='x', padx=12, pady=(8, 6))
        for coluna in range(4):
            form_card.columnconfigure(coluna, weight=1)

        tk.Label(
            form_card, text='Nome do item', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption_strong'],
        ).grid(row=0, column=0, sticky='w')
        self.shopping_nome_entry = tk.Entry(
            form_card, bg=UI_COLORS['field'], fg=COLOR_TEXT, relief='flat',
            insertbackground=COLOR_TEXT,
        )
        self.shopping_nome_entry.grid(row=1, column=0, sticky='we', padx=(0, 6), pady=(2, 8))

        tk.Label(
            form_card, text='Tier (2-8)', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption_strong'],
        ).grid(row=0, column=1, sticky='w')
        self.shopping_tier_entry = tk.Entry(
            form_card, bg=UI_COLORS['field'], fg=COLOR_TEXT, relief='flat',
            insertbackground=COLOR_TEXT, width=4, justify='center',
        )
        self.shopping_tier_entry.insert(0, '4')
        self.shopping_tier_entry.grid(row=1, column=1, sticky='we', padx=6, pady=(2, 8))

        tk.Label(
            form_card, text='Encant. (.0-.4)', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption_strong'],
        ).grid(row=0, column=2, sticky='w')
        self.shopping_encantamento_entry = tk.Entry(
            form_card, bg=UI_COLORS['field'], fg=COLOR_TEXT, relief='flat',
            insertbackground=COLOR_TEXT, width=4, justify='center',
        )
        self.shopping_encantamento_entry.insert(0, '.0')
        self.shopping_encantamento_entry.grid(row=1, column=2, sticky='we', padx=6, pady=(2, 8))

        tk.Label(
            form_card, text='Quantidade', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption_strong'],
        ).grid(row=0, column=3, sticky='w')
        self.shopping_quantidade_entry = tk.Entry(
            form_card, bg=UI_COLORS['field'], fg=COLOR_TEXT, relief='flat',
            insertbackground=COLOR_TEXT, width=8,
        )
        self.shopping_quantidade_entry.insert(0, '1')
        self.shopping_quantidade_entry.grid(row=1, column=3, sticky='we', padx=(6, 0), pady=(2, 8))

        tk.Label(
            form_card,
            text=(
                'Categoria (opcional, ajuda a evitar item errado -- pode ser '
                'resumido "Arma"/"Peitoral"/"Capacete"/"Calçado"/"Mão Secundária"'
                '/"Capa"/"Bolsa"/"Equip Coleta" ou como aparece no jogo)'
            ),
            bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=UI_FONTS['caption_strong'],
            justify='left', wraplength=360,
        ).grid(row=2, column=0, columnspan=4, sticky='w')
        self.shopping_categoria_entry = tk.Entry(
            form_card, bg=UI_COLORS['field'], fg=COLOR_TEXT, relief='flat',
            insertbackground=COLOR_TEXT,
        )
        self.shopping_categoria_entry.grid(row=3, column=0, columnspan=4, sticky='we', pady=(2, 8))

        add_btn = self.create_3d_button(
            form_card, 'ADICIONAR À LISTA', type_color='gold',
            command=self.adicionar_item_lista_compras,
        )
        add_btn.grid(row=4, column=0, columnspan=4, sticky='we', pady=(4, 0))

        tree_border = tk.Frame(self.shopping_tab, bg=COLOR_NAV)
        tree_border.pack(fill='x', padx=12, pady=6)
        style = ttk.Style(self.root)
        style.configure(
            'MKT.Treeview', background=COLOR_CARD, fieldbackground=COLOR_CARD,
            foreground=COLOR_TEXT, rowheight=25, borderwidth=0, font=('Segoe UI', 8),
        )
        style.configure(
            'MKT.Treeview.Heading', background=COLOR_NAV, foreground=COLOR_ACCENT,
            relief='flat', font=('Segoe UI Semibold', 7),
        )
        self.shopping_tree = ttk.Treeview(
            tree_border,
            columns=('nome', 'tier', 'encantamento', 'quantidade', 'categoria', 'status'),
            show='headings', style='MKT.Treeview', selectmode='browse', height=8,
        )
        headings = (
            ('nome', 'ITEM', 150),
            ('tier', 'TIER', 45),
            ('encantamento', 'ENCANT.', 60),
            ('quantidade', 'QTD', 50),
            ('categoria', 'CATEGORIA', 100),
            ('status', 'STATUS', 110),
        )
        for key, label, width in headings:
            self.shopping_tree.heading(key, text=label)
            self.shopping_tree.column(key, width=width, anchor='w', stretch=key == 'nome')
        self.shopping_tree.pack(fill='both', expand=True)

        remove_row = tk.Frame(self.shopping_tab, bg=COLOR_BG)
        remove_row.pack(fill='x', padx=12, pady=(0, 6))
        remove_btn = self.create_3d_button(
            remove_row, 'REMOVER ITEM SELECIONADO', type_color='red',
            command=self.remover_item_lista_compras,
        )
        remove_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
        remove_all_btn = self.create_3d_button(
            remove_row, 'REMOVER TUDO', type_color='red',
            command=self.remover_todos_itens_lista_compras,
        )
        remove_all_btn.pack(side='left', fill='x', expand=True)

        csv_row = tk.Frame(self.shopping_tab, bg=COLOR_BG)
        csv_row.pack(fill='x', padx=12, pady=(0, 6))
        exportar_csv_btn = self.create_3d_button(
            csv_row, 'GERAR CSV (EXCEL)', type_color='gold',
            command=self.exportar_lista_compras_csv,
        )
        exportar_csv_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
        importar_csv_btn = self.create_3d_button(
            csv_row, 'IMPORTAR CSV', type_color='gold',
            command=self.importar_lista_compras_csv,
        )
        importar_csv_btn.pack(side='left', fill='x', expand=True)

        tk.Label(
            self.shopping_tab,
            text='F6 pausa/continua • F8 ou Insert interrompe.',
            bg=COLOR_BG, fg=COLOR_TEXT_DIM, font=UI_FONTS['caption'], pady=8,
        ).pack()

        shopping_config_btn = self.create_3d_button(
            self.shopping_tab, 'CONFIGURAR COMPRA PROGRAMADA', type_color='gold',
            command=self.show_calib_tab,
        )
        shopping_config_btn.pack(fill='x', padx=12, pady=(4, 8))

        self.shopping_items: list[dict] = []
        self.carregar_lista_compras_ui()

    def show_shopping_tab(self):
        self.atualizar_status_calibragem()
        self.carregar_lista_compras_ui()
        self.carregar_valor_maximo_shopping_ui()
        self.switch_tab('SHOPPING', self.shopping_tab)

    def _create_remover_pedidos_tab(self):
        self.remover_pedidos_tab = tk.Frame(self.content_area, bg=COLOR_BG)
        self.create_page_header(
            self.remover_pedidos_tab,
            'Cancelar pedidos que perderam a posição',
            'Remover Pedidos',
            'Percorre a tela "Pedidos de Compra" já aberta, verifica cada pedido '
            'em "Editar pedido de compra" e cancela (X da lista) somente os que '
            'não são mais o topo do livro. Deixe a tela aberta antes de iniciar.',
        )

        self.remover_pedidos_start_btn_container = tk.Frame(self.remover_pedidos_tab, bg=COLOR_BG)
        self.remover_pedidos_start_btn_container.pack(fill='x', padx=12, pady=(8, 4))
        self.remover_pedidos_running = False
        self.remover_pedidos_paused = False
        self._remover_pedidos_poll_job = None
        self.atualizar_botao_remover_pedidos()

        status_card = tk.Frame(
            self.remover_pedidos_tab, bg=COLOR_CARD, padx=14, pady=12,
            highlightthickness=1, highlightbackground=COLOR_BORDER,
        )
        status_card.pack(fill='x', padx=12, pady=(8, 6))
        tk.Label(
            status_card, text='STATUS DO MÓDULO', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
            font=UI_FONTS['caption_strong'],
        ).pack(anchor='w')
        self.remover_pedidos_module_status_lbl = tk.Label(
            status_card, text='VERIFICANDO CALIBRAGEM', bg=COLOR_CARD,
            fg=COLOR_ACCENT, font=UI_FONTS['section_title'],
        )
        self.remover_pedidos_module_status_lbl.pack(anchor='w', pady=(3, 0))
        tk.Label(
            status_card,
            text=(
                'Cancelar devolve a prata reservada do pedido (a taxa de 2,5% '
                'já paga na criação não volta). Em caso de leitura ambígua, o '
                'bot NÃO cancela e segue para o próximo item, por segurança.'
            ),
            bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=UI_FONTS['body'],
            justify='left', wraplength=320,
        ).pack(anchor='w', pady=(4, 0))

        calib_btn = self.create_3d_button(
            self.remover_pedidos_tab, 'CONFIGURAR REMOVER PEDIDOS', type_color='gold',
            command=self.show_calib_tab,
        )
        calib_btn.pack(fill='x', padx=12, pady=(8, 12))

    def show_remover_pedidos_tab(self):
        self.atualizar_status_calibragem()
        self.switch_tab('REMOVER', self.remover_pedidos_tab)

    def atualizar_botao_remover_pedidos(self):
        for child in self.remover_pedidos_start_btn_container.winfo_children():
            child.destroy()
        if self.remover_pedidos_running:
            row = tk.Frame(self.remover_pedidos_start_btn_container, bg=COLOR_BG)
            row.pack(fill='x')
            pausar_btn = self.create_3d_button(
                row, '⏸ PAUSAR', type_color='gold', command=self.pausar_remover_pedidos,
            )
            pausar_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
            parar_btn = self.create_3d_button(
                row, '■ PARAR', type_color='red', command=self.parar_remover_pedidos,
            )
            parar_btn.pack(side='left', fill='x', expand=True)
        elif getattr(self, 'remover_pedidos_paused', False):
            row = tk.Frame(self.remover_pedidos_start_btn_container, bg=COLOR_BG)
            row.pack(fill='x')
            continuar_btn = self.create_3d_button(
                row, '▶ CONTINUAR', type_color='green', command=self.continuar_remover_pedidos,
            )
            continuar_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
            parar_btn = self.create_3d_button(
                row, '■ PARAR', type_color='red', command=self.parar_remover_pedidos,
            )
            parar_btn.pack(side='left', fill='x', expand=True)
        else:
            btn = self.create_3d_button(
                self.remover_pedidos_start_btn_container, '▶ INICIAR REMOÇÃO DE PEDIDOS',
                type_color='green', command=self.iniciar_remover_pedidos,
            )
            btn.pack(fill='x')

    def iniciar_remover_pedidos(self):
        if self.running or self.sell_running or self.cycle_running or getattr(self, 'fechando_ordens', False) or getattr(self, 'shopping_running', False):
            messagebox.showwarning(
                'Remover Pedidos',
                'Pare a outra automação antes de iniciar a remoção de pedidos.',
            )
            return
        if not self.validar_calibragem_para_modo('remover_pedidos'):
            return
        self.minimizar_para_execucao()
        self.remover_pedidos_running = True
        self.remover_pedidos_paused = False
        self.remover_pedidos_module_status_lbl.config(text='VERIFICANDO PEDIDOS', fg=COLOR_SUCCESS)
        with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
            json.dump(build_control_state(True, 'remover_pedidos', False), handle)
        self.log('>>> Remover Pedidos iniciado.')
        self.atualizar_botao_remover_pedidos()
        self.root.after(2000, self._poll_remover_pedidos_status)

    def pausar_remover_pedidos(self):
        if not self.remover_pedidos_running:
            return
        self.remover_pedidos_running = False
        self.remover_pedidos_paused = True
        self.remover_pedidos_module_status_lbl.config(text='PAUSADO', fg=COLOR_ACCENT)
        with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
            json.dump(
                build_control_state(False, 'remover_pedidos', False, preserve_position=True),
                handle,
            )
        self.log('>>> Remover Pedidos pausado.')
        self.atualizar_botao_remover_pedidos()

    def continuar_remover_pedidos(self):
        if not self.remover_pedidos_paused:
            return
        self.remover_pedidos_running = True
        self.remover_pedidos_paused = False
        self.remover_pedidos_module_status_lbl.config(text='VERIFICANDO PEDIDOS', fg=COLOR_SUCCESS)
        with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
            json.dump(
                build_control_state(True, 'remover_pedidos', False, preserve_position=True),
                handle,
            )
        self.log('>>> Remover Pedidos retomado.')
        self.atualizar_botao_remover_pedidos()
        self.root.after(2000, self._poll_remover_pedidos_status)

    def parar_remover_pedidos(self):
        self.remover_pedidos_running = False
        self.remover_pedidos_paused = False
        try:
            self.remover_pedidos_module_status_lbl.config(text='PARADO', fg=COLOR_TEXT_DIM)
        except Exception:
            pass
        with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
            json.dump(build_control_state(False, 'buy', False), handle)
        self.log('>>> Remover Pedidos parado.')
        self.atualizar_botao_remover_pedidos()

    def _poll_remover_pedidos_status(self):
        if not self.remover_pedidos_running:
            self._remover_pedidos_poll_job = None
            return
        try:
            with open(CONTROL_FILE, 'r', encoding='utf-8') as handle:
                estado = json.load(handle)
        except Exception:
            estado = {}
        if not estado.get('run', True) or estado.get('mode') != 'remover_pedidos':
            self.remover_pedidos_running = False
            try:
                self.remover_pedidos_module_status_lbl.config(text='PARADO PELO BOT', fg=COLOR_TEXT_DIM)
            except Exception:
                pass
            self.atualizar_botao_remover_pedidos()
            self._remover_pedidos_poll_job = None
            return
        self._remover_pedidos_poll_job = self.root.after(2000, self._poll_remover_pedidos_status)

    def carregar_lista_compras_ui(self):
        dados = load_settings(LISTA_COMPRAS_FILE)
        itens = dados.get('itens') if isinstance(dados, dict) else None
        self.shopping_items = itens if isinstance(itens, list) else []
        self._render_shopping_tree()

    def salvar_lista_compras_ui(self):
        save_settings(LISTA_COMPRAS_FILE, {'itens': self.shopping_items})

    def carregar_valor_maximo_shopping_ui(self):
        entry = getattr(self, 'shopping_valor_maximo_entry', None)
        if entry is None:
            return
        data = load_settings('offsets.json')
        valor = data.get('compra_programada_valor_maximo', 0) if isinstance(data, dict) else 0
        entry.delete(0, 'end')
        entry.insert(0, str(int(valor) if isinstance(valor, (int, float)) else 0))

    def salvar_valor_maximo_shopping_ui(self):
        """Lê, valida e persiste o limite; devolve o valor válido ou None se inválido."""
        entry = getattr(self, 'shopping_valor_maximo_entry', None)
        if entry is None:
            return 0
        texto = entry.get()
        try:
            valor = parse_silver(texto) if str(texto).strip() else 0
            if valor < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                'Compra Programada',
                'Valor máximo por pedido inválido. Use um número inteiro (ex.: 2.000.000) ou 0 para sem limite.',
            )
            return None
        data = load_settings('offsets.json')
        if not isinstance(data, dict):
            data = {}
        data['compra_programada_valor_maximo'] = valor
        save_settings('offsets.json', data)
        self.offsets = data
        return valor

    def _render_shopping_tree(self):
        if not hasattr(self, 'shopping_tree'):
            return
        self.shopping_tree.delete(*self.shopping_tree.get_children())
        status_labels = {
            'pendente': 'PENDENTE',
            'pedido_criado': 'PEDIDO CRIADO',
            'nao_encontrado': 'NÃO ENCONTRADO',
            'limite_excedido': 'LIMITE EXCEDIDO',
            'sem_media': 'SEM MÉDIA',
        }
        for item in self.shopping_items:
            tier = item.get('tier')
            self.shopping_tree.insert('', 'end', values=(
                item.get('nome', ''),
                f"T{tier}" if tier else '-',
                item.get('encantamento') or '.0',
                item.get('quantidade', 1),
                item.get('categoria') or '-',
                status_labels.get(item.get('status'), 'PENDENTE'),
            ))

    @staticmethod
    def _montar_item_lista_compras(nome_raw, tier_raw, encantamento_raw, quantidade_raw, categoria_raw=''):
        """Valida e monta um item da lista; devolve (item, None) ou (None, motivo).

        Reaproveitado tanto pelo formulário (adicionar 1 item) quanto pela
        importação de CSV, pra manter as mesmas regras nos dois caminhos.
        """
        nome = str(nome_raw or '').strip()
        if not nome:
            return None, 'Digite o nome do item.'
        try:
            tier = int(str(tier_raw).strip())
            if not 2 <= tier <= 8:
                raise ValueError
        except (TypeError, ValueError):
            return None, 'Tier precisa ser um número de 2 a 8.'
        encantamento = str(encantamento_raw or '').strip()
        if encantamento and not encantamento.startswith('.'):
            encantamento = f'.{encantamento}'
        if encantamento not in ENCANTAMENTO_OPCOES:
            return None, 'Encantamento precisa ser .0, .1, .2, .3 ou .4.'
        try:
            quantidade = int(str(quantidade_raw).strip())
            if quantidade < 1:
                raise ValueError
        except (TypeError, ValueError):
            return None, 'Quantidade precisa ser um número inteiro maior que zero.'
        categoria_normalizada = _normalizar_categoria_texto(categoria_raw)
        if categoria_normalizada:
            categoria = CATEGORIA_ALIASES.get(categoria_normalizada)
            if categoria is None:
                return None, (
                    'Categoria não reconhecida (ou deixe em branco pra não filtrar). '
                    f"Use uma dessas: {', '.join(CATEGORIA_OPCOES)}."
                )
        else:
            categoria = ''
        return {
            'nome': nome,
            'tier': tier,
            'encantamento': encantamento,
            'quantidade': quantidade,
            'categoria': categoria,
            'status': 'pendente',
        }, None

    def adicionar_item_lista_compras(self):
        nome_raw = self.shopping_nome_entry.get()
        if not str(nome_raw or '').strip():
            messagebox.showwarning('Compra Programada', 'Digite o nome do item.')
            return
        item, erro = self._montar_item_lista_compras(
            nome_raw,
            self.shopping_tier_entry.get(),
            self.shopping_encantamento_entry.get(),
            self.shopping_quantidade_entry.get(),
            self.shopping_categoria_entry.get(),
        )
        if item is None:
            messagebox.showwarning('Compra Programada', erro)
            return

        self.shopping_items.append(item)
        self.salvar_lista_compras_ui()
        self._render_shopping_tree()
        self.shopping_nome_entry.delete(0, 'end')
        self.shopping_quantidade_entry.delete(0, 'end')
        self.shopping_quantidade_entry.insert(0, '1')
        self.log(
            f">>> Item adicionado à Compra Programada: {item['nome']} T{item['tier']}"
            f"{item['encantamento']} x{item['quantidade']}."
        )

    def remover_item_lista_compras(self):
        selecionado = self.shopping_tree.selection()
        if not selecionado:
            return
        indice = self.shopping_tree.index(selecionado[0])
        if 0 <= indice < len(self.shopping_items):
            removido = self.shopping_items.pop(indice)
            self.salvar_lista_compras_ui()
            self._render_shopping_tree()
            self.log(
                f">>> Item removido da Compra Programada: {removido.get('nome', '')}."
            )

    def remover_todos_itens_lista_compras(self):
        if not self.shopping_items:
            return
        if not messagebox.askyesno(
            'Compra Programada',
            f'Remover todos os {len(self.shopping_items)} item(ns) da lista?',
        ):
            return
        self.shopping_items = []
        self.salvar_lista_compras_ui()
        self._render_shopping_tree()
        self.log('>>> Todos os itens da Compra Programada foram removidos.')

    def exportar_lista_compras_csv(self):
        destino = filedialog.asksaveasfilename(
            title='Gerar CSV da Compra Programada',
            defaultextension='.csv',
            filetypes=[('CSV', '*.csv')],
            initialfile='compra_programada.csv',
        )
        if not destino:
            return
        try:
            with open(destino, 'w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.writer(handle, delimiter=';')
                writer.writerow(['Nome', 'Tier', 'Encantamento', 'Quantidade', 'Categoria'])
                for item in self.shopping_items:
                    writer.writerow([
                        item.get('nome', ''),
                        item.get('tier', ''),
                        item.get('encantamento', ''),
                        item.get('quantidade', ''),
                        item.get('categoria', ''),
                    ])
        except OSError as exc:
            messagebox.showerror('Compra Programada', f'Não foi possível gerar o CSV:\n{exc}')
            return
        self.log(f'>>> CSV da Compra Programada gerado: {destino}')
        messagebox.showinfo(
            'Compra Programada',
            f'CSV gerado com {len(self.shopping_items)} item(ns).\n\n'
            'Abra no Excel, preencha/edite as colunas Nome, Tier, Encantamento, '
            'Quantidade e Categoria (opcional; ajuda a busca do jogo a evitar '
            'itens de nome parecido), salve e use "IMPORTAR CSV" pra trazer de volta.',
        )

    def importar_lista_compras_csv(self):
        origem = filedialog.askopenfilename(
            title='Importar CSV da Compra Programada',
            filetypes=[('CSV', '*.csv'), ('Todos os arquivos', '*.*')],
        )
        if not origem:
            return
        try:
            with open(origem, 'r', newline='', encoding='utf-8-sig') as handle:
                amostra = handle.read(2048)
                handle.seek(0)
                try:
                    dialeto = csv.Sniffer().sniff(amostra, delimiters=';,')
                except csv.Error:
                    dialeto = csv.excel
                    dialeto.delimiter = ';'
                linhas = list(csv.reader(handle, dialeto))
        except OSError as exc:
            messagebox.showerror('Compra Programada', f'Não foi possível abrir o CSV:\n{exc}')
            return

        if not linhas:
            messagebox.showwarning('Compra Programada', 'O arquivo CSV está vazio.')
            return

        primeira_linha = [celula.strip().lower() for celula in linhas[0]]
        inicio = 1 if primeira_linha[:1] == ['nome'] else 0

        importados = 0
        ignorados = 0
        for linha in linhas[inicio:]:
            if not linha or not any(celula.strip() for celula in linha):
                continue
            # Preenche até 5 campos (Categoria é opcional e aditiva: CSVs
            # antigos, sem essa coluna, continuam importando normalmente).
            campos = (list(linha) + ['', '', '', '', ''])[:5]
            item, _erro = self._montar_item_lista_compras(*campos)
            if item is None:
                ignorados += 1
                continue
            self.shopping_items.append(item)
            importados += 1

        if importados:
            self.salvar_lista_compras_ui()
            self._render_shopping_tree()
        self.log(
            f'>>> CSV importado para a Compra Programada: {importados} item(ns) '
            f'adicionados, {ignorados} linha(s) ignorada(s).'
        )
        aviso_ignorados = f' {ignorados} linha(s) ignorada(s) por erro.' if ignorados else ''
        messagebox.showinfo(
            'Compra Programada',
            f'{importados} item(ns) importado(s).{aviso_ignorados}',
        )

    def atualizar_botao_shopping(self):
        for child in self.shopping_start_btn_container.winfo_children():
            child.destroy()
        if self.shopping_running:
            row = tk.Frame(self.shopping_start_btn_container, bg=COLOR_BG)
            row.pack(fill='x')
            pausar_btn = self.create_3d_button(
                row, '⏸ PAUSAR', type_color='gold', command=self.pausar_shopping,
            )
            pausar_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
            parar_btn = self.create_3d_button(
                row, '■ PARAR', type_color='red', command=self.parar_shopping,
            )
            parar_btn.pack(side='left', fill='x', expand=True)
        elif getattr(self, 'shopping_paused', False):
            row = tk.Frame(self.shopping_start_btn_container, bg=COLOR_BG)
            row.pack(fill='x')
            continuar_btn = self.create_3d_button(
                row, '▶ CONTINUAR', type_color='green', command=self.continuar_shopping,
            )
            continuar_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
            parar_btn = self.create_3d_button(
                row, '■ PARAR', type_color='red', command=self.parar_shopping,
            )
            parar_btn.pack(side='left', fill='x', expand=True)
        else:
            btn = self.create_3d_button(
                self.shopping_start_btn_container, '▶ INICIAR COMPRA PROGRAMADA',
                type_color='green', command=self.iniciar_shopping,
            )
            btn.pack(fill='x')

    def iniciar_shopping(self):
        if not self.modulo_liberado(MODULE_PURCHASE, 'a Compra Programada'):
            return
        if self.running or self.sell_running or self.cycle_running or getattr(self, 'fechando_ordens', False) or getattr(self, 'remover_pedidos_running', False):
            messagebox.showwarning(
                'Compra Programada',
                'Pare a outra automação antes de iniciar a compra programada.',
            )
            return
        if not self.shopping_items:
            messagebox.showwarning(
                'Compra Programada', 'Adicione pelo menos um item à lista antes de iniciar.',
            )
            return
        if not any(item.get('status') == 'pendente' for item in self.shopping_items):
            messagebox.showwarning(
                'Compra Programada',
                'Todos os itens já foram processados. Adicione itens novos.',
            )
            return
        if not self.validar_calibragem_para_modo('shopping'):
            return
        if self.salvar_valor_maximo_shopping_ui() is None:
            return
        self.minimizar_para_execucao()
        self.shopping_running = True
        self.shopping_paused = False
        self.shopping_module_status_lbl.config(text='PROCURANDO ITENS', fg=COLOR_SUCCESS)
        with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
            json.dump(build_control_state(True, 'shopping', False), handle)
        self.log('>>> Compra Programada iniciada.')
        self.atualizar_botao_shopping()
        self.root.after(2000, self._poll_shopping_status)

    def pausar_shopping(self):
        if not self.shopping_running:
            return
        self.shopping_running = False
        self.shopping_paused = True
        self.shopping_module_status_lbl.config(text='PAUSADA', fg=COLOR_ACCENT)
        with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
            json.dump(
                build_control_state(False, 'shopping', False, preserve_position=True),
                handle,
            )
        self.log('>>> Compra Programada pausada.')
        self.atualizar_botao_shopping()

    def continuar_shopping(self):
        if not self.shopping_paused:
            return
        if self.salvar_valor_maximo_shopping_ui() is None:
            return
        self.shopping_running = True
        self.shopping_paused = False
        self.shopping_module_status_lbl.config(text='PROCURANDO ITENS', fg=COLOR_SUCCESS)
        with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
            json.dump(
                build_control_state(True, 'shopping', False, preserve_position=True),
                handle,
            )
        self.log('>>> Compra Programada retomada.')
        self.atualizar_botao_shopping()
        self.root.after(2000, self._poll_shopping_status)

    def parar_shopping(self):
        self.shopping_running = False
        self.shopping_paused = False
        try:
            self.shopping_module_status_lbl.config(text='PARADA', fg=COLOR_TEXT_DIM)
        except Exception:
            pass
        with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
            json.dump(build_control_state(False, 'buy', False), handle)
        self.log('>>> Compra Programada parada.')
        self.atualizar_botao_shopping()

    def _poll_shopping_status(self):
        if not self.shopping_running:
            self._shopping_poll_job = None
            return
        self.carregar_lista_compras_ui()
        if not any(item.get('status') == 'pendente' for item in self.shopping_items):
            self.shopping_running = False
            try:
                self.shopping_module_status_lbl.config(text='LISTA CONCLUÍDA', fg=COLOR_SUCCESS)
            except Exception:
                pass
            self.atualizar_botao_shopping()
            self._shopping_poll_job = None
            return
        self._shopping_poll_job = self.root.after(2000, self._poll_shopping_status)

    def _add_rounded_block_background(self, container, radius=8):
        """Adiciona borda arredondada atrás do conteúdo sem alterar o layout."""
        background = tk.Canvas(
            container, bg=COLOR_BG, highlightthickness=0, bd=0,
        )
        background.place(x=0, y=0, relwidth=1, relheight=1)

        def redraw(event):
            background.delete('rounded_block')
            width = max(2, event.width)
            height = max(2, event.height)
            draw_canvas_rounded_rectangle(
                background, 1, 1, width - 1, height - 1, radius,
                fill=COLOR_CARD, outline=COLOR_BORDER, width=1,
                tags='rounded_block',
            )

        background.bind('<Configure>', redraw)
        container._mkt_rounded_background = background
        return background

    def _render_cycle_stage(self, widget):
        """Redesenha uma etapa do ciclo com cantos arredondados discretos."""
        width = max(2, widget.winfo_width())
        height = max(2, widget.winfo_height())
        active = bool(getattr(widget, '_mkt_stage_active', False))
        widget.delete('stage')
        draw_canvas_rounded_rectangle(
            widget, 1, 1, width - 1, height - 1, 8,
            fill=UI_COLORS['success_surface'] if active else COLOR_CARD,
            outline=COLOR_SUCCESS if active else COLOR_BORDER,
            width=1, tags='stage',
        )
        widget.create_text(
            width / 2, height / 2,
            text=getattr(widget, '_mkt_stage_text', ''),
            fill=UI_COLORS['success_text'] if active else COLOR_TEXT_DIM,
            font=UI_FONTS['caption_strong'], tags='stage',
        )

    def _set_cycle_stage(self, stage):
        """Atualiza somente o feedback visual do estágio atual do ciclo."""
        valid_stage = stage if stage in {'buy', 'collect', 'sell'} else None
        self.cycle_stage = valid_stage
        for stage_key, label in getattr(self, 'cycle_stage_labels', {}).items():
            active = stage_key == valid_stage
            try:
                label._mkt_stage_active = active
                self._render_cycle_stage(label)
            except Exception:
                pass

        if valid_stage and hasattr(self, 'cycle_module_status_lbl'):
            status_text = {
                'buy': 'COMPRANDO • MONITORANDO ITENS PRONTOS',
                'collect': 'COLETANDO ITENS',
                'sell': 'VENDENDO ITENS',
            }[valid_stage]
            try:
                self.cycle_module_status_lbl.config(text=status_text, fg=COLOR_SUCCESS)
            except Exception:
                pass

    def _update_cycle_counters(self):
        """Reflete contadores já confirmados, sem consultar o jogo novamente."""
        try:
            self.cycle_orders_count_lbl.config(text=str(self.cycle_orders_completed))
        except Exception:
            pass
        try:
            self.cycle_sold_count_lbl.config(text=str(self.cycle_items_sold))
        except Exception:
            pass

    def atualizar_botao_ciclo(self):
        for child in self.cycle_start_btn_container.winfo_children():
            child.destroy()
        if self.cycle_running:
            text, color = '■ PARAR CICLO AUTOMÁTICO', 'red'
        else:
            text, color = '▶ INICIAR CICLO AUTOMÁTICO', 'green'
        button = self.create_3d_button(
            self.cycle_start_btn_container, text, type_color=color,
            command=self.toggle_cycle_bot,
        )
        button.pack(fill='x')

    def _salvar_limite_ciclo(self):
        try:
            value = int(self.cycle_limit_entry.get().strip())
        except (TypeError, ValueError):
            messagebox.showerror('Ciclo automático', 'Informe uma quantidade inteira de itens.')
            return None
        if not 1 <= value <= 48:
            messagebox.showerror('Ciclo automático', 'Use uma quantidade entre 1 e 48 itens.')
            return None
        data = load_settings('offsets.json')
        data['cycle_order_limit'] = value
        save_settings('offsets.json', data)
        self.offsets = data
        return value

    def toggle_cycle_bot(self):
        for module, title in (
            (MODULE_PURCHASE, 'o Bot de Compra'),
            (MODULE_SELL, 'o Bot de Venda'),
            (MODULE_CYCLE, 'o Ciclo Automático'),
        ):
            if not self.modulo_liberado(module, title):
                return
        if not self.cycle_running:
            if (
                self.running or self.sell_running
                or getattr(self, 'fechando_ordens', False)
                or getattr(self, 'shopping_running', False)
                or getattr(self, 'remover_pedidos_running', False)
            ):
                messagebox.showwarning('Ciclo automático', 'Pare a outra automação antes de iniciar o ciclo.')
                return
            if not self.salvar_ajustes_financeiros(notificar=False):
                messagebox.showerror('Ajustes financeiros', 'Corrija os limites financeiros antes de iniciar.')
                return
            limit = self._salvar_limite_ciclo()
            if limit is None:
                return
            if not self.validar_calibragem_para_modo('cycle'):
                self.log('[BLOQUEADO] Complete as calibragens de Compra, Venda e Ciclo.')
                return
            self.minimizar_para_execucao()
            self.cycle_running = True
            self._set_cycle_stage('buy')
            with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
                json.dump(build_control_state(True, 'buy', True), handle)
            self.log(f'>>> CICLO AUTOMÁTICO iniciado; limite: {limit} compras.')
        else:
            self.cycle_running = False
            self.cycle_module_status_lbl.config(text='PAUSADO', fg=COLOR_TEXT_DIM)
            self._set_cycle_stage(None)
            with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
                json.dump(
                    build_control_state(False, 'buy', True, preserve_position=True),
                    handle,
                )
            self.log('>>> CICLO AUTOMÁTICO pausado.')
        self.atualizar_botao_ciclo()

    def show_bot_tab(self):
        self.switch_tab('BOT', self.bot_tab)
    def show_sell_tab(self):
        self.atualizar_status_calibragem()
        self.switch_tab('SELL', self.sell_tab)
    def show_cycle_tab(self):
        self.atualizar_status_calibragem()
        self.switch_tab('CYCLE', self.cycle_tab)

    def atualizar_botao_venda(self):
        for child in self.sell_start_btn_container.winfo_children():
            child.destroy()
        if self.sell_running:
            button = self.create_3d_button(
                self.sell_start_btn_container, '■ PARAR BOT DE VENDA',
                type_color='red', command=self.iniciar_bot_venda,
            )
        else:
            button = self.create_3d_button(
                self.sell_start_btn_container, '▶ INICIAR BOT DE VENDA',
                type_color='green', command=self.iniciar_bot_venda,
            )
        button.pack(fill='x')

    def iniciar_bot_venda(self):
        if not self.modulo_liberado(MODULE_SELL, 'o Bot de Venda'):
            return
        if not self.sell_running:
            if (
                self.running or self.cycle_running
                or getattr(self, 'fechando_ordens', False)
                or getattr(self, 'shopping_running', False)
                or getattr(self, 'remover_pedidos_running', False)
            ):
                messagebox.showwarning('Bot de venda', 'Pare a outra automação antes de iniciar a venda.')
                return
            if not self.validar_calibragem_para_modo('sell'):
                return
            self.minimizar_para_execucao()
            self.sell_running = True
            self.sell_module_status_lbl.config(text='VENDENDO ITENS', fg=COLOR_SUCCESS)
            with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
                json.dump(build_control_state(True, 'sell', False), handle)
            self.log('>>> Bot de VENDA iniciado.')
        else:
            self.sell_running = False
            self.sell_module_status_lbl.config(text='PAUSADO', fg=COLOR_TEXT_DIM)
            with open(CONTROL_FILE, 'w', encoding='utf-8') as handle:
                json.dump(build_control_state(False, 'sell', False), handle)
            self.log('>>> Bot de VENDA pausado.')
        self.atualizar_botao_venda()

    def show_calib_tab(self):
        self.atualizar_status_calibragem()
        self.switch_tab('CALIB', self.calib_tab)
    def show_seq_tab(self):
        self.switch_tab('SEQ', self.seq_tab)
    def show_cliq_tab(self):
        self.render_cliq_tab()
        self.switch_tab('CLIQ', self.cliq_tab)
    def show_config_tab(self):
        self.carregar_ajustes_financeiros()
        self.switch_tab('CFG', self.config_tab)
    def show_edit_tab(self):
        self.switch_tab('EDIT', self.edit_tab)
    def show_sys_tab(self):
        self.switch_tab('SYS', self.sys_tab)
    def update_scroll_region(self):
        self.root.update_idletasks()
        if hasattr(self, 'canvas_main') and self.canvas_main:
            self.canvas_main.configure(scrollregion=self.canvas_main.bbox('all'))

    def switch_tab(self, name, frame):
        self.current_tab = name
        for btn_name, btn_widget in self.tab_btns.items():
            self.update_tab_visual(btn_widget, btn_name == name)

        all_tabs = [
            getattr(self, 'bot_tab', None),
            getattr(self, 'sell_tab', None),
            getattr(self, 'cycle_tab', None),
            getattr(self, 'shopping_tab', None),
            getattr(self, 'remover_pedidos_tab', None),
            getattr(self, 'calib_tab', None),
            getattr(self, 'seq_tab', None),
            getattr(self, 'cliq_tab', None),
            getattr(self, 'config_tab', None),
            getattr(self, 'edit_tab', None),
            getattr(self, 'sys_tab', None)
        ]
        for f in all_tabs:
            if f and f.winfo_exists():
                f.pack_forget()

        if frame:
            frame.pack(fill='both', expand=True)

        self.width = PANEL_SAFE_WIDTH
        self.canvas_main.itemconfig(self.canvas_window_id, width=self.width - 12)

        if not getattr(self, 'user_dragged', False):
            win = get_albion_window()
            if win and not win.isMinimized:
                self.root.geometry(f'{self.width}x{self.height}+{win.left}+{win.top}')
            else:
                self.root.geometry(f'{self.width}x{self.height}')
        else:
            self.root.geometry(f'{self.width}x{self.height}')

        self.update_scroll_region()
        self.canvas_main.yview_moveto(0)
    def carregar_sequencia_categorias(self):
        data = load_settings('offsets.json')
        seq = data.get('cat_sequence')
        enabled = data.get('cat_enabled', {})
        if seq and isinstance(seq, list) and isinstance(enabled, dict):
            self.category_list = []
            for name in seq:
                key = next((c['key'] for c in DEFAULT_CATEGORIES if c['name'] == name), None)
                if key:
                    is_en = bool(enabled.get(name, True))
                    self.category_list.append({'name': name, 'key': key, 'enabled': is_en})
            for item in DEFAULT_CATEGORIES:
                if not any((c['name'] == item['name'] for c in self.category_list)):
                    self.category_list.append(item.copy())
            return
        import copy
        self.category_list = copy.deepcopy(DEFAULT_CATEGORIES)

    def salvar_sequencia_categorias(self):
        try:
            data = load_settings('offsets.json')
            data['cat_sequence'] = [c['name'] for c in self.category_list]
            data['cat_enabled'] = {c['name']: c['enabled'] for c in self.category_list}
            save_settings('offsets.json', data)
        except Exception as e:
            self.log(f'Erro ao salvar sequência: {e}')
    def mover_categoria(self, index, direction):
        new_index = index + direction
        if 0 <= new_index < len(self.category_list):
            self.category_list[index], self.category_list[new_index] = (self.category_list[new_index], self.category_list[index])
            self.salvar_sequencia_categorias()
            self.render_seq_tab()

    def render_seq_tab(self):
        # ***<module>.AlbionBotGUI.render_seq_tab: Failure detected at line number 908 and instruction offset 32: Different bytecode
        for child in self.seq_list_frame.winfo_children():
            child.destroy()
        self.seq_vars = {}
        enabled_count = sum(1 for category in self.category_list if category.get('enabled', True))
        self.create_page_header(
            self.seq_list_frame,
            'Ordem de navegação',
            'Categorias automáticas',
            f'{enabled_count} categorias ativas. Use as setas para definir a prioridade.',
        )
        for i, cat in enumerate(self.category_list):
            row_bg = COLOR_CARD
            card = tk.Frame(self.seq_list_frame, bg=row_bg, pady=7, padx=9)
            card.pack(fill='x', padx=12, pady=3)
            def make_on_toggle(c=cat):
                def toggle_fn(val):
                    c['enabled'] = val
                    self.salvar_sequencia_categorias()
                    self.render_seq_tab()
                return toggle_fn
            chk_frame = self.create_puffy_checkbox(card, cat['name'], cat['enabled'], make_on_toggle(), bg_color=row_bg)
            chk_frame.pack(side='left', padx=5)
            for child in chk_frame.winfo_children():
                if isinstance(child, tk.Label):
                    child.config(font=('Segoe UI Semibold', 8), fg=COLOR_TEXT if cat['enabled'] else COLOR_TEXT_DIM)
            btn_frame = tk.Frame(card, bg=row_bg)
            btn_frame.pack(side='right')
            if i > 0:
                btn_up = self.create_3d_button(btn_frame, '▲', type_color='gold', command=lambda idx=i: self.mover_categoria(idx, (-1)))
                btn_up.pack(side='left', padx=1)
            if i < len(self.category_list) - 1:
                btn_dn = self.create_3d_button(btn_frame, '▼', type_color='gold', command=lambda idx=i: self.mover_categoria(idx, 1))
                btn_dn.pack(side='left', padx=1)
    def render_cliq_tab(self):
        # ***<module>.AlbionBotGUI.render_cliq_tab: Failure detected at line number 935 and instruction offset 26: Different bytecode
        for child in self.cliq_tab.winfo_children():
            child.destroy()
        back_btn_cliq = tk.Label(self.cliq_tab, text='←  VOLTAR', fg=COLOR_TEXT_DIM, bg=COLOR_BG, font=('Segoe UI Semibold', 8), cursor='hand2')
        back_btn_cliq.pack(anchor='w', padx=10, pady=(10, 0))
        back_btn_cliq.bind('<Button-1>', lambda e: self.show_config_tab())
        tk.Label(self.cliq_tab, text='CALIBRAR CLIQUES', bg=COLOR_BG, fg=COLOR_ACCENT, font=('Segoe UI Semibold', 9), pady=10).pack()
        guide_categories = self.create_3d_button(
            self.cliq_tab,
            'GUIAR CATEGORIAS ATIVAS',
            type_color='green',
            command=lambda: self.abrir_calibragem_guiada('categories'),
        )
        guide_categories.pack(fill='x', padx=10, pady=(0, 6))
        self.click_status_labels = {}
        f_main = tk.Frame(self.cliq_tab, bg=COLOR_CARD, pady=8, padx=10)
        f_main.pack(fill='x', padx=10, pady=5)
        tk.Label(f_main, text='CATEGORIAS', bg=COLOR_CARD, fg=COLOR_TEXT, font=('Segoe UI Semibold', 8)).pack(side='left', padx=8)
        btn_main = self.create_3d_button(f_main, 'MARCAR', type_color='gold', command=lambda: self.iniciar_calibragem_campo('cat_clique_principal', 'click'))
        btn_main.pack(side='right', padx=5)
        status_main = tk.Label(f_main, text='○', bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=('Segoe UI', 10))
        status_main.pack(side='right', padx=(2, 0))
        self.click_status_labels['cat_clique_principal'] = status_main
        tk.Label(self.cliq_tab, text='2º Clique por Categoria', bg=COLOR_BG, fg=COLOR_TEXT_DIM, font=('Segoe UI Semibold', 8), pady=5).pack()
        for cat in DEFAULT_CATEGORIES:
            f = tk.Frame(self.cliq_tab, bg=COLOR_CARD, pady=7, padx=10)
            f.pack(fill='x', padx=12, pady=3)
            tk.Label(f, text=cat['name'], bg=COLOR_CARD, fg=COLOR_TEXT, font=('Segoe UI Semibold', 8)).pack(side='left', padx=8)
            btn = self.create_3d_button(f, 'MARCAR', type_color='gold', command=lambda k=cat['key']: self.iniciar_calibragem_campo(k, 'click'))
            btn.pack(side='right', padx=5)
            status_lbl = tk.Label(f, text='○', bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=('Segoe UI', 10))
            status_lbl.pack(side='right', padx=(2, 0))
            self.click_status_labels[cat['key']] = status_lbl
        self.root.after(100, self.atualizar_status_calibragem)
    def create_compact_stat_card(self, parent, label, value, col):
        # ***<module>.AlbionBotGUI.create_compact_stat_card: Failure detected at line number 954 and instruction offset 2: Different bytecode
        card = tk.Frame(parent, bg=COLOR_CARD)
        card.grid(row=0, column=col, sticky='ew', padx=3)
        parent.grid_columnconfigure(col, weight=1)
        inner = tk.Frame(card, bg=COLOR_CARD)
        inner.pack(fill='both', expand=True, padx=6, pady=7)
        tk.Label(inner, text=label, bg=COLOR_CARD, fg=COLOR_TEXT_DIM, font=UI_FONTS['caption_strong']).pack()
        val_label = tk.Label(inner, text=value, bg=COLOR_CARD, fg=COLOR_ACCENT, font=UI_FONTS['section_title'])
        val_label.pack(pady=(3, 0))
        return val_label
    def _poll_log_queue(self):
        """Drena um lote limitado da fila por tique, para nunca travar o Tk.

        Drenar a fila inteira de uma vez (sem limite) trava a thread principal
        quando o bot gera mensagens mais rapido do que a tela consegue exibir,
        o que o Windows detecta como "nao esta respondendo". Processando em
        lotes, a janela de mensagens do Windows sempre tem uma chance de ser
        atendida entre um lote e outro.
        """
        LOTE_MAXIMO = 200
        processadas = 0
        try:
            while processadas < LOTE_MAXIMO:
                msg = _log_queue.get_nowait()
                self._process_log_message(msg)
                processadas += 1
        except queue.Empty:
            pass
        self.process_notif_queue()
        # Se o lote encheu, provavelmente ainda ha fila acumulada: continua
        # quase imediatamente em vez de esperar o intervalo normal.
        proximo_intervalo = 0 if processadas >= LOTE_MAXIMO else 100
        self.root.after(proximo_intervalo, self._poll_log_queue)
    def log(self, message):
        """Coloca a mensagem na fila thread-safe. Se chamado da thread principal, processa direto."""
        _log_queue.put(message)
    def _process_log_message(self, message):
        # irreducible cflow, using cdg fallback
        """Processa uma mensagem de log (DEVE rodar na thread principal)."""
        # ***<module>.AlbionBotGUI._process_log_message: Failure: Compilation Error
        self.log_window.log(message)
        line = message.strip()
        if line.startswith('[INTERVENÇÃO NECESSÁRIA]'):
            self.running = False
            self.sell_running = False
            self.cycle_running = False
            self.fechando_ordens = False
            self._mini_intervention_required = True
            try:
                self.card_status.config(text='INTERVENÇÃO', fg=COLOR_ERROR)
                self.atualizar_botao_inicial()
                self.atualizar_botao_venda()
                self.atualizar_botao_ciclo()
            except Exception:
                pass
            self.show_notification('INTERVENÇÃO NECESSÁRIA')
        elif line.startswith('>>> BOT INICIADO!'):
            self._mini_intervention_required = False
        if line.startswith('[PAUSA PROTEGIDA]'):
            if 'Iniciada' in line or 'Restam' in line:
                remaining_match = re.search(r'(\d+m \d{2}s)', line)
                pause_text = (
                    f'PAUSA {remaining_match.group(1)}'
                    if remaining_match else 'PAUSA PROTEGIDA'
                )
                try:
                    self.card_status.config(text=pause_text, fg=COLOR_ACCENT)
                except Exception:
                    pass
                if getattr(self, 'sell_running', False):
                    try:
                        self.sell_module_status_lbl.config(text=pause_text, fg=COLOR_ACCENT)
                    except Exception:
                        pass
                if getattr(self, 'cycle_running', False):
                    try:
                        self.cycle_module_status_lbl.config(text=pause_text, fg=COLOR_ACCENT)
                    except Exception:
                        pass
            elif 'Encerrada' in line:
                try:
                    self.card_status.config(text='ATIVO', fg=COLOR_SUCCESS)
                except Exception:
                    pass
                if getattr(self, 'sell_running', False):
                    try:
                        self.sell_module_status_lbl.config(text='VENDENDO ITENS', fg=COLOR_SUCCESS)
                    except Exception:
                        pass
                if getattr(self, 'cycle_running', False):
                    self._render_cycle_stage()
        if getattr(self, 'cycle_running', False):
            if '[CICLO]' in line and (
                'Coletando e abrindo vendas' in line
                or 'Aguardando 10 segundos' in line
            ):
                self._set_cycle_stage('collect')
            elif '[CICLO]' in line and 'Coleta concluida e tela de venda confirmada' in line:
                self._set_cycle_stage('sell')
            elif '[CICLO]' in line and 'Tela de compra confirmada' in line:
                self._set_cycle_stage('buy')
            elif line == '>>> Bot em Standby.':
                self.cycle_running = False
                self._set_cycle_stage(None)
                try:
                    self.cycle_module_status_lbl.config(text='PAUSADO', fg=COLOR_TEXT_DIM)
                    self.atualizar_botao_ciclo()
                except Exception:
                    pass
        if line.startswith('[DATA]'):
            raw_data = line.replace('[DATA] ', '', 1).split('|')
            if len(raw_data) >= 4:
                self.last_item_name = raw_data[0]
                self.insert_tree(raw_data)
        elif line.startswith('[BUY]'):
            try:
                lucro = float(line.replace('[BUY] ', '', 1))
                self.total_orders += 1
                self.total_profit += lucro
                self.atualizar_contadores_reais()
                if getattr(self, 'cycle_running', False):
                    self.cycle_orders_completed = getattr(self, 'cycle_orders_completed', 0) + 1
                    self._update_cycle_counters()
                self.play_order_sound()
            except Exception:
                pass
        elif line.startswith('[BUY_DETAIL] '):
            try:
                detail = json.loads(line.replace('[BUY_DETAIL] ', '', 1))
                preco_pedido = detail.get('preco_pedido')
                taxa_pedido = detail.get('taxa_pedido')
                if isinstance(preco_pedido, (int, float)):
                    self.total_gasto += preco_pedido
                    self.atualizar_contadores_reais()
                if isinstance(taxa_pedido, (int, float)):
                    self.total_taxa += taxa_pedido
            except Exception:
                pass
        elif line.startswith('[VENDA] Pedido de venda criado com sucesso.'):
            if getattr(self, 'cycle_running', False):
                self.cycle_items_sold = getattr(self, 'cycle_items_sold', 0) + 1
                self._update_cycle_counters()
    def insert_tree(self, data):
        empty_state = getattr(self, 'tree_empty_state', None)
        if empty_state is not None:
            try:
                empty_state.place_forget()
            except Exception:
                pass
        is_opp = len(data) >= 5 and data[4] == '1'
        item_vals = list(data[:4])
        for index in (1, 2):
            try:
                number = int(float(item_vals[index]))
                item_vals[index] = f'{number:,}'.replace(',', '.')
            except (TypeError, ValueError):
                pass
        if is_opp:
            tag = 'opp'
        else:
            n_rows = len(self.tree.get_children())
            tag = 'even' if n_rows % 2 == 0 else 'odd'
        self.tree.insert('', 0, values=item_vals, tags=(tag,))
        if len(self.tree.get_children()) > 50:
            self.tree.delete(self.tree.get_children()[(-1)])
    def show_notification(self, message):
        """Exibe uma notificação elegante que some sozinha no canto superior do jogo."""
        try:
            win = get_albion_window()
            notif = tk.Toplevel(self.root)
            notif.overrideredirect(True)
            notif.attributes('-topmost', True)
            notif.config(bg='#050505', highlightthickness=1, highlightbackground=COLOR_ACCENT)
            if win and not win.isMinimized:
                nx = win.left + win.width - 220
                ny = win.top + 45
            else:
                nx = self.root.winfo_x() + self.root.winfo_width() + 10
                ny = self.root.winfo_y() + 10
            notif.geometry(f'200x40+{nx}+{ny}')
            tk.Label(notif, text='✔ ' + message, fg=COLOR_ACCENT, bg='#050505', font=('Verdana', 8, 'bold')).pack(expand=True)
            self.root.after(1500, lambda: notif.destroy() if notif.winfo_exists() else None)
        except Exception as e:
            self.log(f'Notificação: {message}')

    def _passos_calibragem_guiada(self, scope='buy'):
        if scope == 'sell':
            return list(GUIDED_SELL_STEPS)
        if scope == 'cycle':
            return list(GUIDED_CYCLE_STEPS)
        if scope == 'close':
            return [
                ('FECHAMENTO', "Área dos botões X", 'area_fecha_pedidos', 'area',
                 'Abra a tela das suas ordens e contorne somente a região onde aparecem os botões X.'),
            ]
        if scope == 'categories':
            steps = [
                ('CATEGORIAS', 'Abrir menu Categorias', 'cat_clique_principal', 'click',
                 'Com a loja aberta, marque o centro do menu usado para abrir as categorias.'),
            ]
            categories = getattr(self, 'category_list', DEFAULT_CATEGORIES)
            enabled = [cat for cat in categories if cat.get('enabled', True)]
            if not enabled:
                enabled = list(categories)
            for cat in enabled:
                steps.append((
                    'CATEGORIAS',
                    cat['name'],
                    cat['key'],
                    'click',
                    f"Abra o menu Categorias no Albion e marque o centro da opção {cat['name']}.",
                ))
            return steps
        return list(GUIDED_BUY_STEPS)

    def atualizar_status_calibragem(self):
        try:
            data = load_settings('offsets.json')
        except Exception:
            data = {}

        for labels_name in ('calib_status_labels', 'click_status_labels'):
            labels = getattr(self, labels_name, {})
            for key, label in labels.items():
                try:
                    configured = bool(data.get(key))
                    label.config(
                        text='●' if configured else '○',
                        fg=COLOR_SUCCESS if configured else COLOR_TEXT_DIM,
                    )
                except Exception:
                    pass

        required = set(BUY_REQUIRED_KEYS)
        if data.get('cat_ativo'):
            required.add('cat_clique_principal')
            categories = getattr(self, 'category_list', DEFAULT_CATEGORIES)
            required.update(cat['key'] for cat in categories if cat.get('enabled', True))
        completed = sum(1 for key in required if data.get(key))

        sell_completed = sum(1 for key in SELL_REQUIRED_KEYS if data.get(key))
        sell_ready = sell_completed == len(SELL_REQUIRED_KEYS)
        cycle_completed = sum(1 for key in CYCLE_REQUIRED_KEYS if data.get(key))
        cycle_ready = cycle_completed == len(CYCLE_REQUIRED_KEYS)
        shopping_completed = sum(1 for key in SHOPPING_REQUIRED_KEYS if data.get(key))
        shopping_ready = shopping_completed == len(SHOPPING_REQUIRED_KEYS)
        remover_pedidos_completed = sum(
            1 for key in REMOVER_PEDIDOS_REQUIRED_KEYS if data.get(key)
        )
        remover_pedidos_ready = remover_pedidos_completed == len(REMOVER_PEDIDOS_REQUIRED_KEYS)
        buy_ready = completed == len(required)
        full_cycle_ready = buy_ready and sell_ready and cycle_ready
        if hasattr(self, 'shopping_module_status_lbl') and not getattr(self, 'shopping_running', False):
            try:
                self.shopping_module_status_lbl.config(
                    text=(
                        'PRONTO PARA INICIAR' if shopping_ready
                        else f'CALIBRAGEM PENDENTE {shopping_completed}/{len(SHOPPING_REQUIRED_KEYS)}'
                    ),
                    fg=COLOR_SUCCESS if shopping_ready else COLOR_ACCENT,
                )
            except Exception:
                pass
        if hasattr(self, 'remover_pedidos_module_status_lbl') and not getattr(
            self, 'remover_pedidos_running', False
        ):
            try:
                self.remover_pedidos_module_status_lbl.config(
                    text=(
                        'PRONTO PARA INICIAR' if remover_pedidos_ready
                        else f'CALIBRAGEM PENDENTE {remover_pedidos_completed}/{len(REMOVER_PEDIDOS_REQUIRED_KEYS)}'
                    ),
                    fg=COLOR_SUCCESS if remover_pedidos_ready else COLOR_ACCENT,
                )
            except Exception:
                pass
        if hasattr(self, 'sell_calibration_lbl'):
            try:
                self.sell_calibration_lbl.config(
                    text=('CALIBRAGEM PRONTA' if sell_ready else
                          f'CALIBRAGEM PENDENTE {sell_completed}/{len(SELL_REQUIRED_KEYS)}'),
                    fg=COLOR_SUCCESS if sell_ready else COLOR_ACCENT,
                )
            except Exception:
                pass
        if hasattr(self, 'cycle_calibration_lbl'):
            try:
                self.cycle_calibration_lbl.config(
                    text=('CALIBRAGEM PRONTA' if cycle_ready else
                          f'CALIBRAGEM PENDENTE {cycle_completed}/{len(CYCLE_REQUIRED_KEYS)}'),
                    fg=COLOR_SUCCESS if cycle_ready else COLOR_ACCENT,
                )
            except Exception:
                pass
        if hasattr(self, 'sell_prepare_calibration_lbl'):
            try:
                self.sell_prepare_calibration_lbl.config(
                    text='PRONTA' if sell_ready else f'PENDENTE {sell_completed}/{len(SELL_REQUIRED_KEYS)}',
                    fg=COLOR_SUCCESS if sell_ready else COLOR_ACCENT,
                )
            except Exception:
                pass
        if hasattr(self, 'sell_module_status_lbl') and not getattr(self, 'sell_running', False):
            try:
                self.sell_module_status_lbl.config(
                    text='PRONTO PARA INICIAR' if sell_ready else 'CALIBRAGEM PENDENTE',
                    fg=COLOR_SUCCESS if sell_ready else COLOR_ACCENT,
                )
            except Exception:
                pass
        if hasattr(self, 'cycle_module_status_lbl') and not getattr(self, 'cycle_running', False):
            try:
                self.cycle_module_status_lbl.config(
                    text='PRONTO PARA INICIAR' if full_cycle_ready else 'CALIBRAGEM PENDENTE',
                    fg=COLOR_SUCCESS if full_cycle_ready else COLOR_ACCENT,
                )
            except Exception:
                pass

        if hasattr(self, 'calib_health_lbl'):
            if buy_ready:
                status_text = f'PRONTO • {completed}/{len(required)} campos configurados'
                status_color = COLOR_SUCCESS
            else:
                status_text = f'PENDENTE • {completed}/{len(required)} campos configurados'
                status_color = COLOR_ACCENT
            try:
                self.calib_health_lbl.config(text=status_text, fg=status_color)
            except Exception:
                pass
        if hasattr(self, 'bot_calibration_lbl'):
            try:
                self.bot_calibration_lbl.config(
                    text='PRONTA  ›' if buy_ready else f'PENDENTE {completed}/{len(required)}  ›',
                    fg=COLOR_SUCCESS if buy_ready else COLOR_ACCENT,
                )
            except Exception:
                pass

        if hasattr(self, 'optional_calibration_notice'):
            missing_optional = [
                label for key, label in OPTIONAL_CALIBRATION_KEYS if not data.get(key)
            ]
            try:
                if missing_optional:
                    self.optional_calibration_notice_lbl.config(
                        text=(
                            '⚠ Calibragem opcional recomendada pendente: '
                            + ', '.join(missing_optional)
                            + '. Toque aqui para calibrar.'
                        )
                    )
                    self.optional_calibration_notice.pack(
                        fill='x', padx=14, pady=(0, 6), before=self.start_btn_container
                    )
                else:
                    self.optional_calibration_notice.pack_forget()
            except Exception:
                pass

        guide = getattr(self, 'guided_calibration_window', None)
        if guide is not None:
            try:
                if guide.winfo_exists():
                    self._atualizar_janela_calibragem_guiada()
            except Exception:
                pass

    def abrir_calibragem_guiada(self, scope='buy'):
        if self.automacao_em_execucao():
            messagebox.showwarning('Calibragem', 'Pause o bot antes de alterar a calibragem.')
            return
        win = get_albion_window()
        if not win or win.isMinimized:
            messagebox.showerror('Calibragem', 'Abra e restaure a janela do Albion antes de começar.')
            return

        old_window = getattr(self, 'guided_calibration_window', None)
        try:
            if old_window is not None and old_window.winfo_exists():
                old_window.destroy()
        except Exception:
            pass

        self.guided_calibration_scope = scope
        self.guided_calibration_steps = self._passos_calibragem_guiada(scope)
        data = load_settings('offsets.json')
        self.guided_calibration_index = next(
            (i for i, step in enumerate(self.guided_calibration_steps) if not data.get(step[2])),
            0,
        )

        panel = tk.Toplevel(self.root)
        self.guided_calibration_window = panel
        panel.overrideredirect(True)
        panel.attributes('-topmost', True)
        panel.configure(bg=COLOR_NAV)
        panel.update_idletasks()
        width, height = 580, 680
        px = min(max(10, self.root.winfo_x() + self.root.winfo_width() + 12), panel.winfo_screenwidth() - width - 10)
        py = min(max(10, self.root.winfo_y()), panel.winfo_screenheight() - height - 40)
        panel.geometry(f'{width}x{height}+{px}+{py}')
        aplicar_cantos_arredondados(panel)

        shell = tk.Frame(panel, bg=COLOR_NAV, highlightthickness=1, highlightbackground=COLOR_BORDER)
        shell.pack(fill='both', expand=True)
        header = tk.Frame(shell, bg=COLOR_SIDEBAR, height=54)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text='Calibragem guiada', bg=COLOR_SIDEBAR, fg=COLOR_TEXT,
                 font=('Bahnschrift SemiBold', 13)).pack(side='left', padx=(18, 12))
        scope_names = {'buy': 'COMPRAS', 'sell': 'VENDAS', 'categories': 'CATEGORIAS', 'close': 'FECHAMENTO'}
        tk.Label(header, text=scope_names.get(scope, scope.upper()), bg=UI_COLORS['surface_raised'], fg=COLOR_ACCENT,
                 font=('Segoe UI Semibold', 8), padx=10, pady=5).pack(side='left')
        close_btn = tk.Button(header, text='×', command=self._fechar_calibragem_guiada,
                              bg=COLOR_SIDEBAR, fg=COLOR_TEXT_DIM, activebackground=COLOR_ERROR,
                              activeforeground='white', relief='flat', bd=0,
                              font=('Arial', 18, 'bold'), cursor='hand2')
        close_btn.pack(side='right', padx=9)

        drag = {'x': 0, 'y': 0}
        def start_drag(event):
            drag['x'], drag['y'] = event.x_root - panel.winfo_x(), event.y_root - panel.winfo_y()
        def move_drag(event):
            panel.geometry(f'+{event.x_root - drag["x"]}+{event.y_root - drag["y"]}')
        header.bind('<Button-1>', start_drag)
        header.bind('<B1-Motion>', move_drag)

        body = tk.Frame(shell, bg=COLOR_BG, padx=20, pady=16)
        body.pack(fill='both', expand=True)
        self.guide_progress_label = tk.Label(body, text='', bg=COLOR_BG, fg=COLOR_TEXT_DIM,
                                             font=('Segoe UI Semibold', 8))
        self.guide_progress_label.pack(anchor='w')
        self.guide_progress_var = tk.DoubleVar(value=0)
        progress = ttk.Progressbar(body, variable=self.guide_progress_var, maximum=100)
        progress.pack(fill='x', pady=(7, 16))

        step_card = tk.Frame(body, bg=COLOR_CARD, padx=16, pady=15)
        step_card.pack(fill='x')
        self.guide_group_label = tk.Label(step_card, text='', bg=COLOR_CARD, fg=COLOR_ACCENT,
                                          font=('Segoe UI Semibold', 8))
        self.guide_group_label.pack(anchor='w')
        self.guide_step_label = tk.Label(step_card, text='', bg=COLOR_CARD, fg=COLOR_TEXT,
                                         font=('Bahnschrift SemiBold', 14))
        self.guide_step_label.pack(anchor='w', pady=(5, 6))
        self.guide_instruction_label = tk.Label(step_card, text='', bg=COLOR_CARD, fg=COLOR_TEXT_DIM,
                                                font=('Segoe UI', 9), justify='left', anchor='w',
                                                wraplength=510)
        self.guide_instruction_label.pack(fill='x')
        self.guide_saved_label = tk.Label(step_card, text='', bg=COLOR_CARD, fg=COLOR_SUCCESS,
                                          font=('Segoe UI Semibold', 8))
        self.guide_saved_label.pack(anchor='w', pady=(7, 0))

        tk.Label(body, text='ETAPAS', bg=COLOR_BG, fg=COLOR_TEXT_DIM,
                 font=('Segoe UI Semibold', 8)).pack(anchor='w', pady=(16, 6))
        self.guide_list = tk.Listbox(body, bg=UI_COLORS['field'], fg=COLOR_TEXT, selectbackground=UI_COLORS['surface_raised'],
                                    selectforeground=COLOR_TEXT, relief='flat', bd=0,
                                    highlightthickness=1, highlightbackground=COLOR_BORDER,
                                    font=('Consolas', 9), activestyle='none', height=11)
        self.guide_list.pack(fill='both', expand=True)
        self.guide_list.bind('<<ListboxSelect>>', self._selecionar_etapa_guiada)

        nav = tk.Frame(body, bg=COLOR_BG)
        nav.pack(fill='x', pady=(12, 8))
        tk.Button(nav, text='‹ ANTERIOR', command=lambda: self._mover_etapa_guiada(-1),
                  bg=UI_COLORS['surface_raised'], fg=COLOR_TEXT, activebackground=UI_COLORS['surface_hover'], activeforeground=COLOR_TEXT,
                  relief='flat', bd=0, padx=13, pady=10, font=('Segoe UI Semibold', 8), cursor='hand2').pack(side='left')
        tk.Button(nav, text='CALIBRAR ESTA ETAPA', command=self._calibrar_etapa_guiada,
                  bg=UI_COLORS['success_surface'], fg=COLOR_TEXT, activebackground=COLOR_SUCCESS, activeforeground=COLOR_TEXT,
                  relief='flat', bd=0, padx=18, pady=10, font=('Segoe UI Semibold', 9), cursor='hand2').pack(side='left', expand=True, padx=10)
        tk.Button(nav, text='PRÓXIMA ›', command=lambda: self._mover_etapa_guiada(1),
                  bg=UI_COLORS['surface_raised'], fg=COLOR_TEXT, activebackground=UI_COLORS['surface_hover'], activeforeground=COLOR_TEXT,
                  relief='flat', bd=0, padx=13, pady=10, font=('Segoe UI Semibold', 8), cursor='hand2').pack(side='right')
        tk.Button(body, text='VALIDAR SEM CLIQUES', command=self._validar_pelo_guia,
                  bg=COLOR_CARD, fg=COLOR_ACCENT, activebackground=UI_COLORS['surface_raised'], activeforeground=COLOR_ACCENT,
                  relief='flat', bd=0, pady=9, font=('Segoe UI Semibold', 8), cursor='hand2').pack(fill='x')
        tk.Label(body, text='A calibragem acontece antes da execução e não reduz a velocidade do bot.',
                 bg=COLOR_BG, fg=COLOR_TEXT_DIM, font=('Segoe UI', 8)).pack(pady=(10, 0))
        self._atualizar_janela_calibragem_guiada()

    def _atualizar_janela_calibragem_guiada(self):
        panel = getattr(self, 'guided_calibration_window', None)
        if panel is None or not panel.winfo_exists():
            return
        steps = self.guided_calibration_steps
        index = max(0, min(self.guided_calibration_index, len(steps) - 1))
        self.guided_calibration_index = index
        data = load_settings('offsets.json')
        completed = sum(1 for step in steps if data.get(step[2]))
        self.guide_progress_var.set((completed / max(1, len(steps))) * 100)
        self.guide_progress_label.config(text=f'{completed}/{len(steps)} etapas configuradas')
        group, label, key, mode, instruction = steps[index]
        self.guide_group_label.config(text=f'{group}  •  {"ÁREA" if mode == "area" else "PONTO"}')
        self.guide_step_label.config(text=f'{index + 1}. {label}')
        self.guide_instruction_label.config(text=instruction)
        self.guide_saved_label.config(
            text='● Já configurado — você pode refazer' if data.get(key) else '○ Ainda não configurado',
            fg=COLOR_SUCCESS if data.get(key) else COLOR_ACCENT,
        )
        self.guide_list.delete(0, 'end')
        for item_index, item in enumerate(steps):
            configured = bool(data.get(item[2]))
            prefix = '✓' if configured else '○'
            self.guide_list.insert('end', f' {prefix}  {item_index + 1:02d}  {item[0]:<11}  {item[1]}')
            self.guide_list.itemconfig(item_index, fg=COLOR_SUCCESS if configured else COLOR_TEXT)
        self.guide_list.selection_clear(0, 'end')
        self.guide_list.selection_set(index)
        self.guide_list.see(index)

    def _selecionar_etapa_guiada(self, _event=None):
        selection = self.guide_list.curselection()
        if selection:
            new_index = int(selection[0])
            if new_index != self.guided_calibration_index:
                self.guided_calibration_index = new_index
                self._atualizar_janela_calibragem_guiada()

    def _mover_etapa_guiada(self, delta):
        count = len(self.guided_calibration_steps)
        self.guided_calibration_index = max(0, min(count - 1, self.guided_calibration_index + delta))
        self._atualizar_janela_calibragem_guiada()

    def _calibrar_etapa_guiada(self):
        win = get_albion_window()
        if not win or win.isMinimized:
            messagebox.showerror('Calibragem', 'Abra e restaure a janela do Albion.')
            return
        step = self.guided_calibration_steps[self.guided_calibration_index]
        try:
            self.guided_calibration_window.withdraw()
        except Exception:
            pass
        self.iniciar_calibragem_campo(step[2], step[3])

    def _retomar_calibragem_guiada(self, campo=None, saved=False):
        panel = getattr(self, 'guided_calibration_window', None)
        if panel is None:
            return
        try:
            if not panel.winfo_exists():
                return
            if saved and campo:
                current = self.guided_calibration_index
                if current < len(self.guided_calibration_steps) - 1:
                    self.guided_calibration_index = current + 1
            panel.deiconify()
            panel.lift()
            self._atualizar_janela_calibragem_guiada()
        except Exception:
            pass

    def _validar_pelo_guia(self):
        scope = getattr(self, 'guided_calibration_scope', 'buy')
        self._fechar_calibragem_guiada()
        validator = self.testar_calibragem_venda if scope == 'sell' else self.testar_calibragem
        self.root.after(100, validator)

    def _fechar_calibragem_guiada(self):
        panel = getattr(self, 'guided_calibration_window', None)
        try:
            if panel is not None and panel.winfo_exists():
                panel.destroy()
        except Exception:
            pass
        self.guided_calibration_window = None
        self.atualizar_status_calibragem()

    def iniciar_calibragem_campo(self, campo, modo='area'):
        if self.automacao_em_execucao():
            messagebox.showwarning('Calibragem', 'Pause o bot antes de alterar a calibragem.')
            self._retomar_calibragem_guiada()
            return
        self.calib_campo = campo
        self.calib_modo = modo
        win = get_albion_window()
        if not win or win.isMinimized:
            messagebox.showerror('Calibragem', 'Abra e restaure a janela do Albion antes de calibrar.')
            return
        try:
            geometry = get_client_geometry(win)
        except Exception as exc:
            messagebox.showerror('Calibragem', f'Não foi possível medir a área interna do Albion:\n{exc}')
            self._retomar_calibragem_guiada()
            return

        self.calibration_active = True
        try:
            self.root.withdraw()
            self.root.update_idletasks()
            time.sleep(0.08)
        except Exception:
            pass
        try:
            self.calib_snapshot = capture_region((geometry.left, geometry.top, geometry.width, geometry.height)).convert('RGB')
        except Exception:
            self.calib_snapshot = None

        self.calib_win = tk.Toplevel(self.root)
        self.calib_win.overrideredirect(True)
        self.calib_win.geometry(f'{geometry.width}x{geometry.height}{geometry.left:+d}{geometry.top:+d}')
        self.calib_win.attributes('-topmost', True)

        self.calib_canvas = tk.Canvas(self.calib_win, cursor='crosshair', bg=UI_COLORS['field'], highlightthickness=0)
        self.calib_canvas.pack(fill='both', expand=True)
        if self.calib_snapshot is not None:
            darkened = ImageEnhance.Brightness(self.calib_snapshot).enhance(0.72)
            self.calib_snapshot_photo = ImageTk.PhotoImage(darkened)
            self.calib_canvas.create_image(0, 0, image=self.calib_snapshot_photo, anchor='nw', tags='snapshot')
        else:
            try:
                self.calib_win.attributes('-alpha', 0.38)
            except Exception:
                pass

        if campo == 'btn_pedido':
            action_instruction = 'Contorne APENAS 1 botão Pedido de Compra\nNÃO selecione a coluna inteira'
        else:
            action_instruction = ('Clique e arraste para desenhar a área' if modo == 'area' else 'Clique no centro exato')
        instr = f"CALIBRANDO: {campo.upper()}\n{action_instruction}\nESC ou botão direito: cancelar"
        lbl_instr = tk.Label(self.calib_win, text=instr, font=('Segoe UI Semibold', 11),
                             fg=COLOR_ACCENT, bg=COLOR_NAV, padx=14, pady=9,
                             justify='left', highlightthickness=1, highlightbackground=COLOR_ACCENT_DIM)
        lbl_instr.place(x=18, y=max(18, geometry.height - 112))

        self.calib_zoom_canvas = tk.Canvas(self.calib_win, width=174, height=202,
                                           bg=COLOR_NAV, highlightthickness=2,
                                           highlightbackground=COLOR_ACCENT_DIM)
        self.calib_zoom_canvas.place(x=max(8, geometry.width - 194), y=18)
        self.calib_zoom_canvas.create_text(87, 190, text='LUPA DE PRECISÃO', fill=COLOR_TEXT_DIM,
                                           font=('Segoe UI Semibold', 7))

        self.calib_geometry = geometry
        self.calib_canvas.bind('<Button-1>', self.on_calib_click)
        self.calib_canvas.bind('<Motion>', self.on_calib_motion)
        if modo == 'area':
            self.calib_canvas.bind('<B1-Motion>', self.on_calib_drag)
        self.calib_canvas.bind('<ButtonRelease-1>', self.on_calib_release)
        self.calib_canvas.bind('<Button-3>', self.cancelar_calibragem_campo)
        self.calib_win.bind('<Escape>', self.cancelar_calibragem_campo)
        self.calib_win.focus_force()

    def on_calib_motion(self, event):
        try:
            x = max(0, min(int(event.x), self.calib_geometry.width - 1))
            y = max(0, min(int(event.y), self.calib_geometry.height - 1))
            self.calib_canvas.delete('cursor_guide')
            self.calib_canvas.create_line(x - 18, y, x + 18, y, fill=COLOR_ACCENT, width=1,
                                          tags='cursor_guide')
            self.calib_canvas.create_line(x, y - 18, x, y + 18, fill=COLOR_ACCENT, width=1,
                                          tags='cursor_guide')
            if self.calib_snapshot is None:
                return
            radius = 18
            tile = Image.new('RGB', (radius * 2, radius * 2), UI_COLORS['field'])
            left, top = max(0, x - radius), max(0, y - radius)
            right = min(self.calib_snapshot.width, x + radius)
            bottom = min(self.calib_snapshot.height, y + radius)
            crop = self.calib_snapshot.crop((left, top, right, bottom))
            tile.paste(crop, (left - (x - radius), top - (y - radius)))
            zoom = tile.resize((162, 162), Image.Resampling.NEAREST)
            draw = ImageDraw.Draw(zoom)
            center = 81
            draw.line((center - 18, center, center + 18, center), fill=COLOR_ACCENT, width=2)
            draw.line((center, center - 18, center, center + 18), fill=COLOR_ACCENT, width=2)
            draw.ellipse((center - 3, center - 3, center + 3, center + 3), outline=COLOR_TEXT, width=2)
            self.calib_zoom_photo = ImageTk.PhotoImage(zoom)
            self.calib_zoom_canvas.delete('zoom_image')
            self.calib_zoom_canvas.create_image(6, 6, image=self.calib_zoom_photo, anchor='nw', tags='zoom_image')
            self.calib_zoom_canvas.delete('coords')
            self.calib_zoom_canvas.create_text(87, 175, text=f'X {x:04d}   Y {y:04d}', fill=COLOR_TEXT,
                                               font=('Consolas', 8, 'bold'), tags='coords')
        except Exception:
            pass

    def cancelar_calibragem_campo(self, _event=None):
        try:
            if hasattr(self, 'calib_win') and self.calib_win.winfo_exists():
                self.calib_win.destroy()
        except Exception:
            pass
        self.calibration_active = False
        try:
            self.root.deiconify()
            self.root.lift()
        except Exception:
            pass
        self._retomar_calibragem_guiada(saved=False)

    def on_calib_click(self, event):
        self.calib_start = (event.x_root, event.y_root)
        if self.calib_modo == 'area':
            start_x = event.x_root - self.calib_win.winfo_rootx()
            start_y = event.y_root - self.calib_win.winfo_rooty()
            self.calib_rect = self.calib_canvas.create_rectangle(start_x, start_y, start_x, start_y, outline=COLOR_ACCENT, width=3)
        else:
            cx = event.x_root - self.calib_win.winfo_rootx()
            cy = event.y_root - self.calib_win.winfo_rooty()
            self.calib_canvas.create_line(cx - 12, cy, cx + 12, cy, fill=COLOR_ACCENT, width=3)
            self.calib_canvas.create_line(cx, cy - 12, cx, cy + 12, fill=COLOR_ACCENT, width=3)

    def on_calib_drag(self, event):
        self.on_calib_motion(event)
        if self.calib_modo == 'area' and hasattr(self, 'calib_rect'):
            start_x = self.calib_start[0] - self.calib_win.winfo_rootx()
            start_y = self.calib_start[1] - self.calib_win.winfo_rooty()
            cur_x = event.x_root - self.calib_win.winfo_rootx()
            cur_y = event.y_root - self.calib_win.winfo_rooty()
            self.calib_canvas.coords(self.calib_rect, start_x, start_y, cur_x, cur_y)

    def on_calib_release(self, event):
        x1, y1 = (event.x_root, event.y_root)
        try:
            if self.calib_modo == 'area':
                x0, y0 = self.calib_start
                w, h = (abs(x1 - x0), abs(y1 - y0))
                if w < 3 or h < 3:
                    raise ValueError('A área selecionada é pequena demais.')
                if self.calib_campo == 'btn_pedido':
                    valid, reason = bot.validar_amostra_botao_pedido(
                        w, h, self.calib_geometry.width, self.calib_geometry.height
                    )
                    if not valid:
                        messagebox.showerror('Amostra inválida', reason, parent=self.calib_win)
                        try:
                            self.calib_canvas.delete(self.calib_rect)
                        except Exception:
                            pass
                        return
                valor = normalize_rect(min(x0, x1), min(y0, y1), w, h, self.calib_geometry)
            else:
                valor = normalize_point(x1, y1, self.calib_geometry)
        except ValueError as exc:
            messagebox.showerror('Calibragem', str(exc), parent=self.calib_win)
            self.cancelar_calibragem_campo()
            return

        try:
            self.calib_win.withdraw()
            self.calib_win.update_idletasks()
            self.root.update_idletasks()
            self.root.update()
            time.sleep(0.1)
        except Exception:
            pass
        self.salvar_calibração(self.calib_campo, valor)
        try:
            self.calib_win.destroy()
        except Exception:
            pass
        self.calibration_active = False
        try:
            self.root.deiconify()
            self.root.lift()
        except Exception:
            pass
        self.atualizar_status_calibragem()
        self._retomar_calibragem_guiada(self.calib_campo, saved=True)
        self.show_notification(f'{self.calib_campo.upper()} SALVO')
    def resetar_calibragens(self):
        # ***<module>.AlbionBotGUI.resetar_calibragens: Failure detected at line number 1048 and instruction offset 2: Different bytecode
        if messagebox.askyesno('Confirmar Reset', 'Isso apagará todas as calibragens. Deseja continuar?'):
            data = strip_spatial_settings(load_settings('offsets.json'))
            save_settings('offsets.json', data)
            self.offsets = data
            self.show_notification('CALIBRAGEM RESETADA')
            self.log('>>> Calibragens apagadas; preferências financeiras foram preservadas.')
            self.atualizar_status_calibragem()

    def testar_calibragem_venda(self):
        win = get_albion_window()
        if not win or win.isMinimized:
            messagebox.showerror('Venda', 'Abra e restaure a janela do Albion.')
            return
        try:
            geometry = get_client_geometry(win)
            data = load_settings('offsets.json')
            valid, reason = validate_calibration(data, geometry, mode='sell')
            if valid:
                messagebox.showinfo(
                    'Venda',
                    'Calibragem de venda válida e pronta para uso.',
                )
            else:
                messagebox.showerror('Venda', reason)
            self.atualizar_status_calibragem()
        except Exception as exc:
            messagebox.showerror('Venda', f'Falha ao validar calibragem:\n{exc}')

    def testar_calibragem_ciclo(self):
        win = get_albion_window()
        if not win or win.isMinimized:
            messagebox.showerror('Ciclo automático', 'Abra e restaure a janela do Albion.')
            return
        try:
            geometry = get_client_geometry(win)
            data = load_settings('offsets.json')
            valid, reason = validate_calibration(data, geometry, mode='cycle')
            if valid:
                messagebox.showinfo(
                    'Ciclo automático',
                    'Calibragens de Compra, Venda e Ciclo estão válidas.',
                )
            else:
                messagebox.showerror('Ciclo automático', reason)
            self.atualizar_status_calibragem()
        except Exception as exc:
            messagebox.showerror(
                'Ciclo automático', f'Falha ao validar calibragem:\n{exc}'
            )

    def testar_calibragem(self):
        win = get_albion_window()
        if not win or win.isMinimized:
            messagebox.showerror('Teste', 'Abra e restaure a janela do Albion.')
            return
        try:
            geometry = get_client_geometry(win)
            data = load_settings('offsets.json')
            valid, reason = validate_calibration(data, geometry, required_keys=[])
            if not valid:
                messagebox.showerror('Teste', reason)
                return

            configured = [(key, value) for key, value in data.items() if is_spatial_key(key)]
            required = set(BUY_REQUIRED_KEYS)
            if data.get('cat_ativo'):
                required.add('cat_clique_principal')
                categories = getattr(self, 'category_list', DEFAULT_CATEGORIES)
                required.update(cat['key'] for cat in categories if cat.get('enabled', True))
            missing = sorted(key for key in required if not data.get(key))

            pedido_count = 0
            pedido_score = -1.0
            pedido_template = 'não testado'
            if data.get('area_lista') and os.path.exists(calibration_template_path('pedido_usuario.png')):
                try:
                    botoes, pedido_score, pedido_template = bot.detectar_botoes_pedido(win, data)
                    pedido_count = len(botoes)
                except Exception as detection_error:
                    pedido_template = f'erro: {detection_error}'

            overlay = tk.Toplevel(self.root)
            overlay.overrideredirect(True)
            overlay.geometry(f'{geometry.width}x{geometry.height}{geometry.left:+d}{geometry.top:+d}')
            overlay.attributes('-topmost', True)
            try:
                overlay.attributes('-transparentcolor', '#010203')
            except Exception:
                overlay.attributes('-alpha', 0.45)
            canvas = tk.Canvas(overlay, bg='#010203', highlightthickness=0)
            canvas.pack(fill='both', expand=True)
            count = 0
            ocr_keys = {'nome', 'venda', 'compra', 'preco_final_compra', 'icone'}
            for key, value in configured:
                color = COLOR_ACCENT if key.startswith('cat_clique_') else '#d3bd8a' if key in ocr_keys else '#7fa47a'
                rect = resolve_rect(value, geometry, data)
                if rect:
                    x, y, w, h = rect
                    x -= geometry.left
                    y -= geometry.top
                    count += 1
                    canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=3)
                    canvas.create_rectangle(x, y, x + min(w, 24), y + min(h, 20), fill=COLOR_NAV, outline=color)
                    canvas.create_text(x + 5, y + 3, text=str(count), fill=color, anchor='nw', font=('Segoe UI Semibold', 8))
                    canvas.create_text(x + 4, y + h + 4, text=key, fill='#ffffff', anchor='nw', font=('Arial', 8, 'bold'))
                    continue
                point = resolve_point(value, geometry, data)
                if point:
                    x, y = point[0] - geometry.left, point[1] - geometry.top
                    count += 1
                    canvas.create_oval(x - 9, y - 9, x + 9, y + 9, outline=color, width=3)
                    canvas.create_line(x - 14, y, x + 14, y, fill=color, width=2)
                    canvas.create_line(x, y - 14, x, y + 14, fill=color, width=2)
                    canvas.create_text(x + 13, y - 12, text=f'{count}  {key}', fill='#ffffff',
                                       anchor='nw', font=('Arial', 8, 'bold'))

            summary = tk.Frame(overlay, bg=COLOR_NAV, padx=14, pady=11,
                               highlightthickness=2, highlightbackground=COLOR_ACCENT_DIM)
            summary.place(x=18, y=18)
            tk.Label(summary, text='DIAGNÓSTICO DE CALIBRAGEM', bg=COLOR_NAV, fg=COLOR_ACCENT,
                     font=('Segoe UI Semibold', 10)).pack(anchor='w')
            config_text = f'{count} marcações exibidas • ' + ('configuração completa' if not missing else f'{len(missing)} campos pendentes')
            tk.Label(summary, text=config_text, bg=COLOR_NAV,
                     fg=COLOR_SUCCESS if not missing else COLOR_ACCENT,
                     font=('Arial', 8, 'bold')).pack(anchor='w', pady=(4, 1))
            pedido_text = (
                f'Botão Pedido: {pedido_count} encontrado(s) • score {pedido_score:.3f} • {pedido_template}'
                if pedido_score >= 0 else f'Botão Pedido: {pedido_template}'
            )
            tk.Label(summary, text=pedido_text, bg=COLOR_NAV,
                     fg=COLOR_SUCCESS if pedido_count else COLOR_ERROR,
                     font=('Arial', 8, 'bold')).pack(anchor='w')
            if data.get('compra_topo_cor'):
                try:
                    eh_meu, brilho = bot.linha_pedido_e_minha(data, win)
                    cor_texto = (
                        f'Cor da linha do topo: brilho={brilho:.1f} • '
                        + ('PEDIDO MEU (escura)' if eh_meu else 'linha normal (clara)')
                    )
                    tk.Label(summary, text=cor_texto, bg=COLOR_NAV, fg=COLOR_ACCENT,
                             font=('Arial', 8, 'bold')).pack(anchor='w', pady=(1, 0))
                except Exception as color_error:
                    tk.Label(summary, text=f'Cor da linha do topo: erro ({color_error})',
                             bg=COLOR_NAV, fg=COLOR_ERROR, font=('Arial', 8, 'bold')).pack(anchor='w', pady=(1, 0))
            if data.get('remover_pedidos_area_lista'):
                try:
                    editar_boxes, editar_score, editar_template = bot.detectar_botoes_por_template(
                        win, data, 'remover_pedidos_area_lista', 'editar_pedido_usuario.png'
                    )
                    cancelar_boxes, cancelar_score, cancelar_template = bot.detectar_botoes_por_template(
                        win, data, 'remover_pedidos_area_lista', 'cancelar_pedido_usuario.png'
                    )
                    pares = bot.parear_editar_com_cancelar(editar_boxes, cancelar_boxes)
                    pareados_editar = {par[0] for par in pares}
                    pareados_cancelar = {par[1] for par in pares}
                    for box in editar_boxes:
                        cor_caixa = '#39ff6a' if box in pareados_editar else '#ff2d55'
                        x0, y0 = box.left - geometry.left, box.top - geometry.top
                        canvas.create_rectangle(
                            x0, y0, x0 + box.width, y0 + box.height,
                            outline=cor_caixa, width=3,
                        )
                        canvas.create_text(
                            x0, max(0, y0 - 11), text='EDITAR', fill=cor_caixa, anchor='sw',
                            font=('Arial', 8, 'bold'),
                        )
                    for box in cancelar_boxes:
                        cor_caixa = '#39ff6a' if box in pareados_cancelar else '#ff2d55'
                        x0, y0 = box.left - geometry.left, box.top - geometry.top
                        canvas.create_rectangle(
                            x0, y0, x0 + box.width, y0 + box.height,
                            outline=cor_caixa, width=3,
                        )
                        canvas.create_text(
                            x0 + box.width, max(0, y0 - 11), text='X', fill=cor_caixa, anchor='se',
                            font=('Arial', 8, 'bold'),
                        )
                    remover_texto = (
                        f'Remover Pedidos: {len(editar_boxes)} EDITAR (score {editar_score:.2f}) • '
                        f'{len(cancelar_boxes)} X (score {cancelar_score:.2f}) • {len(pares)} par(es) válido(s)'
                    )
                    tk.Label(
                        summary, text=remover_texto, bg=COLOR_NAV,
                        fg=COLOR_SUCCESS if pares else COLOR_ERROR,
                        font=('Arial', 8, 'bold'),
                    ).pack(anchor='w', pady=(1, 0))
                    if editar_boxes or cancelar_boxes:
                        tk.Label(
                            summary,
                            text='Caixas no jogo: verde = par válido • vermelho = sem par '
                            '(confira se algum vermelho está fora de "Pedidos de Compra")',
                            bg=COLOR_NAV, fg=COLOR_TEXT_DIM, font=('Arial', 8),
                        ).pack(anchor='w')
                    if not editar_boxes or not cancelar_boxes:
                        tk.Label(
                            summary,
                            text='(deixe a tela "Pedidos de Compra" aberta para testar a detecção)',
                            bg=COLOR_NAV, fg=COLOR_TEXT_DIM, font=('Arial', 8),
                        ).pack(anchor='w')
                except Exception as remover_error:
                    tk.Label(
                        summary, text=f'Remover Pedidos: erro ({remover_error})',
                        bg=COLOR_NAV, fg=COLOR_ERROR, font=('Arial', 8, 'bold'),
                    ).pack(anchor='w', pady=(1, 0))
                if data.get('remover_pedidos_topo_cor'):
                    try:
                        eh_meu_rp, brilho_rp = bot.linha_pedido_e_minha(
                            data, win, 'remover_pedidos_topo_cor'
                        )
                        cor_texto_rp = (
                            f'Cor do topo (Editar pedido): brilho={brilho_rp:.1f} • '
                            + ('PEDIDO MEU (escura)' if eh_meu_rp else 'linha normal (clara)')
                            if brilho_rp is not None else
                            'Cor do topo (Editar pedido): não calibrado'
                        )
                        tk.Label(
                            summary, text=cor_texto_rp, bg=COLOR_NAV, fg=COLOR_ACCENT,
                            font=('Arial', 8, 'bold'),
                        ).pack(anchor='w')
                        tk.Label(
                            summary,
                            text='(abra "Editar pedido de compra" de um item para testar a leitura)',
                            bg=COLOR_NAV, fg=COLOR_TEXT_DIM, font=('Arial', 8),
                        ).pack(anchor='w')
                    except Exception as color_error_rp:
                        tk.Label(
                            summary, text=f'Cor do topo (Editar pedido): erro ({color_error_rp})',
                            bg=COLOR_NAV, fg=COLOR_ERROR, font=('Arial', 8, 'bold'),
                        ).pack(anchor='w')
            if missing:
                shown_missing = ', '.join(missing[:6]) + ('...' if len(missing) > 6 else '')
                tk.Label(summary, text='Pendentes: ' + shown_missing, bg=COLOR_NAV, fg=COLOR_TEXT,
                         font=('Arial', 8), wraplength=520, justify='left').pack(anchor='w', pady=(3, 0))
            tk.Label(summary, text='ESC para fechar • encerramento automático em 7 segundos',
                     bg=COLOR_NAV, fg=COLOR_TEXT_DIM, font=('Segoe UI', 8)).pack(anchor='w', pady=(6, 0))
            overlay.bind('<Escape>', lambda _event: overlay.destroy())
            overlay.after(7000, overlay.destroy)
            self.atualizar_status_calibragem()
            self.log(
                f'>>> Teste sem cliques: {count} marcações, {pedido_count} botão(ões) Pedido, '
                f'score {pedido_score:.3f}, {len(missing)} pendência(s).'
            )
        except Exception as exc:
            messagebox.showerror('Teste', f'Falha ao testar calibragem:\n{exc}')
    def salvar_calibração(self, campo, valor):
        data = load_settings('offsets.json')
        geometry = getattr(self, 'calib_geometry', None)
        if geometry is None:
            win = get_albion_window()
            geometry = get_client_geometry(win)
        data, reset = prepare_for_calibration(data, geometry)
        if reset:
            self.log('>>> Calibragem antiga/incompatível removida. Iniciado perfil v2 para esta janela.')
        data.pop('calibration_preset_id', None)
        data[campo] = valor
        self.offsets[campo] = valor

        if campo in (
            'ancora', 'btn_sim', 'btn_nao', 'btn_pedido', 'sell_button_sample',
            'remover_pedidos_btn_editar', 'remover_pedidos_btn_cancelar',
        ):
            import pyautogui
            try:
                calibration_assets_dir().mkdir(parents=True, exist_ok=True)
                if isinstance(valor, list) and len(valor) >= 4:
                    filename = {
                        'ancora': calibration_assets_dir() / 'fechar.png',
                        'btn_sim': calibration_assets_dir() / 'aviso_sim.png',
                        'btn_nao': calibration_assets_dir() / 'aviso_nao.png',
                        'btn_pedido': calibration_assets_dir() / 'pedido_usuario.png',
                        'sell_button_sample': calibration_assets_dir() / 'vender_usuario.png',
                        'remover_pedidos_btn_editar': calibration_assets_dir() / 'editar_pedido_usuario.png',
                        'remover_pedidos_btn_cancelar': calibration_assets_dir() / 'cancelar_pedido_usuario.png',
                    }[campo]
                    region = resolve_rect(valor, geometry, data)
                    if region:
                        scr = capture_region(region)
                        scr.save(filename)
                        bot.invalidate_template_cache()
                        self.log(f'>>> Imagem de referência salva: {filename.name}')
            except Exception as e:
                self.log(f'Erro ao salvar imagem de referência ({campo}): {e}')
        try:
            save_settings('offsets.json', data)
        except Exception as e:
            self.log(f'Erro ao salvar offsets.json: {e}')
        self.offsets = data
    def iniciar_calibragem_navegacao(self):
        self.iniciar_calibragem_campo('drag_start', 'click')
        self.show_notification('CALIBRE O PONTO FINAL')
    def iniciar_calibragem_integrada(self):
        return None
    def proximo_passo_nav(self):
        if self.passo_atual < len(self.passos):
            self.calib_instruction.config(text=self.passos[self.passo_atual][1])
        else:
            self.finalizar_calibragem_navegacao()
    def render_canvas(self):
        # ***<module>.AlbionBotGUI.render_canvas: Failure: Different bytecode
        if self.screenshot_original is None:
            pass
        else:
            scale = self.base_scale * self.zoom_level
            resized_img = self.screenshot_original.resize(new_size, Image.Resampling.LANCZOS)
            self.canvas.delete('all')
    def on_mousewheel(self, event):
        old_scale = self.base_scale * self.zoom_level
        mx = self.canvas.canvasx(event.x)
        my = self.canvas.canvasy(event.y)
        if event.delta > 0:
            self.zoom_level *= 1.2
        else:
            self.zoom_level /= 1.2
            self.zoom_level = max(0.5, self.zoom_level)
        new_scale = self.base_scale * self.zoom_level
        new_mx = mx * (new_scale / old_scale)
        new_my = my * (new_scale / old_scale)
        self.canvas.xview_moveto((new_mx - event.x) / (self.screenshot_original.width * new_scale))

    def proximo_passo(self):
        if self.passo_atual < len(self.passos):
            self.calib_instruction.config(text=self.passos[self.passo_atual][1])
        else:
            self.finalizar_calibragem()
    def on_button_press(self, event):
        # ***<module>.AlbionBotGUI.on_button_press: Failure: Different control flow
        self.start_x = self.canvas.canvasx(event.x)
        self.canvas.delete(self.temp_rect) if self.temp_rect else None
        self.temp_rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x + 1, self.start_y + 1, outline='red', width=2)
    def on_move_press(self, event):
        cur_x, cur_y = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self.canvas.coords(self.temp_rect, self.start_x, self.start_y, cur_x, cur_y)
    def on_button_release(self, event):
        # ***<module>.AlbionBotGUI.on_button_release: Failure: Different bytecode
        end_x, end_y = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        key, scale = (self.base_scale * self.zoom_level,) * self.passos[self.passo_atual][0]
        self.offsets_temp[key] = [int(min(self.start_x, end_x) / scale), int(min(self.start_y, end_y) / scale), int(abs(end_x - self.start_x) / scale), int(abs(end_y - self.start_y) / scale)]
        self.passo_atual += 1
        if hasattr(self, 'passos') and len(self.passos) == 4:
            self.proximo_passo_nav()
        else:
            self.proximo_passo()
    def finalizar_calibragem(self):
        messagebox.showinfo('Calibragem', 'Use os botões SET da calibragem v2.')
        self.show_config_tab()
    def finalizar_calibragem_navegacao(self):
        messagebox.showinfo('Calibragem', 'Use os botões SET da calibragem v2.')
        self.show_config_tab()

    def _atualizar_botoes_perfil_compra(self):
        for profile, button in getattr(self, 'purchase_profile_buttons', {}).items():
            selected = profile == getattr(self, 'purchase_profile', PROFILE_CUSTOM)
            button.config(
                bg=COLOR_ACCENT_DIM if selected else COLOR_CARD,
                fg=COLOR_TEXT if selected else COLOR_TEXT_DIM,
            )

    def _mostrar_resultado_perfil_compra(self, settings=None, error=None):
        label = getattr(self, 'purchase_profile_result_lbl', None)
        if label is None:
            return
        if error:
            label.config(text=str(error), fg=COLOR_ERROR)
            return
        if settings is None:
            return
        exposure = (
            f'{settings.exposure_percent:g}% da banca'
            if settings.exposure_percent is not None
            else 'Definida manualmente'
        )
        label.config(
            text=(
                f'Perfil: {PROFILE_LABELS[settings.profile]}\n'
                f'Lucro mínimo por venda: {settings.minimum_profit_percent:g}%\n'
                f'Limite por ordem: {format_silver(settings.order_limit)} prata\n'
                f'Exposição máxima por ordem: {exposure}\n'
                f'Orçamento da execução: '
                f'{format_silver(settings.operational_bank) if settings.operational_bank else "Sem limite total"}'
            ),
            fg=COLOR_TEXT,
        )

    def _atualizar_resultado_personalizado(self):
        if getattr(self, 'purchase_profile', PROFILE_CUSTOM) != PROFILE_CUSTOM:
            return
        if not (
            hasattr(self, 'config_lucro_ent')
            and hasattr(self, 'config_vmax_ent')
            and hasattr(self, 'operational_bank_entry')
        ):
            return
        try:
            settings = resolve_purchase_profile(
                PROFILE_CUSTOM,
                self._ler_banca_operacional(),
                self.config_lucro_ent.get(),
                self.config_vmax_ent.get(),
            )
            self._mostrar_resultado_perfil_compra(settings=settings)
        except ValueError as exc:
            self._mostrar_resultado_perfil_compra(error=exc)

    def _aplicar_configuracao_perfil_compra(self, settings):
        self.purchase_profile = settings.profile
        if hasattr(self, 'config_lucro_ent'):
            self.config_lucro_ent.delete(0, 'end')
            self.config_lucro_ent.insert(0, f'{settings.minimum_profit_percent:g}')
            self.config_lucro_ent.set_editable(settings.profile == PROFILE_CUSTOM)
        if hasattr(self, 'config_vmax_ent'):
            self.config_vmax_ent.delete(0, 'end')
            self.config_vmax_ent.insert(0, str(settings.order_limit))
            self.config_vmax_ent.set_editable(settings.profile == PROFILE_CUSTOM)
        self._atualizar_botoes_perfil_compra()
        self._mostrar_resultado_perfil_compra(settings=settings)
        self.atualizar_resumo_limites()

    def _ler_banca_operacional(self):
        entry = getattr(self, 'operational_bank_entry', None)
        return parse_silver(entry.get() if entry is not None else 0)

    def selecionar_perfil_compra(self, profile):
        try:
            settings = resolve_purchase_profile(
                profile,
                self._ler_banca_operacional(),
                self.config_lucro_ent.get(),
                self.config_vmax_ent.get(),
            )
            self._aplicar_configuracao_perfil_compra(settings)
        except ValueError as exc:
            self._mostrar_resultado_perfil_compra(error=exc)
            messagebox.showerror('Perfil de compra', str(exc))

    def _on_operational_bank_change(self, _event=None):
        self.atualizar_resumo_limites()
        profile = getattr(self, 'purchase_profile', PROFILE_CUSTOM)
        if profile == PROFILE_CUSTOM:
            try:
                settings = resolve_purchase_profile(
                    profile,
                    self._ler_banca_operacional(),
                    self.config_lucro_ent.get(),
                    self.config_vmax_ent.get(),
                )
                self._mostrar_resultado_perfil_compra(settings=settings)
            except ValueError:
                pass
            return
        try:
            settings = resolve_purchase_profile(profile, self._ler_banca_operacional())
            self._aplicar_configuracao_perfil_compra(settings)
        except ValueError as exc:
            self._mostrar_resultado_perfil_compra(error=exc)

    def _format_operational_bank(self, _event=None):
        try:
            value = self._ler_banca_operacional()
            if value < 0:
                raise ValueError('A banca operacional não pode ser negativa.')
            entry = self.operational_bank_entry
            entry.delete(0, 'end')
            entry.insert(0, format_silver(value))
            self._on_operational_bank_change()
        except ValueError as exc:
            self._mostrar_resultado_perfil_compra(error=exc)

    def carregar_ajustes_financeiros(self):
        try:
            data = load_settings('offsets.json')
            settings = settings_from_legacy_config(data)
            if hasattr(self, 'operational_bank_entry'):
                self.operational_bank_entry.delete(0, 'end')
                self.operational_bank_entry.insert(
                    0, format_silver(settings.operational_bank)
                )
            self._aplicar_configuracao_perfil_compra(settings)

            if hasattr(self, 'config_delay_clique_ent'):
                self.config_delay_clique_ent.delete(0, 'end')
                self.config_delay_clique_ent.insert(0, str(data.get('delay_clique', 0.3)))

            if hasattr(self, 'config_delay_pagina_ent'):
                self.config_delay_pagina_ent.delete(0, 'end')
                self.config_delay_pagina_ent.insert(0, str(data.get('delay_pagina', 0.5)))
            self.protected_pause_enabled = bool(
                data.get(bot.PROTECTED_PAUSE_ENABLED_KEY, False)
            )
        except Exception:
            pass

        for attr in ['config_lucro_ent', 'config_vmax_ent', 'config_delay_clique_ent', 'config_delay_pagina_ent']:
            ent = getattr(self, attr, None)
            if ent and hasattr(ent, 'master') and hasattr(ent.master, 'update_bg'):
                ent.master.update_bg()

    def alternar_pausa_protegida(self, enabled):
        self.protected_pause_enabled = bool(enabled)
        checkbox = getattr(self, 'protected_pause_checkbox', None)
        if checkbox is not None and hasattr(checkbox, 'set_active'):
            checkbox.set_active(self.protected_pause_enabled)
        try:
            data = load_settings('offsets.json')
            data[bot.PROTECTED_PAUSE_ENABLED_KEY] = self.protected_pause_enabled
            save_settings('offsets.json', data)
            self.offsets = data
            estado = 'ATIVADA' if self.protected_pause_enabled else 'DESATIVADA'
            self.log(f'>>> Pausa protegida {estado}.')
        except Exception as exc:
            self.log(f'Erro ao salvar Pausa protegida: {exc}')

    def _criar_toggle_media_semanal(self, parent, bg_color=None):
        """Cria (ou registra) o botão selecionável "Exigir média semanal".

        Aparece do lado dos botões de iniciar em cada modo que cria pedido de
        compra (Compra, Ciclo, Compra Programada); todos ligam/desligam o
        mesmo ajuste compartilhado (VERIFICAR_MEDIA_SEMANAL_KEY).
        """
        if not hasattr(self, 'verificar_media_semanal'):
            self.verificar_media_semanal = bool(
                getattr(self, 'offsets', {}).get(bot.VERIFICAR_MEDIA_SEMANAL_KEY, False)
            )
        checkbox = self.create_puffy_checkbox(
            parent,
            'Exigir média semanal (não compra item parado)',
            self.verificar_media_semanal,
            self.alternar_verificar_media_semanal,
            bg_color=bg_color,
        )
        self._media_semanal_checkboxes = getattr(self, '_media_semanal_checkboxes', [])
        self._media_semanal_checkboxes.append(checkbox)
        return checkbox

    def alternar_verificar_media_semanal(self, enabled):
        self.verificar_media_semanal = bool(enabled)
        for checkbox in getattr(self, '_media_semanal_checkboxes', []):
            if hasattr(checkbox, 'set_active'):
                checkbox.set_active(self.verificar_media_semanal)
        try:
            data = load_settings('offsets.json')
            data[bot.VERIFICAR_MEDIA_SEMANAL_KEY] = self.verificar_media_semanal
            save_settings('offsets.json', data)
            self.offsets = data
            estado = 'ATIVADA' if self.verificar_media_semanal else 'DESATIVADA'
            self.log(f'>>> Verificação de média semanal (liquidez) {estado}.')
        except Exception as exc:
            self.log(f'Erro ao salvar verificação de média semanal: {exc}')

    def atualizar_resumo_limites(self):
        label = getattr(self, 'financial_rule_summary', None)
        if label is None:
            return
        try:
            percentual = max(0.0, float(self.config_lucro_ent.get()))
            teto_prata = max(0, int(float(self.config_vmax_ent.get())))
            venda_exemplo = 100_000
            limite_percentual = int(venda_exemplo * (1 - percentual / 100))
            limite_usado = min(limite_percentual, teto_prata)
            vencedor = 'REGRA 1' if limite_percentual <= teto_prata else 'REGRA 2'
            texto = (
                f'EXEMPLO: VENDA {venda_exemplo:,}\n'
                f'LUCRO {percentual:g}% = COMPRA ATÉ {limite_percentual:,}  |  TETO = {teto_prata:,}\n'
                f'RESULTADO: ATÉ {limite_usado:,} ({vencedor})'
            ).replace(',', '.')
        except Exception:
            texto = 'Preencha os dois limites para ver um exemplo.'
        try:
            label.config(text=texto)
        except Exception:
            pass

    def mostrar_ajuda_custo_maximo(self):
        existing = getattr(self, '_cost_help_window', None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.update_idletasks()
                if existing.winfo_width() > 50 and existing.winfo_height() > 50:
                    existing.deiconify()
                    existing.lift()
                    return
                existing.destroy()
        except Exception:
            pass

        try:
            percentual = float(self.config_lucro_ent.get())
        except (TypeError, ValueError):
            percentual = 28.0
        try:
            teto_prata = int(float(self.config_vmax_ent.get()))
        except (TypeError, ValueError):
            teto_prata = 50_000
        exemplo_venda = 100_000
        limite_percentual = int(exemplo_venda * (1 - percentual / 100))
        limite_usado = min(limite_percentual, teto_prata)
        venda_alta = 1_000_000
        limite_percentual_alto = int(venda_alta * (1 - percentual / 100))
        limite_alto_usado = min(limite_percentual_alto, teto_prata)

        try:
            modal = tk.Toplevel(self.root)
            self._cost_help_window = modal
            modal.withdraw()
            modal.overrideredirect(True)
            modal.attributes('-topmost', True)
            modal.configure(bg=COLOR_ACCENT_DIM)

            def close_help():
                try:
                    modal.destroy()
                finally:
                    self._cost_help_window = None

            panel = tk.Frame(modal, bg=COLOR_BG, highlightthickness=1,
                             highlightbackground=COLOR_BORDER)
            panel.pack(fill='both', expand=True, padx=2, pady=2)

            header = tk.Frame(panel, bg=COLOR_NAV, height=42)
            header.pack(fill='x')
            header.pack_propagate(False)
            tk.Label(header, text='COMO FUNCIONA?', bg=COLOR_NAV, fg=COLOR_ACCENT,
                     font=('Segoe UI Semibold', 10)).pack(side='left', padx=15)
            close_btn = tk.Button(
                header, text='×', command=close_help, bg=COLOR_NAV,
                fg=COLOR_TEXT_DIM, activebackground=UI_COLORS['surface_hover'], activeforeground=COLOR_TEXT,
                relief='flat', bd=0, cursor='hand2', font=('Segoe UI Semibold', 13),
            )
            close_btn.pack(side='right', padx=10)

            body = tk.Frame(panel, bg=COLOR_BG, padx=18, pady=14)
            body.pack(fill='both', expand=True)
            tk.Label(
                body,
                text='A compra precisa passar por DUAS regras:',
                bg=COLOR_BG,
                fg=COLOR_TEXT,
                font=('Segoe UI Semibold', 10),
            ).pack(anchor='w')
            tk.Label(
                body,
                text=(
                    f'1. Lucro mínimo de {percentual:g}% sobre a venda.\n'
                    f'2. {teto_prata:,} prata: nenhuma ordem pode passar disso.\n\n'
                    'O bot calcula os dois e sempre escolhe o MENOR.'
                ).replace(',', '.'),
                bg=COLOR_BG,
                fg=COLOR_TEXT,
                justify='left',
                wraplength=286,
                font=('Segoe UI', 9),
            ).pack(anchor='w', pady=(7, 10))

            rule = tk.Frame(body, bg=UI_COLORS['surface_raised'], padx=11, pady=9,
                            highlightthickness=1, highlightbackground=COLOR_ACCENT_DIM)
            rule.pack(fill='x')
            tk.Label(
                rule,
                text=(
                    f'VENDA: {exemplo_venda:,}\n'
                    f'LUCRO {percentual:g}% = COMPRA ATÉ {limite_percentual:,}\n'
                    f'LIMITE/ORDEM = {teto_prata:,}\n'
                    f'RESULTADO: COMPRA ATÉ {limite_usado:,}'
                ).replace(',', '.'),
                bg=UI_COLORS['surface_raised'],
                fg=COLOR_SUCCESS,
                font=('Consolas', 8, 'bold'),
            ).pack()

            tk.Label(
                body,
                text=(
                    f'Outro exemplo: venda de {venda_alta:,}\n'
                    f'Lucro mínimo de {percentual:g}% permitiria comprar até {limite_percentual_alto:,}, mas o limite por ordem '
                    f'limita a compra a {limite_alto_usado:,}.\n\n'
                    'Se uma das duas regras bloquear, o bot pula o item.'
                ).replace(',', '.'),
                bg=COLOR_BG,
                fg=COLOR_TEXT_DIM,
                justify='left',
                wraplength=286,
                font=('Segoe UI', 8),
            ).pack(anchor='w', pady=(11, 9))

            understood = self.create_3d_button(
                body, 'FECHAR AJUDA', type_color='green', command=close_help
            )
            understood.pack(fill='x')
            modal.bind('<Escape>', lambda _event: close_help())
            modal.protocol('WM_DELETE_WINDOW', close_help)

            width, height = 350, 390
            self.root.update_idletasks()
            modal.update_idletasks()
            root_width = max(self.root.winfo_width(), width)
            root_height = max(self.root.winfo_height(), height)
            x = self.root.winfo_rootx() + (root_width - width) // 2
            y = self.root.winfo_rooty() + (root_height - height) // 2
            modal.geometry(f'{width}x{height}{x:+d}{y:+d}')
            modal.deiconify()
            modal.lift()
            modal.focus_set()
            modal.update_idletasks()
            if modal.winfo_width() <= 50 or modal.winfo_height() <= 50:
                raise RuntimeError('A janela de ajuda não ficou visível.')
        except Exception as exc:
            try:
                if getattr(self, '_cost_help_window', None) is not None:
                    self._cost_help_window.destroy()
            except Exception:
                pass
            self._cost_help_window = None
            messagebox.showinfo(
                'Como funciona o lucro mínimo',
                (
                    f'A compra precisa passar por duas regras:\n\n'
                    f'1. Preservar ao menos {percentual:g}% de lucro bruto sobre a venda.\n'
                    f'2. Nunca passar de {teto_prata:,} prata.\n\n'
                    'O bot sempre usa o menor dos dois valores.'
                ).replace(',', '.'),
                parent=self.root,
            )
            try:
                self.log(f'>>> Ajuda financeira abriu em modo compatível: {exc}')
            except Exception:
                pass

    def salvar_ajustes_financeiros(self, notificar=True):
        try:
            data = load_settings('offsets.json')
            settings = resolve_purchase_profile(
                getattr(self, 'purchase_profile', PROFILE_CUSTOM),
                self._ler_banca_operacional(),
                self.config_lucro_ent.get(),
                self.config_vmax_ent.get(),
            )
            data['banca_operacional'] = settings.operational_bank
            data['perfil_compra'] = settings.profile
            data['financial_rule_version'] = FINANCIAL_RULE_VERSION
            data['lucro_minimo_venda'] = settings.minimum_profit_percent
            # Mantém o limite equivalente para versões anteriores do motor.
            data['lucro'] = 100.0 - settings.minimum_profit_percent
            data['valor_max'] = settings.order_limit
            self._aplicar_configuracao_perfil_compra(settings)

            if hasattr(self, 'config_delay_clique_ent'):
                data['delay_clique'] = max(0.05, float(self.config_delay_clique_ent.get()))

            if hasattr(self, 'config_delay_pagina_ent'):
                data['delay_pagina'] = max(0.1, float(self.config_delay_pagina_ent.get()))

            data[bot.PROTECTED_PAUSE_ENABLED_KEY] = bool(
                getattr(self, 'protected_pause_enabled', False)
            )

            save_settings('offsets.json', data)

            self.offsets = data
            if notificar:
                self.show_notification('CONFIGURAÇÕES SALVAS')
            self.log('>>> Ajustes financeiros e delays salvos em offsets.json')
            return True
        except Exception as e:
            self.log(f'Valores inválidos: {e}')
            if notificar:
                messagebox.showerror('Ajustes financeiros', str(e))
            return False
    def carregar_offsets(self):
        data = load_settings('offsets.json')
        if not is_v2(data) and any(is_spatial_key(key) for key in data):
            data = strip_spatial_settings(data)
            save_settings('offsets.json', data)
        return data
    def carregar_dados_iniciais(self):
        self.log('>>> MKT carregado.')
        self.log('>>> Pronto para operar.')
    def focar_jogo(self):
        win = get_albion_window()
        if win:
            try:
                win.activate()
            except Exception:
                pass

    def minimizar_para_execucao(self):
        """Recolhe o painel antes da automação e devolve o foco ao Albion."""
        if hasattr(self, 'log_window'):
            self.log_window.hide()
        if not getattr(self, 'minimized', False):
            self.toggle_minimize()
        root = getattr(self, 'root', None)
        if root is not None:
            # Faz o Windows processar os withdraws antes de o bot receber RUN.
            # Sem isso, a primeira coordenada pode ser executada sobre uma
            # janela que visualmente ainda esta terminando de desaparecer.
            try:
                root.update_idletasks()
                root.update()
            except tk.TclError:
                pass
        self.focar_jogo()
        if root is not None:
            time.sleep(AUTOMATION_START_GUARD_SECONDS)
    def validar_calibragem_para_modo(self, mode='buy'):
        win = get_albion_window()
        if not win or win.isMinimized:
            messagebox.showerror('MKT', 'Abra e restaure a janela do Albion antes de iniciar.')
            return False
        try:
            geometry = get_client_geometry(win)
            data = load_settings('offsets.json')
            valid, reason = validate_calibration(data, geometry, mode=mode)
            if valid and mode in {'buy', 'cycle'} and not os.path.exists(calibration_template_path('pedido_usuario.png')):
                valid = False
                reason = 'Calibre AMOSTRA BOTÃO PEDIDO para este computador.'
            if valid and mode in {'buy', 'cycle'} and not os.path.exists(calibration_template_path('aviso_nao.png')):
                valid = False
                reason = 'Calibre BOTÃO NÃO (Cancelar) para este computador.'
            if valid and mode == 'remover_pedidos' and not os.path.exists(calibration_template_path('editar_pedido_usuario.png')):
                valid = False
                reason = 'Calibre a AMOSTRA DO BOTÃO EDITAR para este computador.'
            if valid and mode == 'remover_pedidos' and not os.path.exists(calibration_template_path('cancelar_pedido_usuario.png')):
                valid = False
                reason = 'Calibre a AMOSTRA DO X DE CANCELAR para este computador.'
        except Exception as exc:
            valid, reason = False, str(exc)
        if not valid:
            self.log(f'[BLOQUEADO] {reason}')
            messagebox.showerror('Calibragem necessária', reason)
            return False
        self.offsets = data
        return True
    def iniciar_processo_background(self):
        # ***<module>.AlbionBotGUI.iniciar_processo_background: Failure detected at line number 1159 and instruction offset 20: Different bytecode
        self.log('>>> Pré-carregando motores em background...')
        os.path.exists(CONTROL_FILE) and os.remove(CONTROL_FILE)
        threading.Thread(target=bot.main, daemon=True).start()
    def toggle_bot(self):
        # ***<module>.AlbionBotGUI.toggle_bot: Failure detected at line number 1168 and instruction offset 58: Different bytecode
        if not self.modulo_liberado(MODULE_PURCHASE, 'o Bot de Compra'):
            return
        if not self.running:
            if (
                self.sell_running or self.cycle_running
                or getattr(self, 'fechando_ordens', False)
                or getattr(self, 'shopping_running', False)
                or getattr(self, 'remover_pedidos_running', False)
            ):
                messagebox.showwarning('MKT', 'Pare a outra automação antes de iniciar a compra.')
                return
            if not self.salvar_ajustes_financeiros(notificar=False):
                messagebox.showerror(
                    'Ajustes financeiros',
                    'Corrija os limites financeiros antes de iniciar o bot.',
                )
                return
            if not self.validar_calibragem_para_modo('buy'):
                return
            self.minimizar_para_execucao()
            self.running = True
            self.buy_paused = False
            self.atualizar_botao_inicial()
            self.card_status.config(text='ATIVO', fg=COLOR_SUCCESS)
            with open(CONTROL_FILE, 'w') as f:
                json.dump(build_control_state(True, 'buy', False), f)
        else:
            self.running = False
            self.buy_paused = False
            self.atualizar_botao_inicial()
            self.card_status.config(text='PARADO', fg=COLOR_TEXT_DIM)
            with open(CONTROL_FILE, 'w') as f:
                json.dump(build_control_state(False, 'buy', False), f)
            self.log('>>> Bot em Standby.')
    def pausar_bot(self):
        """Pausa a varredura de compra preservando a posição para continuar depois."""
        if not self.running:
            return
        self.running = False
        self.buy_paused = True
        self.atualizar_botao_inicial()
        self.card_status.config(text='EM PAUSA', fg=COLOR_ACCENT)
        with open(CONTROL_FILE, 'w', encoding='utf-8') as f:
            json.dump(build_control_state(False, 'buy', False, preserve_position=True), f)
        self.log('>>> Bot PAUSADO; a posição foi salva para continuar depois.')

    def continuar_bot(self):
        """Retoma a varredura de compra exatamente de onde foi pausada."""
        if not self.buy_paused:
            return
        self.running = True
        self.buy_paused = False
        self.atualizar_botao_inicial()
        self.card_status.config(text='ATIVO', fg=COLOR_SUCCESS)
        with open(CONTROL_FILE, 'w', encoding='utf-8') as f:
            json.dump(build_control_state(True, 'buy', False, preserve_position=True), f)
        self.log('>>> Bot retomado de onde parou.')

    def pause_bot(self):
        """Envia sempre uma parada segura, mesmo se o estado visual estiver dessincronizado."""
        estava_ativo = self.automacao_em_execucao()
        self.running = False
        self.buy_paused = False
        self.sell_running = False
        self.cycle_running = False
        self.fechando_ordens = False
        self.shopping_running = False
        self.shopping_paused = False
        try:
            self.atualizar_botao_inicial()
            self.atualizar_botao_venda()
            self.atualizar_botao_ciclo()
            self.atualizar_botao_shopping()
            self.card_status.config(text='PARADO', fg=COLOR_TEXT_DIM)
        except Exception:
            pass
        try:
            self.shopping_module_status_lbl.config(text='PARADA', fg=COLOR_TEXT_DIM)
        except Exception:
            pass
        try:
            self.edit_status_lbl.config(text='STATUS: PAUSADO', fg=COLOR_TEXT_DIM)
        except Exception:
            pass
        try:
            self.sell_module_status_lbl.config(text='PAUSADO', fg=COLOR_TEXT_DIM)
        except Exception:
            pass
        try:
            self.cycle_module_status_lbl.config(text='PAUSADO', fg=COLOR_TEXT_DIM)
        except Exception:
            pass
        try:
            self._set_cycle_stage(None)
        except Exception:
            pass
        try:
            with open(CONTROL_FILE, 'w', encoding='utf-8') as f:
                json.dump(build_control_state(False, 'buy', False), f)
        except Exception as exc:
            self.log(f'[ERRO] Não foi possível enviar a parada ao bot: {exc}')
            return
        if estava_ativo:
            self.log('>>> Bot PAUSADO pelo comando de parada (F8/Insert).')
    def animate_fechamento_gif(self):
        if not getattr(self, 'fechando_ordens', False):
            try:
                self.edit_gif_lbl.config(image='')
            except:
                pass
            return None
        else:
            if hasattr(self, 'fechamento_frames') and self.fechamento_frames:
                    try:
                        self.edit_gif_lbl.config(image=self.fechamento_frames[self.fechamento_frame_idx])
                        self.fechamento_frame_idx = (self.fechamento_frame_idx + 1) % len(self.fechamento_frames)
                    except:
                        pass
                    self.root.after(30, self.animate_fechamento_gif)
    def toggle_fechamento(self):
        # ***<module>.AlbionBotGUI.toggle_fechamento: Failure detected at line number 1218 and instruction offset 124: Different bytecode
        self.fechando_ordens = getattr(self, 'fechando_ordens', False)
        if not self.fechando_ordens:
            if self.running or self.sell_running or self.cycle_running or getattr(self, 'remover_pedidos_running', False):
                messagebox.showwarning('MKT', 'Pare a outra automação antes de fechar ordens.')
                return
            if not self.validar_calibragem_para_modo('close'):
                return
            self.minimizar_para_execucao()
            self.fechando_ordens = True
            self.running = False
            self.atualizar_botao_inicial()
            self.card_status.config(text='PARADO', fg=COLOR_TEXT_DIM)
            self.edit_status_lbl.config(text='STATUS: FECHANDO ORDENS...', fg=COLOR_SUCCESS)
            if hasattr(self, 'fechamento_frames') and self.fechamento_frames:
                    self.fechamento_frame_idx = 0
                    self.animate_fechamento_gif()
            with open(CONTROL_FILE, 'w') as f:
                json.dump(build_control_state(True, 'close', False), f)
            self.log('>>> Iniciado FECHAMENTO DE ORDENS.')
        else:
            self.fechando_ordens = False
            self.edit_status_lbl.config(text='STATUS: PAUSADO', fg=COLOR_TEXT_DIM)
            try:
                self.edit_gif_lbl.config(image='')
            except:
                pass
            with open(CONTROL_FILE, 'w') as f:
                json.dump(build_control_state(False, 'buy', False), f)
            self.log('>>> Fechamento de ordens interrompido.')
    def resetar_contadores(self):
        """Zera ordens e lucro estimado exibidos no topo da aba BOT."""
        self.total_orders = 0
        self.total_profit = 0
        self.total_gasto = 0
        self.total_taxa = 0
        self.cycle_orders_completed = 0
        self.cycle_items_sold = 0
        self._update_cycle_counters()
        try:
            self.card_orders.config(text='0')
            self.card_profit.config(text='0')
        except:
            pass
        self.log('>>> Contadores ZERADOS (Ordens e Lucro Estimado).')
    def on_tree_resize(self, event):
        """Detecta o redimensionamento das colunas pelo usuário e salva as larguras no json."""
        if self.tree.identify_region(event.x, event.y) == 'separator' or True:
            pass
        self.root.after(100, self._save_tree_widths)
    def _save_tree_widths(self):
        try:
            w_item = self.tree.column('Item', width=None)
            w_v = self.tree.column('V', width=None)
            w_c = self.tree.column('C', width=None)
            w_roi = self.tree.column('ROI', width=None)
            self.salvar_calibração('col_w_item', w_item)
            self.salvar_calibração('col_w_v', w_v)
            self.salvar_calibração('col_w_c', w_c)
            self.salvar_calibração('col_w_roi', w_roi)
            self.log('>>> Largura das colunas salvas.')
        except Exception as e:
            return None
    def atualizar_contadores_reais(self):
        try:
            self.card_orders.config(text=str(self.total_orders))
            lucro_fmt = f'{int(self.total_profit):,}'.replace(',', '.')
            self.card_profit.config(text=lucro_fmt)
        except:
            return None
    def update_log_loop(self):
        # ***<module>.AlbionBotGUI.update_log_loop: Failure detected at line number 1269 and instruction offset 30: Different bytecode
        if os.path.exists(OPPORTUNITIES_FILE):
            try:
                with open(OPPORTUNITIES_FILE, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    data = list(reader)
                if len(data) > 1:
                    self.tree.delete(*self.tree.get_children())
                    rows = data[1:]
                    last_rows = rows[(-20):]
                    total_roi = 0.0
                    for row in rows:
                        try:
                            roi_val = float(row[(-1)].replace('x', '').replace('%', '').replace(',', '.'))
                            total_roi += roi_val
                        except:
                            pass
                    for row in reversed(last_rows):
                        if len(row) >= 4:
                            self.tree.insert('', 'end', values=(row[0], row[1], row[2], row[(-1)]), tags=('opp',))
                    self.card_opps.config(text=str(len(rows)))
                    self.card_total.config(text=f'{total_roi:.2f}x')
            except:
                pass
        self.root.after(3000, self.update_log_loop)
    def _save_cached_item_icon(self, image, path):
        os.makedirs(ITEM_ICON_CACHE_DIR, exist_ok=True)
        temp_path = f'{path}.{os.getpid()}.tmp'
        image.convert('RGBA').save(temp_path, format='PNG', optimize=True)
        os.replace(temp_path, path)

    def _item_icon_cache_worker(self):
        """Grava capturas e busca renders sem bloquear cliques ou a interface."""
        while True:
            item_name, item_icon = self._item_icon_cache_queue.get()
            try:
                capture_path, render_path = item_icon_cache_paths(item_name)
                if isinstance(item_icon, Image.Image) and not os.path.exists(capture_path):
                    self._save_cached_item_icon(item_icon, capture_path)

                cache_key = os.path.basename(render_path)
                _bundled_capture, bundled_render = bundled_item_icon_cache_paths(item_name)
                if (
                    cache_key in self._item_icon_fetch_attempted
                    or os.path.exists(render_path)
                    or os.path.exists(bundled_render)
                ):
                    continue
                self._item_icon_fetch_attempted.add(cache_key)
                response = requests.get(
                    build_item_render_url(item_name),
                    timeout=(3.0, 8.0),
                    headers={'User-Agent': 'MKT-Item-Icon-Cache/1.0'},
                )
                content_type = response.headers.get('content-type', '').lower()
                if response.status_code != 200 or 'image/png' not in content_type:
                    continue
                if not 100 <= len(response.content) <= 4_000_000:
                    continue
                rendered = Image.open(io.BytesIO(response.content)).convert('RGBA')
                if rendered.width < 16 or rendered.height < 16:
                    continue
                self._save_cached_item_icon(rendered, render_path)
            except Exception:
                # A captura local continua disponível quando a internet falha.
                pass
            finally:
                self._item_icon_cache_queue.task_done()

    def _load_cached_item_icon(self, item_name):
        capture_path, render_path = item_icon_cache_paths(item_name)
        bundled_capture, bundled_render = bundled_item_icon_cache_paths(item_name)
        for path in (render_path, bundled_render, capture_path, bundled_capture):
            try:
                if os.path.exists(path):
                    with Image.open(path) as cached:
                        return cached.convert('RGBA').copy()
            except Exception:
                pass
        return None

    def _load_official_item_icon(self, item_name):
        """LÃª somente o PNG oficial, sem confundir captura com render."""
        _capture_path, render_path = item_icon_cache_paths(item_name)
        _bundled_capture, bundled_render = bundled_item_icon_cache_paths(item_name)
        for path in (render_path, bundled_render):
            try:
                if os.path.exists(path):
                    with Image.open(path) as cached:
                        return cached.convert('RGBA').copy()
            except Exception:
                pass
        return None

    def prefetch_item_icon(self, item_name, item_icon=None):
        """Agenda o PNG oficial antes da confirmaÃ§Ã£o, sem esperar pela rede."""
        cache_queue = getattr(self, '_item_icon_cache_queue', None)
        if cache_queue is None:
            return
        try:
            icon_copy = item_icon.copy() if isinstance(item_icon, Image.Image) else None
            cache_queue.put_nowait((item_name, icon_copy))
        except Exception:
            pass

    def enqueue_notification(self, item_name, profit_val, item_icon=None):
        """Enfileira uma única notificação e agenda o cache fora do motor."""
        icon_copy = item_icon.copy() if isinstance(item_icon, Image.Image) else None
        self.notif_queue.append((item_name, profit_val, icon_copy))
        self.prefetch_item_icon(item_name, icon_copy)
    def process_notif_queue(self):
        """Processa a fila de notificações se não houver nenhuma ativa no momento."""
        if getattr(self, 'active_notification', None) is not None:
            return None
        else:
            if not self.notif_queue:
                return None
            else:
                payload = self.notif_queue.pop(0)
                if len(payload) >= 3:
                    item_name, profit_val, item_icon = payload[:3]
                else:
                    item_name, profit_val = payload
                    item_icon = None
                self.show_premium_buy_notification(item_name, profit_val, item_icon)
    def show_premium_buy_notification(self, item_name, profit_val, item_icon=None):
        # irreducible cflow, using cdg fallback
        # ***<module>.AlbionBotGUI.show_premium_buy_notification: Failure: Compilation Error
        w, h = (self.width, 84)
        scale = 3
        w_s, h_s = (w * scale, h * scale)
        im = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)
        r_s = 18 * scale
        draw_rounded_rectangle(draw, [0, 0, w_s, h_s], r_s, (45, 25, 15, 120))
        border_thickness = int(1.5 * scale)
        border_draw = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(border_draw)
        draw_rounded_rectangle(b_draw, [0, 0, w_s, h_s], r_s, (191, 132, 21, 200))
        draw_rounded_rectangle(b_draw, [border_thickness, border_thickness, w_s - border_thickness, h_s - border_thickness], r_s - border_thickness, (0, 0, 0, 0))
        im = Image.alpha_composite(im, border_draw)
        draw = ImageDraw.Draw(im)
        inner_thickness = int(1.0 * scale)
        inner_draw = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
        idw = ImageDraw.Draw(inner_draw)
        draw_rounded_rectangle(idw, [border_thickness, border_thickness, w_s - border_thickness, h_s - border_thickness], r_s - border_thickness, (255, 255, 255, 80))
        draw_rounded_rectangle(idw, [border_thickness + inner_thickness, border_thickness + inner_thickness, w_s - border_thickness - inner_thickness, h_s - border_thickness - inner_thickness], r_s - border_thickness - inner_thickness, (0, 0, 0, 0))
        im = Image.alpha_composite(im, inner_draw)
        draw = ImageDraw.Draw(im)
        # O PNG oficial do cache tem prioridade; o recorte do jogo Ã© o fallback.
        official_icon = self._load_official_item_icon(item_name)
        is_official_icon = isinstance(official_icon, Image.Image)
        if is_official_icon:
            display_icon = official_icon
            icon_size = 60
        else:
            cached_icon = self._load_cached_item_icon(item_name)
            display_icon = cached_icon if isinstance(cached_icon, Image.Image) else item_icon
            icon_size = 48
        prepared_icon = prepare_notification_item_icon(display_icon, icon_size * scale)
        if prepared_icon is not None:
            if not is_official_icon:
                icon_panel = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
                icon_draw = ImageDraw.Draw(icon_panel)
                draw_rounded_rectangle(
                    icon_draw,
                    [8 * scale, 8 * scale, 76 * scale, 76 * scale],
                    13 * scale,
                    (255, 255, 255, 34),
                )
                im = Image.alpha_composite(im, icon_panel)
            mask = Image.new('L', prepared_icon.size, 0)
            mask_draw = ImageDraw.Draw(mask)
            draw_rounded_rectangle(
                mask_draw,
                [0, 0, prepared_icon.width - 1, prepared_icon.height - 1],
                10 * scale,
                255,
            )
            prepared_icon.putalpha(ImageChops.multiply(prepared_icon.getchannel('A'), mask))
            icon_x = (42 - icon_size // 2) * scale
            icon_y = (42 - icon_size // 2) * scale
            im.alpha_composite(prepared_icon, (icon_x, icon_y))
        else:
            # Compatibilidade: somente itens sem captura/cache usam o sÃ­mbolo genÃ©rico.
            cx, cy = (42 * scale, 42 * scale)
            cr = 24 * scale
            glass_circle = Image.new('RGBA', (w_s, h_s), (0, 0, 0, 0))
            gc_draw = ImageDraw.Draw(glass_circle)
            gc_draw.ellipse(
                [cx - cr, cy - cr, cx + cr, cy + cr],
                fill=(255, 255, 255, 30),
                outline=(255, 255, 255, 75),
                width=max(1, int(scale)),
            )
            s_len = 10 * scale
            s_width = int(2.0 * scale)
            gc_draw.line(
                [cx - s_len, cy - s_len, cx + s_len, cy + s_len],
                fill=(255, 255, 255, 255),
                width=s_width,
            )
            gc_draw.line(
                [cx + s_len, cy - s_len, cx - s_len, cy + s_len],
                fill=(255, 255, 255, 255),
                width=s_width,
            )
            im = Image.alpha_composite(im, glass_circle)
        draw = ImageDraw.Draw(im)
        try:
            font_name = ImageFont.truetype('ariblk.ttf', int(8 * scale))
        except Exception:
            font_name = ImageFont.load_default()

        try:
            font_profit = ImageFont.truetype('ariblk.ttf', int(9 * scale))
        except Exception:
            font_profit = ImageFont.load_default()

        tx = 86 * scale
        ty_name = 24 * scale
        ty_profit = 47 * scale
        profit_str = f'+ {int(profit_val):,}'.replace(',', '.')
        draw.text((tx, ty_name), item_name.upper(), font=font_name, fill=(255, 255, 255, 255))
        draw.text((tx, ty_profit), profit_str, font=font_profit, fill=(255, 199, 53, 255))
        bg_im = Image.new('RGBA', (w_s, h_s), (1, 1, 1, 255))
        bg_im.alpha_composite(im)
        resized = bg_im.resize((w, h), Image.Resampling.LANCZOS)
        notif = tk.Toplevel(self.root)
        self.active_notification = notif
        notif.overrideredirect(True)
        notif.attributes('-disabled', True)
        notif.attributes('-transparentcolor', '#010101')
        notif.configure(bg='#010101')
        aplicar_efeito_blur_janela(notif, 0.72)
        self.root.update_idletasks()
        rx = self.root.winfo_rootx()
        ry = self.root.winfo_rooty()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        nx = rx
        ny = ry + rh + 10
        if ny + h > screen_h - 40:
            ny = screen_h - h - 45
        if nx < 10:
            nx = 10
        elif nx + w > screen_w - 10:
            nx = screen_w - w - 10
        canvas = tk.Canvas(notif, width=w, height=h, bg='#010101', highlightthickness=0)
        canvas.pack()
        notif.img = ImageTk.PhotoImage(resized)
        canvas.create_image(0, 0, image=notif.img, anchor='nw')
        notif.lift()
        notif.attributes('-topmost', True)
        notif.geometry(f'{w}x{h}+{nx}+{ny + 25}')
        notif.update()
        steps = 10
        def slide_in_step(step):
            if not notif.winfo_exists():
                return
            current_y = ny + 25 - int(step / steps * 25)
            notif.geometry(f'{w}x{h}+{nx}+{current_y}')
            notif.lift()
            notif.attributes('-topmost', True)
            if step < steps:
                notif.after(15, lambda: slide_in_step(step + 1))
            else:
                notif.after(3000, lambda: slide_out_step(1))

        def slide_out_step(step):
            if not notif.winfo_exists():
                return
            current_y = ny + int(step / steps * 25)
            notif.geometry(f'{w}x{h}+{nx}+{current_y}')
            if step < steps:
                notif.after(15, lambda: slide_out_step(step + 1))
            else:
                try:
                    notif.destroy()
                except Exception:
                    pass
                if getattr(self, 'active_notification', None) == notif:
                    self.active_notification = None
                self.root.after(100, self.process_notif_queue)

        slide_in_step(1)
if __name__ == '__main__':
    multiprocessing.freeze_support()
    if '--diagnose-ocr' in sys.argv:
        import traceback
        diagnostic_path = os.path.join(_BASE_DIR, 'diagnostico_ocr.txt')
        try:
            started_at = time.time()
            reader = bot.get_reader()
            with open(diagnostic_path, 'w', encoding='utf-8') as diagnostic:
                diagnostic.write(f'OK\nreader={type(reader).__name__}\nseconds={time.time() - started_at:.2f}\n')
            raise SystemExit(0)
        except SystemExit:
            raise
        except Exception as exc:
            with open(diagnostic_path, 'w', encoding='utf-8') as diagnostic:
                diagnostic.write(f'ERROR\n{type(exc).__name__}: {exc}\n{traceback.format_exc()}')
            raise SystemExit(2)
    stop_automations()
    try:
        import shutil
        import sys
        if hasattr(sys, '_MEIPASS'):
            internal_assets = os.path.join(sys._MEIPASS, 'assets')
            if os.path.exists(internal_assets) and not os.path.exists('assets'):
                shutil.copytree(internal_assets, 'assets')
        else:
            if not os.path.exists('assets'):
                os.makedirs('assets')
    except Exception:
        os.makedirs('assets', exist_ok=True)

    try:
        root = tk.Tk()
        root.withdraw()
        try:
            icon_path = 'assets/icon.ico'
            if hasattr(sys, '_MEIPASS'):
                icon_path = os.path.join(sys._MEIPASS, 'assets', 'icon.ico')
            if os.path.exists(icon_path):
                root.wm_iconbitmap(icon_path)
        except Exception:
            pass

        key_info = {}
        _albion_app = None
        _preset_setup = None

        def proceed_to_app():
            def open_main_window():
                global _albion_app, _preset_setup
                _preset_setup = None
                _albion_app = AlbionBotGUI(root, key_info=key_info)
                root.deiconify()
                _albion_app.update_scroll_region()

            def continue_after_release_notes():
                global _preset_setup

                existing_ready = False
                albion = get_albion_window()
                if albion and not albion.isMinimized:
                    try:
                        geometry = get_client_geometry(albion)
                        settings = load_settings('offsets.json')
                        existing_ready, _reason = validate_calibration(
                            settings, geometry, mode='buy'
                        )
                        existing_ready = bool(
                            existing_ready
                            and os.path.exists(calibration_template_path('pedido_usuario.png'))
                            and os.path.exists(calibration_template_path('aviso_nao.png'))
                        )
                    except Exception:
                        existing_ready = False

                if existing_ready:
                    open_main_window()
                    return

                _preset_setup = PresetSetupWindow(
                    root,
                    presets_dir=os.path.join(_BASE_DIR, 'presets'),
                    asset_root=_BASE_DIR,
                    settings_path=OFFSETS_FILE,
                    find_albion_window=get_albion_window,
                    on_complete=open_main_window,
                )

            start_startup_update_check(
                root,
                lambda: show_current_release_notes(root, continue_after_release_notes),
            )

        splash = SplashScreen(root, on_finish=proceed_to_app)
        root.wait_window(splash.root)
        root.mainloop()
    except Exception as e:
        import traceback
        error_msg = f'Erro fatal ao iniciar MKT:\n\n{str(e)}\n\n{traceback.format_exc()}'
        print(error_msg)
        messagebox.showerror('Erro de Inicialização', error_msg)
