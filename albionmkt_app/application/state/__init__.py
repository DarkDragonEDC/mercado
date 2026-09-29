"""In-memory state derived exclusively from real application events."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from ..events import (
    BotErrorReceived,
    BotStatusChanged,
    LicenseStateChanged,
    MarketObservationReceived,
    PurchaseRecorded,
    SessionMetricsReset,
    SettingsChanged,
)
from ..types import (
    BotMode,
    BotStatus,
    LicenseState,
    MarketItemObservation,
    PurchaseEvent,
    SettingsSnapshot,
)


@dataclass(frozen=True)
class ApplicationSnapshot:
    bot_status: BotStatus
    bot_mode: BotMode
    analyzed_items: int
    opportunities: int
    purchases: int
    estimated_profit: float
    last_observation: MarketItemObservation | None
    last_purchase: PurchaseEvent | None
    settings: SettingsSnapshot
    license_state: LicenseState
    last_error: BotErrorReceived | None

    @property
    def items_analyzed(self) -> int:
        return self.analyzed_items

    @property
    def purchases_count(self) -> int:
        return self.purchases


class ApplicationState:
    def __init__(self) -> None:
        self._lock = RLock()
        self._bot_status = BotStatus.STOPPED
        self._bot_mode = BotMode.BUY
        self._analyzed_items = 0
        self._opportunities = 0
        self._purchases = 0
        self._estimated_profit = 0.0
        self._last_observation: MarketItemObservation | None = None
        self._last_purchase: PurchaseEvent | None = None
        self._settings = SettingsSnapshot()
        self._license_state = LicenseState()
        self._last_error: BotErrorReceived | None = None

    def apply(self, event: object) -> None:
        with self._lock:
            if isinstance(event, MarketObservationReceived):
                self._analyzed_items += 1
                self._last_observation = event.observation
                if event.observation.opportunity:
                    self._opportunities += 1
            elif isinstance(event, PurchaseRecorded):
                self._purchases += 1
                self._estimated_profit += event.purchase.estimated_profit
                self._last_purchase = event.purchase
            elif isinstance(event, BotStatusChanged):
                self._bot_status = event.status
                if event.mode is not None:
                    self._bot_mode = event.mode
            elif isinstance(event, SettingsChanged):
                self._settings = event.settings
            elif isinstance(event, LicenseStateChanged):
                self._license_state = event.license_state
            elif isinstance(event, BotErrorReceived):
                self._last_error = event
            elif isinstance(event, SessionMetricsReset):
                self._analyzed_items = 0
                self._opportunities = 0
                self._purchases = 0
                self._estimated_profit = 0.0
                self._last_observation = None
                self._last_purchase = None
                self._last_error = None

    def snapshot(self) -> ApplicationSnapshot:
        with self._lock:
            return ApplicationSnapshot(
                bot_status=self._bot_status,
                bot_mode=self._bot_mode,
                analyzed_items=self._analyzed_items,
                opportunities=self._opportunities,
                purchases=self._purchases,
                estimated_profit=self._estimated_profit,
                last_observation=self._last_observation,
                last_purchase=self._last_purchase,
                settings=self._settings,
                license_state=self._license_state,
                last_error=self._last_error,
            )


__all__ = ["ApplicationSnapshot", "ApplicationState"]
