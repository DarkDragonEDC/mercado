import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coordinate_system import (
    BUY_REQUIRED_KEYS,
    CYCLE_REQUIRED_KEYS,
    SELL_REQUIRED_KEYS,
    ClientGeometry,
    MAX_SETTINGS_FILE_SIZE,
    META_KEY,
    normalize_point,
    normalize_rect,
    prepare_for_calibration,
    resolve_point,
    resolve_rect,
    save_settings,
    load_settings,
    strip_spatial_settings,
    validate_calibration,
)


class CoordinateSystemTests(unittest.TestCase):
    def setUp(self):
        self.geometry = ClientGeometry(left=100, top=50, width=1600, height=900)

    def test_point_round_trip_uses_client_origin(self):
        data, _ = prepare_for_calibration({}, self.geometry)
        data["btn_mais"] = normalize_point(500, 275, self.geometry)
        self.assertEqual(resolve_point(data["btn_mais"], self.geometry, data), (500, 275))

    def test_small_coordinates_are_not_added_to_anchor(self):
        data, _ = prepare_for_calibration({}, self.geometry)
        data["ancora"] = normalize_point(1400, 700, self.geometry)
        data["btn_mais"] = normalize_point(220, 150, self.geometry)
        self.assertEqual(resolve_point(data["btn_mais"], self.geometry, data), (220, 150))

    def test_rect_scales_to_same_proportion_on_larger_window(self):
        data, _ = prepare_for_calibration({}, self.geometry)
        data["area_lista"] = normalize_rect(500, 275, 800, 450, self.geometry)
        larger = ClientGeometry(left=20, top=30, width=1920, height=1080)
        self.assertEqual(resolve_rect(data["area_lista"], larger, data), (500, 300, 960, 540))

    def test_legacy_spatial_values_are_removed_but_preferences_remain(self):
        legacy = {"btn_mais": [873, 617], "lucro": 28.0, "cat_ativo": False}
        stripped = strip_spatial_settings(legacy)
        self.assertNotIn("btn_mais", stripped)
        self.assertEqual(stripped["lucro"], 28.0)

    def test_aspect_ratio_change_invalidates_profile(self):
        data, _ = prepare_for_calibration({}, self.geometry)
        ok, reason = validate_calibration(
            data,
            ClientGeometry(0, 0, 1280, 1024),
            required_keys=[],
        )
        self.assertFalse(ok)
        self.assertIn("formato", reason.lower())

    def test_window_resize_invalidates_profile_even_with_same_aspect(self):
        data, _ = prepare_for_calibration({}, self.geometry)
        ok, reason = validate_calibration(
            data,
            ClientGeometry(0, 0, 1920, 1080),
            required_keys=[],
        )
        self.assertFalse(ok)
        self.assertIn("tamanho", reason.lower())

    def test_buy_validation_requires_all_fields(self):
        data, _ = prepare_for_calibration({}, self.geometry)
        for key in BUY_REQUIRED_KEYS:
            data[key] = normalize_point(500, 275, self.geometry)
        ok, reason = validate_calibration(data, self.geometry, mode="buy")
        self.assertTrue(ok, reason)

    def test_atomic_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "offsets.json")
            payload = {"lucro": 25.0, META_KEY: {"schema_version": 2}}
            save_settings(path, payload)
            self.assertEqual(load_settings(path), payload)
            self.assertFalse(Path(path + ".tmp").exists())

    def test_save_settings_retries_transient_permission_error(self):
        # No Windows, um os.replace pode falhar com PermissionError quando
        # outro processo (ex.: a interface lendo o mesmo arquivo) tem o
        # destino aberto no instante exato da troca. Isso derrubava a
        # automacao inteira por uma disputa passageira; agora tenta de novo.
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "offsets.json")
            payload = {"lucro": 25.0}
            falhas_restantes = [2]
            real_replace = os.replace

            def replace_falha_depois_sucesso(src, dst):
                if falhas_restantes[0] > 0:
                    falhas_restantes[0] -= 1
                    raise PermissionError("acesso negado (simulado)")
                return real_replace(src, dst)

            with patch("coordinate_system.os.replace", side_effect=replace_falha_depois_sucesso), \
                 patch("coordinate_system.time.sleep"):
                save_settings(path, payload)
            self.assertEqual(load_settings(path), payload)
            self.assertEqual(falhas_restantes[0], 0)

    def test_save_settings_gives_up_after_persistent_permission_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "offsets.json")
            with patch(
                "coordinate_system.os.replace",
                side_effect=PermissionError("acesso negado (simulado)"),
            ) as replace, patch("coordinate_system.time.sleep"):
                with self.assertRaises(PermissionError):
                    save_settings(path, {"lucro": 25.0})
            self.assertEqual(replace.call_count, 5)

    def test_oversized_settings_are_rejected_without_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offsets.json"
            with path.open("wb") as handle:
                handle.seek(MAX_SETTINGS_FILE_SIZE)
                handle.write(b"}")

            self.assertEqual(load_settings(str(path)), {})

    def test_sell_validation_is_independent_from_buy_fields(self):
        data, _ = prepare_for_calibration({}, self.geometry)
        for key in SELL_REQUIRED_KEYS:
            data[key] = normalize_point(500, 275, self.geometry)
        ok, reason = validate_calibration(data, self.geometry, mode="sell")
        self.assertTrue(ok, reason)
        self.assertFalse(any(key in data for key in BUY_REQUIRED_KEYS))

    def test_cycle_validation_reuses_buy_sell_and_cycle_fields(self):
        data, _ = prepare_for_calibration({}, self.geometry)
        for key in BUY_REQUIRED_KEYS | SELL_REQUIRED_KEYS | CYCLE_REQUIRED_KEYS:
            data[key] = normalize_point(500, 275, self.geometry)
        ok, reason = validate_calibration(data, self.geometry, mode="cycle")
        self.assertTrue(ok, reason)

        data.pop("cycle_collect_all")
        ok, reason = validate_calibration(data, self.geometry, mode="cycle")
        self.assertFalse(ok)
        self.assertIn("cycle_collect_all", reason)


if __name__ == "__main__":
    unittest.main()
