import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from calibration_presets import (
    PresetError,
    apply_preset,
    build_preset_document,
    check_compatibility,
    discover_presets,
    merge_preset_settings,
    select_compatible_preset,
    validate_preset_document,
)
from coordinate_system import (
    BUY_REQUIRED_KEYS,
    SHOPPING_REQUIRED_KEYS,
    REMOVER_PEDIDOS_REQUIRED_KEYS,
    ClientGeometry,
    load_settings,
    save_settings,
)


def buy_settings(width=1920, height=1080, dpi=96):
    settings = {
        "_calibration": {
            "schema_version": 2,
            "coordinate_space": "albion_client_normalized",
            "client_width": width,
            "client_height": height,
            "aspect_ratio": round(width / height, 6),
            "dpi": dpi,
        },
        "banca_operacional": 40_000_000,
        "lucro": 35,
        "cat_ativo": False,
    }
    for index, key in enumerate(sorted(BUY_REQUIRED_KEYS)):
        start = 0.02 + index * 0.01
        settings[key] = [start, 0.10] if key in {
            "btn_proxima", "btn_mais", "btn_criar", "drag_start", "drag_end",
            "top_start", "top_end",
        } else [start, 0.10, 0.03, 0.03]
    return settings


def buy_preset(**overrides):
    preset = build_preset_document(
        buy_settings(),
        preset_id="albion-1920x1080-dpi96-v1",
        label="Albion 1920x1080",
        supported_modes=["buy"],
        language="pt-BR",
        game_ui_scale="default",
    )
    preset.update(overrides)
    return preset


def shopping_settings(width=1920, height=1080, dpi=96):
    settings = buy_settings(width=width, height=height, dpi=dpi)
    extras = sorted(set(SHOPPING_REQUIRED_KEYS) - set(BUY_REQUIRED_KEYS))
    for index, key in enumerate(extras):
        start = 0.5 + index * 0.01
        settings[key] = [start, 0.10, 0.03, 0.03]
    return settings


def shopping_preset(**overrides):
    preset = build_preset_document(
        shopping_settings(),
        preset_id="albion-1920x1080-dpi96-shopping-v1",
        label="Albion 1920x1080 (Compra Programada)",
        supported_modes=["shopping"],
        language="pt-BR",
        game_ui_scale="default",
    )
    preset.update(overrides)
    return preset


def remover_pedidos_settings(width=1920, height=1080, dpi=96):
    settings = buy_settings(width=width, height=height, dpi=dpi)
    extras = sorted(REMOVER_PEDIDOS_REQUIRED_KEYS)
    for index, key in enumerate(extras):
        start = 0.5 + index * 0.01
        settings[key] = [start, 0.10] if key.endswith(
            ("_start", "_end", "_proxima")
        ) else [start, 0.10, 0.03, 0.03]
    return settings


def remover_pedidos_preset(**overrides):
    preset = build_preset_document(
        remover_pedidos_settings(),
        preset_id="albion-1920x1080-dpi96-remover-pedidos-v1",
        label="Albion 1920x1080 (Remover Pedidos)",
        supported_modes=["remover_pedidos"],
        language="pt-BR",
        game_ui_scale="default",
    )
    preset.update(overrides)
    return preset


