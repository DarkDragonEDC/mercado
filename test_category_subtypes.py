import unittest
from unittest.mock import Mock, patch

import bot
import interface
from category_config import ITEM_TIERS
from coordinate_system import (
    BUY_REQUIRED_KEYS,
    META_KEY,
    ClientGeometry,
    calibration_metadata,
    validate_calibration,
)


CATEGORY_KEYS = {
    "ARMAS": "cat_clique_armas",
    "PEITORAL": "cat_clique_peitoral",
    "CAPACETES": "cat_clique_capacetes",
    "BOTAS": "cat_clique_botas",
    "MÃO SECUNDARIA": "cat_clique_mao_secundaria",
    "CAPAS": "cat_clique_capas",
    "BOLSAS": "cat_clique_bolsas",
    "EQUIP COLETA": "cat_clique_equip_coleta",
}


class CategorySettingsTests(unittest.TestCase):
    def test_targets_follow_category_order_and_enabled_selection(self):
        targets = bot.build_active_category_targets(
            ["CAPACETES", "BOTAS", "ARMAS"],
            {name: name in {"CAPACETES", "ARMAS"} for name in CATEGORY_KEYS},
            CATEGORY_KEYS,
        )

        self.assertEqual(
            [target["label"] for target in targets],
            ["CAPACETES", "ARMAS"],
        )
        self.assertTrue(all("subtype" not in target for target in targets))

    def test_no_selected_category_produces_no_navigation_target(self):
        targets = bot.build_active_category_targets(
            list(CATEGORY_KEYS),
            {name: False for name in CATEGORY_KEYS},
            CATEGORY_KEYS,
        )

        self.assertEqual(targets, [])

    def test_missing_settings_enable_all_categories(self):
        targets = bot.build_active_category_targets([], {}, CATEGORY_KEYS)

        self.assertEqual(
            [target["category"] for target in targets],
            list(CATEGORY_KEYS),
        )

    def test_interface_persists_categories_and_preserves_inert_old_fields(self):
        gui = interface.AlbionBotGUI.__new__(interface.AlbionBotGUI)
        gui.category_list = [
            {"name": "ARMAS", "key": "cat_clique_armas", "enabled": True}
        ]
        gui.log = Mock()
        old_fields = {
            "preservar": 1,
            "cat_subtypes_enabled": {"ARMAS": {"Espada": False}},
            "cat_subtype_tiers": {"ARMAS": {"Espada": {"3": False}}},
        }

        with patch.object(interface, "load_settings", return_value=old_fields), patch.object(
            interface, "save_settings"
        ) as save:
            gui.salvar_sequencia_categorias()

        saved = save.call_args.args[1]
        self.assertEqual(saved["preservar"], 1)
        self.assertEqual(saved["cat_sequence"], ["ARMAS"])
        self.assertEqual(saved["cat_enabled"], {"ARMAS": True})
        self.assertEqual(saved["cat_subtypes_enabled"], old_fields["cat_subtypes_enabled"])
        self.assertEqual(saved["cat_subtype_tiers"], old_fields["cat_subtype_tiers"])

class ItemTierDetectionTests(unittest.TestCase):
    def test_tier_is_detected_from_portuguese_item_name(self):
        self.assertEqual(bot.detectar_tier_nome("Botas do Iniciante"), 3)
        self.assertEqual(bot.detectar_tier_nome("Lança do Adepto"), 4)
        self.assertEqual(bot.detectar_tier_nome("Espada do Grão-Mestre"), 7)

    def test_tier_three_is_rejected_when_only_four_and_above_are_selected(self):
        allowed, tier, reason = bot.validar_tier_item(
            "Lança do Iniciante", [4, 5, 6, 7, 8]
        )

        self.assertFalse(allowed)
        self.assertEqual(tier, 3)
        self.assertIn("desmarcado", reason)

    def test_unknown_tier_is_allowed_when_filter_is_unrestricted(self):
        allowed, tier, _reason = bot.validar_tier_item("Item OCR incompleto", ITEM_TIERS)

        self.assertTrue(allowed)
        self.assertIsNone(tier)


class CategoryNavigationTests(unittest.TestCase):
    def test_category_navigation_clicks_menu_then_category_without_ocr(self):
        geometry = ClientGeometry(0, 0, 1000, 700)
        points = iter(((100, 40), (120, 100)))
        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_point", side_effect=lambda *_: next(points)
        ), patch.object(bot, "safe_click", return_value=True) as click, patch.object(
            bot, "smart_sleep"
        ), patch.object(
            bot, "retornar_ao_topo", return_value=True
        ):
            changed = bot.executar_troca_categoria(
                object(), {}, "cat_clique_armas"
            )

        self.assertTrue(changed)
        self.assertEqual(
            [call.args[:2] for call in click.call_args_list],
            [(100, 40), (120, 100)],
        )


class ArtefatoCategoryTests(unittest.TestCase):
    """A categoria ARTEFATO (clique único no menu, igual às demais) precisa
    estar presente nos três lugares que hoje duplicam esse mapeamento:
    bot.CATEGORIA_CLIQUE_KEYS, interface.DEFAULT_CATEGORIES e o name_to_key
    interno de validate_calibration -- faltar em um deles deixa a categoria
    "invisível" para alguma parte do fluxo (navegação, UI ou validação)."""

    def test_artefato_is_registered_in_category_click_keys(self):
        self.assertEqual(
            bot.CATEGORIA_CLIQUE_KEYS.get("ARTEFATO"), "cat_clique_artefato"
        )

    def test_artefato_is_registered_in_default_categories(self):
        artefato = next(
            (c for c in interface.DEFAULT_CATEGORIES if c["name"] == "ARTEFATO"),
            None,
        )
        self.assertIsNotNone(artefato)
        self.assertEqual(artefato["key"], "cat_clique_artefato")
        self.assertTrue(artefato["enabled"])

    def test_artefato_click_is_required_when_active_and_enabled(self):
        geometry = ClientGeometry(0, 0, 1920, 1080)
        offsets = {key: [0.1, 0.1, 0.1, 0.1] for key in BUY_REQUIRED_KEYS}
        offsets[META_KEY] = calibration_metadata(geometry)
        offsets["cat_ativo"] = True
        offsets["cat_sequence"] = ["ARTEFATO"]
        offsets["cat_enabled"] = {"ARTEFATO": True}
        offsets["cat_clique_principal"] = [0.1, 0.1]

        valid, reason = validate_calibration(offsets, geometry, mode="buy")

        self.assertFalse(valid)
        self.assertIn("cat_clique_artefato", reason)

        offsets["cat_clique_artefato"] = [0.2, 0.2]
        valid, reason = validate_calibration(offsets, geometry, mode="buy")

        self.assertTrue(valid, reason)


if __name__ == "__main__":
    unittest.main()
