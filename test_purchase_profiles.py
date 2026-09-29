import unittest
from unittest.mock import Mock, call, patch

import bot
import interface
from purchase_profiles import (
    PROFILE_AGGRESSIVE,
    PROFILE_BALANCED,
    PROFILE_CONSERVATIVE,
    PROFILE_CUSTOM,
    parse_silver,
    resolve_purchase_profile,
    settings_from_legacy_config,
)


class PurchaseProfileTests(unittest.TestCase):
    def assert_profile(self, bank, profile, percent, limit):
        result = resolve_purchase_profile(profile, bank)
        self.assertEqual(result.max_percent, percent)
        self.assertEqual(result.order_limit, limit)

    def test_five_million_conservative(self):
        self.assert_profile(5_000_000, PROFILE_CONSERVATIVE, 50.0, 25_000)

    def test_five_million_balanced(self):
        self.assert_profile(5_000_000, PROFILE_BALANCED, 40.0, 50_000)

    def test_five_million_aggressive(self):
        self.assert_profile(5_000_000, PROFILE_AGGRESSIVE, 30.0, 100_000)

    def test_fifty_million_balanced(self):
        self.assert_profile(50_000_000, PROFILE_BALANCED, 40.0, 500_000)

    def test_fifty_million_aggressive(self):
        self.assert_profile(50_000_000, PROFILE_AGGRESSIVE, 30.0, 1_000_000)

    def test_legacy_configuration_becomes_custom(self):
        result = settings_from_legacy_config({"lucro": 28.0, "valor_max": 75_000})
        self.assertEqual(result.profile, PROFILE_CUSTOM)
        self.assertEqual(result.minimum_profit_percent, 72.0)
        self.assertEqual(result.order_limit, 75_000)

    def test_custom_preserves_manual_values(self):
        result = resolve_purchase_profile(PROFILE_CUSTOM, 0, 31.5, 123_456)
        self.assertEqual(result.max_percent, 31.5)
        self.assertEqual(result.order_limit, 123_456)

    def test_bank_change_recalculates_limit(self):
        first = resolve_purchase_profile(PROFILE_BALANCED, 5_000_000)
        second = resolve_purchase_profile(PROFILE_BALANCED, 50_000_000)
        self.assertEqual(first.order_limit, 50_000)
        self.assertEqual(second.order_limit, 500_000)

    def test_profile_change_recalculates_parameters(self):
        conservative = resolve_purchase_profile(PROFILE_CONSERVATIVE, 50_000_000)
        aggressive = resolve_purchase_profile(PROFILE_AGGRESSIVE, 50_000_000)
        self.assertEqual((conservative.minimum_profit_percent, conservative.order_limit), (50.0, 250_000))
        self.assertEqual((aggressive.minimum_profit_percent, aggressive.order_limit), (30.0, 1_000_000))

    def test_original_purchase_formula_receives_identical_effective_values(self):
        effective = resolve_purchase_profile(PROFILE_BALANCED, 50_000_000)
        direct = bot.validar_compra_financeira(30_000, 100_000, 30.0, 500_000)
        through_profile = bot.validar_compra_financeira(
            30_000,
            100_000,
            effective.max_percent,
            effective.order_limit,
        )
        self.assertEqual(through_profile, direct)

    def test_minimum_profit_uses_sale_price_as_denominator(self):
        self.assertEqual(
            bot.validar_compra_financeira(70_000, 100_000, 30.0, 100_000),
            (True, ""),
        )
        allowed, reason = bot.validar_compra_financeira(
            70_001, 100_000, 30.0, 100_000
        )
        self.assertFalse(allowed)
        self.assertIn("lucro mínimo", reason)

    def test_v2_settings_keep_minimum_profit_value(self):
        result = settings_from_legacy_config({
            "financial_rule_version": 2,
            "lucro_minimo_venda": 40.0,
            "valor_max": 150_000,
        })
        self.assertEqual(result.minimum_profit_percent, 40.0)

    def test_legacy_cost_limit_is_migrated_without_behavior_change(self):
        result = settings_from_legacy_config({"lucro": 60.0, "valor_max": 150_000})
        self.assertEqual(result.minimum_profit_percent, 40.0)
        self.assertEqual(
            bot.validar_compra_financeira(60_000, 100_000, result.minimum_profit_percent, 150_000),
            (True, ""),
        )

    def test_operational_bank_limits_total_confirmed_session_spend(self):
        self.assertEqual(
            bot.calcular_limite_disponivel_sessao(200_000, 20_000_000, 19_900_000),
            100_000,
        )
        self.assertEqual(
            bot.calcular_limite_disponivel_sessao(200_000, 20_000_000, 20_000_000),
            0,
        )

    def test_zero_operational_bank_keeps_only_per_order_limit(self):
        self.assertEqual(
            bot.calcular_limite_disponivel_sessao(150_000, 0, 99_000_000),
            150_000,
        )

    def test_failed_item_cooldown_expires(self):
        key = ("Capote Sectário do Mestre .4", 1_399_999, 22_891)
        blocked = {key: 700.0}
        self.assertTrue(bot.item_em_cooldown(blocked, key, agora=100.0))
        self.assertFalse(bot.item_em_cooldown(blocked, key, agora=701.0))
        self.assertNotIn(key, blocked)

    def test_protected_pause_scheduler_uses_approved_ranges(self):
        clock = Mock(return_value=1_000.0)
        rng = Mock()
        rng.randint.side_effect = [2_700, 180, 5_400]
        scheduler = bot.ProtectedPauseScheduler(rng=rng, clock=clock)

        scheduler.reset(True)
        self.assertEqual(scheduler.next_pause_at, 3_700.0)
        clock.return_value = 3_700.0
        self.assertTrue(scheduler.due())
        self.assertEqual(scheduler.begin_pause(), 180)
        scheduler.finish_pause()
        self.assertEqual(scheduler.next_pause_at, 9_100.0)
        self.assertEqual(
            rng.randint.call_args_list,
            [
                call(*bot.PROTECTED_PAUSE_INTERVAL_RANGE),
                call(*bot.PROTECTED_PAUSE_DURATION_RANGE),
                call(*bot.PROTECTED_PAUSE_INTERVAL_RANGE),
            ],
        )

    def test_protected_pause_is_absent_when_disabled(self):
        scheduler = bot.ProtectedPauseScheduler(
            rng=Mock(), clock=Mock(return_value=50_000.0)
        )
        scheduler.reset(False)

        self.assertFalse(scheduler.due())
        self.assertIsNone(scheduler.next_pause_at)

    def test_protected_pause_wait_is_interruptible_and_reschedules(self):
        class FakeClock:
            value = 0.0

            def __call__(self):
                return self.value

        clock = FakeClock()
        rng = Mock()
        rng.randint.side_effect = [2_700, 180, 2_700]
        scheduler = bot.ProtectedPauseScheduler(rng=rng, clock=clock)
        scheduler.reset(True)
        clock.value = 2_700.0
        messages = []

        paused = bot.protected_pause_checkpoint(
            scheduler,
            {bot.PROTECTED_PAUSE_ENABLED_KEY: True},
            settings_loader=lambda: {bot.PROTECTED_PAUSE_ENABLED_KEY: True},
            sleep_fn=lambda duration: setattr(clock, 'value', clock.value + duration),
            log_fn=messages.append,
        )

        self.assertTrue(paused)
        self.assertEqual(clock.value, 2_880.0)
        self.assertEqual(scheduler.next_pause_at, 5_580.0)
        self.assertIn('Iniciada por 3m 00s', messages[0])
        self.assertIn('Retomando automação', messages[-1])

    def test_protected_pause_can_be_disabled_while_waiting(self):
        clock = Mock(return_value=0.0)
        rng = Mock()
        rng.randint.side_effect = [2_700, 180]
        scheduler = bot.ProtectedPauseScheduler(rng=rng, clock=clock)
        scheduler.reset(True)
        clock.return_value = 2_700.0
        messages = []

        paused = bot.protected_pause_checkpoint(
            scheduler,
            {bot.PROTECTED_PAUSE_ENABLED_KEY: True},
            settings_loader=lambda: {bot.PROTECTED_PAUSE_ENABLED_KEY: False},
            sleep_fn=Mock(),
            log_fn=messages.append,
        )

        self.assertFalse(paused)
        self.assertFalse(scheduler.enabled)
        self.assertIn('Cancelada', messages[-1])

    def test_stop_command_interrupts_protected_pause(self):
        clock = Mock(return_value=0.0)
        rng = Mock()
        rng.randint.side_effect = [2_700, 180]
        scheduler = bot.ProtectedPauseScheduler(rng=rng, clock=clock)
        scheduler.reset(True)
        clock.return_value = 2_700.0

        with self.assertRaises(bot.BotStoppedException):
            bot.protected_pause_checkpoint(
                scheduler,
                {bot.PROTECTED_PAUSE_ENABLED_KEY: True},
                settings_loader=lambda: {bot.PROTECTED_PAUSE_ENABLED_KEY: True},
                sleep_fn=lambda _duration: (_ for _ in ()).throw(bot.BotStoppedException()),
                log_fn=Mock(),
            )

    def test_portuguese_silver_format_is_accepted(self):
        self.assertEqual(parse_silver("50.000.000"), 50_000_000)

    def test_negative_bank_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_purchase_profile(PROFILE_BALANCED, -1)


