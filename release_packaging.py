"""Empacotamento verificavel dos assets certificados de calibragem."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path, PurePosixPath

from calibration_presets import discover_presets


class ReleasePackagingError(RuntimeError):
    """Indica que um pacote de release perderia um preset certificado."""


def validate_packaged_presets(
    presets_dir: str | Path,
    *,
    asset_root: str | Path,
    expected_count: int | None = None,
) -> tuple[str, ...]:
    """Valida os presets exatamente contra a arvore que sera distribuida."""

    presets_path = Path(presets_dir)
    presets, errors = discover_presets(presets_path, asset_root=Path(asset_root))
    declared_count = len(list(presets_path.glob("*.json")))
    wanted_count = declared_count if expected_count is None else int(expected_count)
    if errors:
        raise ReleasePackagingError("; ".join(errors))
    if wanted_count <= 0 or len(presets) != wanted_count:
        raise ReleasePackagingError(
            f"Quantidade de presets empacotados invalida: {len(presets)}/{wanted_count}."
        )
    return tuple(str(preset["preset_id"]) for preset in presets)


def stage_certified_preset_assets(
    repo_root: str | Path,
    presets_dir: str | Path,
    packaged_assets: str | Path,
) -> tuple[Path, ...]:
    """Copia somente arquivos referenciados e validados pelos presets oficiais."""

    root = Path(repo_root).resolve()
    presets_path = Path(presets_dir).resolve()
    destination = Path(packaged_assets).resolve()
    presets, errors = discover_presets(presets_path, asset_root=root)
    if errors:
        raise ReleasePackagingError("; ".join(errors))
    if not presets:
        raise ReleasePackagingError("Nenhum preset certificado foi encontrado.")

    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    seen_targets: set[Path] = set()
    for preset in presets:
        for spec in preset.get("templates", {}).values():
            relative = PurePosixPath(str(spec["path"]).replace("\\", "/"))
            if not relative.parts or relative.parts[0] != "assets":
                raise ReleasePackagingError(
                    f"Asset fora da pasta permitida: {relative.as_posix()}"
                )
            source = root.joinpath(*relative.parts)
            target = destination.joinpath(*relative.parts[1:]).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise ReleasePackagingError(
                    f"Destino inseguro para asset: {relative.as_posix()}"
                ) from exc
            if target in seen_targets:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            seen_targets.add(target)
            copied.append(target)

    validate_packaged_presets(
        presets_path,
        asset_root=destination.parent,
        expected_count=len(presets),
    )
    return tuple(copied)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    stage = subcommands.add_parser("stage")
    stage.add_argument("--repo-root", required=True, type=Path)
    stage.add_argument("--presets-dir", required=True, type=Path)
    stage.add_argument("--packaged-assets", required=True, type=Path)

    validate = subcommands.add_parser("validate")
    validate.add_argument("--presets-dir", required=True, type=Path)
    validate.add_argument("--asset-root", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "stage":
        copied = stage_certified_preset_assets(
            args.repo_root, args.presets_dir, args.packaged_assets
        )
        print(f"PRESET_ASSETS_OK copied={len(copied)}")
    else:
        preset_ids = validate_packaged_presets(
            args.presets_dir, asset_root=args.asset_root
        )
        print("PACKAGED_PRESETS_OK ids=" + ",".join(preset_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
