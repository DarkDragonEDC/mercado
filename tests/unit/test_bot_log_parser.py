import unittest

from albionmkt_app.adapters import LegacyBotLogParser
from albionmkt_app.application import (
    MarketItemObservation,
    PurchaseEvent,
    PurchaseSource,
)


class LegacyBotLogParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = LegacyBotLogParser()

    def test_parses_real_data_protocol_into_typed_observation(self):
        result = self.parser.parse("[DATA] Morgana Cape .1|8450|5210|61.7%|1")
        self.assertEqual(
            result,
            MarketItemObservation("Morgana Cape .1", 8450, 5210, 61.7, True),
        )

    def test_parses_buy_protocol_without_inventing_item_name(self):
        result = self.parser.parse("[BUY] 3240.5")
        self.assertEqual(result, PurchaseEvent(3240.5, PurchaseSource.LOG))

    def test_ignores_common_and_non_string_messages(self):
        self.assertIsNone(self.parser.parse("bot iniciou normalmente"))
        self.assertIsNone(self.parser.parse(None))

    def test_rejects_missing_or_extra_data_fields(self):
        self.assertIsNone(self.parser.parse("[DATA] name|1|2|50%"))
        self.assertIsNone(self.parser.parse("[DATA] name|1|2|50%|1|extra"))

    def test_rejects_invalid_numbers_percentage_and_opportunity(self):
        invalid = (
            "[DATA] name|abc|2|50%|1",
            "[DATA] name|1|abc|50%|1",
            "[DATA] name|1|2|abc%|1",
            "[DATA] name|1|2|50|1",
            "[DATA] name|1|2|50%|yes",
            "[BUY] not-a-number",
        )
        for message in invalid:
            with self.subTest(message=message):
                self.assertIsNone(self.parser.parse(message))

    def test_accepts_protocol_whitespace_without_relaxing_marker(self):
        result = self.parser.parse("  [DATA]   Bag | 1280 | 820 | 64.1% | 0  ")
        self.assertEqual(result, MarketItemObservation("Bag", 1280, 820, 64.1, False))
        self.assertIsNone(self.parser.parse("[DATA]name|1|2|50%|1"))


if __name__ == "__main__":
    unittest.main()

