import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from coordinate_system import ClientGeometry
from preset_visual_validation import validate_buy_preset_passively
from test_calibration_presets import buy_preset, buy_settings


def patterned_image(width, height, *, invert=False):
    data = np.zeros((height, width, 3), dtype=np.uint8)
    data[:, :] = 30 if not invert else 220
    data[::2, ::2] = 230 if not invert else 20
    data[height // 3: height // 2, width // 4: width * 3 // 4] = (90, 170, 240)
    return Image.fromarray(data, mode="RGB")


class PassivePresetValidationTests(unittest.TestCase):
    def _fixture(self, root):
        assets = root / "assets"
        assets.mkdir()
        anchor = patterned_image(24, 24)
        order = patterned_image(36, 18, invert=True)
        anchor.save(assets / "anchor.png")
        order.save(assets / "order.png")
        preset = buy_preset()
        preset["templates"] = {
            "anchor": {
                "path": "assets/anchor.png",
                "sha256": hashlib.sha256((assets / "anchor.png").read_bytes()).hexdigest(),
            },
            "purchase_order": {
                "path": "assets/order.png",
                "sha256": hashlib.sha256((assets / "order.png").read_bytes()).hexdigest(),
            },
        }
        return preset, anchor, order

    def test_validates_multiple_visual_references_without_clicking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preset, anchor, order = self._fixture(root)
            content = patterned_image(70, 24)
            with patch(
                "preset_visual_validation.get_client_geometry",
                return_value=ClientGeometry(0, 0, 1920, 1080),
            ), patch(
                "preset_visual_validation.bot.ensure_game_region_visible",
                return_value=(True, "visivel"),
            ), patch(
                "preset_visual_validation.capture_region",
                side_effect=[anchor, order, content, content, content],
            ), patch("preset_visual_validation.bot.safe_click") as click:
                result = validate_buy_preset_passively(
                    object(), preset, buy_settings(), asset_root=root
                )

        self.assertTrue(result.passed)
        click.assert_not_called()
        self.assertEqual(6, len(result.evidence))

    def test_covered_window_stops_before_image_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preset, _anchor, _order = self._fixture(root)
            with patch(
                "preset_visual_validation.get_client_geometry",
                return_value=ClientGeometry(0, 0, 1920, 1080),
            ), patch(
                "preset_visual_validation.bot.ensure_game_region_visible",
                return_value=(False, "coberta"),
            ), patch("preset_visual_validation.capture_region") as capture:
                result = validate_buy_preset_passively(
                    object(), preset, buy_settings(), asset_root=root
                )

        self.assertFalse(result.passed)
        capture.assert_not_called()

    def test_blank_market_fields_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preset, anchor, order = self._fixture(root)
            blank = Image.new("RGB", (70, 24), "#111111")
            with patch(
                "preset_visual_validation.get_client_geometry",
                return_value=ClientGeometry(0, 0, 1920, 1080),
            ), patch(
                "preset_visual_validation.bot.ensure_game_region_visible",
                return_value=(True, "visivel"),
            ), patch(
                "preset_visual_validation.capture_region",
                side_effect=[anchor, order, blank, blank, blank],
            ):
                result = validate_buy_preset_passively(
                    object(), preset, buy_settings(), asset_root=root
                )

        self.assertFalse(result.passed)
        self.assertIn("Selecione um item", result.summary)

    def test_mismatch_explains_required_hud_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preset, anchor, order = self._fixture(root)
            preset["target"]["game_ui_scale"] = "94%"
            content = patterned_image(70, 24)
            with patch(
                "preset_visual_validation.get_client_geometry",
                return_value=ClientGeometry(0, 0, 1920, 1080),
            ), patch(
                "preset_visual_validation.bot.ensure_game_region_visible",
                return_value=(True, "visivel"),
            ), patch(
                "preset_visual_validation.capture_region",
                side_effect=[anchor, order, content, content, content],
            ), patch(
                "preset_visual_validation._template_score",
                side_effect=[0.1, 0.2],
            ):
                result = validate_buy_preset_passively(
                    object(), preset, buy_settings(), asset_root=root
                )

        self.assertFalse(result.passed)
        self.assertIn("HUD em 94%", result.summary)


if __name__ == "__main__":
    unittest.main()