class _FakeEntry:
    def __init__(self, value=""):
        self.value = str(value)
        self.editable = True

    def get(self):
        return self.value

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = str(value)

    def set_editable(self, editable):
        self.editable = bool(editable)


class PurchaseProfileInterfaceTests(unittest.TestCase):
    def make_gui(self):
        gui = interface.AlbionBotGUI.__new__(interface.AlbionBotGUI)
        gui.purchase_profile = PROFILE_CUSTOM
        gui.purchase_profile_buttons = {}
        gui.operational_bank_entry = _FakeEntry("0")
        gui.config_lucro_ent = _FakeEntry("28")
        gui.config_vmax_ent = _FakeEntry("75000")
        gui.protected_pause_enabled = False
        gui.protected_pause_checkbox = Mock()
        gui.show_notification = Mock()
        gui.log = Mock()
        return gui

    def test_balanced_profile_saves_effective_legacy_fields(self):
        gui = self.make_gui()
        gui.purchase_profile = PROFILE_BALANCED
        gui.operational_bank_entry.value = "50.000.000"
        with patch.object(interface, "load_settings", return_value={"preservar": 1}), patch.object(
            interface, "save_settings"
        ) as save:
            saved_ok = gui.salvar_ajustes_financeiros()

        self.assertTrue(saved_ok)
        data = save.call_args.args[1]
        self.assertEqual(data["preservar"], 1)
        self.assertEqual(data["banca_operacional"], 50_000_000)
        self.assertEqual(data["perfil_compra"], PROFILE_BALANCED)
        self.assertEqual(data["financial_rule_version"], 2)
        self.assertEqual(data["lucro_minimo_venda"], 40.0)
        self.assertEqual(data["lucro"], 60.0)
        self.assertEqual(data["valor_max"], 500_000)
        self.assertFalse(data[bot.PROTECTED_PAUSE_ENABLED_KEY])
        self.assertFalse(gui.config_lucro_ent.editable)
        self.assertFalse(gui.config_vmax_ent.editable)

    def test_loading_old_file_keeps_values_and_selects_custom(self):
        gui = self.make_gui()
        with patch.object(
            interface,
            "load_settings",
            return_value={"lucro": 27.0, "valor_max": 90_000},
        ):
            gui.carregar_ajustes_financeiros()

        self.assertEqual(gui.purchase_profile, PROFILE_CUSTOM)
        self.assertEqual(gui.config_lucro_ent.get(), "73")
        self.assertEqual(gui.config_vmax_ent.get(), "90000")
        self.assertTrue(gui.config_lucro_ent.editable)
        self.assertTrue(gui.config_vmax_ent.editable)

    def test_protected_pause_preference_is_persisted(self):
        gui = self.make_gui()
        gui.protected_pause_enabled = True
        with patch.object(interface, "load_settings", return_value={}), patch.object(
            interface, "save_settings"
        ) as save:
            self.assertTrue(gui.salvar_ajustes_financeiros())

        self.assertTrue(save.call_args.args[1][bot.PROTECTED_PAUSE_ENABLED_KEY])

    def test_protected_pause_toggle_updates_saved_value_and_checkbox(self):
        gui = self.make_gui()
        with patch.object(interface, "load_settings", return_value={}), patch.object(
            interface, "save_settings"
        ) as save:
            gui.alternar_pausa_protegida(True)

        self.assertTrue(gui.protected_pause_enabled)
        self.assertTrue(save.call_args.args[1][bot.PROTECTED_PAUSE_ENABLED_KEY])
        gui.protected_pause_checkbox.set_active.assert_called_once_with(True)


