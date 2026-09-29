import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from albionmkt_app.application import (
    BotControlState,
    BotMode,
    BotStatus,
    LicenseState,
    LicenseStatus,
    SettingsIssue,
    SettingsIssueKind,
    SettingsLoadResult,
    SettingsSaveResult,
    SettingsSnapshot,
)
from albionmkt_app.application.orchestrator import ApplicationOrchestrator
from albionmkt_app.application.events import (
    BotErrorReceived,
    BotStatusChanged,
    LicenseStateChanged,
    MarketObservationReceived,
    PurchaseCallbackReceived,
    PurchaseRecorded,
    SessionMetricsReset,
    SettingsChanged,
)


class FakeBotControl:
    def __init__(self):
        self.state = BotControlState()
        self.calls = []

    def read(self):
        self.calls.append(("read",))
        return self.state

    def request_start(self, mode=BotMode.BUY):
        self.calls.append(("start", mode))
        self.state = BotControlState(True, mode.value)
        return self.state

    def request_stop(self):
        self.calls.append(("stop",))
        self.state = BotControlState(False, self.state.mode)
        return self.state

    def update_mode(self, mode):
        self.calls.append(("mode", mode))
        self.state = BotControlState(self.state.run, mode.value)
        return self.state


class FakeSettings:
    def __init__(self):
        self.load_result = SettingsLoadResult(SettingsSnapshot())
        self.save_result = SettingsSaveResult(True)
        self.saved = []

    def load(self):
        return self.load_result

    def save(self, snapshot):
        self.saved.append(snapshot)
        return self.save_result


class ApplicationOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.bot_control = FakeBotControl()
        self.settings = FakeSettings()
        self.app = ApplicationOrchestrator(self.bot_control, self.settings)

    def test_valid_data_updates_real_session_metrics(self):
        self.app.handle_bot_log_line("[DATA] Bag|1280|820|64.1%|0")
        self.app.handle_bot_log_line("[DATA] Cape|8450|5210|61.7%|1")
        snapshot = self.app.snapshot()
        self.assertEqual(snapshot.items_analyzed, 2)
        self.assertEqual(snapshot.opportunities, 1)
        self.assertEqual(snapshot.last_observation.item_name, "Cape")

    def test_invalid_log_does_not_change_metrics_or_publish(self):
        received = []
        self.app.events.subscribe(MarketObservationReceived, received.append)
        self.assertIsNone(self.app.handle_bot_log_line("[DATA] invalid"))
        self.assertEqual(self.app.snapshot().items_analyzed, 0)
        self.assertEqual(received, [])

    def test_buy_log_is_canonical_for_purchase_metrics(self):
        event = self.app.handle_bot_log_line("[BUY] 3240.5")
        snapshot = self.app.snapshot()
        self.assertIsInstance(event, PurchaseRecorded)
        self.assertEqual(snapshot.purchases_count, 1)
        self.assertEqual(snapshot.estimated_profit, 3240.5)
        self.assertEqual(snapshot.last_purchase, event.purchase)

    def test_callback_is_informative_and_does_not_duplicate_metrics(self):
        received = []
        self.app.events.subscribe(PurchaseCallbackReceived, received.append)
        self.app.handle_bot_log_line("[BUY] 100")
        callback_event = self.app.handle_purchase_callback("Bag", 100)
        snapshot = self.app.snapshot()
        self.assertEqual(snapshot.purchases_count, 1)
        self.assertEqual(snapshot.estimated_profit, 100.0)
        self.assertEqual(received, [callback_event])

    def test_callback_alone_does_not_create_canonical_purchase(self):
        event = self.app.handle_purchase_callback("Bag", 100)
        self.assertIsInstance(event, PurchaseCallbackReceived)
        self.assertEqual(self.app.snapshot().purchases_count, 0)

    def test_multiple_canonical_buys_accumulate(self):
        self.app.handle_bot_log_line("[BUY] 100.5")
        self.app.handle_bot_log_line("[BUY] 200")
        snapshot = self.app.snapshot()
        self.assertEqual(snapshot.purchases_count, 2)
        self.assertEqual(snapshot.estimated_profit, 300.5)

    def test_start_stop_mode_and_refresh_delegate_and_publish(self):
        received = []
        self.app.events.subscribe(BotStatusChanged, received.append)
        self.app.start_bot(BotMode.CLOSE)
        self.app.change_bot_mode(BotMode.BUY)
        self.app.refresh_bot_state()
        self.app.stop_bot()
        self.assertEqual(
            self.bot_control.calls,
            [
                ("start", BotMode.CLOSE),
                ("mode", BotMode.BUY),
                ("read",),
                ("stop",),
            ],
        )
        self.assertEqual(len(received), 4)
        self.assertEqual(self.app.snapshot().bot_status, BotStatus.STOPPED)
        self.assertEqual(self.app.snapshot().bot_mode, BotMode.BUY)

    def test_successful_settings_load_updates_state_and_publishes(self):
        settings = SettingsSnapshot(minimum_profit_percentage=25.0)
        self.settings.load_result = SettingsLoadResult(settings)
        received = []
        self.app.events.subscribe(SettingsChanged, received.append)
        result = self.app.load_settings()
        self.assertEqual(result.snapshot, settings)
        self.assertEqual(self.app.snapshot().settings, settings)
        self.assertEqual(received, [SettingsChanged(settings)])

    def test_settings_error_is_structured_and_does_not_replace_state(self):
        initial = self.app.snapshot().settings
        issue = SettingsIssue(SettingsIssueKind.INVALID_JSON, "invalid json")
        self.settings.load_result = SettingsLoadResult(SettingsSnapshot(), issue)
        received = []
        self.app.events.subscribe(BotErrorReceived, received.append)
        self.app.load_settings()
        self.assertEqual(self.app.snapshot().settings, initial)
        self.assertEqual(self.app.snapshot().last_error.code, "settings.invalid_json")
        self.assertEqual(received, [self.app.snapshot().last_error])

    def test_save_settings_delegates_then_updates_state(self):
        settings = SettingsSnapshot(max_purchase_value=45000)
        self.app.save_settings(settings)
        self.assertEqual(self.settings.saved, [settings])
        self.assertEqual(self.app.snapshot().settings, settings)

    def test_failed_save_publishes_error_without_updating_settings(self):
        issue = SettingsIssue(SettingsIssueKind.IO_ERROR, "disk failure")
        self.settings.save_result = SettingsSaveResult(False, issue)
        before = self.app.snapshot().settings
        self.app.save_settings(SettingsSnapshot(max_purchase_value=1))
        self.assertEqual(self.app.snapshot().settings, before)
        self.assertEqual(self.app.snapshot().last_error.code, "settings.io_error")

    def test_reset_session_metrics_preserves_non_session_state(self):
        settings = SettingsSnapshot(minimum_profit_percentage=20.0)
        license_state = LicenseState(LicenseStatus.VALID, code="OK")
        self.settings.load_result = SettingsLoadResult(settings)
        self.app.load_settings()
        self.app.update_license_state(license_state)
        self.app.handle_bot_log_line("[DATA] Cape|100|50|50%|1")
        self.app.handle_bot_log_line("[BUY] 50")
        self.settings.load_result = SettingsLoadResult(
            SettingsSnapshot(),
            SettingsIssue(SettingsIssueKind.INVALID_JSON, "old error"),
        )
        self.app.load_settings()
        self.app.reset_session_metrics()
        snapshot = self.app.snapshot()
        self.assertEqual(snapshot.items_analyzed, 0)
        self.assertEqual(snapshot.opportunities, 0)
        self.assertEqual(snapshot.purchases_count, 0)
        self.assertEqual(snapshot.estimated_profit, 0.0)
        self.assertIsNone(snapshot.last_observation)
        self.assertIsNone(snapshot.last_purchase)
        self.assertIsNone(snapshot.last_error)
        self.assertEqual(snapshot.settings, settings)
        self.assertEqual(snapshot.license_state, license_state)

    def test_reset_and_license_events_are_published(self):
        reset_events = []
        license_events = []
        self.app.events.subscribe(SessionMetricsReset, reset_events.append)
        self.app.events.subscribe(LicenseStateChanged, license_events.append)
        license_state = LicenseState(LicenseStatus.VALID, code="OK")
        self.app.reset_session_metrics()
        self.app.update_license_state(license_state)
        self.assertEqual(reset_events, [SessionMetricsReset()])
        self.assertEqual(license_events, [LicenseStateChanged(license_state)])

    def test_state_is_updated_before_listener_is_called(self):
        observed_counts = []

        def listener(_event):
            observed_counts.append(self.app.snapshot().items_analyzed)

        self.app.events.subscribe(MarketObservationReceived, listener)
        self.app.handle_bot_log_line("[DATA] Bag|100|50|50%|0")
        self.assertEqual(observed_counts, [1])

    def test_simple_concurrent_inputs_do_not_lose_increments(self):
        workers = 8
        messages = 200
        barrier = threading.Barrier(workers)

        def submit_batch(batch):
            barrier.wait()
            for index in batch:
                self.app.handle_bot_log_line(
                    f"[DATA] Item {index}|100|50|50%|1"
                )

        batches = [range(start, messages, workers) for start in range(workers)]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            list(executor.map(submit_batch, batches))
        snapshot = self.app.snapshot()
        self.assertEqual(snapshot.items_analyzed, messages)
        self.assertEqual(snapshot.opportunities, messages)


if __name__ == "__main__":
    unittest.main()
