import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

import numpy as np
from PIL import Image

import bot
from coordinate_system import ClientGeometry


class PedidoDetectionTests(unittest.TestCase):
    def test_purchase_motor_never_uses_escape_as_recovery(self):
        source = Path(bot.__file__).read_text(encoding="utf-8")
        self.assertNotIn("keyboard", source)

    def test_no_button_match_is_restricted_to_calibrated_area(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        template = np.zeros((20, 50), dtype=np.uint8)
        template[3:17, 4:46] = 180
        template[7:13, 16:34] = 40
        screenshot = np.zeros((40, 100), dtype=np.uint8)
        screenshot[10:30, 30:80] = template
        image = Image.fromarray(screenshot, mode="L").convert("RGB")

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=(40, 30, 50, 20)
        ), patch.object(bot, "get_template", return_value=template), patch.object(
            bot, "capture_region", return_value=image
        ) as capture:
            position, score, name = bot.localizar_referencia_na_area_offset(
                object(), {"btn_nao": [0.2, 0.3, 0.25, 0.2]}, "btn_nao", ("aviso_nao.png",)
            )

        self.assertEqual(name, "aviso_nao.png")
        self.assertGreaterEqual(score, 0.99)
        self.assertEqual(position, (70.0, 40.0))
        self.assertEqual(capture.call_args.args[0], (15, 20, 100, 40))

    def test_manual_intervention_writes_stop_before_raising(self):
        with patch.object(bot, "check_control", return_value=(True, "buy")), patch.object(
            bot, "auto_cycle_enabled", return_value=False
        ), patch("builtins.open", mock_open()) as control, patch.object(
            bot.json, "dump"
        ) as dump:
            with self.assertRaises(bot.BotStoppedException):
                bot.solicitar_intervencao_manual("teste")

        control.assert_called_once_with(bot.CONTROL_FILE, "w", encoding="utf-8")
        dump.assert_called_once_with(
            {"run": False, "mode": "buy", "auto_cycle": False},
            unittest.mock.ANY,
        )

    def test_fast_visual_check_uses_a_small_region_near_calibrated_point(self):
        geometry = ClientGeometry(0, 0, 1000, 800)
        offsets = {
            "_calibration": {
                "schema_version": 2,
                "coordinate_space": "albion_client_normalized",
                "client_width": 1000,
                "client_height": 800,
                "aspect_ratio": 1.25,
            },
            "sell_create_button": [0.5, 0.5],
        }
        template = np.zeros((18, 42), dtype=np.uint8)
        template[2:16, 3:39] = 80
        template[6:12, 9:33] = 220
        screen = np.full((60, 80), 15, dtype=np.uint8)
        screen[20:38, 19:61] = template
        image = Image.fromarray(screen, mode="L").convert("RGB")

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "get_template", return_value=template
        ), patch.object(bot, "capture_region", return_value=image) as capture:
            found, score, name = bot.verificar_referencia_proxima_offset(
                object(),
                offsets,
                "sell_create_button",
                ("btn_criar_venda.png",),
                threshold=0.8,
            )

        self.assertTrue(found)
        self.assertGreaterEqual(score, 0.99)
        self.assertEqual(name, "btn_criar_venda.png")
        self.assertLess(capture.call_args.args[0][2], geometry.width / 4)
        self.assertLess(capture.call_args.args[0][3], geometry.height / 4)

    def test_category_menu_waits_for_the_list_before_selecting(self):
        geometry = ClientGeometry(0, 0, 1000, 800)
        offsets = {
            "_calibration": {
                "schema_version": 2,
                "coordinate_space": "albion_client_normalized",
                "client_width": 1000,
                "client_height": 800,
                "aspect_ratio": 1.25,
            },
            "cat_clique_principal": [0.4, 0.1],
            "cat_clique_armas": [0.4, 0.3],
        }
        calls = []

        def click(x, y, _win):
            calls.append(("click", x, y))
            return True

        def sleep(duration):
            calls.append(("sleep", duration))

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "safe_click", side_effect=click
        ), patch.object(bot, "smart_sleep", side_effect=sleep), patch.object(
            bot, "retornar_ao_topo"
        ):
            changed = bot.executar_troca_categoria(
                object(), offsets, "cat_clique_armas"
            )

        self.assertTrue(changed)
        self.assertEqual(calls[0][0], "click")
        self.assertEqual(calls[1], ("sleep", bot.CATEGORY_MENU_OPEN_DELAY))
        self.assertEqual(calls[2][0], "click")
        self.assertGreaterEqual(bot.CATEGORY_MENU_OPEN_DELAY, 1.5)

    def test_next_page_always_restores_scrollbar_to_top(self):
        geometry = ClientGeometry(0, 0, 1000, 800)
        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_point", return_value=(500, 760)
        ), patch.object(bot, "safe_click", return_value=True), patch.object(
            bot, "smart_sleep"
        ), patch.object(bot, "retornar_ao_topo", return_value=True) as reset_top:
            changed = bot.clicar_proxima_pagina(object(), {})

        self.assertTrue(changed)
        reset_top.assert_called_once_with({}, unittest.mock.ANY, "top_start", "top_end")

    def test_visual_line_signatures_distinguish_similar_rows(self):
        region = (0, 0, 400, 240)
        image = np.full((240, 400, 3), 215, dtype=np.uint8)
        image[25:95, 10:80] = (210, 40, 40)
        image[145:215, 10:80] = (40, 210, 40)
        image[48:56, 95:260] = 30
        image[168:176, 95:260] = 30
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        boxes = [Box(300, 40, 80, 40), Box(300, 160, 80, 40)]

        signatures = bot._assinaturas_linhas_pedido(image, region, boxes)

        self.assertEqual(len(signatures), 2)
        self.assertFalse(bot.assinaturas_equivalentes(signatures[0], signatures[1]))
        self.assertTrue(bot.assinaturas_equivalentes(signatures[0], signatures[0]))

    def test_overlapping_rows_are_filtered_without_ocr(self):
        boxes = ["old", "new"]
        old_signature = (bytes([0] * 32), bytes([0] * 32), bytes([0] * 16))
        new_signature = (
            bytes([255] * 32),
            bytes([255] * 32),
            bytes([255] * 16),
        )

        rows, repeated = bot.filtrar_linhas_novas(
            boxes,
            [old_signature, new_signature],
            [old_signature],
        )

        self.assertEqual(rows, [("new", new_signature)])
        self.assertEqual(repeated, 1)

    def test_row_signature_survives_vertical_relocation_after_scroll(self):
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        boxes = [Box(300, 20, 80, 40), Box(300, 100, 80, 40)]
        before = np.full((160, 400, 3), 215, dtype=np.uint8)
        after = np.full((160, 400, 3), 215, dtype=np.uint8)
        before[20:60, 10:70] = (40, 210, 40)
        before[100:140, 10:70] = (40, 40, 210)
        after[20:60, 10:70] = (40, 40, 210)
        after[100:140, 10:70] = (210, 210, 40)
        before[36:44, 90:250] = 25
        before[116:124, 90:250] = 25
        after[36:44, 90:250] = 25
        after[116:124, 90:250] = 25

        before_signatures = bot._assinaturas_linhas_pedido(
            before, (0, 0, 400, 160), boxes
        )
        after_signatures = bot._assinaturas_linhas_pedido(
            after, (0, 0, 400, 160), boxes
        )

        self.assertTrue(
            bot.assinaturas_equivalentes(
                before_signatures[1], after_signatures[0]
            )
        )

    def test_unchanged_visible_batch_marks_real_page_end(self):
        signatures = [
            (
                bytes([index] * 32),
                bytes([index] * 32),
                bytes([index] * 16),
            )
            for index in range(1, 4)
        ]

        self.assertTrue(
            bot.conjuntos_assinaturas_equivalentes(signatures, list(reversed(signatures)))
        )

    def test_semantic_safety_key_blocks_same_row_but_preserves_quality(self):
        common = bytes([0] * 32)
        normal = (common, common, bytes([10] * 16))
        excellent = (common, common, bytes([20] * 16))

        first = bot.criar_chave_semantica_linha(
            "Arco do Mestre .1", 100_000, 40_000, normal
        )
        repeated = bot.criar_chave_semantica_linha(
            "  arco DO mestre .1 ", 100_000, 40_000, normal
        )
        other_quality = bot.criar_chave_semantica_linha(
            "Arco do Mestre .1", 100_000, 40_000, excellent
        )

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, other_quality)

    def test_exact_expected_price_wins_over_noisy_second_read(self):
        value, reason = bot._escolher_preco_confirmado(
            [(454, 0.95), (654, 0.95)], esperado=454
        )

        self.assertEqual(value, 454)
        self.assertEqual(reason, "")

    def test_never_removes_an_extra_digit_from_a_high_price(self):
        value, reason = bot._escolher_preco_confirmado(
            [(241_112, 0.99), (241_112, 0.98)], esperado=24_112
        )

        self.assertIsNone(value)
        self.assertIn("não corresponde", reason)

    def test_does_not_guess_when_one_digit_removal_cannot_make_expected_price(self):
        value, reason = bot._escolher_preco_confirmado(
            [(134_116, 0.99), (134_116, 0.98)], esperado=13_616
        )

        self.assertIsNone(value)
        self.assertIn("não corresponde", reason)

    def test_price_confirmation_accepts_small_real_ocr_difference(self):
        value, reason = bot._escolher_preco_confirmado(
            [(25_044, 0.91), (25_064, 0.83)], esperado=25_064
        )

        self.assertEqual(value, 25_064)
        self.assertEqual(reason, "")

    def test_price_confirmation_accepts_one_low_confidence_when_other_is_strong(self):
        value, reason = bot._escolher_preco_confirmado(
            [(39_718, 0.44), (39_718, 1.0)], esperado=39_718
        )

        self.assertEqual(value, 39_718)
        self.assertEqual(reason, "")

    def test_price_confirmation_rejects_material_difference(self):
        value, reason = bot._escolher_preco_confirmado(
            [(25_064, 0.99), (26_064, 0.99)], esperado=25_500
        )

        self.assertIsNone(value)
        self.assertIn("divergentes", reason)

    def test_final_purchase_price_uses_its_own_modal_region(self):
        geometry = ClientGeometry(0, 0, 100, 100)
        image = Image.fromarray(np.zeros((10, 20), dtype=np.uint8), mode="L").convert("RGB")
        reader = unittest.mock.Mock()
        reader.readtext.return_value = [(
            [[0, 0], [19, 0], [19, 9], [0, 9]],
            "24112",
            0.99,
        )]
        offsets = {
            "_calibration": {
                "schema_version": 2,
                "coordinate_space": "albion_client_normalized",
                "client_width": 100,
                "client_height": 100,
                "aspect_ratio": 1.0,
            },
            "compra": [0.7, 0.2, 0.1, 0.1],
            "preco_final_compra": [0.2, 0.5, 0.2, 0.1],
        }

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", wraps=bot.resolve_rect
        ) as resolve, patch.object(bot, "capture_region", return_value=image), patch.object(
            bot, "get_reader", return_value=reader
        ):
            value, reason = bot._ler_preco_compra_confirmacao(
                object(), offsets, preco_esperado=24_112
            )

        self.assertEqual(value, 24_112)
        self.assertEqual(reason, "")
        self.assertEqual(resolve.call_args.args[0], offsets["preco_final_compra"])

    def test_final_price_retry_costs_only_point_two_seconds(self):
        with patch.object(
            bot,
            "_ler_preco_compra_confirmacao",
            side_effect=[(None, "falha"), (24_112, "")],
        ), patch.object(bot, "smart_sleep") as sleep:
            value, reason = bot._confirmar_preco_final_compra(object(), {}, 24_111)

        self.assertEqual(value, 24_112)
        self.assertEqual(reason, "")
        sleep.assert_called_once_with(0.2)

    def test_parses_large_silver_value_with_group_separators(self):
        self.assertEqual(bot.limpar_num(["89.000.000"]), 89_000_000)

    def test_financial_limit_blocks_89_million_with_25_thousand_limit(self):
        allowed, reason = bot.validar_compra_financeira(
            89_000_000, 100_000_000, 25.0, 25_000
        )

        self.assertFalse(allowed)
        self.assertIn("excede o limite", reason)

    def test_financial_limit_accepts_valid_opportunity(self):
        allowed, reason = bot.validar_compra_financeira(
            20_000, 100_000, 25.0, 25_000
        )

        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_purchase_flow_does_not_click_when_initial_price_exceeds_limit(self):
        with patch.object(bot, "carregar_offsets", return_value={"valor_max": 25_000}), patch.object(
            bot, "clicar_offset"
        ) as click:
            purchased = bot.executar_cliques_compra(
                object(), {}, 89_000_000, 100_000_000, 25.0, 25_000
            )

        self.assertFalse(purchased)
        click.assert_not_called()

    def test_purchase_flow_never_clicks_create_when_final_price_exceeds_limit(self):
        with patch.object(bot, "carregar_offsets", return_value={"valor_max": 25_000}), patch.object(
            bot, "clicar_offset", return_value=True
        ) as click, patch.object(bot, "smart_sleep"), patch.object(
            bot, "_ler_preco_compra_confirmacao", return_value=(25_001, "")
        ), patch.object(
            bot, "recuperar_ou_parar_compra"
        ):
            purchased = bot.executar_cliques_compra(
                object(), {}, 24_999, 100_000, 25.0, 25_000
            )

        self.assertFalse(purchased)
        self.assertEqual([item.args[0] for item in click.call_args_list], ["btn_mais"])

    def test_rejects_selection_containing_the_whole_button_column(self):
        valid, reason = bot.validar_amostra_botao_pedido(128, 470, 1588, 890)

        self.assertFalse(valid)
        self.assertIn("APENAS UM", reason)

    def test_accepts_a_tight_single_button_selection(self):
        valid, reason = bot.validar_amostra_botao_pedido(106, 37, 1588, 890)

        self.assertTrue(valid)
        self.assertEqual(reason, "")

    def test_orders_detected_rows_from_top_to_bottom(self):
        Box = __import__("collections").namedtuple("Box", ["left", "top", "width", "height"])
        candidates = [
            (0.99, Box(100, 310, 105, 36)),
            (0.96, Box(101, 110, 105, 36)),
            (0.97, Box(99, 210, 105, 36)),
        ]

        boxes = bot._ordenar_botoes_pedido(candidates)

        self.assertEqual([box.top for box in boxes], [110, 210, 310])

    def test_detects_buttons_outside_old_rightmost_filter(self):
        template = np.zeros((12, 14), dtype=np.uint8)
        template[2:10, 2:12] = 70
        template[4:8, 4:10] = 230
        template[5:7, :] = 150

        screen = np.full((100, 120), 15, dtype=np.uint8)
        screen[10:22, 8:22] = template
        screen[60:72, 74:88] = template
        image = Image.fromarray(screen, mode="L").convert("RGB")
        geometry = ClientGeometry(0, 0, 120, 100)

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=(0, 0, 120, 100)
        ), patch.object(bot, "capture_region", return_value=image), patch.object(
            bot, "resource_path", side_effect=lambda path: path
        ), patch.object(bot.os.path, "exists", return_value=True), patch.object(
            bot, "get_template", return_value=template
        ):
            boxes, score, _template_name = bot.detectar_botoes_pedido(object(), {})

        self.assertGreaterEqual(score, 0.99)
        self.assertGreaterEqual(len(boxes), 2)
        self.assertTrue(any(box.left < 25 for box in boxes))
        self.assertTrue(any(box.left > 60 for box in boxes))

    def test_detects_sell_buttons_from_top_to_bottom(self):
        template = np.zeros((12, 24), dtype=np.uint8)
        template[2:10, 2:22] = 70
        template[4:8, 5:19] = 230
        template[5:7, :] = 150
        screen = np.full((100, 80), 15, dtype=np.uint8)
        screen[12:24, 40:64] = template
        screen[60:72, 40:64] = template
        image = Image.fromarray(screen, mode="L").convert("RGB")
        geometry = ClientGeometry(0, 0, 80, 100)

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=(0, 0, 80, 100)
        ), patch.object(bot, "capture_region", return_value=image), patch.object(
            bot, "resource_path", side_effect=lambda path: path
        ), patch.object(bot.os.path, "exists", return_value=True), patch.object(
            bot, "get_template", return_value=template
        ):
            boxes, score, _ = bot.detectar_botoes_vender(object(), {})

        self.assertGreaterEqual(score, 0.99)
        self.assertEqual([box.top for box in boxes], [12, 60])

    def test_sale_clicks_vender_minus_then_create(self):
        Box = __import__("collections").namedtuple("Box", ["left", "top", "width", "height"])
        button = Box(100, 200, 90, 30)
        calls = []

        def record_offset(name, _win, _offsets):
            calls.append(name)
            return True

        with patch.object(bot, "clicar_centro_bbox", side_effect=lambda *_: calls.append("vender") or True), patch.object(
            bot, "clicar_offset", side_effect=record_offset
        ), patch.object(bot, "ler_valor_venda", return_value=(1551, "1.551")), patch.object(
            bot, "smart_sleep"
        ), patch.object(bot, "check_stop"):
            completed = bot.executar_cliques_venda(object(), {}, button)

        self.assertEqual(completed, "sold")
        self.assertEqual(calls, ["vender", "sell_price_minus", "sell_create_button"])

    def test_sale_does_not_click_create_when_visual_reference_is_missing(self):
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        calls = []

        def record_offset(name, _win, _offsets):
            calls.append(name)
            return True

        with patch.object(
            bot, "clicar_centro_bbox", side_effect=lambda *_: calls.append("vender") or True
        ), patch.object(
            bot, "clicar_offset", side_effect=record_offset
        ), patch.object(
            bot, "ler_valor_venda", return_value=(1551, "1.551")
        ), patch.object(
            bot, "esperar_referencia_proxima_offset", side_effect=[True, False]
        ), patch.object(bot, "smart_sleep"), patch.object(bot, "check_stop"):
            completed = bot.executar_cliques_venda(
                object(), {}, Box(100, 200, 90, 30)
            )

        self.assertIsNone(completed)
        self.assertEqual(calls, ["vender", "sell_price_minus", "sell_close_button"])

    def test_sale_continues_when_modal_disappearance_is_ambiguous(self):
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        with patch.object(bot, "clicar_centro_bbox", return_value=True), patch.object(
            bot, "clicar_offset", return_value=True
        ), patch.object(
            bot, "ler_valor_venda", return_value=(1551, "1.551")
        ), patch.object(
            bot, "esperar_referencia_proxima_offset", return_value=True
        ), patch.object(
            bot, "esperar_referencia_sumir", return_value=False
        ), patch.object(
            bot, "garantir_modal_fechado", return_value=True
        ) as recover, patch.object(bot, "smart_sleep"), patch.object(bot, "check_stop"):
            completed = bot.executar_cliques_venda(
                object(), {}, Box(100, 200, 90, 30)
            )

        self.assertEqual(completed, "sold")
        recover.assert_called_once()

    def test_sale_closure_prefers_unique_price_control_disappearance(self):
        with patch.object(
            bot, "esperar_referencia_sumir", return_value=True
        ) as wait:
            closed = bot.confirmar_fechamento_modal_venda(object(), {})

        self.assertTrue(closed)
        wait.assert_called_once_with(
            unittest.mock.ANY,
            {},
            "sell_price_minus",
            ("btn_diminuir_preco.png",),
            timeout=0.8,
        )

    def test_sale_closure_uses_create_button_as_secondary_evidence(self):
        with patch.object(
            bot, "esperar_referencia_sumir", side_effect=[False, True]
        ) as wait:
            closed = bot.confirmar_fechamento_modal_venda(object(), {})

        self.assertTrue(closed)
        self.assertEqual(wait.call_count, 2)

    def test_sale_closure_is_ambiguous_only_when_both_controls_remain(self):
        with patch.object(
            bot, "esperar_referencia_sumir", side_effect=[False, False]
        ):
            closed = bot.confirmar_fechamento_modal_venda(object(), {})

        self.assertFalse(closed)

    def test_purchase_does_not_click_create_when_visual_reference_is_missing(self):
        with patch.object(
            bot, "carregar_offsets", return_value={"valor_max": 25_000}
        ), patch.object(
            bot, "clicar_offset", return_value=True
        ) as click, patch.object(
            bot, "_confirmar_preco_final_compra", return_value=(20_001, "")
        ), patch.object(
            bot, "esperar_referencia_proxima_offset", return_value=False
        ), patch.object(bot, "smart_sleep"), patch.object(
            bot, "recuperar_ou_parar_compra"
        ):
            purchased = bot.executar_cliques_compra(
                object(), {}, 20_000, 100_000, 25.0, 25_000
            )

        self.assertFalse(purchased)
        self.assertEqual([item.args[0] for item in click.call_args_list], ["btn_mais"])

    def test_purchase_recovery_clicks_no_only_when_both_buttons_are_visible(self):
        with patch.object(
            bot,
            "esperar_referencia_proxima_offset",
            return_value=True,
        ), patch.object(
            bot,
            "localizar_referencia_na_area_offset",
            return_value=((72.0, 48.0), 0.93, "aviso_nao.png"),
        ), patch.object(bot, "safe_click", return_value=True) as click, patch.object(
            bot, "esperar_referencia_sumir", side_effect=[True, True]
        ):
            recovered = bot.cancelar_confirmacao_compra_se_aberta(object(), {})

        self.assertTrue(recovered)
        click.assert_called_once_with(72.0, 48.0, unittest.mock.ANY)

    def test_purchase_recovery_does_nothing_when_confirmation_is_absent(self):
        with patch.object(
            bot, "esperar_referencia_proxima_offset", return_value=False
        ), patch.object(
            bot,
            "localizar_referencia_na_area_offset",
            return_value=(None, 0.12, "aviso_nao.png"),
        ), patch.object(bot, "safe_click") as click:
            recovered = bot.cancelar_confirmacao_compra_se_aberta(object(), {})

        self.assertTrue(recovered)
        click.assert_not_called()

    def test_purchase_recovery_refuses_partial_visual_confirmation(self):
        with patch.object(
            bot, "esperar_referencia_proxima_offset", return_value=True
        ), patch.object(
            bot,
            "localizar_referencia_na_area_offset",
            return_value=(None, 0.31, "aviso_nao.png"),
        ), patch.object(bot, "safe_click") as click:
            recovered = bot.cancelar_confirmacao_compra_se_aberta(object(), {})

        self.assertFalse(recovered)
        click.assert_not_called()

    def test_purchase_recovery_requires_both_buttons_to_disappear(self):
        with patch.object(
            bot, "esperar_referencia_proxima_offset", return_value=True
        ), patch.object(
            bot,
            "localizar_referencia_na_area_offset",
            return_value=((72.0, 48.0), 0.93, "aviso_nao.png"),
        ), patch.object(bot, "safe_click", return_value=True), patch.object(
            bot, "esperar_referencia_sumir", side_effect=[True, False]
        ):
            recovered = bot.cancelar_confirmacao_compra_se_aberta(object(), {})

        self.assertFalse(recovered)

    def test_sim_fallback_is_blocked_without_local_visual_confirmation(self):
        geometry = ClientGeometry(0, 0, 100, 100)
        blank = Image.fromarray(np.zeros((100, 100), dtype=np.uint8), mode="L").convert("RGB")
        offsets = {
            "_calibration": {
                "schema_version": 2,
                "coordinate_space": "albion_client_normalized",
                "client_width": 100,
                "client_height": 100,
                "aspect_ratio": 1.0,
            },
            "btn_sim": [0.4, 0.4, 0.2, 0.1],
        }
        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "capture_region", return_value=blank
        ), patch.object(bot, "localizar_imagem_cv2", return_value=None), patch.object(
            bot, "esperar_referencia_proxima_offset", return_value=False
        ), patch.object(bot, "safe_click") as click, patch.object(
            bot, "smart_sleep"
        ), patch.object(bot, "check_stop"):
            confirmed = bot.confirmar_sim(object(), offsets)

        self.assertFalse(confirmed)
        click.assert_not_called()

    def test_sale_without_price_closes_item_without_selling(self):
        Box = __import__("collections").namedtuple("Box", ["left", "top", "width", "height"])
        calls = []

        def record_offset(name, _win, _offsets):
            calls.append(name)
            return True

        with patch.object(bot, "clicar_centro_bbox", side_effect=lambda *_: calls.append("vender") or True), patch.object(
            bot, "clicar_offset", side_effect=record_offset
        ), patch.object(bot, "ler_valor_venda", return_value=(None, "N/A")), patch.object(
            bot, "smart_sleep"
        ), patch.object(bot, "check_stop"):
            result = bot.executar_cliques_venda(object(), {}, Box(1, 2, 3, 4))

        self.assertEqual(result, "skipped")
        self.assertEqual(calls, ["vender", "sell_close_button"])

    def test_zero_na_and_empty_prices_are_rejected(self):
        for text in ([], ["0"], ["N/A"], ["sem preço"]):
            with self.subTest(text=text):
                self.assertIsNone(bot.extrair_valor_venda(text))

    def test_sale_scroll_moves_five_items_inside_calibrated_area(self):
        geometry = ClientGeometry(0, 0, 800, 600)
        before = Image.fromarray(np.zeros((100, 300), dtype=np.uint8), mode="L").convert("RGB")
        after_array = np.zeros((100, 300), dtype=np.uint8)
        after_array[:, 20:80] = 100
        after = Image.fromarray(after_array, mode="L").convert("RGB")

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=(600, 100, 100, 100)
        ), patch.object(bot, "capture_region", side_effect=[before, after]), patch.object(
            bot.pyautogui, "moveTo"
        ) as move_to, patch.object(bot.pyautogui, "scroll") as scroll, patch.object(
            bot, "smart_sleep"
        ):
            moved = bot.realizar_scroll_venda(object(), {}, itens=5)

        self.assertTrue(moved)
        move_to.assert_called_once_with(650, 150)
        scroll.assert_called_once_with(-5)

    def test_collect_cycle_clicks_counter_collect_all_and_sale_menu(self):
        calls = []

        def record_offset(name, _win, _offsets):
            calls.append(name)
            return True

        with patch.object(bot, "clicar_offset", side_effect=record_offset), patch.object(
            bot, "smart_sleep"
        ) as sleep, patch.object(
            bot, "esperar_template_ciclo", return_value=True
        ), patch.object(
            bot, "esperar_botoes_ciclo", return_value=True
        ), patch.object(bot, "trocar_modo_controle") as change_mode:
            completed = bot.coletar_e_abrir_vendas(object(), {})

        self.assertTrue(completed)
        self.assertEqual(
            calls,
            ["cycle_counter_area", "cycle_collect_all", "cycle_sell_menu"],
        )
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [10.0])
        change_mode.assert_called_once_with("sell")

    def test_missing_transaction_button_is_read_as_no_counter(self):
        geometry = ClientGeometry(0, 0, 100, 100)
        blank = Image.fromarray(np.zeros((20, 20), dtype=np.uint8), mode="L").convert("RGB")
        reader = unittest.mock.Mock()
        reader.readtext.return_value = []
        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=(10, 10, 20, 20)
        ), patch.object(bot, "capture_region", return_value=blank), patch.object(
            bot, "get_reader", return_value=reader
        ):
            value, raw = bot.ler_contador_transacoes(object(), {})

        self.assertIsNone(value)
        self.assertEqual(raw, "")

    def test_purchase_page_number_uses_calibrated_area(self):
        geometry = ClientGeometry(0, 0, 100, 100)
        image = Image.fromarray(np.full((12, 18), 120, dtype=np.uint8), mode="L").convert("RGB")
        reader = unittest.mock.Mock()
        reader.readtext.return_value = ["12"]
        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=(40, 80, 18, 12)
        ) as resolve, patch.object(bot, "capture_region", return_value=image), patch.object(
            bot, "get_reader", return_value=reader
        ):
            value, raw = bot.ler_numero_pagina_compra(
                object(), {"buy_page_number_area": {"x": 0.4}}
            )

        self.assertEqual((value, raw), (12, "12"))
        self.assertEqual(resolve.call_args.args[0], {"x": 0.4})

    def test_purchase_page_confirmation_requires_two_equal_reads(self):
        with patch.object(
            bot,
            "ler_numero_pagina_compra",
            side_effect=[(3, "3"), (2, "2")],
        ), patch.object(bot, "smart_sleep"):
            confirmed, read, raw = bot.confirmar_pagina_compra(object(), {}, 3)

        self.assertFalse(confirmed)
        self.assertEqual(read, 2)
        self.assertEqual(raw, "3 / 2")

    def test_cycle_restore_replays_page_and_scroll_then_confirms(self):
        win = object()
        state = {
            "category_key": "cat_clique_armas",
            "category_label": "ARMAS",
            "page": 3,
            "scroll_batches": 2,
        }
        with patch.object(bot, "executar_troca_categoria", return_value=True) as category, patch.object(
            bot, "tem_mais_paginas", return_value=True
        ) as more_pages, patch.object(
            bot, "clicar_proxima_pagina", return_value=True
        ) as next_page, patch.object(
            bot, "realizar_scroll", return_value=True
        ) as scroll, patch.object(
            bot, "confirmar_pagina_compra", return_value=(True, 3, "3 / 3")
        ) as confirm, patch.object(bot, "smart_sleep"):
            restored = bot.restaurar_navegacao_compra(win, {}, state)

        self.assertTrue(restored)
        category.assert_called_once_with(win, {}, "cat_clique_armas")
        self.assertEqual(more_pages.call_count, 2)
        self.assertEqual(next_page.call_count, 2)
        self.assertEqual(scroll.call_count, 2)
        confirm.assert_called_once_with(win, {}, 3)

    def test_cycle_restore_stops_when_page_cannot_be_confirmed(self):
        state = {
            "category_key": "cat_clique_armas",
            "category_label": "ARMAS",
            "page": 1,
            "scroll_batches": 0,
        }
        with patch.object(bot, "executar_troca_categoria", return_value=True), patch.object(
            bot, "confirmar_pagina_compra", return_value=(False, None, "vazio / vazio")
        ):
            restored = bot.restaurar_navegacao_compra(object(), {}, state)

        self.assertFalse(restored)

    def test_purchase_menu_opens_without_panel_toggle_click(self):
        calls = []

        def record_offset(name, _win, _offsets):
            calls.append(name)
            return True

        with patch.object(bot, "clicar_offset", side_effect=record_offset), patch.object(
            bot, "smart_sleep"
        ) as sleep, patch.object(
            bot, "esperar_botoes_ciclo", return_value=True
        ), patch.object(bot, "trocar_modo_controle") as change_mode:
            completed = bot.abrir_ordens_de_compra(object(), {})

        self.assertTrue(completed)
        self.assertEqual(calls, ["cycle_buy_menu"])
        sleep.assert_not_called()
        change_mode.assert_called_once_with("buy")

