import unittest

from albionmkt_app.application import (
    BotMode,
    BotStatus,
    LicenseState,
    LicenseStatus,
    MarketItemObservation,
    PurchaseEvent,
    PurchaseSource,
    SettingsSnapshot,
)
from albionmkt_app.application.events import (
    BotErrorReceived,
    BotStatusChanged,
    LicenseStateChanged,
    MarketObservationReceived,
    PurchaseRecorded,
    SettingsChanged,
)
from albionmkt_app.application.state import ApplicationState


class ApplicationStateTests(unittest.TestCase):
    def test_initial_state_contains_only_real_zero_or_unknown_values(self):
        snapshot = ApplicationState().snapshot()
        self.assertEqual(snapshot.bot_status, BotStatus.STOPPED)
        self.assertEqual(snapshot.bot_mode, BotMode.BUY)
        self.assertEqual(snapshot.analyzed_items, 0)
        self.assertEqual(snapshot.opportunities, 0)
        self.assertEqual(snapshot.purchases, 0)
        self.assertEqual(snapshot.estimated_profit, 0.0)
        self.assertEqual(snapshot.license_state.status, LicenseStatus.UNKNOWN)

    def test_observations_derive_session_counts(self):
        state = ApplicationState()
        first = MarketItemObservation("Bag", 100, 70, 70.0, False)
        second = MarketItemObservation("Cape", 100, 50, 50.0, True)
        state.apply(MarketObservationReceived(first))
        state.apply(MarketObservationReceived(second))
        snapshot = state.snapshot()
        self.assertEqual(snapshot.analyzed_items, 2)
        self.assertEqual(snapshot.opportunities, 1)
        self.assertEqual(snapshot.last_observation, second)

    def test_purchases_accumulate_current_estimated_profit(self):
        state = ApplicationState()
        first = PurchaseEvent(100.5, PurchaseSource.LOG)
        second = PurchaseEvent(200.0, PurchaseSource.CALLBACK, "Cape")
        state.apply(PurchaseRecorded(first))
        state.apply(PurchaseRecorded(second))
        snapshot = state.snapshot()
        self.assertEqual(snapshot.purchases, 2)
        self.assertEqual(snapshot.estimated_profit, 300.5)
        self.assertEqual(snapshot.last_purchase, second)

    def test_status_settings_license_and_error_are_replaced_by_events(self):
        state = ApplicationState()
        settings = SettingsSnapshot(minimum_profit_percentage=25.0)
        license_state = LicenseState(LicenseStatus.VALID, code="OK")
        error = BotErrorReceived("temporary", "E1")
        state.apply(BotStatusChanged(BotStatus.RUNNING, BotMode.CLOSE))
        state.apply(SettingsChanged(settings))
        state.apply(LicenseStateChanged(license_state))
        state.apply(error)
        snapshot = state.snapshot()
        self.assertEqual(snapshot.bot_status, BotStatus.RUNNING)
        self.assertEqual(snapshot.bot_mode, BotMode.CLOSE)
        self.assertEqual(snapshot.settings, settings)
        self.assertEqual(snapshot.license_state, license_state)
        self.assertEqual(snapshot.last_error, error)

    def test_unknown_events_do_not_mutate_state(self):
        state = ApplicationState()
        before = state.snapshot()
        state.apply(object())
        self.assertEqual(state.snapshot(), before)

    def test_snapshot_does_not_expose_mutable_category_mapping(self):
        state = ApplicationState()
        settings = SettingsSnapshot(category_enabled={"ARMAS": True})
        state.apply(SettingsChanged(settings))
        snapshot = state.snapshot()
        with self.assertRaises(TypeError):
            snapshot.settings.category_enabled["ARMAS"] = False


if __name__ == "__main__":
    unittest.main()
