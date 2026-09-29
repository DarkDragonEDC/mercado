"""Presets seguros para a calibragem v2 do AlbionMKT.

O preset e um artefato distribuido, somente com dados espaciais e referencias
visuais. O ``offsets.json`` continua sendo o contrato operacional e nunca e
substituido sem backup, merge das preferencias e validacao final.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from coordinate_system import (
    BUY_REQUIRED_KEYS,
    CYCLE_REQUIRED_KEYS,
    SELL_REQUIRED_KEYS,
    SHOPPING_REQUIRED_KEYS,
    REMOVER_PEDIDOS_REQUIRED_KEYS,
    ClientGeometry,
    calibration_metadata,
    get_window_dpi,
    is_spatial_key,
    load_settings,
    save_settings,
    strip_spatial_settings,
    validate_calibration,
)


PRESET_SCHEMA_VERSION = 1
MAX_PRESET_FILE_SIZE = 1024 * 1024
PRESET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SUPPORTED_MODES = {"buy", "sell", "cycle", "shopping", "remover_pedidos"}
ALLOWED_TEMPLATE_NAMES = {
    "anchor",
    "confirmation_yes",
    "confirmation_no",
    "purchase_order",
    "sell_button",
    "edit_button",
    "cancel_button",
}
ACTIVE_TEMPLATE_FILENAMES = {
    "anchor": "fechar.png",
    "confirmation_yes": "aviso_sim.png",
    "confirmation_no": "aviso_nao.png",
    "purchase_order": "pedido_usuario.png",
    "sell_button": "vender_usuario.png",
    "edit_button": "editar_pedido_usuario.png",
    "cancel_button": "cancelar_pedido_usuario.png",
}


class PresetError(ValueError):
    """Erro controlado ao ler, selecionar ou aplicar um preset."""


@dataclass(frozen=True)
class PresetCompatibility:
    compatible: bool
    reason: str


@dataclass(frozen=True)
class PresetApplicationResult:
    preset_id: str
    settings_path: Path
    backup_path: Path | None
    validated_modes: tuple[str, ...]


def _required_keys_for_mode(mode: str) -> set[str]:
    if mode == "buy":
        return set(BUY_REQUIRED_KEYS)
    if mode == "sell":
        return set(SELL_REQUIRED_KEYS)
    if mode == "cycle":
        return set(BUY_REQUIRED_KEYS) | set(SELL_REQUIRED_KEYS) | set(CYCLE_REQUIRED_KEYS)
    if mode == "shopping":
        return set(SHOPPING_REQUIRED_KEYS)
    if mode == "remover_pedidos":
        return set(REMOVER_PEDIDOS_REQUIRED_KEYS)
    raise PresetError(f"Modo de preset desconhecido: {mode}")


def _validate_normalized_value(key: str, value: Any) -> None:
    if not isinstance(value, list) or len(value) not in (2, 4):
        raise PresetError(f"Coordenada invalida no preset: {key}")
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in value
    ):
        raise PresetError(f"Coordenada nao numerica no preset: {key}")
    numbers = [float(item) for item in value]
    if any(item < 0.0 or item > 1.0 for item in numbers[:2]):
        raise PresetError(f"Coordenada fora da janela no preset: {key}")
    if len(numbers) == 4:
        if numbers[2] <= 0.0 or numbers[3] <= 0.0:
            raise PresetError(f"Area vazia no preset: {key}")
        if numbers[0] + numbers[2] > 1.000001 or numbers[1] + numbers[3] > 1.000001:
            raise PresetError(f"Area fora da janela no preset: {key}")


def _safe_asset_path(asset_root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise PresetError("O preset contem um caminho de template inseguro.")
    resolved_root = asset_root.resolve()
    resolved = (resolved_root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise PresetError("O template do preset saiu da pasta permitida.") from exc
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_preset_document(
    preset: dict[str, Any],
    *,
    asset_root: Path | None = None,
    verify_assets: bool = True,
) -> dict[str, Any]:
    """Valida integralmente um documento sem aceitar campos espaciais livres."""

    if not isinstance(preset, dict):
        raise PresetError("O preset precisa ser um objeto JSON.")
    if preset.get("schema_version") != PRESET_SCHEMA_VERSION:
        raise PresetError("Versao de preset nao suportada.")

    preset_id = preset.get("preset_id")
    if not isinstance(preset_id, str) or not PRESET_ID_PATTERN.fullmatch(preset_id):
        raise PresetError("Identificador de preset invalido.")

    label = preset.get("label")
    if not isinstance(label, str) or not label.strip() or len(label) > 100:
        raise PresetError("Nome de preset invalido.")

    target = preset.get("target")
    if not isinstance(target, dict):
        raise PresetError("Metadados de compatibilidade ausentes.")
    try:
        width = int(target["client_width"])
        height = int(target["client_height"])
        dpi = int(target["dpi"])
        aspect = float(target["aspect_ratio"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PresetError("Geometria do preset invalida.") from exc
    if width < 800 or height < 600 or dpi < 72 or dpi > 480:
        raise PresetError("Geometria do preset fora dos limites permitidos.")
    if not math.isfinite(aspect) or abs(aspect - width / height) > 0.001:
        raise PresetError("Proporcao do preset inconsistente.")
    language = target.get("language")
    ui_scale = target.get("game_ui_scale")
    if not isinstance(language, str) or not language.strip():
        raise PresetError("Idioma do preset ausente.")
    if not isinstance(ui_scale, str) or not ui_scale.strip():
        raise PresetError("Escala da interface do jogo ausente.")

    modes = preset.get("supported_modes")
    if not isinstance(modes, list) or not modes or len(set(modes)) != len(modes):
        raise PresetError("Modos suportados invalidos.")
    if any(mode not in SUPPORTED_MODES for mode in modes):
        raise PresetError("O preset declara um modo desconhecido.")

    spatial = preset.get("spatial")
    if not isinstance(spatial, dict) or not spatial:
        raise PresetError("O preset nao possui calibragens espaciais.")
    for key, value in spatial.items():
        if not isinstance(key, str) or not is_spatial_key(key):
            raise PresetError(f"Campo nao espacial recusado no preset: {key}")
        _validate_normalized_value(key, value)
    for mode in modes:
        missing = sorted(_required_keys_for_mode(mode) - set(spatial))
        if missing:
            raise PresetError(
                f"Preset incompleto para {mode}: " + ", ".join(missing)
            )

    templates = preset.get("templates", {})
    if not isinstance(templates, dict):
        raise PresetError("Mapa de templates invalido.")
    for name, spec in templates.items():
        if name not in ALLOWED_TEMPLATE_NAMES or not isinstance(spec, dict):
            raise PresetError(f"Template nao permitido: {name}")
        relative_path = spec.get("path")
        expected_hash = spec.get("sha256")
        if not isinstance(relative_path, str) or not relative_path.lower().endswith(".png"):
            raise PresetError(f"Caminho de template invalido: {name}")
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
            raise PresetError(f"Hash de template invalido: {name}")
        if verify_assets:
            if asset_root is None:
                raise PresetError("A pasta de assets e obrigatoria para verificar o preset.")
            asset_path = _safe_asset_path(asset_root, relative_path)
            if not asset_path.is_file():
                raise PresetError(f"Template ausente no preset: {name}")
            if _sha256(asset_path) != expected_hash:
                raise PresetError(f"Template alterado ou corrompido: {name}")

    return preset


def load_preset(path: str | os.PathLike[str], *, asset_root: Path) -> dict[str, Any]:
    preset_path = Path(path)
    if not preset_path.is_file():
        raise PresetError("Arquivo de preset nao encontrado.")
    if preset_path.stat().st_size > MAX_PRESET_FILE_SIZE:
        raise PresetError("Arquivo de preset excede o tamanho permitido.")
    try:
        with preset_path.open("r", encoding="utf-8") as handle:
            preset = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PresetError("Nao foi possivel ler o preset.") from exc
    return validate_preset_document(preset, asset_root=asset_root)


def discover_presets(
    directory: str | os.PathLike[str], *, asset_root: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    presets: list[dict[str, Any]] = []
    errors: list[str] = []
    root = Path(directory)
    if not root.is_dir():
        return presets, errors
    for path in sorted(root.glob("*.json")):
        try:
            presets.append(load_preset(path, asset_root=asset_root))
        except PresetError as exc:
            errors.append(f"{path.name}: {exc}")
    return presets, errors


def check_compatibility(
    preset: dict[str, Any],
    geometry: ClientGeometry,
    *,
    dpi: int | None = None,
    language: str = "pt-BR",
) -> PresetCompatibility:
    """Faz o filtro tecnico estrito; a prova visual ocorre em outra camada."""

    target = preset["target"]
    if geometry.width != int(target["client_width"]) or geometry.height != int(
        target["client_height"]
    ):
        return PresetCompatibility(False, "tamanho da janela do Albion diferente")
    current_dpi = get_window_dpi(geometry) if dpi is None else int(dpi)
    if current_dpi != int(target["dpi"]):
        return PresetCompatibility(False, "escala/DPI diferente")
    if language.casefold() != str(target["language"]).casefold():
        return PresetCompatibility(False, "idioma do Albion diferente")
    return PresetCompatibility(True, "geometria, DPI e idioma compativeis")


def select_compatible_preset(
    presets: Iterable[dict[str, Any]],
    geometry: ClientGeometry,
    *,
    dpi: int | None = None,
    language: str = "pt-BR",
) -> tuple[dict[str, Any] | None, str]:
    matches = [
        preset
        for preset in presets
        if check_compatibility(preset, geometry, dpi=dpi, language=language).compatible
    ]
    if not matches:
        return None, "nenhum preset certificado corresponde a esta configuracao"
    if len(matches) > 1:
        return None, "mais de um preset corresponde; selecao automatica recusada"
    return matches[0], "preset certificado encontrado"


def merge_preset_settings(
    current: dict[str, Any],
    preset: dict[str, Any],
    geometry: ClientGeometry,
) -> dict[str, Any]:
    """Preserva preferencias e substitui somente calibragens espaciais."""

    merged = strip_spatial_settings(current)
    merged.update({key: list(value) for key, value in preset["spatial"].items()})
    merged["_calibration"] = calibration_metadata(geometry)
    merged["calibration_preset_id"] = preset["preset_id"]
    return merged


def _restore_backup(backup_path: Path | None, settings_path: Path) -> None:
    if backup_path is None:
        settings_path.unlink(missing_ok=True)
        return
    temporary = settings_path.with_suffix(settings_path.suffix + ".restore")
    shutil.copy2(backup_path, temporary)
    os.replace(temporary, settings_path)


def _activate_templates(
    preset: dict[str, Any], asset_root: Path, active_dir: Path
) -> list[tuple[Path, Path | None]]:
    """Ativa templates certificados e devolve informacoes para rollback."""

    validate_preset_document(preset, asset_root=asset_root)
    active_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = active_dir.parent / "calibration_assets.pre-preset"
    backup_dir.mkdir(parents=True, exist_ok=True)
    activated: list[tuple[Path, Path | None]] = []
    try:
        for name, spec in preset.get("templates", {}).items():
            source = _safe_asset_path(asset_root, spec["path"])
            target = active_dir / ACTIVE_TEMPLATE_FILENAMES[name]
            backup: Path | None = None
            if target.is_file():
                backup = backup_dir / target.name
                backup_temp = backup.with_suffix(backup.suffix + ".tmp")
                shutil.copy2(target, backup_temp)
                os.replace(backup_temp, backup)
            temporary = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
            activated.append((target, backup))
    except Exception:
        _restore_templates(activated)
        raise
    return activated


def _restore_templates(activated: Iterable[tuple[Path, Path | None]]) -> None:
    for target, backup in reversed(list(activated)):
        if backup is None:
            target.unlink(missing_ok=True)
            continue
        temporary = target.with_suffix(target.suffix + ".restore")
        shutil.copy2(backup, temporary)
        os.replace(temporary, target)


def apply_preset(
    preset: dict[str, Any],
    geometry: ClientGeometry,
    settings_path: str | os.PathLike[str],
    *,
    dpi: int | None = None,
    language: str = "pt-BR",
    asset_root: str | os.PathLike[str] | None = None,
    active_asset_dir: str | os.PathLike[str] | None = None,
) -> PresetApplicationResult:
    """Aplica com backup, gravacao atomica, releitura e rollback automatico."""

    templates = preset.get("templates", {}) if isinstance(preset, dict) else {}
    if templates and (asset_root is None or active_asset_dir is None):
        raise PresetError(
            "O preset possui templates, mas as pastas de origem/ativacao nao foram informadas."
        )
    validate_preset_document(
        preset,
        asset_root=Path(asset_root) if asset_root is not None else None,
        verify_assets=bool(templates),
    )
    compatibility = check_compatibility(
        preset, geometry, dpi=dpi, language=language
    )
    if not compatibility.compatible:
        raise PresetError(f"Preset incompativel: {compatibility.reason}.")

    target_path = Path(settings_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    current = load_settings(str(target_path))
    merged = merge_preset_settings(current, preset, geometry)
    backup_path: Path | None = None
    if target_path.is_file():
        backup_path = target_path.with_name("offsets.pre-preset.json")
        backup_temp = backup_path.with_suffix(backup_path.suffix + ".tmp")
        shutil.copy2(target_path, backup_temp)
        os.replace(backup_temp, backup_path)

    modes = tuple(str(mode) for mode in preset["supported_modes"])
    activated_templates: list[tuple[Path, Path | None]] = []
    try:
        if templates:
            activated_templates = _activate_templates(
                preset, Path(asset_root), Path(active_asset_dir)
            )
        save_settings(str(target_path), merged)
        saved = load_settings(str(target_path))
        if saved.get("calibration_preset_id") != preset["preset_id"]:
            raise PresetError("A gravacao do preset nao foi confirmada.")
        for mode in modes:
            valid, reason = validate_calibration(saved, geometry, mode=mode)
            if not valid:
                raise PresetError(f"Validacao final falhou em {mode}: {reason}")
    except Exception:
        _restore_backup(backup_path, target_path)
        _restore_templates(activated_templates)
        raise

    return PresetApplicationResult(
        preset_id=preset["preset_id"],
        settings_path=target_path,
        backup_path=backup_path,
        validated_modes=modes,
    )


def build_preset_document(
    settings: dict[str, Any],
    *,
    preset_id: str,
    label: str,
    supported_modes: Iterable[str],
    language: str,
    game_ui_scale: str,
    templates: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Exporta apenas campos espaciais; preferencias nunca entram no pacote."""

    meta = settings.get("_calibration")
    if not isinstance(meta, dict):
        raise PresetError("A calibragem v2 precisa existir antes da exportacao.")
    spatial = {
        key: list(value)
        for key, value in settings.items()
        if is_spatial_key(key)
    }
    preset = {
        "schema_version": PRESET_SCHEMA_VERSION,
        "preset_id": preset_id,
        "label": label,
        "target": {
            "client_width": int(meta.get("client_width", 0)),
            "client_height": int(meta.get("client_height", 0)),
            "aspect_ratio": float(meta.get("aspect_ratio", 0.0)),
            "dpi": int(meta.get("dpi", 0)),
            "language": language,
            "game_ui_scale": game_ui_scale,
        },
        "supported_modes": list(supported_modes),
        "spatial": spatial,
        "templates": templates or {},
    }
    return validate_preset_document(preset, verify_assets=False)


def save_preset_document(path: str | os.PathLike[str], preset: dict[str, Any]) -> None:
    """Grava um pacote exportado de forma atomica."""

    validate_preset_document(preset, verify_assets=False)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(preset, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
