import tempfile
import json
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import bot
from PIL import Image
from interface import (
    COLOR_ACCENT,
    COLOR_ERROR,
    COLOR_SUCCESS,
    MODULE_CYCLE,
    MODULE_PURCHASE,
    MODULE_SELL,
    AUTOMATION_START_GUARD_SECONDS,
    MINI_HUD_HEIGHT,
    MINI_HUD_WIDTH,
    OPTIONAL_CALIBRATION_KEYS,
    PANEL_SAFE_WIDTH,
    UI_COLORS,
    UI_FONTS,
    AlbionBotGUI,
    LogWindow,
    build_control_state,
    build_mini_hud_state,
    build_item_render_url,
    build_soft_order_tone,
    format_mini_elapsed,
    item_icon_cache_paths,
    license_allows_module,
    prepare_notification_item_icon,
    classify_operation_message,
)
from operation_telemetry import BackgroundLogWriter


class _StopLoop(Exception):
    pass


class StandbyLoggingTests(unittest.TestCase):
    def test_operation_log_is_persisted_to_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            window = LogWindow.__new__(LogWindow)
            window.log_path = str(Path(directory) / "operacoes.log")
            window.console = MagicMock()

            window.log("[CLIQUE] acao=cycle_sell_menu destino=(1200,400)")

            saved = Path(window.log_path).read_text(encoding="utf-8")
            self.assertIn("acao=cycle_sell_menu", saved)
            self.assertIn("destino=(1200,400)", saved)

    def test_background_writer_persists_raw_and_structured_records(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = BackgroundLogWriter(directory, session_id="session-test")
            writer.submit(
                "[BUY] 1250.0",
                classify_operation_message("[BUY] 1250.0"),
            )
            self.assertTrue(writer.flush(2.0))
            writer.close()

            raw_files = list(Path(directory).glob("operacoes-*.log"))
            telemetry_files = list(Path(directory).glob("telemetria-*.jsonl"))
            self.assertEqual(len(raw_files), 1)
            self.assertEqual(len(telemetry_files), 1)
            payload = json.loads(telemetry_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["session_id"], "session-test")
            self.assertEqual(payload["event"], "purchase_confirmed")
            self.assertEqual(payload["estimated_margin"], 1250.0)

    def test_structured_event_does_not_copy_the_raw_message(self):
        event = classify_operation_message("[BLOQUEADO] texto de diagnostico local")

        self.assertEqual(event["event"], "safety_protection")
        self.assertEqual(event["result"], "protected")
        self.assertNotIn("message", event)

    def test_normal_price_rejection_is_not_an_error_or_safety_block(self):
        event = classify_operation_message(
            "[!] Pulando: preco 910 excede 50.0% do valor de venda 1790."
        )

        self.assertEqual(event["event"], "log")
        self.assertEqual(event["result"], "skipped")

    def test_manual_interruption_is_informational(self):
        event = classify_operation_message("[!] Interrupcao instantanea!")

        self.assertEqual(event["event"], "automation_interrupted")
        self.assertEqual(event["result"], "info")

    def test_real_execution_failure_remains_an_error(self):
        event = classify_operation_message("[!] Erro na deteccao dos pedidos: falha")

        self.assertEqual(event["event"], "operation_error")
        self.assertEqual(event["result"], "error")

    def test_rejected_data_is_classified_as_ignored(self):
        event = classify_operation_message("[DATA] Arco|1790|910|50.8%|0")

        self.assertEqual(event["event"], "opportunity_evaluated")
        self.assertFalse(event["approved"])
        self.assertEqual(event["result"], "skipped")

    def test_ocr_diagnostic_is_structured_without_becoming_a_visible_event(self):
        payload = {
            "schema": 1,
            "tier": {"value": 4, "source": "name"},
            "enchantment": {
                "value": ".2",
                "status": "color_match",
                "winner_pixels": 84,
            },
        }

        event = classify_operation_message(
            "[OCR_DIAG] " + json.dumps(payload, ensure_ascii=False)
        )

        self.assertEqual(event["event"], "log")
        self.assertEqual(event["module"], "purchase")
        self.assertEqual(event["diagnostic_type"], "item_ocr")
        self.assertEqual(event["diagnostic"], payload)

    def test_ocr_diagnostic_is_saved_but_hidden_from_technical_console(self):
        window = LogWindow.__new__(LogWindow)
        window.writer = MagicMock()
        window.console = MagicMock()
        window.visible = False
        message = '[OCR_DIAG] {"schema":1,"enchantment":{"value":".2"}}'

        window.log(message)

        window.writer.submit.assert_called_once()
        window.console.configure.assert_not_called()
        self.assertEqual(len(window.events), 0)

    def test_standby_is_logged_only_once_while_stopped(self):
        with (
            patch.object(bot.threading, "Thread") as thread,
            patch.object(bot, "check_control", return_value=(False, "buy")),
            patch.object(bot.time, "sleep", side_effect=[None, None, _StopLoop]),
            patch("builtins.print") as output,
        ):
            thread.return_value.start.return_value = None
            with self.assertRaises(_StopLoop):
                bot.main()

        standby_messages = [
            call for call in output.call_args_list if "Bot em Standby" in str(call)
        ]
        self.assertEqual(len(standby_messages), 1)


class OrderSoundTests(unittest.TestCase):
    def test_soft_order_tone_is_a_short_wave_file(self):
        payload = build_soft_order_tone()

        self.assertTrue(payload.startswith(b"RIFF"))
        self.assertIn(b"WAVE", payload[:16])
        self.assertLess(len(payload), 10000)

    def test_confirmed_buy_plays_sound_once(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.log_window = MagicMock()
        gui.total_orders = 0
        gui.total_profit = 0
        gui.last_item_name = "Item"
        gui.atualizar_contadores_reais = MagicMock()
        gui.enqueue_notification = MagicMock()
        gui.insert_tree = MagicMock()
        gui.play_order_sound = MagicMock()

        gui._process_log_message("[BUY] 1250.0")

        gui.play_order_sound.assert_called_once_with()
        gui.enqueue_notification.assert_not_called()
        self.assertEqual(gui.total_orders, 1)

    def test_progress_log_with_pipes_is_not_added_to_market_table(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.log_window = MagicMock()
        gui.insert_tree = MagicMock()

        gui._process_log_message(
            "[#15/50] Item: Elmo | Venda: 10000 | Compra: 4000 | Custo: 40%"
        )

        gui.insert_tree.assert_not_called()

    def test_data_log_is_added_to_market_table(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.log_window = MagicMock()
        gui.insert_tree = MagicMock()

        gui._process_log_message("[DATA] Elmo do Adepto|10000|4000|40%|1")

        gui.insert_tree.assert_called_once_with(
            ["Elmo do Adepto", "10000", "4000", "40%", "1"]
        )


class HotkeyBehaviorTests(unittest.TestCase):
    @staticmethod
    def make_gui(tab):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.running = False
        gui.sell_running = False
        gui.cycle_running = False
        gui.fechando_ordens = False
        gui.current_tab = tab
        gui.iniciar_bot_venda = MagicMock()
        gui.toggle_cycle_bot = MagicMock()
        gui.toggle_bot = MagicMock()
        gui.protected_pause_enabled = False
        gui.alternar_pausa_protegida = MagicMock()
        gui.show_notification = MagicMock()
        return gui

    def test_f7_starts_sales_from_sell_tab(self):
        gui = self.make_gui("SELL")

        gui.iniciar_via_atalho()

        gui.iniciar_bot_venda.assert_called_once_with()
        gui.toggle_bot.assert_not_called()
        gui.toggle_cycle_bot.assert_not_called()

    def test_f7_starts_buying_from_other_tabs(self):
        gui = self.make_gui("BOT")

        gui.iniciar_via_atalho()

        gui.toggle_bot.assert_called_once_with()
        gui.iniciar_bot_venda.assert_not_called()
        gui.toggle_cycle_bot.assert_not_called()

    def test_f7_starts_cycle_from_cycle_tab(self):
        gui = self.make_gui("CYCLE")

        gui.iniciar_via_atalho()

        gui.toggle_cycle_bot.assert_called_once_with()
        gui.toggle_bot.assert_not_called()
        gui.iniciar_bot_venda.assert_not_called()

    def test_f7_does_nothing_when_an_automation_is_running(self):
        gui = self.make_gui("SELL")
        gui.sell_running = True

        gui.iniciar_via_atalho()

        gui.iniciar_bot_venda.assert_not_called()
        gui.toggle_bot.assert_not_called()
        gui.toggle_cycle_bot.assert_not_called()

    def test_f9_enables_protected_pause_without_starting_automation(self):
        gui = self.make_gui("BOT")

        gui.alternar_pausa_protegida_via_atalho()

        gui.alternar_pausa_protegida.assert_called_once_with(True)
        gui.show_notification.assert_called_once_with('PAUSA PROTEGIDA ATIVADA')
        gui.toggle_bot.assert_not_called()

    def test_f9_disables_protected_pause(self):
        gui = self.make_gui("BOT")
        gui.protected_pause_enabled = True

        gui.alternar_pausa_protegida_via_atalho()

        gui.alternar_pausa_protegida.assert_called_once_with(False)
        gui.show_notification.assert_called_once_with('PAUSA PROTEGIDA DESATIVADA')

    def test_stop_command_is_sent_even_when_visual_state_says_stopped(self):
        gui = self.make_gui("BOT")
        gui.atualizar_botao_inicial = MagicMock()
        gui.atualizar_botao_venda = MagicMock()
        gui.atualizar_botao_ciclo = MagicMock()
        gui.card_status = MagicMock()
        gui.edit_status_lbl = MagicMock()
        gui.sell_module_status_lbl = MagicMock()
        gui.cycle_module_status_lbl = MagicMock()
        gui._set_cycle_stage = MagicMock()
        gui.log = MagicMock()

        with patch('builtins.open', mock_open()) as control_file:
            gui.pause_bot()

        control_file.assert_called_once()
        gui.log.assert_not_called()


class OptionalCalibrationWarningTests(unittest.TestCase):
    """Cada calibragem opcional (não exigida pra rodar, mas relevante pra
    alguma verificação) precisa estar registrada aqui, senão o aviso
    "⚠ Calibragem opcional recomendada pendente" nunca menciona ela --
    regressão real: a área "Preço Médio" (verificação de média semanal)
    ficou sem calibrar e o aviso não apareceu."""

    def test_preco_medio_is_registered_as_optional_calibration(self):
        keys = dict(OPTIONAL_CALIBRATION_KEYS)
        self.assertIn("preco_medio", keys)

    def test_compra_topo_cor_is_still_registered(self):
        keys = dict(OPTIONAL_CALIBRATION_KEYS)
        self.assertIn("compra_topo_cor", keys)


class MiniHudTests(unittest.TestCase):
    def test_hud_dimensions_are_visible_without_covering_the_safe_panel_width(self):
        self.assertGreaterEqual(MINI_HUD_WIDTH, 280)
        self.assertLess(MINI_HUD_WIDTH, PANEL_SAFE_WIDTH)
        self.assertGreaterEqual(MINI_HUD_HEIGHT, 64)

    def test_hud_reports_each_operation_and_protected_pause(self):
        self.assertEqual(build_mini_hud_state(running=True)['operation'], 'COMPRA ATIVA')
        self.assertEqual(build_mini_hud_state(sell_running=True)['operation'], 'VENDA ATIVA')
        self.assertEqual(build_mini_hud_state(cycle_running=True)['operation'], 'CICLO ATIVO')
        closing = build_mini_hud_state(closing_orders=True, protected_pause=True)
        self.assertEqual(closing['operation'], 'FECHANDO ORDENS')
        self.assertTrue(closing['protected_pause'])

    def test_hud_reports_shopping_running_as_active(self):
        state = build_mini_hud_state(shopping_running=True)
        self.assertEqual(state['operation'], 'COMPRA PROGRAMADA ATIVA')
        self.assertTrue(state['active'])

    def test_hud_reports_shopping_paused_as_inactive(self):
        state = build_mini_hud_state(shopping_paused=True)
        self.assertEqual(state['operation'], 'COMPRA PROGRAMADA EM PAUSA')
        self.assertFalse(state['active'])

    def test_hud_elapsed_time_uses_hours_minutes_and_seconds(self):
        self.assertEqual(format_mini_elapsed(0), '00:00:00')
        self.assertEqual(format_mini_elapsed(3661), '01:01:01')


class CompanionPanelSafetyTests(unittest.TestCase):
    def test_panel_keeps_the_known_safe_width_next_to_the_store(self):
        # Em 1600x900 a área de itens começa cerca de 403 px após a borda do
        # cliente. Uma largura de 430 px cobria o ponto de segurança do bot.
        self.assertEqual(PANEL_SAFE_WIDTH, 390)

    def test_visual_tokens_keep_a_dark_readable_hierarchy(self):
        self.assertEqual(UI_COLORS["navigation"], "#030812")
        self.assertNotEqual(UI_COLORS["background"], "#000000")
        self.assertNotEqual(UI_COLORS["text"], UI_COLORS["background"])
        self.assertIn("page_title", UI_FONTS)
        self.assertIn("body", UI_FONTS)

    def test_starting_automation_collapses_panel_then_focuses_game(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.minimized = False
        gui.toggle_minimize = MagicMock()
        gui.focar_jogo = MagicMock()

        gui.minimizar_para_execucao()

        gui.toggle_minimize.assert_called_once_with()
        gui.focar_jogo.assert_called_once_with()

    def test_already_collapsed_panel_is_not_toggled_open(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.minimized = True
        gui.toggle_minimize = MagicMock()
        gui.focar_jogo = MagicMock()

        gui.minimizar_para_execucao()

        gui.toggle_minimize.assert_not_called()
        gui.focar_jogo.assert_called_once_with()

    def test_starting_automation_hides_the_monitor_before_focusing_game(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.minimized = False
        gui.log_window = MagicMock()
        gui.toggle_minimize = MagicMock()
        gui.focar_jogo = MagicMock()

        gui.minimizar_para_execucao()

        gui.log_window.hide.assert_called_once_with()
        gui.toggle_minimize.assert_called_once_with()
        gui.focar_jogo.assert_called_once_with()

    def test_first_action_waits_only_after_windows_are_withdrawn(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.minimized = False
        gui.root = MagicMock()
        gui.log_window = MagicMock()
        gui.toggle_minimize = MagicMock()
        gui.focar_jogo = MagicMock()

        with patch('interface.time.sleep') as sleep:
            gui.minimizar_para_execucao()

        gui.log_window.hide.assert_called_once_with()
        gui.root.update_idletasks.assert_called_once_with()
        gui.root.update.assert_called_once_with()
        gui.focar_jogo.assert_called_once_with()
        sleep.assert_called_once_with(AUTOMATION_START_GUARD_SECONDS)
        self.assertLessEqual(AUTOMATION_START_GUARD_SECONDS, 0.5)


class ItemNotificationIconTests(unittest.TestCase):
    def test_render_url_preserves_enchantment_and_requests_high_resolution(self):
        url = build_item_render_url("Arco do Adepto .2")

        self.assertIn("Arco%20do%20Adepto@2.png", url)
        self.assertIn("size=217", url)
        self.assertIn("locale=pt", url)

    def test_cache_paths_are_stable_and_do_not_use_raw_ocr_as_filename(self):
        first = item_icon_cache_paths("Arco do Adepto .2")
        second = item_icon_cache_paths("Arco do Adepto .2")

        self.assertEqual(first, second)
        self.assertTrue(first[0].endswith("_capture.png"))
        self.assertTrue(first[1].endswith("_render.png"))

    def test_rectangular_game_capture_is_normalized_to_square_icon(self):
        source = Image.new("RGB", (80, 40), "red")

        prepared = prepare_notification_item_icon(source, 36)

        self.assertEqual(prepared.size, (36, 36))
        self.assertEqual(prepared.mode, "RGBA")

    def test_official_png_transparent_margin_is_removed_before_resizing(self):
        source = Image.new("RGBA", (217, 217), (0, 0, 0, 0))
        source.paste((255, 0, 0, 255), (50, 50, 167, 167))

        prepared = prepare_notification_item_icon(source, 60)

        self.assertEqual(prepared.size, (60, 60))
        self.assertEqual(prepared.getchannel("A").getbbox(), (0, 0, 60, 60))

    def test_notification_queues_one_icon_payload_and_background_cache_job(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.notif_queue = []
        gui._item_icon_cache_queue = MagicMock()
        source = Image.new("RGBA", (32, 32), "blue")

        gui.enqueue_notification("Arco do Adepto .2", 1234, source)

        self.assertEqual(len(gui.notif_queue), 1)
        self.assertEqual(len(gui.notif_queue[0]), 3)
        self.assertIsInstance(gui.notif_queue[0][2], Image.Image)
        gui._item_icon_cache_queue.put_nowait.assert_called_once()

    def test_three_field_notification_payload_reaches_renderer(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        icon = Image.new("RGBA", (32, 32), "blue")
        gui.active_notification = None
        gui.notif_queue = [("Arco", 1234, icon)]
        gui.show_premium_buy_notification = MagicMock()

        gui.process_notif_queue()

        gui.show_premium_buy_notification.assert_called_once_with("Arco", 1234, icon)

    def test_notification_renderer_accepts_the_real_item_icon_without_tk_window(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.width = 390
        gui.root = MagicMock()
        gui.root.winfo_rootx.return_value = 10
        gui.root.winfo_rooty.return_value = 10
        gui.root.winfo_width.return_value = 390
        gui.root.winfo_height.return_value = 700
        gui.root.winfo_screenwidth.return_value = 1600
        gui.root.winfo_screenheight.return_value = 900
        gui.active_notification = None
        gui._load_official_item_icon = MagicMock(return_value=None)
        gui._load_cached_item_icon = MagicMock(return_value=None)
        icon = Image.new("RGBA", (80, 80), "blue")

        with (
            patch("interface.tk.Toplevel") as toplevel,
            patch("interface.tk.Canvas"),
            patch("interface.ImageTk.PhotoImage") as photo_image,
            patch("interface.aplicar_efeito_blur_janela"),
        ):
            toplevel.return_value.winfo_exists.return_value = True
            gui.show_premium_buy_notification("Arco do Adepto", 1234, icon)

        photo_image.assert_called_once()
        gui._load_cached_item_icon.assert_called_once_with("Arco do Adepto")

    def test_prefetch_only_queues_work_and_never_waits_for_network(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui._item_icon_cache_queue = MagicMock()
        icon = Image.new("RGBA", (48, 48), "blue")

        gui.prefetch_item_icon("Arco do Adepto", icon)

        gui._item_icon_cache_queue.put_nowait.assert_called_once()
        queued_name, queued_icon = gui._item_icon_cache_queue.put_nowait.call_args.args[0]
        self.assertEqual(queued_name, "Arco do Adepto")
        self.assertIsInstance(queued_icon, Image.Image)

    def test_official_cached_png_has_priority_over_game_capture(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.width = 390
        gui.root = MagicMock()
        gui.root.winfo_rootx.return_value = 10
        gui.root.winfo_rooty.return_value = 10
        gui.root.winfo_width.return_value = 390
        gui.root.winfo_height.return_value = 700
        gui.root.winfo_screenwidth.return_value = 1600
        gui.root.winfo_screenheight.return_value = 900
        gui.active_notification = None
        official = Image.new("RGBA", (217, 217), "red")
        capture = Image.new("RGBA", (80, 80), "blue")
        gui._load_official_item_icon = MagicMock(return_value=official)
        gui._load_cached_item_icon = MagicMock(return_value=None)

        with (
            patch("interface.tk.Toplevel") as toplevel,
            patch("interface.tk.Canvas"),
            patch("interface.ImageTk.PhotoImage"),
            patch("interface.aplicar_efeito_blur_janela"),
            patch(
                "interface.prepare_notification_item_icon",
                wraps=prepare_notification_item_icon,
            ) as prepare,
        ):
            toplevel.return_value.winfo_exists.return_value = True
            gui.show_premium_buy_notification("Arco do Adepto", 1234, capture)

        self.assertIs(prepare.call_args.args[0], official)
        self.assertEqual(prepare.call_args.args[1], 180)
        gui._load_cached_item_icon.assert_not_called()


class CycleUiFeedbackTests(unittest.TestCase):
    @staticmethod
    def make_gui():
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.log_window = MagicMock()
        gui.running = False
        gui.cycle_running = True
        gui.cycle_orders_completed = 0
        gui.cycle_items_sold = 0
        gui.cycle_orders_count_lbl = MagicMock()
        gui.cycle_sold_count_lbl = MagicMock()
        gui.cycle_module_status_lbl = MagicMock()
        gui.card_status = MagicMock()
        gui.sell_running = False
        gui.fechando_ordens = False
        gui.atualizar_botao_inicial = MagicMock()
        gui.atualizar_botao_venda = MagicMock()
        gui.atualizar_botao_ciclo = MagicMock()
        gui.show_notification = MagicMock()
        gui.cycle_stage_labels = {
            "buy": MagicMock(),
            "collect": MagicMock(),
            "sell": MagicMock(),
        }
        return gui

    def test_manual_intervention_stops_ui_and_marks_compact_hud(self):
        gui = self.make_gui()

        gui._process_log_message(
            '[INTERVENÇÃO NECESSÁRIA] Confirmação não pôde ser cancelada.'
        )

        self.assertFalse(gui.running)
        self.assertFalse(gui.cycle_running)
        self.assertTrue(gui._mini_intervention_required)
        gui.card_status.config.assert_called_with(text='INTERVENÇÃO', fg=COLOR_ERROR)
        gui.show_notification.assert_called_once_with('INTERVENÇÃO NECESSÁRIA')

    def test_protected_pause_updates_status_and_restores_cycle_stage(self):
        gui = self.make_gui()
        gui._render_cycle_stage = MagicMock()

        gui._process_log_message('[PAUSA PROTEGIDA] Restam 4m 12s.')

        gui.card_status.config.assert_called_with(text='PAUSA 4m 12s', fg=COLOR_ACCENT)
        gui.cycle_module_status_lbl.config.assert_called_with(
            text='PAUSA 4m 12s', fg=COLOR_ACCENT
        )

        gui._process_log_message('[PAUSA PROTEGIDA] Encerrada. Retomando automação.')

        gui.card_status.config.assert_called_with(text='ATIVO', fg=COLOR_SUCCESS)
        gui._render_cycle_stage.assert_called_once_with()

    def test_only_the_current_cycle_stage_is_highlighted(self):
        gui = self.make_gui()
        gui._render_cycle_stage = MagicMock()

        gui._set_cycle_stage("collect")

        self.assertEqual(gui.cycle_stage, "collect")
        self.assertTrue(gui.cycle_stage_labels["collect"]._mkt_stage_active)
        self.assertFalse(gui.cycle_stage_labels["buy"]._mkt_stage_active)
        self.assertFalse(gui.cycle_stage_labels["sell"]._mkt_stage_active)
        self.assertEqual(gui._render_cycle_stage.call_count, 3)

    def test_cycle_stage_follows_existing_transition_logs(self):
        gui = self.make_gui()

        gui._process_log_message(
            "[CICLO] Limite confirmado. Coletando e abrindo vendas..."
        )
        self.assertEqual(gui.cycle_stage, "collect")

        gui._process_log_message(
            "[CICLO] Coleta concluida e tela de venda confirmada."
        )
        self.assertEqual(gui.cycle_stage, "sell")

        gui._process_log_message(
            "[CICLO] Tela de compra confirmada. Retomando as ordens."
        )
        self.assertEqual(gui.cycle_stage, "buy")

    def test_cycle_counts_only_confirmed_orders_and_sales(self):
        gui = self.make_gui()
        gui.total_orders = 0
        gui.total_profit = 0
        gui.last_item_name = "Item"
        gui.atualizar_contadores_reais = MagicMock()
        gui.play_order_sound = MagicMock()
        gui.enqueue_notification = MagicMock()

        gui._process_log_message("[BUY] 1250.0")
        gui._process_log_message("[VENDA] Pedido de venda criado com sucesso.")

        self.assertEqual(gui.cycle_orders_completed, 1)
        self.assertEqual(gui.cycle_items_sold, 1)

    def test_standalone_sale_does_not_change_cycle_counter(self):
        gui = self.make_gui()
        gui.cycle_running = False

        gui._process_log_message("[VENDA] Pedido de venda criado com sucesso.")

        self.assertEqual(gui.cycle_items_sold, 0)

    def test_internal_standby_clears_the_active_cycle_stage(self):
        gui = self.make_gui()
        gui._render_cycle_stage = MagicMock()
        gui.atualizar_botao_ciclo = MagicMock()
        gui._set_cycle_stage("sell")

        gui._process_log_message(">>> Bot em Standby.")

        self.assertFalse(gui.cycle_running)
        self.assertIsNone(gui.cycle_stage)
        gui.atualizar_botao_ciclo.assert_called_once_with()


class ModuleSeparationTests(unittest.TestCase):
    def test_control_states_keep_buy_and_cycle_separate(self):
        self.assertEqual(
            build_control_state(True, "buy", False),
            {"run": True, "mode": "buy", "auto_cycle": False, "preserve_position": False},
        )
        self.assertEqual(
            build_control_state(True, "buy", True),
            {"run": True, "mode": "buy", "auto_cycle": True, "preserve_position": False},
        )

    def test_legacy_license_keeps_all_modules_available(self):
        legacy = {"modules": [MODULE_PURCHASE], "modulesEnforced": False}
        self.assertTrue(license_allows_module(legacy, MODULE_PURCHASE))
        self.assertTrue(license_allows_module(legacy, MODULE_SELL))
        self.assertTrue(license_allows_module(legacy, MODULE_CYCLE))

    def test_modular_license_only_unlocks_purchased_modules(self):
        modular = {"modules": [MODULE_PURCHASE], "modulesEnforced": True}
        self.assertTrue(license_allows_module(modular, MODULE_PURCHASE))
        self.assertFalse(license_allows_module(modular, MODULE_SELL))
        self.assertFalse(license_allows_module(modular, MODULE_CYCLE))

    def test_cycle_requires_purchase_and_sales_modules(self):
        complete = {
            "modules": [MODULE_PURCHASE, MODULE_SELL],
            "modulesEnforced": True,
        }
        self.assertTrue(license_allows_module(complete, MODULE_PURCHASE))
        self.assertTrue(license_allows_module(complete, MODULE_SELL))
        self.assertTrue(license_allows_module(complete, MODULE_CYCLE))

    @staticmethod
    def make_startable_gui():
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.key_info = {"modulesEnforced": False}
        gui.running = False
        gui.buy_paused = False
        gui.sell_running = False
        gui.cycle_running = False
        gui.fechando_ordens = False
        gui.shopping_running = False
        gui.shopping_paused = False
        gui.shopping_items = []
        gui.root = MagicMock()
        gui.salvar_ajustes_financeiros = MagicMock(return_value=True)
        gui.validar_calibragem_para_modo = MagicMock(return_value=True)
        gui.minimizar_para_execucao = MagicMock()
        gui.atualizar_botao_inicial = MagicMock()
        gui.atualizar_botao_ciclo = MagicMock()
        gui.atualizar_botao_venda = MagicMock()
        gui.atualizar_botao_shopping = MagicMock()
        gui.modulo_liberado = MagicMock(return_value=True)
        gui.card_status = MagicMock()
        gui.cycle_module_status_lbl = MagicMock()
        gui.sell_module_status_lbl = MagicMock()
        gui.shopping_module_status_lbl = MagicMock()
        gui.edit_status_lbl = MagicMock()
        gui.log = MagicMock()
        return gui

    def test_purchase_button_starts_buy_without_cycle_or_sell_validation(self):
        gui = self.make_startable_gui()
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.toggle_bot()

        gui.validar_calibragem_para_modo.assert_called_once_with("buy")
        dump.assert_called_once_with(
            {"run": True, "mode": "buy", "auto_cycle": False, "preserve_position": False},
            unittest.mock.ANY,
        )
        gui.minimizar_para_execucao.assert_called_once_with()

    def test_sale_button_collapses_panel_after_sale_calibration(self):
        gui = self.make_startable_gui()
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.iniciar_bot_venda()

        gui.validar_calibragem_para_modo.assert_called_once_with("sell")
        gui.minimizar_para_execucao.assert_called_once_with()
        dump.assert_called_once_with(
            {"run": True, "mode": "sell", "auto_cycle": False, "preserve_position": False},
            unittest.mock.ANY,
        )

    def test_close_orders_button_collapses_panel_after_close_calibration(self):
        gui = self.make_startable_gui()
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.toggle_fechamento()

        gui.validar_calibragem_para_modo.assert_called_once_with("close")
        gui.minimizar_para_execucao.assert_called_once_with()
        dump.assert_called_once_with(
            {"run": True, "mode": "close", "auto_cycle": False, "preserve_position": False},
            unittest.mock.ANY,
        )

    def test_invalid_calibration_does_not_collapse_or_start(self):
        gui = self.make_startable_gui()
        gui.validar_calibragem_para_modo.return_value = False

        gui.toggle_bot()

        gui.minimizar_para_execucao.assert_not_called()
        self.assertFalse(gui.running)

    def test_cycle_button_requires_complete_cycle_calibration_and_enables_cycle(self):
        gui = self.make_startable_gui()
        gui._salvar_limite_ciclo = MagicMock(return_value=48)
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.toggle_cycle_bot()

        self.assertEqual(
            gui.validar_calibragem_para_modo.call_args_list,
            [unittest.mock.call("cycle")],
        )
        dump.assert_called_once_with(
            {"run": True, "mode": "buy", "auto_cycle": True, "preserve_position": False},
            unittest.mock.ANY,
        )
        gui.minimizar_para_execucao.assert_called_once_with()

    def test_cycle_button_stop_preserves_position_to_resume_later(self):
        # O botão mostra "PARAR CICLO AUTOMÁTICO", mas o próprio código trata
        # como pausa (log diz "pausado") -- faltava preserve_position=True,
        # então iniciar de novo descartava a posição salva e recomeçava do
        # zero em vez de continuar.
        gui = self.make_startable_gui()
        gui.cycle_running = True
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.toggle_cycle_bot()

        self.assertFalse(gui.cycle_running)
        dump.assert_called_once_with(
            {"run": False, "mode": "buy", "auto_cycle": True, "preserve_position": True},
            unittest.mock.ANY,
        )

    def test_pausar_bot_preserves_position_and_marks_paused(self):
        gui = self.make_startable_gui()
        gui.running = True
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.pausar_bot()

        self.assertFalse(gui.running)
        self.assertTrue(gui.buy_paused)
        dump.assert_called_once_with(
            {"run": False, "mode": "buy", "auto_cycle": False, "preserve_position": True},
            unittest.mock.ANY,
        )

    def test_pausar_bot_does_nothing_when_not_running(self):
        gui = self.make_startable_gui()
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.pausar_bot()

        self.assertFalse(gui.buy_paused)
        dump.assert_not_called()

    def test_continuar_bot_resumes_from_paused_state(self):
        gui = self.make_startable_gui()
        gui.buy_paused = True
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.continuar_bot()

        self.assertTrue(gui.running)
        self.assertFalse(gui.buy_paused)
        dump.assert_called_once_with(
            {"run": True, "mode": "buy", "auto_cycle": False, "preserve_position": True},
            unittest.mock.ANY,
        )

    def test_continuar_bot_does_nothing_when_not_paused(self):
        gui = self.make_startable_gui()
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.continuar_bot()

        self.assertFalse(gui.running)
        dump.assert_not_called()

    def test_parar_via_pause_bot_clears_paused_flag(self):
        gui = self.make_startable_gui()
        gui.buy_paused = True
        gui.atualizar_botao_venda = MagicMock()
        gui.atualizar_botao_ciclo = MagicMock()
        with patch("builtins.open", mock_open()):
            gui.pause_bot()

        self.assertFalse(gui.buy_paused)

    def test_mini_hud_state_reports_paused_operation(self):
        self.assertEqual(
            build_mini_hud_state(buy_paused=True)["operation"], "COMPRA EM PAUSA"
        )
        self.assertEqual(
            build_mini_hud_state()["operation"], "AUTOMAÇÃO PARADA"
        )

    def test_shopping_refuses_to_start_without_pending_items(self):
        gui = self.make_startable_gui()
        gui.shopping_items = [{"nome": "Machado", "tier": 5, "status": "pedido_criado"}]
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.iniciar_shopping()
        dump.assert_not_called()
        self.assertFalse(gui.shopping_running)

    def test_shopping_refuses_to_start_while_buy_is_running(self):
        gui = self.make_startable_gui()
        gui.running = True
        gui.shopping_items = [{"nome": "Machado", "tier": 5, "status": "pendente"}]
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.iniciar_shopping()
        dump.assert_not_called()
        self.assertFalse(gui.shopping_running)

    def test_shopping_starts_with_pending_items(self):
        gui = self.make_startable_gui()
        gui.shopping_items = [{"nome": "Machado", "tier": 5, "status": "pendente"}]
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.iniciar_shopping()
        self.assertTrue(gui.shopping_running)
        dump.assert_called_once_with(
            {"run": True, "mode": "shopping", "auto_cycle": False, "preserve_position": False},
            unittest.mock.ANY,
        )
        gui.minimizar_para_execucao.assert_called_once_with()

    def test_pausar_shopping_preserves_position(self):
        gui = self.make_startable_gui()
        gui.shopping_running = True
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.pausar_shopping()
        self.assertFalse(gui.shopping_running)
        self.assertTrue(gui.shopping_paused)
        dump.assert_called_once_with(
            {"run": False, "mode": "shopping", "auto_cycle": False, "preserve_position": True},
            unittest.mock.ANY,
        )

    def test_continuar_shopping_resumes(self):
        gui = self.make_startable_gui()
        gui.shopping_paused = True
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.continuar_shopping()
        self.assertTrue(gui.shopping_running)
        self.assertFalse(gui.shopping_paused)
        dump.assert_called_once_with(
            {"run": True, "mode": "shopping", "auto_cycle": False, "preserve_position": True},
            unittest.mock.ANY,
        )

    def test_parar_shopping_resets_state(self):
        gui = self.make_startable_gui()
        gui.shopping_running = True
        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.parar_shopping()
        self.assertFalse(gui.shopping_running)
        self.assertFalse(gui.shopping_paused)
        dump.assert_called_once_with(
            {"run": False, "mode": "buy", "auto_cycle": False, "preserve_position": False},
            unittest.mock.ANY,
        )

    def test_pause_bot_also_stops_shopping(self):
        gui = self.make_startable_gui()
        gui.shopping_running = True
        with patch("builtins.open", mock_open()):
            gui.pause_bot()
        self.assertFalse(gui.shopping_running)
        self.assertFalse(gui.shopping_paused)
        gui.atualizar_botao_shopping.assert_called_once_with()


class ListaComprasUITests(unittest.TestCase):
    @staticmethod
    def make_gui_with_tree():
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.shopping_items = []
        gui.shopping_tree = MagicMock()
        gui.shopping_categoria_entry = MagicMock(get=MagicMock(return_value=""))
        gui.log = MagicMock()
        return gui

    def test_adicionar_item_rejects_empty_name(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="  "))
        with patch("interface.messagebox.showwarning") as warn:
            with patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()):
                gui.adicionar_item_lista_compras()
        warn.assert_called_once()
        self.assertEqual(gui.shopping_items, [])

    def test_adicionar_item_rejects_non_positive_quantity(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="Machado"))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="5"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value=".0"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="0"))
        with patch("interface.messagebox.showwarning") as warn:
            gui.adicionar_item_lista_compras()
        warn.assert_called_once()
        self.assertEqual(gui.shopping_items, [])

    def test_adicionar_item_appends_normalized_entry(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="  Machado  "))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="5"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value=".2"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="10"))
        with patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()):
            gui.adicionar_item_lista_compras()
        self.assertEqual(gui.shopping_items, [{
            "nome": "Machado", "tier": 5, "encantamento": ".2", "quantidade": 10,
            "categoria": "", "status": "pendente",
        }])

    def test_adicionar_item_rejects_tier_out_of_range(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="Machado"))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="9"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value=".0"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="1"))
        with patch("interface.messagebox.showwarning") as warn:
            gui.adicionar_item_lista_compras()
        warn.assert_called_once()
        self.assertEqual(gui.shopping_items, [])

    def test_adicionar_item_rejects_invalid_encantamento(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="Machado"))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="5"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value="9"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="1"))
        with patch("interface.messagebox.showwarning") as warn:
            gui.adicionar_item_lista_compras()
        warn.assert_called_once()
        self.assertEqual(gui.shopping_items, [])

    def test_adicionar_item_normalizes_bare_digit_encantamento(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="Machado"))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="5"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value="3"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="1"))
        with patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()):
            gui.adicionar_item_lista_compras()
        self.assertEqual(gui.shopping_items[0]["encantamento"], ".3")

    def test_adicionar_item_accepts_category_alias(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="Machado"))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="5"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value=".0"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="1"))
        gui.shopping_categoria_entry = MagicMock(get=MagicMock(return_value="arma"))
        with patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()):
            gui.adicionar_item_lista_compras()
        self.assertEqual(gui.shopping_items[0]["categoria"], "ARMAS")

    def test_adicionar_item_accepts_full_ingame_category_label(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="Robe"))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="5"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value=".0"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="1"))
        gui.shopping_categoria_entry = MagicMock(
            get=MagicMock(return_value="Armadura de Calçado")
        )
        with patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()):
            gui.adicionar_item_lista_compras()
        self.assertEqual(gui.shopping_items[0]["categoria"], "BOTAS")

    def test_adicionar_item_leaves_category_blank_by_default(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="Machado"))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="5"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value=".0"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="1"))
        with patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()):
            gui.adicionar_item_lista_compras()
        self.assertEqual(gui.shopping_items[0]["categoria"], "")

    def test_adicionar_item_rejects_unknown_category(self):
        gui = self.make_gui_with_tree()
        gui.shopping_nome_entry = MagicMock(get=MagicMock(return_value="Machado"))
        gui.shopping_tier_entry = MagicMock(get=MagicMock(return_value="5"))
        gui.shopping_encantamento_entry = MagicMock(get=MagicMock(return_value=".0"))
        gui.shopping_quantidade_entry = MagicMock(get=MagicMock(return_value="1"))
        gui.shopping_categoria_entry = MagicMock(get=MagicMock(return_value="categoria-inventada"))
        with patch("interface.messagebox.showwarning") as warn:
            gui.adicionar_item_lista_compras()
        warn.assert_called_once()
        self.assertEqual(gui.shopping_items, [])

    def test_remover_item_pops_selected_index(self):
        gui = self.make_gui_with_tree()
        gui.shopping_items = [
            {"nome": "Machado", "tier": 5, "encantamento": "", "quantidade": 1, "status": "pendente"},
            {"nome": "Capa", "tier": 4, "encantamento": ".2", "quantidade": 2, "status": "pendente"},
        ]
        gui.shopping_tree.selection.return_value = ("row1",)
        gui.shopping_tree.index.return_value = 0
        with patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()):
            gui.remover_item_lista_compras()
        self.assertEqual(len(gui.shopping_items), 1)
        self.assertEqual(gui.shopping_items[0]["nome"], "Capa")

    def test_remover_todos_does_nothing_when_list_already_empty(self):
        gui = self.make_gui_with_tree()
        with patch("interface.messagebox.askyesno") as confirm:
            gui.remover_todos_itens_lista_compras()
        confirm.assert_not_called()

    def test_remover_todos_keeps_list_when_not_confirmed(self):
        gui = self.make_gui_with_tree()
        gui.shopping_items = [
            {"nome": "Machado", "tier": 5, "encantamento": "", "quantidade": 1, "status": "pendente"},
        ]
        with patch("interface.messagebox.askyesno", return_value=False):
            gui.remover_todos_itens_lista_compras()
        self.assertEqual(len(gui.shopping_items), 1)

    def test_remover_todos_clears_list_when_confirmed(self):
        gui = self.make_gui_with_tree()
        gui.shopping_items = [
            {"nome": "Machado", "tier": 5, "encantamento": "", "quantidade": 1, "status": "pendente"},
            {"nome": "Capa", "tier": 4, "encantamento": ".2", "quantidade": 2, "status": "pendente"},
        ]
        with patch("interface.messagebox.askyesno", return_value=True), \
             patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()):
            gui.remover_todos_itens_lista_compras()
        self.assertEqual(gui.shopping_items, [])


