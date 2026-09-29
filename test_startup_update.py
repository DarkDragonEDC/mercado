import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import startup_update


class ImmediateRoot:
    def __init__(self):
        self.destroyed = False

    def after(self, _delay, callback):
        callback()

    def destroy(self):
        self.destroyed = True


class StartupUpdateTests(unittest.TestCase):
    def test_startup_dialog_is_not_transient_when_root_is_withdrawn(self):
        root = Mock()
        root.state.return_value = "withdrawn"
        win = Mock()
        win.after.side_effect = lambda _delay, callback: callback()

        startup_update._show_startup_dialog(win, root)

        win.transient.assert_not_called()
        win.lift.assert_called_once_with()
        win.focus_force.assert_called_once_with()
        self.assertEqual(
            win.attributes.call_args_list,
            [unittest.mock.call("-topmost", True), unittest.mock.call("-topmost", False)],
        )

    def test_release_notes_open_before_the_main_interface(self):
        root = ImmediateRoot()
        continued = Mock()
        with patch("startup_update.ReleaseNotesDialog") as dialog:
            startup_update.show_current_release_notes(root, continued)
        dialog.assert_called_once_with(root, continued)
        dialog.return_value.show.assert_called_once_with()

    def test_unsupported_installation_continues_to_license(self):
        root = ImmediateRoot()
        continued = Mock()
        with patch("startup_update.check_in_background", return_value=False):
            started = startup_update.start_startup_update_check(root, continued)
        self.assertFalse(started)
        continued.assert_called_once_with()
        self.assertFalse(root.destroyed)

    def test_no_update_continues_to_license_once(self):
        root = ImmediateRoot()
        continued = Mock()

        def check(_available, on_error=None, on_no_update=None):
            on_no_update()
            return True

        with patch("startup_update.check_in_background", side_effect=check):
            startup_update.start_startup_update_check(root, continued)
        continued.assert_called_once_with()

    def test_available_update_opens_informative_preparation_dialog(self):
        root = ImmediateRoot()
        continued = Mock()
        manifest = SimpleNamespace(version="2.7.4")

        def check(available, on_error=None, on_no_update=None):
            available(manifest)
            return True

        with patch("startup_update.check_in_background", side_effect=check), patch(
            "startup_update.UpdatePreparationDialog"
        ) as dialog:
            startup_update.start_startup_update_check(root, continued)
        dialog.assert_called_once()
        dialog.return_value.show.assert_called_once_with()
        continued.assert_not_called()

    def test_dialog_starts_updater_and_closes_app(self):
        root = ImmediateRoot()
        continued = Mock()
        manifest = SimpleNamespace(version="2.7.4")
        dialog = startup_update.UpdatePreparationDialog.__new__(
            startup_update.UpdatePreparationDialog
        )
        dialog.root = root
        dialog.win = Mock()
        dialog.manifest = manifest
        dialog.on_continue = continued
        dialog.state = {"resolved": False}
        with patch("startup_update.launch_updater") as launch:
            dialog._update()
        launch.assert_called_once_with(manifest)
        continued.assert_not_called()
        self.assertTrue(root.destroyed)

    def test_network_error_never_blocks_license(self):
        root = ImmediateRoot()
        continued = Mock()

        def check(_available, on_error=None, on_no_update=None):
            on_error(OSError("offline"))
            return True

        with patch("startup_update.check_in_background", side_effect=check):
            startup_update.start_startup_update_check(root, continued)
        continued.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
