import json
import tempfile
import unittest
from pathlib import Path

from albionmkt_app.adapters import BotControlAdapter
from albionmkt_app.application import BotMode, BotStatus


class BotControlAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "bot_control.json"
        self.adapter = BotControlAdapter(self.path)

    def read_payload(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_missing_and_invalid_files_use_legacy_stopped_buy_default(self):
        state = self.adapter.read()
        self.assertFalse(state.run)
        self.assertEqual(state.mode, "buy")
        self.assertEqual(state.status, BotStatus.STOPPED)
        self.path.write_text("invalid", encoding="utf-8")
        self.assertEqual(self.adapter.read().mode, "buy")

    def test_request_start_writes_exact_legacy_fields(self):
        state = self.adapter.request_start(BotMode.CLOSE)
        self.assertTrue(state.run)
        self.assertEqual(self.read_payload(), {"run": True, "mode": "close"})

    def test_request_stop_preserves_current_mode(self):
        self.path.write_text(
            json.dumps({"run": True, "mode": "close"}), encoding="utf-8"
        )
        state = self.adapter.request_stop()
        self.assertFalse(state.run)
        self.assertEqual(self.read_payload(), {"run": False, "mode": "close"})

    def test_update_mode_preserves_run_value(self):
        self.path.write_text(
            json.dumps({"run": True, "mode": "buy"}), encoding="utf-8"
        )
        self.adapter.update_mode(BotMode.CLOSE)
        self.assertEqual(self.read_payload(), {"run": True, "mode": "close"})

    def test_known_mode_reports_only_stable_legacy_modes(self):
        self.path.write_text(
            json.dumps({"run": False, "mode": "future"}), encoding="utf-8"
        )
        self.assertIsNone(self.adapter.read().known_mode)


if __name__ == "__main__":
    unittest.main()

