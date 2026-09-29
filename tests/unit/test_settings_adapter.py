import json
import tempfile
import unittest
from pathlib import Path

from albionmkt_app.adapters import LegacySettingsAdapter
from albionmkt_app.application import SettingsIssueKind, SettingsSnapshot


class LegacySettingsAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "offsets.json"
        self.adapter = LegacySettingsAdapter(self.path)

    def test_missing_file_returns_current_ui_defaults_without_writing(self):
        result = self.adapter.load()
        self.assertEqual(result.snapshot, SettingsSnapshot())
        self.assertIsNone(result.issue)
        self.assertFalse(self.path.exists())

    def test_loads_confirmed_settings_subset(self):
        self.path.write_text(
            json.dumps(
                {
                    "lucro": 28.0,
                    "valor_max": 20000,
                    "delay_clique": 0.4,
                    "delay_pagina": 0.8,
                    "cat_sequence": ["ARMAS", "BOLSAS"],
                    "cat_enabled": {"ARMAS": True, "BOLSAS": False},
                    "compra": [1, 2, 3, 4],
                }
            ),
            encoding="utf-8",
        )
        result = self.adapter.load()
        self.assertIsNone(result.issue)
        self.assertEqual(result.snapshot.minimum_profit_percentage, 72.0)
        self.assertEqual(result.snapshot.category_sequence, ("ARMAS", "BOLSAS"))
        self.assertFalse(result.snapshot.category_enabled["BOLSAS"])

    def test_save_preserves_unknown_and_operational_fields(self):
        original = {"compra": [1, 2, 3, 4], "future": {"keep": True}}
        self.path.write_text(json.dumps(original), encoding="utf-8")
        result = self.adapter.save(
            SettingsSnapshot(
                minimum_profit_percentage=35.5,
                max_purchase_value=45000,
                click_delay=0.04,
                page_delay=0.08,
                category_sequence=("BOLSAS",),
                category_enabled={"BOLSAS": True},
            )
        )
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(result.success)
        self.assertEqual(saved["compra"], [1, 2, 3, 4])
        self.assertEqual(saved["future"], {"keep": True})
        self.assertEqual(saved["delay_clique"], 0.05)
        self.assertEqual(saved["delay_pagina"], 0.1)

    def test_invalid_json_is_reported_and_not_overwritten(self):
        self.path.write_text("not-json", encoding="utf-8")
        loaded = self.adapter.load()
        saved = self.adapter.save(SettingsSnapshot())
        self.assertEqual(loaded.issue.kind, SettingsIssueKind.INVALID_JSON)
        self.assertFalse(saved.success)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "not-json")

    def test_invalid_values_return_controlled_default_snapshot(self):
        self.path.write_text(json.dumps({"lucro": "invalid"}), encoding="utf-8")
        result = self.adapter.load()
        self.assertEqual(result.snapshot, SettingsSnapshot())
        self.assertEqual(result.issue.kind, SettingsIssueKind.INVALID_VALUE)


if __name__ == "__main__":
    unittest.main()