class VerificarMediaSemanalToggleTests(unittest.TestCase):
    """O botão selecionável "Exigir média semanal" aparece do lado dos
    botões de iniciar em cada modo que cria pedido de compra; todos ligam/
    desligam o mesmo ajuste compartilhado (VERIFICAR_MEDIA_SEMANAL_KEY)."""

    def make_gui(self):
        gui = interface.AlbionBotGUI.__new__(interface.AlbionBotGUI)
        gui.offsets = {}
        gui.log = Mock()
        return gui

    def test_toggle_updates_saved_value_and_all_registered_checkboxes(self):
        gui = self.make_gui()
        gui._media_semanal_checkboxes = [Mock(), Mock()]
        with patch.object(interface, "load_settings", return_value={}), patch.object(
            interface, "save_settings"
        ) as save:
            gui.alternar_verificar_media_semanal(True)

        self.assertTrue(gui.verificar_media_semanal)
        self.assertTrue(save.call_args.args[1][bot.VERIFICAR_MEDIA_SEMANAL_KEY])
        for checkbox in gui._media_semanal_checkboxes:
            checkbox.set_active.assert_called_once_with(True)

    def test_criar_toggle_reads_persisted_value_once(self):
        gui = self.make_gui()
        gui.offsets = {bot.VERIFICAR_MEDIA_SEMANAL_KEY: True}
        gui.create_puffy_checkbox = Mock(return_value=Mock())
        parent = Mock()

        checkbox = gui._criar_toggle_media_semanal(parent)

        self.assertTrue(gui.verificar_media_semanal)
        gui.create_puffy_checkbox.assert_called_once()
        args, _kwargs = gui.create_puffy_checkbox.call_args
        self.assertEqual(args[0], parent)
        self.assertTrue(args[2])
        self.assertEqual(args[3], gui.alternar_verificar_media_semanal)
        self.assertIn(checkbox, gui._media_semanal_checkboxes)

    def test_multiple_tabs_share_the_same_underlying_flag(self):
        gui = self.make_gui()
        gui.create_puffy_checkbox = Mock(side_effect=lambda *a, **k: Mock())

        gui._criar_toggle_media_semanal(Mock())
        gui._criar_toggle_media_semanal(Mock())

        self.assertEqual(len(gui._media_semanal_checkboxes), 2)
        # As duas chamadas usam o mesmo valor inicial (lido uma única vez).
        primeira_chamada, segunda_chamada = gui.create_puffy_checkbox.call_args_list
        self.assertEqual(primeira_chamada.args[2], segunda_chamada.args[2])


if __name__ == "__main__":
    unittest.main()
