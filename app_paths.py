"""Caminhos persistentes do MKT, independentes da pasta de instalacao."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_DATA_DIRNAME = "AlbionMKT"
DATA_DIR_ENV = "MKT_DATA_DIR"
LEGACY_STATE_FILES = (
    "license.json",
    "offsets.json",
    "oportunidades.csv",
)
LEGACY_CALIBRATION_ASSETS = (
    "fechar.png",
    "aviso_sim.png",
    "aviso_nao.png",
    "pedido_usuario.png",
    "vender_usuario.png",
)


def application_dir() -> Path:
    """Pasta somente-leitura que contem o executavel ou o codigo-fonte."""

    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_dir(*, create: bool = True) -> Path:
    """Pasta gravavel e preservada entre instalacoes e atualizacoes."""

    override = os.environ.get(DATA_DIR_ENV)
    if override:
        target = Path(override).expanduser().resolve()
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else application_dir()
        target = base / APP_DATA_DIRNAME
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def user_file(name: str, *, create_parent: bool = True) -> Path:
    path = user_data_dir(create=create_parent) / name
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir(*, create: bool = True) -> Path:
    path = user_data_dir(create=create) / "logs"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir(*, create: bool = True) -> Path:
    path = user_data_dir(create=create) / "cache"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def calibration_assets_dir(*, create: bool = True) -> Path:
    """Amostras visuais ativas, gravaveis e preservadas entre atualizacoes."""

    path = user_data_dir(create=create) / "calibration_assets"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def updater_dir(*, create: bool = True) -> Path:
    path = user_data_dir(create=create) / "updater"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def migrate_legacy_state(source_dir: Path | None = None) -> dict[str, Path]:
    """Copia configuracoes antigas sem sobrescrever dados ja migrados.

    A origem nunca e removida. Cada copia usa arquivo temporario e troca
    atomica, evitando que uma interrupcao deixe JSON parcial.
    """

    source = (source_dir or application_dir()).resolve()
    destination = user_data_dir()
    migrated: dict[str, Path] = {}
    if source == destination.resolve():
        return migrated

    for filename in LEGACY_STATE_FILES:
        old_path = source / filename
        new_path = destination / filename
        if new_path.exists() or not old_path.is_file():
            continue
        temporary = new_path.with_suffix(new_path.suffix + ".migrating")
        try:
            shutil.copy2(old_path, temporary)
            os.replace(temporary, new_path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            continue
        migrated[filename] = new_path
    return migrated


def migrate_legacy_calibration_assets(
    source_dir: Path | None = None,
) -> dict[str, Path]:
    """Copia amostras antigas para a pasta persistente sem sobrescrever nada."""

    source = (source_dir or application_dir()).resolve() / "assets"
    destination = calibration_assets_dir()
    migrated: dict[str, Path] = {}
    if not source.is_dir():
        return migrated
    for filename in LEGACY_CALIBRATION_ASSETS:
        old_path = source / filename
        new_path = destination / filename
        if new_path.exists() or not old_path.is_file():
            continue
        temporary = new_path.with_suffix(new_path.suffix + ".migrating")
        try:
            shutil.copy2(old_path, temporary)
            os.replace(temporary, new_path)
        except OSError:
            temporary.unlink(missing_ok=True)
            continue
        migrated[filename] = new_path
    return migrated
