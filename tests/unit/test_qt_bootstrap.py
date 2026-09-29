import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from albionmkt_app.application import BotMode
from albionmkt_app.presentation.qt.app import build_application
from albionmkt_app.presentation.qt.bridge import QtApplicationBridge
from albionmkt_app.presentation.qt.windows import MainWindow


class QtBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime = build_application(
            [],
            data_directory=self.temporary.name,
            application=self.application,
        )
        self.window = self.runtime.window

    def tearDown(self):
        self.window.close()
        self.application.processEvents()

    def test_qapplication_and_minimal_window_can_be_created(self):
        self.assertIsInstance(self.runtime.application, QApplication)
        self.assertIsInstance(self.window, MainWindow)
        self.assertEqual(self.window.windowTitle(), "AlbionMKT")
        self.assertGreaterEqual(self.window.minimumWidth(), 800)

    def test_bridge_can_be_created_without_backend_runtime(self):
        self.assertIsInstance(self.runtime.bridge, QtApplicationBridge)
        self.assertNotIn("easyocr", sys.modules)

    def test_application_event_emits_corresponding_qt_signal(self):
        spy = QSignalSpy(self.runtime.bridge.market_observation_received)
        self.runtime.orchestrator.handle_bot_log_line(
            "[DATA] Morgana Cape|8450|5210|61.7%|1"
        )
        self.assertEqual(spy.count(), 1)

    def test_worker_thread_event_reaches_widget_via_queued_signal(self):
        worker = threading.Thread(
            target=self.runtime.orchestrator.handle_bot_log_line,
            args=("[DATA] Bag|1280|820|64.1%|0",),
        )
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        QTest.qWait(20)
        self.assertEqual(self.window.items_label.text(), "1")
        self.assertIn("Bag", self.window.last_event_label.text())

    def test_start_button_calls_orchestrator(self):
        wrapped = Mock(wraps=self.runtime.orchestrator)
        self.window._orchestrator = wrapped
        QTest.mouseClick(self.window.start_button, Qt.MouseButton.LeftButton)
        wrapped.start_bot.assert_called_once_with(BotMode.BUY)

    def test_stop_button_calls_orchestrator(self):
        wrapped = Mock(wraps=self.runtime.orchestrator)
        self.window._orchestrator = wrapped
        QTest.mouseClick(self.window.stop_button, Qt.MouseButton.LeftButton)
        wrapped.stop_bot.assert_called_once_with()

    def test_mode_change_calls_orchestrator(self):
        wrapped = Mock(wraps=self.runtime.orchestrator)
        self.window._orchestrator = wrapped
        self.window.mode_combo.setCurrentIndex(1)
        wrapped.change_bot_mode.assert_called_once_with(BotMode.CLOSE)

    def test_settings_are_loaded_from_injected_real_contract(self):
        self.window.close()
        Path(self.temporary.name, "offsets.json").write_text(
            json.dumps({"lucro": 28.0, "valor_max": 20000}),
            encoding="utf-8",
        )
        self.runtime = build_application(
            [],
            data_directory=self.temporary.name,
            application=self.application,
        )
        self.window = self.runtime.window
        self.assertEqual(self.window.max_percentage_label.text(), "72%")
        self.assertEqual(self.window.max_value_label.text(), "20,000")

    def test_invalid_settings_show_error_without_breaking_window(self):
        self.window.close()
        Path(self.temporary.name, "offsets.json").write_text(
            "invalid-json", encoding="utf-8"
        )
        self.runtime = build_application(
            [],
            data_directory=self.temporary.name,
            application=self.application,
        )
        self.window = self.runtime.window
        self.assertTrue(self.window.error_label.text().startswith("Erro:"))
        self.assertEqual(self.window.items_label.text(), "0")

    def test_close_cleans_bridge_listeners(self):
        self.window.close()
        self.application.processEvents()
        self.assertTrue(self.runtime.bridge.is_closed)

    def test_import_does_not_create_qapplication_or_load_heavy_backend(self):
        script = (
            "import sys; "
            "from PySide6.QtWidgets import QApplication; "
            "import albionmkt_app.presentation.qt.app; "
            "print(QApplication.instance() is None); "
            "print(','.join(name for name in "
            "('bot','interface','easyocr','torch') if name in sys.modules))"
        )
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], "True")
        self.assertEqual(lines[1] if len(lines) > 1 else "", "")

    def test_composition_root_does_not_load_bot_ocr_or_torch(self):
        script = (
            "import sys, tempfile; "
            "from albionmkt_app.presentation.qt.app import build_application; "
            "directory = tempfile.TemporaryDirectory(); "
            "runtime = build_application([], data_directory=directory.name); "
            "print(','.join(name for name in "
            "('bot','interface','easyocr','torch') if name in sys.modules)); "
            "runtime.window.close(); runtime.bridge.cleanup(); directory.cleanup()"
        )
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
