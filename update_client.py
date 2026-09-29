"""Cliente leve de atualizacao, isolado das automacoes do MKT."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from app_paths import application_dir, updater_dir, user_file
from app_version import APP_VERSION, UPDATE_CHANNEL
from update_manager import UpdateManifest, is_update_available, parse_manifest


RELEASES_REPOSITORY = "luizphotoshop25-prog/AlbionMKT-Releases"
RELEASES_BASE_URL = f"https://github.com/{RELEASES_REPOSITORY}/releases"
UPDATE_ENDPOINT = f"{RELEASES_BASE_URL}/latest/download/latest.json"
TRUSTED_DOWNLOAD_HOST = "github.com"
MAX_MANIFEST_BYTES = 64 * 1024


def _installed_updater() -> Path:
    """Devolve o atualizador externo, renovando-o junto com o patch quando houver.

    O atualizador nao fica dentro da pasta que ele mesmo substitui. Por isso a
    versao embutida no patch e copiada para a area persistente somente quando o
    MKT ja reiniciou, antes de qualquer nova atualizacao ser oferecida.
    """

    destination = updater_dir() / "MKTUpdater.exe"
    bundled = application_dir() / "updater" / "MKTUpdater.exe"
    if bundled.is_file():
        try:
            needs_copy = not destination.is_file() or (
                bundled.stat().st_size != destination.stat().st_size
                or bundled.read_bytes() != destination.read_bytes()
            )
            if needs_copy:
                temporary = destination.with_suffix(".new")
                shutil.copy2(bundled, temporary)
                os.replace(temporary, destination)
        except OSError:
            # Se a copia local falhar, ainda tentamos o atualizador anterior;
            # a verificacao de manifesto continua sendo segura.
            pass
    return destination


def supports_in_app_updates() -> bool:
    """Atualizacao automatica so aparece na versao instalada/compilada."""

    return (
        (getattr(sys, "frozen", False) or "__compiled__" in globals())
        and (application_dir() / "MKT.exe").is_file()
        and _installed_updater().is_file()
    )


def fetch_available_update(endpoint: str = UPDATE_ENDPOINT) -> UpdateManifest | None:
    request = urllib.request.Request(endpoint, headers={"User-Agent": f"MKT/{APP_VERSION}"})
    with urllib.request.urlopen(request, timeout=4) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_MANIFEST_BYTES:
            raise ValueError("Manifesto de atualizacao muito grande.")
        raw = response.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifesto de atualizacao muito grande.")
    manifest = parse_manifest(json.loads(raw.decode("utf-8-sig")))
    parsed_download = urlparse(manifest.download_url)
    expected_path = (
        f"/{RELEASES_REPOSITORY}/releases/download/v{manifest.version}/"
        f"MKT_Update_{manifest.version}.zip"
    )
    if (
        parsed_download.scheme != "https"
        or (parsed_download.hostname or "").lower() != TRUSTED_DOWNLOAD_HOST
        or parsed_download.username is not None
        or parsed_download.password is not None
        or parsed_download.port not in {None, 443}
        or parsed_download.path != expected_path
        or parsed_download.params
        or parsed_download.query
        or parsed_download.fragment
    ):
        raise ValueError("Servidor de download nao autorizado.")
    return manifest if is_update_available(APP_VERSION, manifest) else None


def check_in_background(on_update, on_error=None, on_no_update=None) -> bool:
    """Checa sem bloquear Tk, OCR, cliques ou a inicializacao do bot."""

    if not supports_in_app_updates():
        return False

    def worker():
        try:
            manifest = fetch_available_update()
            if manifest is not None:
                on_update(manifest)
            elif on_no_update is not None:
                on_no_update()
        except Exception as exc:
            if on_error is not None:
                on_error(exc)

    threading.Thread(target=worker, name="mkt-update-check", daemon=True).start()
    return True


def launch_updater(manifest: UpdateManifest) -> None:
    updater = _installed_updater()
    install_dir = application_dir()
    if not updater.is_file() or not (install_dir / "MKT.exe").is_file():
        raise FileNotFoundError("Atualizador ou instalacao do MKT nao encontrado.")
    command = [
        str(updater),
        "--url", manifest.download_url,
        "--sha256", manifest.sha256,
        "--size", str(manifest.size),
        "--version", manifest.version,
        "--notes-json", json.dumps(list(manifest.release_notes), ensure_ascii=False),
        "--install-dir", str(install_dir),
        "--pid", str(os.getpid()),
        "--status-file", str(user_file("update-status.json")),
    ]
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        command,
        cwd=str(updater.parent),
        close_fds=True,
        creationflags=creation_flags,
    )