class ValorMaximoShoppingTests(unittest.TestCase):
    @staticmethod
    def make_gui_with_entry():
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.shopping_valor_maximo_entry = MagicMock()
        return gui

    def test_carregar_reads_persisted_value(self):
        gui = self.make_gui_with_entry()
        with patch("interface.load_settings", return_value={"compra_programada_valor_maximo": 2000000}):
            gui.carregar_valor_maximo_shopping_ui()
        gui.shopping_valor_maximo_entry.delete.assert_called_once_with(0, "end")
        gui.shopping_valor_maximo_entry.insert.assert_called_once_with(0, "2000000")

    def test_carregar_defaults_to_zero_when_missing(self):
        gui = self.make_gui_with_entry()
        with patch("interface.load_settings", return_value={}):
            gui.carregar_valor_maximo_shopping_ui()
        gui.shopping_valor_maximo_entry.insert.assert_called_once_with(0, "0")

    def test_carregar_does_nothing_without_entry(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        with patch("interface.load_settings") as load:
            gui.carregar_valor_maximo_shopping_ui()
        load.assert_not_called()

    def test_salvar_parses_and_persists_formatted_value(self):
        gui = self.make_gui_with_entry()
        gui.shopping_valor_maximo_entry.get.return_value = "2.000.000"
        with patch("interface.load_settings", return_value={}), \
             patch("interface.save_settings") as save:
            valor = gui.salvar_valor_maximo_shopping_ui()
        self.assertEqual(valor, 2000000)
        save.assert_called_once_with("offsets.json", {"compra_programada_valor_maximo": 2000000})

    def test_salvar_treats_blank_as_zero(self):
        gui = self.make_gui_with_entry()
        gui.shopping_valor_maximo_entry.get.return_value = ""
        with patch("interface.load_settings", return_value={}), \
             patch("interface.save_settings"):
            valor = gui.salvar_valor_maximo_shopping_ui()
        self.assertEqual(valor, 0)

    def test_salvar_rejects_negative_value(self):
        gui = self.make_gui_with_entry()
        gui.shopping_valor_maximo_entry.get.return_value = "-5"
        with patch("interface.load_settings", return_value={}), \
             patch("interface.save_settings") as save, \
             patch("interface.messagebox.showwarning") as warn:
            valor = gui.salvar_valor_maximo_shopping_ui()
        self.assertIsNone(valor)
        save.assert_not_called()
        warn.assert_called_once()

    def test_salvar_rejects_garbage_text(self):
        gui = self.make_gui_with_entry()
        gui.shopping_valor_maximo_entry.get.return_value = "abc"
        with patch("interface.load_settings", return_value={}), \
             patch("interface.save_settings") as save, \
             patch("interface.messagebox.showwarning") as warn:
            valor = gui.salvar_valor_maximo_shopping_ui()
        self.assertIsNone(valor)
        save.assert_not_called()
        warn.assert_called_once()

    def test_salvar_without_entry_returns_zero_without_touching_disk(self):
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        with patch("interface.load_settings") as load, \
             patch("interface.save_settings") as save:
            valor = gui.salvar_valor_maximo_shopping_ui()
        self.assertEqual(valor, 0)
        load.assert_not_called()
        save.assert_not_called()


class ListaComprasCsvTests(unittest.TestCase):
    @staticmethod
    def make_gui_with_tree():
        gui = AlbionBotGUI.__new__(AlbionBotGUI)
        gui.shopping_items = []
        gui.shopping_tree = MagicMock()
        gui.log = MagicMock()
        return gui

    def test_exportar_cancelado_nao_grava_nem_loga(self):
        gui = self.make_gui_with_tree()
        with patch("interface.filedialog.asksaveasfilename", return_value=""):
            gui.exportar_lista_compras_csv()
        gui.log.assert_not_called()

    def test_exportar_grava_cabecalho_com_lista_vazia(self):
        gui = self.make_gui_with_tree()
        with tempfile.TemporaryDirectory() as tmpdir:
            destino = str(Path(tmpdir) / "lista.csv")
            with patch("interface.filedialog.asksaveasfilename", return_value=destino), \
                 patch("interface.messagebox.showinfo") as info:
                gui.exportar_lista_compras_csv()
            with open(destino, "r", encoding="utf-8-sig") as handle:
                linhas = handle.read().splitlines()
        self.assertEqual(linhas, ["Nome;Tier;Encantamento;Quantidade;Categoria"])
        info.assert_called_once()
        gui.log.assert_called_once()

    def test_exportar_grava_itens_existentes(self):
        gui = self.make_gui_with_tree()
        gui.shopping_items = [
            {
                "nome": "Machado", "tier": 5, "encantamento": ".2", "quantidade": 10,
                "categoria": "ARMAS", "status": "pendente",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            destino = str(Path(tmpdir) / "lista.csv")
            with patch("interface.filedialog.asksaveasfilename", return_value=destino), \
                 patch("interface.messagebox.showinfo"):
                gui.exportar_lista_compras_csv()
            with open(destino, "r", encoding="utf-8-sig") as handle:
                linhas = handle.read().splitlines()
        self.assertEqual(linhas[0], "Nome;Tier;Encantamento;Quantidade;Categoria")
        self.assertEqual(linhas[1], "Machado;5;.2;10;ARMAS")

    def test_importar_cancelado_nao_altera_lista(self):
        gui = self.make_gui_with_tree()
        with patch("interface.filedialog.askopenfilename", return_value=""):
            gui.importar_lista_compras_csv()
        self.assertEqual(gui.shopping_items, [])
        gui.log.assert_not_called()

    def test_importar_le_cabecalho_e_linhas_validas(self):
        gui = self.make_gui_with_tree()
        with tempfile.TemporaryDirectory() as tmpdir:
            origem = str(Path(tmpdir) / "lista.csv")
            with open(origem, "w", newline="", encoding="utf-8-sig") as handle:
                handle.write(
                    "Nome;Tier;Encantamento;Quantidade\r\n"
                    "Machado;5;.2;10\r\n"
                    "Capa;4;0;3\r\n"
                )
            with patch("interface.filedialog.askopenfilename", return_value=origem), \
                 patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()), \
                 patch("interface.messagebox.showinfo") as info:
                gui.importar_lista_compras_csv()
        self.assertEqual(gui.shopping_items, [
            {"nome": "Machado", "tier": 5, "encantamento": ".2", "quantidade": 10, "categoria": "", "status": "pendente"},
            {"nome": "Capa", "tier": 4, "encantamento": ".0", "quantidade": 3, "categoria": "", "status": "pendente"},
        ])
        info.assert_called_once()

    def test_importar_aceita_csv_separado_por_virgula(self):
        gui = self.make_gui_with_tree()
        with tempfile.TemporaryDirectory() as tmpdir:
            origem = str(Path(tmpdir) / "lista.csv")
            with open(origem, "w", newline="", encoding="utf-8-sig") as handle:
                handle.write(
                    "Nome,Tier,Encantamento,Quantidade\r\n"
                    "Machado,5,.2,10\r\n"
                    "Capa,4,0,3\r\n"
                )
            with patch("interface.filedialog.askopenfilename", return_value=origem), \
                 patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()), \
                 patch("interface.messagebox.showinfo") as info:
                gui.importar_lista_compras_csv()
        self.assertEqual(gui.shopping_items, [
            {"nome": "Machado", "tier": 5, "encantamento": ".2", "quantidade": 10, "categoria": "", "status": "pendente"},
            {"nome": "Capa", "tier": 4, "encantamento": ".0", "quantidade": 3, "categoria": "", "status": "pendente"},
        ])
        info.assert_called_once()

    def test_importar_le_categoria_e_aceita_apelidos(self):
        gui = self.make_gui_with_tree()
        with tempfile.TemporaryDirectory() as tmpdir:
            origem = str(Path(tmpdir) / "lista.csv")
            with open(origem, "w", newline="", encoding="utf-8-sig") as handle:
                handle.write(
                    "Nome;Tier;Encantamento;Quantidade;Categoria\r\n"
                    "Machado;5;.2;10;armas\r\n"
                    "Capa;4;.0;3;Armadura de Peitoral\r\n"
                    "Bolsa;4;.0;1;\r\n"
                )
            with patch("interface.filedialog.askopenfilename", return_value=origem), \
                 patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()), \
                 patch("interface.messagebox.showinfo") as info:
                gui.importar_lista_compras_csv()
        self.assertEqual(gui.shopping_items, [
            {"nome": "Machado", "tier": 5, "encantamento": ".2", "quantidade": 10, "categoria": "ARMAS", "status": "pendente"},
            {"nome": "Capa", "tier": 4, "encantamento": ".0", "quantidade": 3, "categoria": "PEITORAL", "status": "pendente"},
            {"nome": "Bolsa", "tier": 4, "encantamento": ".0", "quantidade": 1, "categoria": "", "status": "pendente"},
        ])
        info.assert_called_once()

    def test_importar_rejeita_categoria_nao_reconhecida(self):
        gui = self.make_gui_with_tree()
        with tempfile.TemporaryDirectory() as tmpdir:
            origem = str(Path(tmpdir) / "lista.csv")
            with open(origem, "w", newline="", encoding="utf-8-sig") as handle:
                handle.write(
                    "Nome;Tier;Encantamento;Quantidade;Categoria\r\n"
                    "Machado;5;.2;10;categoria-inventada\r\n"
                )
            with patch("interface.filedialog.askopenfilename", return_value=origem), \
                 patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()), \
                 patch("interface.messagebox.showinfo") as info:
                gui.importar_lista_compras_csv()
        self.assertEqual(gui.shopping_items, [])
        aviso = info.call_args[0][1]
        self.assertIn("1 linha", aviso)

    def test_importar_ignora_linhas_invalidas_e_conta(self):
        gui = self.make_gui_with_tree()
        with tempfile.TemporaryDirectory() as tmpdir:
            origem = str(Path(tmpdir) / "lista.csv")
            with open(origem, "w", newline="", encoding="utf-8-sig") as handle:
                handle.write(
                    "Nome;Tier;Encantamento;Quantidade\r\n"
                    "Machado;5;.2;10\r\n"
                    ";9;.2;10\r\n"
                )
            with patch("interface.filedialog.askopenfilename", return_value=origem), \
                 patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()), \
                 patch("interface.messagebox.showinfo") as info:
                gui.importar_lista_compras_csv()
        self.assertEqual(len(gui.shopping_items), 1)
        info.assert_called_once()
        aviso = info.call_args[0][1]
        self.assertIn("1 linha", aviso)

    def test_importar_sem_cabecalho_le_primeira_linha_como_dado(self):
        gui = self.make_gui_with_tree()
        with tempfile.TemporaryDirectory() as tmpdir:
            origem = str(Path(tmpdir) / "lista.csv")
            with open(origem, "w", newline="", encoding="utf-8-sig") as handle:
                handle.write("Machado;5;.2;10\r\n")
            with patch("interface.filedialog.askopenfilename", return_value=origem), \
                 patch.object(AlbionBotGUI, "salvar_lista_compras_ui", MagicMock()), \
                 patch("interface.messagebox.showinfo"):
                gui.importar_lista_compras_csv()
        self.assertEqual(len(gui.shopping_items), 1)
        self.assertEqual(gui.shopping_items[0]["nome"], "Machado")

    def test_importar_arquivo_vazio_mostra_aviso(self):
        gui = self.make_gui_with_tree()
        with tempfile.TemporaryDirectory() as tmpdir:
            origem = str(Path(tmpdir) / "lista.csv")
            with open(origem, "w", newline="", encoding="utf-8-sig") as handle:
                handle.write("")
            with patch("interface.filedialog.askopenfilename", return_value=origem), \
                 patch("interface.messagebox.showwarning") as warn:
                gui.importar_lista_compras_csv()
        self.assertEqual(gui.shopping_items, [])
        warn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
