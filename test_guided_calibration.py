import unittest

import interface
from coordinate_system import BUY_REQUIRED_KEYS, CYCLE_REQUIRED_KEYS, SELL_REQUIRED_KEYS


class GuidedCalibrationTests(unittest.TestCase):
    def test_buy_guide_covers_each_runtime_requirement_once(self):
        keys = [step[2] for step in interface.GUIDED_BUY_STEPS]
        self.assertEqual(set(keys), set(BUY_REQUIRED_KEYS))
        self.assertEqual(len(keys), len(set(keys)))

    def test_each_step_has_supported_mode_and_instruction(self):
        steps = (
            interface.GUIDED_BUY_STEPS
            + interface.GUIDED_SELL_STEPS
            + interface.GUIDED_CYCLE_STEPS
        )
        for group, label, key, mode, instruction in steps:
            self.assertTrue(group)
            self.assertTrue(label)
            self.assertTrue(key)
            self.assertIn(mode, {'area', 'click'})
            self.assertGreater(len(instruction), 20)

    def test_sell_guide_covers_each_sale_requirement_once(self):
        keys = [step[2] for step in interface.GUIDED_SELL_STEPS]
        self.assertEqual(set(keys), set(SELL_REQUIRED_KEYS))
        self.assertEqual(len(keys), len(set(keys)))

    def test_sell_scope_uses_only_sell_steps(self):
        dummy = type('Dummy', (), {})()
        steps = interface.AlbionBotGUI._passos_calibragem_guiada(dummy, 'sell')
        self.assertEqual(steps, list(interface.GUIDED_SELL_STEPS))

    def test_cycle_guide_covers_each_cycle_requirement_once(self):
        keys = [step[2] for step in interface.GUIDED_CYCLE_STEPS]
        self.assertEqual(set(keys), set(CYCLE_REQUIRED_KEYS))
        self.assertEqual(len(keys), len(set(keys)))

    def test_cycle_scope_uses_only_cycle_steps(self):
        dummy = type('Dummy', (), {})()
        steps = interface.AlbionBotGUI._passos_calibragem_guiada(dummy, 'cycle')
        self.assertEqual(steps, list(interface.GUIDED_CYCLE_STEPS))

    def test_category_guide_only_uses_enabled_categories(self):
        dummy = type('Dummy', (), {})()
        dummy.category_list = [
            {'name': 'ARMAS', 'key': 'cat_clique_armas', 'enabled': True},
            {'name': 'BOTAS', 'key': 'cat_clique_botas', 'enabled': False},
        ]
        steps = interface.AlbionBotGUI._passos_calibragem_guiada(dummy, 'categories')
        keys = [step[2] for step in steps]
        self.assertEqual(keys, ['cat_clique_principal', 'cat_clique_armas'])


if __name__ == '__main__':
    unittest.main()
