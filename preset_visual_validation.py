"""Validacao visual passiva de presets, sem qualquer clique de automacao."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import ImageStat

import bot
from calibration_presets import PresetError, merge_preset_settings, validate_preset_document
from coordinate_system import capture_region, get_client_geometry, resolve_rect


@dataclass(frozen=True)
class VisualEvidence:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VisualValidationResult:
    passed: bool
    summary: str
    evidence: tuple[VisualEvidence, ...]


def _expanded_region(region, geometry, pad_x: int, pad_y: int):
    left, top, width, height = region
    x1 = max(geometry.left, left - pad_x)
    y1 = max(geometry.top, top - pad_y)
    x2 = min(geometry.right, left + width + pad_x)
    y2 = min(geometry.bottom, top + height + pad_y)
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


def _template_score(capture, template_path: Path) -> float:
    screen = cv2.cvtColor(np.asarray(capture), cv2.COLOR_RGB2GRAY)
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if template is None or template.size == 0:
        raise PresetError(f"Template visual ilegivel: {template_path.name}")
    if template.shape[0] > screen.shape[0] or template.shape[1] > screen.shape[1]:
        return -1.0
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _min_value, max_value, _min_location, _max_location = cv2.minMaxLoc(result)
    return float(max_value)


def _content_present(image) -> tuple[bool, str]:
    gray = image.convert("L")
    stats = ImageStat.Stat(gray)
    deviation = float(stats.stddev[0])
    low, high = gray.getextrema()
    dynamic_range = int(high) - int(low)
    passed = deviation >= 7.0 and dynamic_range >= 28
    return passed, f"contraste {dynamic_range}, variacao {deviation:.1f}"


def _critical_store_region(preview, geometry):
    regions = [
        resolve_rect(preview.get(key), geometry, preview)
        for key in ("ancora", "area_lista", "nome", "venda", "compra")
    ]
    regions = [region for region in regions if region]
    if not regions:
        return None
    left = max(geometry.left, min(region[0] for region in regions) - 8)
    top = max(geometry.top, min(region[1] for region in regions) - 8)
    right = min(
        geometry.right, max(region[0] + region[2] for region in regions) + 8
    )
    bottom = min(
        geometry.bottom, max(region[1] + region[3] for region in regions) + 8
    )
    return left, top, right - left, bottom - top


def validate_buy_preset_passively(
    win,
    preset: dict[str, Any],
    current_settings: dict[str, Any],
    *,
    asset_root: str | Path,
) -> VisualValidationResult:
    """Comprova a tela de compra por referencias independentes, sem OCR/cliques."""

    root = Path(asset_root)
    validate_preset_document(preset, asset_root=root)
    if "buy" not in preset["supported_modes"]:
        return VisualValidationResult(False, "O preset nao oferece Compra.", ())

    geometry = get_client_geometry(win)
    preview = merge_preset_settings(current_settings, preset, geometry)
    evidence: list[VisualEvidence] = []

    store_region = _critical_store_region(preview, geometry)
    visible, visibility_reason = bot.ensure_game_region_visible(win, store_region)
    evidence.append(VisualEvidence("janela", visible, visibility_reason))
    if not visible:
        return VisualValidationResult(
            False,
            "O Albion precisa estar totalmente visivel e em primeiro plano.",
            tuple(evidence),
        )

    templates = preset["templates"]
    mandatory_templates = {
        "anchor": ("ancora", 0.72),
        "purchase_order": ("area_lista", 0.72),
    }
    for template_name, (offset_key, threshold) in mandatory_templates.items():
        spec = templates.get(template_name)
        if not spec:
            evidence.append(
                VisualEvidence(template_name, False, "referencia certificada ausente")
            )
            continue
        region = resolve_rect(preview.get(offset_key), geometry, preview)
        if not region:
            evidence.append(VisualEvidence(template_name, False, "area invalida"))
            continue
        if template_name == "anchor":
            region = _expanded_region(
                region, geometry, max(14, region[2] // 2), max(12, region[3] // 2)
            )
        score = _template_score(capture_region(region), root / spec["path"])
        evidence.append(
            VisualEvidence(
                template_name,
                score >= threshold,
                f"confianca {score:.3f} (minimo {threshold:.2f})",
            )
        )

    content_passes = 0
    for key in ("nome", "venda", "compra"):
        region = resolve_rect(preview.get(key), geometry, preview)
        if not region:
            evidence.append(VisualEvidence(key, False, "area invalida"))
            continue
        passed, detail = _content_present(capture_region(region))
        content_passes += int(passed)
        evidence.append(VisualEvidence(key, passed, detail))

    mandatory_ok = all(
        item.passed
        for item in evidence
        if item.name in {"janela", "purchase_order"}
    )
    supporting_passes = sum(
        int(item.passed)
        for item in evidence
        if item.name in {"anchor", "nome", "venda", "compra"}
    )
    passed = mandatory_ok and supporting_passes >= 3
    if passed:
        summary = "Preset confirmado por referencias visuais independentes."
    elif not mandatory_ok:
        hud_scale = str(preset.get("target", {}).get("game_ui_scale") or "").strip()
        hud_hint = f" Confirme a escala do HUD em {hud_scale}." if hud_scale else ""
        summary = (
            "A tela aberta nao corresponde com seguranca ao preset."
            + hud_hint
        )
    else:
        summary = "Selecione um item no mercado para preencher os campos de leitura."
    return VisualValidationResult(passed, summary, tuple(evidence))
