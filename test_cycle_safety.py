import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bot


class CycleCounterSafetyTests(unittest.TestCase):
    def test_accepts_two_equal_plausible_reads_at_limit(self):
        self.assertTrue(bot.contador_ciclo_confirmado(2, 2, 2))

    def test_rejects_different_consecutive_reads(self):
        self.assertFalse(bot.contador_ciclo_confirmado(2, 3, 2))

    def test_rejects_impossible_ocr_value(self):
        self.assertFalse(bot.contador_ciclo_confirmado(41666, 41666, 2))

    def test_rejects_value_below_limit(self):
        self.assertFalse(bot.contador_ciclo_confirmado(1, 1, 2))

    def test_cycle_limit_is_capped_at_game_capacity(self):
        self.assertEqual(bot.get_cycle_order_limit({"cycle_order_limit": 49}), 48)
        self.assertEqual(bot.get_cycle_order_limit({"cycle_order_limit": 2}), 2)


class PreservePositionControlTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.control_path = Path(self._tmpdir.name) / "bot_control.json"
        self._patch = patch("bot.CONTROL_FILE", str(self.control_path))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def _write(self, payload):
        with open(self.control_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_missing_file_never_preserves_position(self):
        self.assertFalse(bot.controle_deve_preservar_posicao())

    def test_pause_requests_preserving_position(self):
        self._write({"run": False, "mode": "buy", "preserve_position": True})
        self.assertTrue(bot.controle_deve_preservar_posicao())

    def test_stop_does_not_preserve_position(self):
        self._write({"run": False, "mode": "buy", "preserve_position": False})
        self.assertFalse(bot.controle_deve_preservar_posicao())

    def test_legacy_file_without_field_defaults_to_no_preservation(self):
        self._write({"run": False, "mode": "buy"})
        self.assertFalse(bot.controle_deve_preservar_posicao())


if __name__ == "__main__":
    unittest.main()
