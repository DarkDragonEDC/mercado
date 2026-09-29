"""Contrato seguro de atualizacao do MKT.

O download e a troca dos binarios serao feitos por um executavel separado.
Este modulo apenas valida o manifesto e o pacote, sem alterar a instalacao.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    channel: str
    download_url: str
    sha256: str
    size: int
    mandatory: bool
    minimum_version: str | None = None
    signature: str | None = None
    release_notes: tuple[str, ...] = ()


def version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError("Versao invalida; use o formato MAJOR.MINOR.PATCH.")
    return tuple(int(part) for part in match.groups())


def parse_manifest(payload: dict[str, Any]) -> UpdateManifest:
    if not isinstance(payload, dict):
        raise ValueError("Manifesto de atualizacao invalido.")
    version = str(payload.get("version") or "").strip()
    version_tuple(version)
    channel = str(payload.get("channel") or "").strip()
    if channel not in {"stable", "beta"}:
        raise ValueError("Canal de atualizacao invalido.")
    download_url = str(payload.get("downloadUrl") or "").strip()
    parsed_url = urlparse(download_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("A atualizacao exige um endereco HTTPS.")
    digest = str(payload.get("sha256") or "").strip().lower()
    if not _SHA256_PATTERN.fullmatch(digest):
        raise ValueError("SHA-256 da atualizacao invalido.")
    size = payload.get("size")
    if not isinstance(size, int) or size <= 0:
        raise ValueError("Tamanho da atualizacao invalido.")
    mandatory = payload.get("mandatory")
    if not isinstance(mandatory, bool):
        raise ValueError("Indicador de atualizacao obrigatoria invalido.")
    minimum = payload.get("minimumVersion")
    if minimum is not None:
        minimum = str(minimum).strip()
        version_tuple(minimum)
    signature = payload.get("signature")
    if signature is not None and not isinstance(signature, str):
        raise ValueError("Assinatura da atualizacao invalida.")
    raw_notes = payload.get("releaseNotes", [])
    if raw_notes is None:
        raw_notes = []
    if not isinstance(raw_notes, list) or len(raw_notes) > 8:
        raise ValueError("Notas da atualizacao invalidas.")
    release_notes: list[str] = []
    for note in raw_notes:
        if not isinstance(note, str):
            raise ValueError("Notas da atualizacao invalidas.")
        cleaned = note.strip()
        if not cleaned or len(cleaned) > 180:
            raise ValueError("Notas da atualizacao invalidas.")
        release_notes.append(cleaned)
    return UpdateManifest(
        version=version,
        channel=channel,
        download_url=download_url,
        sha256=digest,
        size=size,
        mandatory=mandatory,
        minimum_version=minimum,
        signature=signature,
        release_notes=tuple(release_notes),
    )


def is_update_available(current_version: str, manifest: UpdateManifest) -> bool:
    return version_tuple(manifest.version) > version_tuple(current_version)


def verify_package(path: str | Path, manifest: UpdateManifest) -> bool:
    package = Path(path)
    try:
        if not package.is_file() or package.stat().st_size != manifest.size:
            return False
        digest = hashlib.sha256()
        with package.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest() == manifest.sha256
    except OSError:
        return False
