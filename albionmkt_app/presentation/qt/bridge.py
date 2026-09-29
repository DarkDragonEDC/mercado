"""Thread boundary between application events and Qt widgets."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from ...application.events import (
    ApplicationEventDispatcher,
    BotErrorReceived,
    BotStatusChanged,
    LicenseStateChanged,
    MarketObservationReceived,
    PurchaseRecorded,
    SessionMetricsReset,
    SettingsChanged,
)
from ...application.orchestrator import ApplicationOrchestrator


class QtApplicationBridge(QObject):
    """Emit Qt signals without calling widgets from producer threads."""

    state_changed = Signal(object)
    bot_status_changed = Signal(object)
    market_observation_received = Signal(object)
    purchase_recorded = Signal(object)
    application_error = Signal(object)

    def __init__(
        self,
        orchestrator: ApplicationOrchestrator,
        dispatcher: ApplicationEventDispatcher,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._unsubscribers: list[Callable[[], None]] = []
        self._closed = False
        self._subscribe(dispatcher)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    def _subscribe(self, dispatcher: ApplicationEventDispatcher) -> None:
        subscriptions = (
            (MarketObservationReceived, self._on_market_observation),
            (PurchaseRecorded, self._on_purchase_recorded),
            (BotStatusChanged, self._on_bot_status_changed),
            (SettingsChanged, self._on_state_only),
            (LicenseStateChanged, self._on_state_only),
            (SessionMetricsReset, self._on_state_only),
            (BotErrorReceived, self._on_application_error),
        )
        for event_type, listener in subscriptions:
            self._unsubscribers.append(dispatcher.subscribe(event_type, listener))

    def _emit_state(self) -> None:
        if not self._closed:
            self.state_changed.emit(self._orchestrator.snapshot())

    def _on_market_observation(self, event: MarketObservationReceived) -> None:
        if self._closed:
            return
        self._emit_state()
        self.market_observation_received.emit(event.observation)

    def _on_purchase_recorded(self, event: PurchaseRecorded) -> None:
        if self._closed:
            return
        self._emit_state()
        self.purchase_recorded.emit(event.purchase)

    def _on_bot_status_changed(self, event: BotStatusChanged) -> None:
        if self._closed:
            return
        snapshot = self._orchestrator.snapshot()
        self.state_changed.emit(snapshot)
        self.bot_status_changed.emit(snapshot)

    def _on_application_error(self, event: BotErrorReceived) -> None:
        if self._closed:
            return
        self._emit_state()
        self.application_error.emit(event)

    def _on_state_only(self, _event: object) -> None:
        self._emit_state()

