import unittest

from albionmkt_app.adapters import PurchaseEventNormalizer
from albionmkt_app.application import PurchaseEvent, PurchaseSource


class PurchaseEventNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = PurchaseEventNormalizer()

    def test_log_path_has_no_item_identity(self):
        event = self.normalizer.from_log(100.5)
        self.assertEqual(event, PurchaseEvent(100.5, PurchaseSource.LOG))

    def test_callback_path_preserves_real_name_and_profit(self):
        event = self.normalizer.from_callback(" Morgana Cape ", "3240")
        self.assertEqual(
            event,
            PurchaseEvent(3240.0, PurchaseSource.CALLBACK, "Morgana Cape"),
        )

    def test_invalid_callback_data_is_ignored(self):
        self.assertIsNone(self.normalizer.from_callback("", 10))
        self.assertIsNone(self.normalizer.from_callback("Item", "invalid"))

    def test_paths_remain_distinct_without_heuristic_deduplication(self):
        log_event = self.normalizer.from_log(100)
        callback_event = self.normalizer.from_callback("Item", 100)
        self.assertNotEqual(log_event, callback_event)


if __name__ == "__main__":
    unittest.main()

