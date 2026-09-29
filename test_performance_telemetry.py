import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from performance_telemetry import PerformanceTelemetry


class PerformanceTelemetryTests(unittest.TestCase):
    def test_sample_aggregates_stage_durations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = PerformanceTelemetry(temp_dir, interval=1)
            monitor.observe("ocr_purchase_item", 0.100)
            monitor.observe("ocr_purchase_item", 0.200)

            sample = monitor.sample()

            self.assertEqual(sample["type"], "sample")
            self.assertIn("process_cpu_percent", sample)
            self.assertIn("system_cpu_percent", sample)
            self.assertIn("working_set_mb", sample)
            self.assertIn("python_threads", sample)
            self.assertEqual(
                sample["stages"]["ocr_purchase_item"],
                {"count": 2, "average_ms": 150.0, "max_ms": 200.0},
            )
            if os.name == "nt":
                self.assertIsNotNone(sample["working_set_mb"])
                self.assertGreater(sample["working_set_mb"], 0)

    def test_background_writer_creates_json_lines_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = PerformanceTelemetry(temp_dir, interval=0.05)
            path = monitor.start()
            monitor.observe("purchase_button_detection", 0.025)
            time.sleep(0.12)
            monitor.stop()

            records = [
                json.loads(line)
                for line in Path(path).read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(records[0]["type"], "session_start")
            samples = [record for record in records if record["type"] == "sample"]
            self.assertGreaterEqual(len(samples), 1)
            self.assertEqual(
                samples[0]["stages"]["purchase_button_detection"]["count"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
