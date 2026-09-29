import unittest

import cv2
import numpy as np
from PIL import Image

import bot


def _solid_rgb_from_hsv(hue: int, size: int = 40) -> Image.Image:
    hsv = np.zeros((size, size, 3), dtype=np.uint8)
    hsv[:, :, 0] = hue
    hsv[:, :, 1] = 255
    hsv[:, :, 2] = 255
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


class EnchantmentDiagnosticTests(unittest.TestCase):
    def test_color_match_exposes_evidence_used_by_classifier(self):
        value, diagnostic = bot.analisar_encantamento_icone(
            _solid_rgb_from_hsv(88)
        )

        self.assertEqual(value, ".2")
        self.assertEqual(diagnostic["value"], ".2")
        self.assertEqual(diagnostic["status"], "color_match")
        self.assertGreaterEqual(diagnostic["winner_pixels"], 35)
        self.assertEqual(diagnostic["winner"], ".2")
        self.assertGreater(diagnostic["margin_pixels"], 0)

    def test_low_saturation_preserves_zero_default_and_explains_reason(self):
        image = Image.new("RGB", (40, 40), (120, 120, 120))

        value, diagnostic = bot.analisar_encantamento_icone(image)

        self.assertEqual(value, ".0")
        self.assertEqual(diagnostic["value"], ".0")
        self.assertEqual(diagnostic["status"], "default_zero_insufficient_color")
        self.assertEqual(diagnostic["neon_pixels"], 0)

    def test_invalid_image_fails_closed_with_diagnostic_status(self):
        value, diagnostic = bot.analisar_encantamento_icone(None)

        self.assertEqual(value, "")
        self.assertEqual(diagnostic["status"], "error")
        self.assertTrue(diagnostic["error_type"])


class PriceReadDiagnosticTests(unittest.TestCase):
    def test_price_status_does_not_claim_empty_capture_is_no_liquidity(self):
        self.assertEqual(bot._price_read_status([], 0), "empty_capture")

    def test_price_status_recognizes_explicit_no_offer(self):
        self.assertEqual(bot._price_read_status(["N/A"], 0), "explicit_no_offer")

    def test_price_status_distinguishes_parsed_and_unparsed_text(self):
        self.assertEqual(bot._price_read_status(["12.345"], 12345), "parsed")
        self.assertEqual(bot._price_read_status(["I2?A"], 0), "unparsed_text")


if __name__ == "__main__":
    unittest.main()
