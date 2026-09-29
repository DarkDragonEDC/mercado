import unittest
from unittest.mock import Mock, patch


class SplashScreenTests(unittest.TestCase):
    def test_failsafe_finishes_even_if_a_visual_frame_fails(self):
        import interface

        splash = interface.SplashScreen.__new__(interface.SplashScreen)
        splash._finished = False
        splash.on_finish = Mock()
        splash.root = Mock()
        splash.root.winfo_exists.return_value = True
        splash.step = 0
        splash.draw_hud_frame = Mock(side_effect=RuntimeError("canvas unavailable"))

        splash.animate()
        splash.on_finish.assert_not_called()

        splash.finish()
        splash.finish()

        splash.on_finish.assert_called_once_with()
        splash.root.destroy.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