class CycleLimitTests(unittest.TestCase):
    def test_cycle_limit_defaults_to_48_for_old_or_invalid_settings(self):
        self.assertEqual(bot.get_cycle_order_limit({}), 48)
        self.assertEqual(bot.get_cycle_order_limit({"cycle_order_limit": "inválido"}), 48)
        self.assertEqual(bot.get_cycle_order_limit({"cycle_order_limit": 0}), 48)

    def test_cycle_limit_accepts_configured_value(self):
        self.assertEqual(bot.get_cycle_order_limit({"cycle_order_limit": "24"}), 24)
        self.assertEqual(bot.get_cycle_order_limit({"cycle_order_limit": "72"}), 48)


class RemoverPedidosTests(unittest.TestCase):
    def test_linha_pedido_e_minha_uses_default_key_when_omitted(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        offsets = {"compra_topo_cor": [0.1, 0.1, 0.2, 0.2]}
        image = Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8) + 50, mode="RGB")

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect"
        ) as resolve_rect, patch.object(bot, "capture_region", return_value=image):
            resolve_rect.return_value = (0, 0, 10, 10)
            eh_meu, brilho = bot.linha_pedido_e_minha(offsets, object())

        resolve_rect.assert_called_once_with(
            offsets["compra_topo_cor"], geometry, offsets
        )
        self.assertTrue(eh_meu)
        self.assertAlmostEqual(brilho, 50.0)

    def test_linha_pedido_e_minha_reads_alternate_calibrated_key(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        offsets = {
            "compra_topo_cor": [0.1, 0.1, 0.2, 0.2],
            "remover_pedidos_topo_cor": [0.5, 0.5, 0.2, 0.2],
        }
        image = Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8) + 220, mode="RGB")

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect"
        ) as resolve_rect, patch.object(bot, "capture_region", return_value=image):
            resolve_rect.return_value = (0, 0, 10, 10)
            eh_meu, brilho = bot.linha_pedido_e_minha(
                offsets, object(), "remover_pedidos_topo_cor"
            )

        resolve_rect.assert_called_once_with(
            offsets["remover_pedidos_topo_cor"], geometry, offsets
        )
        self.assertFalse(eh_meu)
        self.assertAlmostEqual(brilho, 220.0)

    def test_linha_pedido_e_minha_returns_none_when_alternate_key_not_calibrated(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        offsets = {}

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=None
        ):
            eh_meu, brilho = bot.linha_pedido_e_minha(
                offsets, object(), "remover_pedidos_topo_cor"
            )

        self.assertFalse(eh_meu)
        self.assertIsNone(brilho)

    def test_realizar_scroll_and_retornar_ao_topo_accept_alternate_keys(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        offsets = {
            "remover_pedidos_drag_start": [0.1, 0.8],
            "remover_pedidos_drag_end": [0.1, 0.2],
            "remover_pedidos_top_start": [0.1, 0.2],
            "remover_pedidos_top_end": [0.1, 0.8],
        }

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_point", side_effect=lambda value, *_a, **_k: tuple(value) if value else None
        ), patch.object(bot.pyautogui, "moveTo"), patch.object(
            bot.pyautogui, "mouseDown"
        ), patch.object(bot.pyautogui, "mouseUp"), patch.object(
            bot.pyautogui, "dragTo"
        ), patch.object(bot, "smart_sleep"):
            scrolled = bot.realizar_scroll(
                offsets, object(), "remover_pedidos_drag_start", "remover_pedidos_drag_end"
            )
            reset = bot.retornar_ao_topo(
                offsets, object(), "remover_pedidos_top_start", "remover_pedidos_top_end"
            )

        self.assertTrue(scrolled)
        self.assertTrue(reset)

    def test_realizar_scroll_with_default_keys_still_works(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        offsets = {"drag_start": [0.1, 0.8], "drag_end": [0.1, 0.2]}

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_point", side_effect=lambda value, *_a, **_k: tuple(value) if value else None
        ), patch.object(bot.pyautogui, "moveTo"), patch.object(
            bot.pyautogui, "mouseDown"
        ), patch.object(bot.pyautogui, "mouseUp"), patch.object(bot, "smart_sleep"):
            scrolled = bot.realizar_scroll(offsets, object())

        self.assertTrue(scrolled)

    def test_tem_mais_paginas_accepts_alternate_key(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        offsets = {"remover_pedidos_btn_proxima": [0.5, 0.5]}

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_point", return_value=(100, 50)
        ) as resolve_point, patch.object(
            bot, "capture_region", return_value=Image.new("RGB", (40, 40), (0, 0, 0))
        ):
            bot.tem_mais_paginas(object(), offsets, "remover_pedidos_btn_proxima")

        resolve_point.assert_called_once_with(
            offsets["remover_pedidos_btn_proxima"], geometry, offsets
        )

    def test_clicar_proxima_pagina_forwards_alternate_keys_to_retornar_ao_topo(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        offsets = {"remover_pedidos_btn_proxima": [0.5, 0.5]}

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_point", return_value=(100, 50)
        ), patch.object(bot, "safe_click", return_value=True), patch.object(
            bot, "smart_sleep"
        ), patch.object(bot, "retornar_ao_topo", return_value=True) as reset_top:
            changed = bot.clicar_proxima_pagina(
                object(),
                offsets,
                "remover_pedidos_btn_proxima",
                "remover_pedidos_top_start",
                "remover_pedidos_top_end",
            )

        self.assertTrue(changed)
        reset_top.assert_called_once_with(
            offsets, unittest.mock.ANY, "remover_pedidos_top_start", "remover_pedidos_top_end"
        )

    def test_parear_editar_com_cancelar_matches_same_row_by_vertical_proximity(self):
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        editar = [Box(100, 40, 90, 30), Box(100, 140, 90, 30)]
        cancelar = [Box(300, 145, 24, 24), Box(300, 45, 24, 24)]

        pares = bot.parear_editar_com_cancelar(editar, cancelar)

        self.assertEqual(len(pares), 2)
        self.assertEqual(pares[0], (editar[0], cancelar[1]))
        self.assertEqual(pares[1], (editar[1], cancelar[0]))

    def test_parear_editar_com_cancelar_ignores_rows_without_a_close_match(self):
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        editar = [Box(100, 40, 90, 30), Box(100, 140, 90, 30)]
        cancelar = [Box(300, 45, 24, 24)]

        pares = bot.parear_editar_com_cancelar(editar, cancelar, tolerancia_vertical=22.0)

        self.assertEqual(pares, [(editar[0], cancelar[0])])

    def test_parear_editar_com_cancelar_does_not_reuse_the_same_cancel_button(self):
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        editar = [Box(100, 40, 90, 30), Box(100, 44, 90, 30)]
        cancelar = [Box(300, 42, 24, 24)]

        pares = bot.parear_editar_com_cancelar(editar, cancelar)

        self.assertEqual(len(pares), 1)

    def test_detectar_botoes_por_template_uses_area_key_and_template_filename(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        template = np.zeros((20, 50), dtype=np.uint8)
        template[3:17, 4:46] = 180
        template[7:13, 16:34] = 40
        screenshot = np.zeros((40, 100), dtype=np.uint8)
        screenshot[10:30, 30:80] = template
        image = Image.fromarray(screenshot, mode="L").convert("RGB")

        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=(0, 0, 100, 40)
        ) as resolve_rect, patch.object(
            bot, "resource_path", return_value="assets/editar_pedido_usuario.png"
        ), patch("os.path.exists", return_value=True), patch.object(
            bot, "get_template", return_value=template
        ), patch.object(bot, "capture_region", return_value=image):
            boxes, score, name = bot.detectar_botoes_por_template(
                object(), {"remover_pedidos_area_lista": [0, 0, 1, 1]},
                "remover_pedidos_area_lista", "editar_pedido_usuario.png",
            )

        resolve_rect.assert_called_once_with(
            [0, 0, 1, 1], geometry, {"remover_pedidos_area_lista": [0, 0, 1, 1]}
        )
        self.assertEqual(name, "editar_pedido_usuario.png")
        self.assertGreaterEqual(score, 0.99)
        self.assertEqual(len(boxes), 1)
        self.assertEqual((boxes[0].left, boxes[0].top), (30, 10))

    def test_detectar_botoes_por_template_reports_missing_area(self):
        geometry = ClientGeometry(0, 0, 200, 100)
        with patch.object(bot, "get_client_geometry", return_value=geometry), patch.object(
            bot, "resolve_rect", return_value=None
        ):
            boxes, score, reason = bot.detectar_botoes_por_template(
                object(), {}, "remover_pedidos_area_lista", "editar_pedido_usuario.png"
            )

        self.assertEqual(boxes, [])
        self.assertEqual(score, -1.0)
        self.assertIn("remover_pedidos_area_lista", reason)

    def test_keep_then_cancel_index_advances_through_a_shrinking_list(self):
        """Regressão: um item mantido (ainda meu) não pode travar o loop no
        mesmo item para sempre, e cancelar um item não pode fazer o bot voltar
        a ler desde o topo -- a próxima posição livre já é o próximo item."""
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        editar = [Box(100, 40, 90, 30), Box(100, 100, 90, 30), Box(100, 160, 90, 30)]
        cancelar = [Box(300, 42, 24, 24), Box(300, 102, 24, 24), Box(300, 162, 24, 24)]
        pares = bot.parear_editar_com_cancelar(editar, cancelar)

        itens_mantidos_no_topo = 0
        # item 1 ainda é meu -> mantém, avança o contador sem cancelar nada.
        self.assertEqual(pares[itens_mantidos_no_topo], (editar[0], cancelar[0]))
        itens_mantidos_no_topo += 1

        # item 2 não é mais meu -> seria cancelado aqui; o contador NÃO avança.
        self.assertEqual(pares[itens_mantidos_no_topo], (editar[1], cancelar[1]))

        # O jogo remove o item cancelado e desloca o item 3 pra cima.
        pares_apos_cancelar = bot.parear_editar_com_cancelar(
            [editar[0], editar[2]], [cancelar[0], cancelar[2]]
        )

        # Com o mesmo contador (não voltou a 0), o próximo item conferido é o
        # item 3 -- não o item 1 de novo.
        self.assertEqual(
            pares_apos_cancelar[itens_mantidos_no_topo], (editar[2], cancelar[2])
        )

    def test_capturar_conteudo_linha_crops_fixed_slot_left_of_editar_button(self):
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        area_region = (100, 200, 400, 300)
        editar_box = Box(350, 240, 90, 30)

        with patch.object(bot, "capture_region") as capture_region:
            capture_region.return_value = Image.new("RGB", (10, 10), (0, 0, 0))
            bot.capturar_conteudo_linha(area_region, editar_box)

        capture_region.assert_called_once_with((100, 240, 238, 30))

    def test_cancellation_confirmation_detects_content_change_even_with_same_row_count(self):
        """Regressão: se a lista tiver mais itens do que cabem na tela, um item
        escondido sobe para a posição cancelada e a CONTAGEM total não muda --
        a confirmação precisa reconhecer que o CONTEÚDO daquela linha mudou."""
        Box = __import__("collections").namedtuple(
            "Box", ["left", "top", "width", "height"]
        )
        area_region = (0, 0, 400, 240)
        editar_box = Box(300, 40, 90, 30)

        antes = np.full((30, 218, 3), 215, dtype=np.uint8)
        antes[5:25, 5:75] = (210, 40, 40)  # item cancelado (ícone vermelho)
        depois = np.full((30, 218, 3), 215, dtype=np.uint8)
        depois[5:25, 5:75] = (40, 40, 210)  # item que subiu no lugar (ícone azul)

        sig_antes = bot._assinatura_visual_linha(antes)
        sig_depois = bot._assinatura_visual_linha(depois)

        self.assertFalse(bot.assinaturas_equivalentes(sig_antes, sig_depois))

    def test_cancellation_confirmation_rejects_an_unchanged_row(self):
        image = np.full((30, 218, 3), 215, dtype=np.uint8)
        image[5:25, 5:75] = (210, 40, 40)

        sig_antes = bot._assinatura_visual_linha(image)
        sig_depois = bot._assinatura_visual_linha(image.copy())

        self.assertTrue(bot.assinaturas_equivalentes(sig_antes, sig_depois))


