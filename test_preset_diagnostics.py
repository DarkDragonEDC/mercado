import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from preset_diagnostics import write_preset_diagnostic


class PresetDiagnosticTests(unittest.TestCase):
    def test_diagnostic_is_persisted_in_local_logs(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"MKT_DATA_DIR": directory}
        ):
            path = write_preset_diagnostic(
                "environment_inspected",
                geometry={"width": 1920, "height": 1080},
                dpi=96,
                preset_errors=[],
            )

            self.assertIsNotNone(path)
            self.assertTrue(path.parent.samefile(Path(directory, "logs")))
            record = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual("environment_inspected", record["event"])
            self.assertEqual(96, record["details"]["dpi"])
            self.assertEqual(1920, record["details"]["geometry"]["width"])

    def test_logging_failure_never_blocks_the_wizard(self):
        with patch("preset_diagnostics.logs_dir", side_effect=OSError("disk")):
            self.assertIsNone(write_preset_diagnostic("wizard_opened"))


if __name__ == "__main__":
    unittest.main()
