"""Exporta uma calibragem local sanitizada para homologacao de preset.

Uso interno, por exemplo:
    python scripts/export_calibration_preset.py --id albion-2560x1440-dpi96-ptbr-v1 \
        --label "Albion 2560x1440 - PT-BR" --modes buy --output C:\\Preset-2K
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_paths import application_dir, calibration_assets_dir, user_file
from calibration_presets import build_preset_document, save_preset_document
from coordinate_system import load_settings


TEMPLATE_SOURCES = {
    "anchor": "fechar.png",
    "confirmation_yes": "aviso_sim.png",
    "confirmation_no": "aviso_nao.png",
    "purchase_order": "pedido_usuario.png",
    "sell_button": "vender_usuario.png",
    "edit_button": "editar_pedido_usuario.png",
    "cancel_button": "cancelar_pedido_usuario.png",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_template(filename: str) -> Path | None:
    candidates = (
        calibration_assets_dir(create=False) / filename,
        application_dir() / "assets" / filename,
    )
    return next((path for path in candidates if path.is_file()), None)


def export_bundle(args) -> Path:
    output = Path(args.output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("A pasta de saida precisa estar vazia.")
    assets = output / "assets" / args.preset_id
    assets.mkdir(parents=True, exist_ok=True)

    modes = list(dict.fromkeys(args.modes))
    required_templates = {"anchor", "confirmation_yes", "confirmation_no", "purchase_order"}
    if "sell" in modes or "cycle" in modes:
        required_templates.add("sell_button")
    if "remover_pedidos" in modes:
        required_templates.update({"edit_button", "cancel_button"})

    template_specs = {}
    missing = []
    for name in sorted(required_templates):
        filename = TEMPLATE_SOURCES[name]
        source = find_template(filename)
        if source is None:
            missing.append(filename)
            continue
        destination = assets / filename
        shutil.copy2(source, destination)
        template_specs[name] = {
            "path": f"assets/{args.preset_id}/{filename}",
            "sha256": file_sha256(destination),
        }
    if missing:
        raise RuntimeError("Amostras visuais ausentes: " + ", ".join(missing))

    settings = load_settings(str(user_file("offsets.json")))
    preset = build_preset_document(
        settings,
        preset_id=args.preset_id,
        label=args.label,
        supported_modes=modes,
        language=args.language,
        game_ui_scale=args.game_ui_scale,
        templates=template_specs,
    )
    preset_path = output / "preset.json"
    save_preset_document(preset_path, preset)
    return preset_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Exporta somente calibragens e amostras visuais do AlbionMKT."
    )
    parser.add_argument("--id", dest="preset_id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("buy", "sell", "cycle", "shopping", "remover_pedidos"),
        required=True,
    )
    parser.add_argument("--language", default="pt-BR")
    parser.add_argument("--game-ui-scale", default="default")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        path = export_bundle(parse_args())
    except Exception as exc:
        print(f"EXPORT_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"EXPORT_OK: {path}")