class RemoverPedidosCalibrationTests(unittest.TestCase):
    def test_required_keys_cover_the_new_calibration_group(self):
        from coordinate_system import REMOVER_PEDIDOS_REQUIRED_KEYS, SPATIAL_KEYS

        expected = {
            "remover_pedidos_area_lista",
            "remover_pedidos_btn_editar",
            "remover_pedidos_btn_cancelar",
            "remover_pedidos_topo_cor",
            "remover_pedidos_btn_proxima",
            "remover_pedidos_drag_start",
            "remover_pedidos_drag_end",
            "remover_pedidos_top_start",
            "remover_pedidos_top_end",
        }
        self.assertEqual(set(REMOVER_PEDIDOS_REQUIRED_KEYS), expected)
        self.assertTrue(expected.issubset(SPATIAL_KEYS))

    def test_validate_calibration_blocks_when_a_required_key_is_missing(self):
        from coordinate_system import (
            META_KEY,
            REMOVER_PEDIDOS_REQUIRED_KEYS,
            calibration_metadata,
            validate_calibration,
        )

        geometry = ClientGeometry(0, 0, 1920, 1080)
        offsets = {
            key: [0.1, 0.1, 0.1, 0.1]
            for key in list(REMOVER_PEDIDOS_REQUIRED_KEYS)[:-1]
        }
        offsets[META_KEY] = calibration_metadata(geometry)

        valid, _reason = validate_calibration(offsets, geometry, mode="remover_pedidos")

        self.assertFalse(valid)

    def test_validate_calibration_passes_with_all_required_keys(self):
        from coordinate_system import (
            META_KEY,
            REMOVER_PEDIDOS_REQUIRED_KEYS,
            calibration_metadata,
            validate_calibration,
        )

        geometry = ClientGeometry(0, 0, 1920, 1080)
        offsets = {key: [0.1, 0.1, 0.1, 0.1] for key in REMOVER_PEDIDOS_REQUIRED_KEYS}
        offsets[META_KEY] = calibration_metadata(geometry)

        valid, reason = validate_calibration(offsets, geometry, mode="remover_pedidos")

        self.assertTrue(valid, reason)


if __name__ == "__main__":
    unittest.main()
