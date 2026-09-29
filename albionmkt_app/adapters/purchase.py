"""Normalize the two existing purchase notification paths."""

from __future__ import annotations

from ..application.types import PurchaseEvent, PurchaseSource


class PurchaseEventNormalizer:
    """Create consistent events without attempting heuristic deduplication."""

    def from_log(self, estimated_profit: float) -> PurchaseEvent:
        return PurchaseEvent(
            estimated_profit=float(estimated_profit),
            source=PurchaseSource.LOG,
        )

    def from_callback(
        self, item_name: object, estimated_profit: object
    ) -> PurchaseEvent | None:
        try:
            normalized_name = str(item_name).strip()
            normalized_profit = float(estimated_profit)
        except (TypeError, ValueError):
            return None
        if not normalized_name:
            return None
        return PurchaseEvent(
            item_name=normalized_name,
            estimated_profit=normalized_profit,
            source=PurchaseSource.CALLBACK,
        )

