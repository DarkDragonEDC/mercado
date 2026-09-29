"""Verificacao rapida e persistente das dependencias do MKT."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"
MARKER_FILE = BASE_DIR / ".mkt_dependencies.ok"

IMPORT_NAMES = {
    "easyocr": "easyocr",
    "keyboard": "keyboard",
    "numpy": "numpy",
    "opencv-python": "cv2",
    "pillow": "PIL",
    "pyautogui": "pyautogui",
    "pygetwindow": "pygetwindow",
    "requests": "requests",
    "torch": "torch",
    "torchvision": "torchvision",
}


def requirements_hash() -> str:
    return hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()


def pinned_requirements() -> dict[str, str]:
    requirements: dict[str, str] = {}
    for raw_line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"Dependencia sem versao fixa: {line}")
        name, version = line.split("==", 1)
        requirements[name.strip()] = version.strip()
    return requirements


def installed_versions_are_valid() -> tuple[bool, str]:
    try:
        requirements = pinned_requirements()
    except Exception as exc:
        return False, str(exc)
    for name, expected in requirements.items():
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return False, f"Pacote ausente: {name}"
        if installed != expected:
            return False, f"Versao incorreta: {name} {installed} (esperada {expected})"
    return True, "Dependencias registradas corretamente."


def marker_is_valid() -> tuple[bool, str]:
    if not MARKER_FILE.exists():
        return False, "Primeira verificacao ainda nao concluida."
    try:
        marker = json.loads(MARKER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False, "Marcador de instalacao invalido."
    if marker.get("requirements_sha256") != requirements_hash():
        return False, "O arquivo requirements.txt foi alterado."
    if marker.get("python") != f"{sys.version_info.major}.{sys.version_info.minor}":
        return False, "A versao do Python foi alterada."
    return installed_versions_are_valid()


def verify_imports_and_mark() -> tuple[bool, str]:
    valid, reason = installed_versions_are_valid()
    if not valid:
        return False, reason
    for package, module in IMPORT_NAMES.items():
        try:
            importlib.import_module(module)
        except Exception as exc:
            return False, f"Falha ao carregar {package}: {exc}"
    marker = {
        "requirements_sha256": requirements_hash(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    MARKER_FILE.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return True, "Dependencias verificadas e salvas."


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if action == "--check":
        valid, reason = marker_is_valid()
    elif action == "--verify-and-mark":
        valid, reason = verify_imports_and_mark()
    else:
        print("Uso: dependency_manager.py [--check|--verify-and-mark]")
        return 2
    print(reason)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
