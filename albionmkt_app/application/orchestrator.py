"""GUI-independent coordination of adapters, events, and application state."""

from __future__ import annotations

from threading import RLock

from .events import (
    ApplicationEventDispatcher,
    BotErrorReceived,
    BotStatusChanged,
    LicenseStateChanged,
    MarketObservationReceived,
    PurchaseCallbackReceived,
    PurchaseRecorded,
    SessionMetricsReset,
    SettingsChanged,
)
from .ports import BotControlPort, SettingsPort
from .state import ApplicationSnapshot, ApplicationState
from .types import (
    BotControlState,
    BotMode,
    LicenseState,
    MarketItemObservation,
    PurchaseEvent,
    SettingsLoadResult,
    SettingsSaveResult,
    SettingsSnapshot,
)
from ..adapters.bot_log import LegacyBotLogParser
from ..adapters.purchase import PurchaseEventNormalizer


class ApplicationOrchestrator:
    """Single application entry point for legacy data and future UI intents."""

    def __init__(
        self,
        bot_control: BotControlPort,
        settings: SettingsPort,
        *,
        parser: LegacyBotLogParser | None = None,
        purchases: PurchaseEventNormalizer | None = None,
        state: ApplicationState | None = None,
        events: ApplicationEventDispatcher | None = None,
    ) -> None:
        self.bot_control = bot_control
        self.settings = settings
        self.parser = parser or LegacyBotLogParser()
        self.purchases = purchases or PurchaseEventNormalizer()
        self.state = state or ApplicationState()
        self.events = events or ApplicationEventDispatcher()
        self._mutation_lock = RLock()

    def snapshot(self) -> ApplicationSnapshot:
        return self.state.snapshot()

    def handle_bot_log_line(
        self, line: object
    ) -> MarketObservationReceived | PurchaseRecorded | None:
        parsed = self.parser.parse(line)
        if isinstance(parsed, MarketItemObservation):
            event = MarketObservationReceived(parsed)
            self._apply_then_publish(event)
            return event
        if isinstance(parsed, PurchaseEvent):
            # [BUY] is always emitted before the optional callback in bot.py and
            # is the sole canonical source for purchase metrics.
            event = PurchaseRecorded(parsed)
            self._apply_then_publish(event)
            return event
        return None

    def handle_purchase_callback(
        self, item_name: object, estimated_profit: object
    ) -> PurchaseCallbackReceived | None:
        purchase = self.purchases.from_callback(item_name, estimated_profit)
        if purchase is None:
            return None
        event = PurchaseCallbackReceived(purchase)
        self.events.publish(event)
        return event

    def start_bot(self, mode: BotMode = BotMode.BUY) -> BotControlState:
        control = self.bot_control.request_start(mode)
        self._publish_control_state(control)
        return control

    def stop_bot(self) -> BotControlState:
        control = self.bot_control.request_stop()
        self._publish_control_state(control)
        return control

    def change_bot_mode(self, mode: BotMode) -> BotControlState:
        control = self.bot_control.update_mode(mode)
        self._publish_control_state(control)
        return control

    def refresh_bot_state(self) -> BotControlState:
        control = self.bot_control.read()
        self._publish_control_state(control)
        return control

    def load_settings(self) -> SettingsLoadResult:
        result = self.settings.load()
        if result.issue is None:
            self._apply_then_publish(SettingsChanged(result.snapshot))
        else:
            self._publish_settings_error(result.issue.kind.value, result.issue.message)
        return result

    def save_settings(self, snapshot: SettingsSnapshot) -> SettingsSaveResult:
        result = self.settings.save(snapshot)
        if result.success:
            self._apply_then_publish(SettingsChanged(snapshot))
        elif result.issue is not None:
            self._publish_settings_error(result.issue.kind.value, result.issue.message)
        return result

    def reset_session_metrics(self) -> ApplicationSnapshot:
        return self._apply_then_publish(SessionMetricsReset())

    def update_license_state(self, license_state: LicenseState) -> ApplicationSnapshot:
        return self._apply_then_publish(LicenseStateChanged(license_state))

    def _publish_control_state(self, control: BotControlState) -> ApplicationSnapshot:
        return self._apply_then_publish(
            BotStatusChanged(status=control.status, mode=control.known_mode)
        )

    def _publish_settings_error(self, code: str, message: str) -> ApplicationSnapshot:
        return self._apply_then_publish(
            BotErrorReceived(message=message, code=f"settings.{code}")
        )

    def _apply_then_publish(self, event: object) -> ApplicationSnapshot:
        # Only mutation and snapshot creation are serialized. Listener work is
        # deliberately outside this lock because the dispatcher is synchronous.
        with self._mutation_lock:
            self.state.apply(event)
            snapshot = self.state.snapshot()
        self.events.publish(event)
        return snapshot