class CalibrationPresetContractTests(unittest.TestCase):
    def test_export_contains_only_spatial_settings(self):
        preset = buy_preset()

        self.assertNotIn("banca_operacional", preset["spatial"])
        self.assertNotIn("lucro", preset["spatial"])
        self.assertEqual(set(BUY_REQUIRED_KEYS), set(preset["spatial"]))

    def test_non_spatial_field_is_rejected(self):
        preset = buy_preset()
        preset["spatial"]["banca_operacional"] = 1

        with self.assertRaisesRegex(PresetError, "nao espacial"):
            validate_preset_document(preset, verify_assets=False)

    def test_incomplete_mode_is_rejected(self):
        preset = buy_preset()
        preset["spatial"].pop("btn_nao")

        with self.assertRaisesRegex(PresetError, "incompleto"):
            validate_preset_document(preset, verify_assets=False)

    def test_template_path_traversal_is_rejected(self):
        preset = buy_preset()
        preset["templates"] = {
            "confirmation_yes": {
                "path": "../segredo.png",
                "sha256": "a" * 64,
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(PresetError, "inseguro"):
                validate_preset_document(preset, asset_root=Path(directory))

    def test_changed_template_hash_is_rejected(self):
        preset = buy_preset()
        preset["templates"] = {
            "confirmation_yes": {
                "path": "assets/sim.png",
                "sha256": "a" * 64,
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "assets" / "sim.png").write_bytes(b"not-the-certified-file")
            with self.assertRaisesRegex(PresetError, "corrompido"):
                validate_preset_document(preset, asset_root=root)


class ShoppingPresetSupportTests(unittest.TestCase):
    """A Compra Programada (modo "shopping") existe há um tempo, mas o
    sistema de presets nunca reconheceu esse modo -- só declarava
    buy/sell/cycle como válidos."""

    def test_shopping_is_a_valid_preset_mode(self):
        preset = shopping_preset()
        self.assertEqual(["shopping"], preset["supported_modes"])
        self.assertEqual(set(SHOPPING_REQUIRED_KEYS), set(preset["spatial"]) & set(SHOPPING_REQUIRED_KEYS))

    def test_shopping_preset_missing_busca_mercado_is_rejected(self):
        preset = shopping_preset()
        preset["spatial"].pop("busca_mercado")

        with self.assertRaisesRegex(PresetError, "incompleto"):
            validate_preset_document(preset, verify_assets=False)

    def test_shopping_preset_missing_shopping_qtd_valor_is_rejected(self):
        preset = shopping_preset()
        preset["spatial"].pop("shopping_qtd_valor")

        with self.assertRaisesRegex(PresetError, "incompleto"):
            validate_preset_document(preset, verify_assets=False)

    def test_unknown_mode_is_still_rejected(self):
        with self.assertRaisesRegex(PresetError, "desconhecido"):
            build_preset_document(
                shopping_settings(),
                preset_id="albion-1920x1080-dpi96-invalid-v1",
                label="Modo inválido",
                supported_modes=["nao_existe"],
                language="pt-BR",
                game_ui_scale="default",
            )

    def test_apply_preset_validates_shopping_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "offsets.json"
            geometry = ClientGeometry(left=0, top=0, width=1920, height=1080)

            result = apply_preset(
                shopping_preset(), geometry, settings_path,
            )

            self.assertEqual(("shopping",), result.validated_modes)
            saved = load_settings(str(settings_path))
            self.assertIn("busca_mercado", saved)
            self.assertIn("shopping_qtd_valor", saved)


class RemoverPedidosPresetSupportTests(unittest.TestCase):
    """O modo "remover_pedidos" (cancelar pedidos que perderam a posição)
    também precisa ser reconhecido pelo sistema de presets, incluindo as
    duas amostras visuais próprias (botão EDITAR e X de cancelar)."""

    def test_remover_pedidos_is_a_valid_preset_mode(self):
        preset = remover_pedidos_preset()
        self.assertEqual(["remover_pedidos"], preset["supported_modes"])
        self.assertEqual(
            set(REMOVER_PEDIDOS_REQUIRED_KEYS),
            set(preset["spatial"]) & set(REMOVER_PEDIDOS_REQUIRED_KEYS),
        )

    def test_remover_pedidos_preset_missing_area_lista_is_rejected(self):
        preset = remover_pedidos_preset()
        preset["spatial"].pop("remover_pedidos_area_lista")

        with self.assertRaisesRegex(PresetError, "incompleto"):
            validate_preset_document(preset, verify_assets=False)

    def test_remover_pedidos_preset_missing_topo_cor_is_rejected(self):
        preset = remover_pedidos_preset()
        preset["spatial"].pop("remover_pedidos_topo_cor")

        with self.assertRaisesRegex(PresetError, "incompleto"):
            validate_preset_document(preset, verify_assets=False)

    def test_apply_preset_validates_remover_pedidos_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "offsets.json"
            geometry = ClientGeometry(left=0, top=0, width=1920, height=1080)

            result = apply_preset(
                remover_pedidos_preset(), geometry, settings_path,
            )

            self.assertEqual(("remover_pedidos",), result.validated_modes)
            saved = load_settings(str(settings_path))
            self.assertIn("remover_pedidos_area_lista", saved)
            self.assertIn("remover_pedidos_btn_editar", saved)
            self.assertIn("remover_pedidos_btn_cancelar", saved)


class CalibrationPresetSelectionTests(unittest.TestCase):
    def test_match_requires_exact_client_size_and_dpi(self):
        preset = buy_preset()

        self.assertTrue(
            check_compatibility(
                preset, ClientGeometry(0, 0, 1920, 1080), dpi=96
            ).compatible
        )
        self.assertFalse(
            check_compatibility(
                preset, ClientGeometry(0, 0, 1920, 1080), dpi=120
            ).compatible
        )
        self.assertFalse(
            check_compatibility(
                preset, ClientGeometry(0, 0, 1919, 1080), dpi=96
            ).compatible
        )

    def test_ambiguous_automatic_selection_is_refused(self):
        preset = buy_preset()
        duplicate = json.loads(json.dumps(preset))
        duplicate["preset_id"] = "albion-1920x1080-dpi96-v2"

        selected, reason = select_compatible_preset(
            [preset, duplicate], ClientGeometry(0, 0, 1920, 1080), dpi=96
        )

        self.assertIsNone(selected)
        self.assertIn("mais de um", reason)

    def test_discovery_isolates_invalid_presets(self):
        preset = buy_preset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.json").write_text(json.dumps(preset), encoding="utf-8")
            (root / "broken.json").write_text("{", encoding="utf-8")

            presets, errors = discover_presets(root, asset_root=root)

        self.assertEqual([preset["preset_id"]], [item["preset_id"] for item in presets])
        self.assertEqual(1, len(errors))


class CalibrationPresetApplicationTests(unittest.TestCase):
    def test_merge_preserves_preferences_and_replaces_only_spatial_data(self):
        current = buy_settings()
        current["btn_mais"] = [0.90, 0.90]
        preset = buy_preset()

        merged = merge_preset_settings(
            current, preset, ClientGeometry(50, 20, 1920, 1080)
        )

        self.assertEqual(40_000_000, merged["banca_operacional"])
        self.assertEqual(35, merged["lucro"])
        self.assertEqual(preset["spatial"]["btn_mais"], merged["btn_mais"])
        self.assertEqual(1920, merged["_calibration"]["client_width"])
        self.assertEqual(preset["preset_id"], merged["calibration_preset_id"])

    def test_apply_creates_backup_and_validates_saved_settings(self):
        preset = buy_preset()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offsets.json"
            original = buy_settings()
            original["delay_clique"] = 0.7
            save_settings(str(path), original)

            result = apply_preset(
                preset,
                ClientGeometry(0, 0, 1920, 1080),
                path,
                dpi=96,
            )
            saved = load_settings(str(path))
            backup = load_settings(str(result.backup_path))

        self.assertEqual(0.7, saved["delay_clique"])
        self.assertEqual(preset["preset_id"], saved["calibration_preset_id"])
        self.assertNotIn("calibration_preset_id", backup)
        self.assertEqual(("buy",), result.validated_modes)

    def test_failed_confirmation_restores_original_file(self):
        preset = buy_preset()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offsets.json"
            original = buy_settings()
            original["sentinel"] = "preservar"
            save_settings(str(path), original)
            real_save = save_settings

            def corrupt_save(target, data):
                real_save(target, {"corrompido": True})

            with patch("calibration_presets.save_settings", side_effect=corrupt_save):
                with self.assertRaises(PresetError):
                    apply_preset(
                        preset,
                        ClientGeometry(0, 0, 1920, 1080),
                        path,
                        dpi=96,
                    )
            restored = load_settings(str(path))

        self.assertEqual("preservar", restored["sentinel"])

    def test_apply_activates_certified_template_without_changing_source(self):
        source_bytes = b"certified-png-placeholder"
        preset = buy_preset()
        preset["templates"] = {
            "confirmation_yes": {
                "path": "assets/source.png",
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "assets" / "source.png").write_bytes(source_bytes)
            active = root / "user" / "calibration_assets"
            active.mkdir(parents=True)
            (active / "aviso_sim.png").write_bytes(b"old-user-template")
            path = root / "user" / "offsets.json"
            save_settings(str(path), buy_settings())

            apply_preset(
                preset,
                ClientGeometry(0, 0, 1920, 1080),
                path,
                dpi=96,
                asset_root=root,
                active_asset_dir=active,
            )

            self.assertEqual(source_bytes, (active / "aviso_sim.png").read_bytes())
            self.assertEqual(
                b"old-user-template",
                (root / "user" / "calibration_assets.pre-preset" / "aviso_sim.png").read_bytes(),
            )
            self.assertEqual(source_bytes, (root / "assets" / "source.png").read_bytes())


class BuiltInPresetTests(unittest.TestCase):
    def test_official_1080p_preset_and_assets_are_certified(self):
        root = Path(__file__).resolve().parent

        presets, errors = discover_presets(root / "presets", asset_root=root)

        self.assertEqual([], errors)
        self.assertEqual(1, len(presets))
        self.assertEqual(
            ["buy", "sell", "cycle", "shopping", "remover_pedidos"],
            presets[0]["supported_modes"],
        )
        self.assertEqual(1920, presets[0]["target"]["client_width"])
        self.assertIn("cycle_collect_all", presets[0]["spatial"])
        self.assertIn("buy_page_number_area", presets[0]["spatial"])
        # Adicionados pela Compra Programada, categorias e verificação de
        # média semanal -- regressão real: ficaram de fora do preset shipado
        # até serem exportados de novo com a calibragem completa.
        self.assertIn("busca_mercado", presets[0]["spatial"])
        self.assertIn("shopping_qtd_valor", presets[0]["spatial"])
        self.assertIn("compra_topo_cor", presets[0]["spatial"])
        self.assertIn("preco_medio", presets[0]["spatial"])
        self.assertIn("cat_clique_principal", presets[0]["spatial"])
        self.assertIn("sell_button", presets[0]["templates"])
        # Remover Pedidos: adicionado depois, precisa das 9 chaves e das 2
        # amostras visuais próprias (botão EDITAR e X de cancelar).
        self.assertEqual(
            set(REMOVER_PEDIDOS_REQUIRED_KEYS),
            set(REMOVER_PEDIDOS_REQUIRED_KEYS) & set(presets[0]["spatial"]),
        )
        self.assertIn("edit_button", presets[0]["templates"])
        self.assertIn("cancel_button", presets[0]["templates"])
        self.assertNotIn("banca_operacional", presets[0]["spatial"])
        self.assertNotIn("lucro", presets[0]["spatial"])

    def test_release_build_includes_certified_presets(self):
        root = Path(__file__).resolve().parent
        build_script = (root / "build_release.ps1").read_text(encoding="utf-8")

        self.assertIn("$CalibrationPresets", build_script)
        self.assertIn("--include-data-dir=$CalibrationPresets=presets", build_script)
        self.assertIn('release_packaging.py") stage', build_script)
        self.assertIn('release_packaging.py") validate', build_script)


if __name__ == "__main__":
    unittest.main()
