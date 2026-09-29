"""Explicit, failure-tolerant parser for legacy bot log markers."""

from __future__ import annotations

from ..application.types import MarketItemObservation, PurchaseEvent
from .purchase import PurchaseEventNormalizer


class LegacyBotLogParser:
    DATA_MARKER = "[DATA]"
    BUY_MARKER = "[BUY]"

    def __init__(self, purchases: PurchaseEventNormalizer | None = None) -> None:
        self._purchases = purchases or PurchaseEventNormalizer()

    def parse(self, message: object) -> MarketItemObservation | PurchaseEvent | None:
        if not isinstance(message, str):
            return None
        line = message.strip()
        if self._has_marker(line, self.DATA_MARKER):
            return self._parse_data(line[len(self.DATA_MARKER) :].strip())
        if self._has_marker(line, self.BUY_MARKER):
            return self._parse_buy(line[len(self.BUY_MARKER) :].strip())
        return None

    @staticmethod
    def _has_marker(line: str, marker: str) -> bool:
        return line.startswith(marker) and (
            len(line) == len(marker) or line[len(marker)].isspace()
        )

    @staticmethod
    def _parse_data(payload: str) -> MarketItemObservation | None:
        fields = [field.strip() for field in payload.split("|")]
        if len(fields) != 5 or not fields[0]:
            return None
        try:
            sell_price = int(fields[1])
            buy_price = int(fields[2])
            percentage_text = fields[3]
            if not percentage_text.endswith("%"):
                return None
            cost_percentage = float(percentage_text[:-1].strip())
            if fields[4] not in {"0", "1"}:
                return None
        except (TypeError, ValueError):
            return None
        return MarketItemObservation(
            item_name=fields[0],
            sell_price=sell_price,
            buy_price=buy_price,
            cost_percentage=cost_percentage,
            opportunity=fields[4] == "1",
        )

    def _parse_buy(self, payload: str) -> PurchaseEvent | None:
        try:
            estimated_profit = float(payload)
        except (TypeError, ValueError):
            return None
        return self._purchases.from_log(estimated_profit)

