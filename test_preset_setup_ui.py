import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from preset_setup_ui import PresetSetupWindow


class PresetSetupVisibilityTests(unittest.TestCase):
    def _create_wizard(self, root, data_dir):
        return PresetSetupWindow(
            root,
            presets_dir=Path(__file__).resolve().parent / "presets",
            asset_root=Path(__file__).resolve().parent,
            settings_path=Path(data_dir) / "offsets.json",
            find_albion_window=lambda: None,
            on_complete=lambda: None,
        )

    def test_wizard_is_visible_while_main_root_is_withdrawn(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as data_dir, patch.dict(
                os.environ, {"MKT_DATA_DIR": data_dir}
            ):
                wizard = self._create_wizard(root, data_dir)
                root.update_idletasks()
                root.update()

                self.assertEqual("withdrawn", root.state())
                self.assertEqual("normal", wizard.win.state())
                self.assertEqual(1, wizard.win.winfo_viewable())
                wizard.win.destroy()
        finally:
            root.destroy()

    def test_action_buttons_remain_visible_after_long_diagnostic(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as data_dir, patch.dict(
                os.environ, {"MKT_DATA_DIR": data_dir}
            ):
                wizard = self._create_wizard(root, data_dir)
                wizard.evidence_label.config(
                    text="\n".join(
                        ["A tela aberta nao corresponde com seguranca ao preset."]
                        + [f"FALHA referencia {index}: confianca insuficiente" for index in range(12)]
                    )
                )
                root.update_idletasks()
                root.update()

                window_bottom = wizard.win.winfo_rooty() + wizard.win.winfo_height()
                for button in (wizard.retry_button, wizard.validate_button):
                    self.assertEqual(1, button.winfo_viewable())
                    self.assertLessEqual(
                        button.winfo_rooty() + button.winfo_height(), window_bottom
                    )
                wizard.win.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
