"""Testes da aba ARTEFATOS: compra dedicada, travada na categoria Artefato, com
quantidade de unidades por pedido."""

import contextlib
import io
import unittest
from unittest.mock import MagicMock, mock_open, patch

import bot
import interface
from coordinate_system import (
    ARTEFATOS_REQUIRED_KEYS,
    BUY_REQUIRED_KEYS,
    META_KEY,
    ClientGeometry,
    calibration_metadata,
    validate_calibration,
)

# Preço/limites usados nos cenários de compra. Com quantidade 10 o pedido custa
# (20_000 + 1) * 10 = 200_010 de prata + 5_000 de taxa (2,5%) = 205_010.
PRECO = 20_000
VENDA = 100_000
LUCRO_MINIMO = 25.0
LIMITE_EXATO_QTD_10 = 205_010


class CompraComQuantidadeTests(unittest.TestCase):
    """executar_cliques_compra: quantidade_desejada > 1 (só o modo Artefatos usa)."""

    def executar(
        self,
        *,
        preco=PRECO,
        venda=VENDA,
        limite=250_000,
        quantidade=None,
        preco_final=None,
        resultado_quantidade=(True, ""),
    ):
        eventos: list[str] = []

        def clicar(nome, *_args, **_kwargs):
            eventos.append(nome)
            return True

        def ajustar(_win, _offsets, quantidade_pedida):
            eventos.append(f"qtd:{quantidade_pedida}")
            return resultado_quantidade

        argumentos = [object(), {}, preco, venda, LUCRO_MINIMO, limite]
        if quantidade is not None:
            argumentos.append(quantidade)

        saida = io.StringIO()
        with patch.object(
            bot, "carregar_offsets", return_value={"valor_max": limite}
        ), patch.object(bot, "clicar_offset", side_effect=clicar), patch.object(
            bot, "_ajustar_quantidade_pedido", side_effect=ajustar
        ), patch.object(
            bot,
            "_confirmar_preco_final_compra",
            return_value=(preco_final if preco_final is not None else preco + 1, ""),
        ), patch.object(
            bot, "esperar_referencia_proxima_offset", return_value=True
        ), patch.object(bot, "confirmar_sim", return_value=True), patch.object(
            bot, "esperar_referencia_sumir", return_value=True
        ), patch.object(bot, "smart_sleep"), patch.object(
            bot, "recuperar_ou_parar_compra"
        ) as recuperar, contextlib.redirect_stdout(saida):
            comprou = bot.executar_cliques_compra(*argumentos)

        return comprou, eventos, recuperar, saida.getvalue()

    def test_default_call_never_touches_the_quantity_field(self):
        comprou, eventos, recuperar, _ = self.executar()

        self.assertTrue(comprou)
        self.assertEqual(eventos, ["btn_mais", "btn_criar"])
        recuperar.assert_not_called()

    def test_quantity_one_behaves_like_the_default_call(self):
        comprou, eventos, _, _ = self.executar(quantidade=1)

        self.assertTrue(comprou)
        self.assertEqual(eventos, ["btn_mais", "btn_criar"])

    def test_invalid_quantity_is_treated_as_one(self):
        for invalida in (0, -3):
            with self.subTest(quantidade=invalida):
                comprou, eventos, _, _ = self.executar(quantidade=invalida)

                self.assertTrue(comprou)
                self.assertEqual(eventos, ["btn_mais", "btn_criar"])

    def test_quantity_is_set_before_the_plus_click(self):
        comprou, eventos, recuperar, _ = self.executar(quantidade=10)

        self.assertTrue(comprou)
        self.assertEqual(eventos, ["qtd:10", "btn_mais", "btn_criar"])
        recuperar.assert_not_called()

    def test_estimated_total_above_limit_blocks_before_any_click(self):
        comprou, eventos, _, saida = self.executar(quantidade=20, limite=250_000)

        self.assertFalse(comprou)
        self.assertEqual(eventos, [])
        self.assertIn("excede o limite", saida)

    def test_total_exactly_at_the_limit_is_allowed(self):
        comprou, eventos, _, _ = self.executar(
            quantidade=10, limite=LIMITE_EXATO_QTD_10
        )

        self.assertTrue(comprou)
        self.assertEqual(eventos, ["qtd:10", "btn_mais", "btn_criar"])

    def test_total_one_silver_above_the_limit_is_blocked(self):
        comprou, eventos, _, _ = self.executar(
            quantidade=10, limite=LIMITE_EXATO_QTD_10 - 1
        )

        self.assertFalse(comprou)
        self.assertEqual(eventos, [])

    def test_confirmed_total_above_limit_never_clicks_create(self):
        # O preço lido depois do "+" (20_005) ainda cabe na tolerância do OCR,
        # mas o total confirmado passa do limite que a estimativa respeitava.
        comprou, eventos, recuperar, saida = self.executar(
            quantidade=10, limite=LIMITE_EXATO_QTD_10, preco_final=PRECO + 5
        )

        self.assertFalse(comprou)
        self.assertEqual(eventos, ["qtd:10", "btn_mais"])
        recuperar.assert_called_once()
        self.assertIn("total confirmado", saida)

    def test_quantity_adjust_failure_stops_before_plus_and_create(self):
        comprou, eventos, recuperar, _ = self.executar(
            quantidade=5, resultado_quantidade=(False, "área da quantidade não calibrada")
        )

        self.assertFalse(comprou)
        self.assertEqual(eventos, ["qtd:5"])
        recuperar.assert_called_once()
        self.assertIn("quantidade", recuperar.call_args.args[2])

    def test_minimum_profit_is_still_enforced_with_quantity(self):
        comprou, eventos, _, _ = self.executar(preco=90_000, quantidade=3)

        self.assertFalse(comprou)
        self.assertEqual(eventos, [])


class ConfiguracaoArtefatosTests(unittest.TestCase):
    def test_reads_saved_quantity(self):
        casos = (
            ({}, 1),
            ({"artefatos_quantidade": 5}, 5),
            ({"artefatos_quantidade": "12"}, 12),
            ({"artefatos_quantidade": 0}, 1),
            ({"artefatos_quantidade": -4}, 1),
            ({"artefatos_quantidade": None}, 1),
            ({"artefatos_quantidade": "abc"}, 1),
            ({"artefatos_quantidade": ""}, 1),
        )
        for offsets, esperado in casos:
            with self.subTest(offsets=offsets):
                self.assertEqual(bot.ler_quantidade_artefatos(offsets), esperado)

    def test_fixed_target_is_only_the_artefato_category(self):
        self.assertEqual(
            bot.ARTEFATO_CATEGORY_TARGETS,
            [
                {
                    "category": "ARTEFATO",
                    "key": bot.CATEGORIA_CLIQUE_KEYS["ARTEFATO"],
                    "label": "ARTEFATO",
                }
            ],
        )

    def test_required_keys_extend_the_purchase_keys(self):
        self.assertTrue(set(BUY_REQUIRED_KEYS) < set(ARTEFATOS_REQUIRED_KEYS))
        self.assertEqual(
            set(ARTEFATOS_REQUIRED_KEYS) - set(BUY_REQUIRED_KEYS),
            {"cat_clique_principal", "cat_clique_artefato", "shopping_qtd_valor"},
        )


class CalibragemArtefatosTests(unittest.TestCase):
    GEOMETRY = ClientGeometry(0, 0, 1920, 1080)

    def offsets_com(self, chaves):
        offsets = {chave: [0.1, 0.1, 0.1, 0.1] for chave in chaves}
        offsets[META_KEY] = calibration_metadata(self.GEOMETRY)
        return offsets

    def test_passes_with_every_required_key(self):
        offsets = self.offsets_com(ARTEFATOS_REQUIRED_KEYS)

        valido, motivo = validate_calibration(offsets, self.GEOMETRY, mode="artefatos")

        self.assertTrue(valido, motivo)

    def test_blocks_when_any_artefatos_only_key_is_missing(self):
        for chave in ("cat_clique_principal", "cat_clique_artefato", "shopping_qtd_valor"):
            with self.subTest(chave=chave):
                offsets = self.offsets_com(set(ARTEFATOS_REQUIRED_KEYS) - {chave})

                valido, motivo = validate_calibration(
                    offsets, self.GEOMETRY, mode="artefatos"
                )

                self.assertFalse(valido)
                self.assertIn(chave, motivo)

    def test_buy_mode_alone_does_not_satisfy_artefatos(self):
        offsets = self.offsets_com(BUY_REQUIRED_KEYS)

        self.assertTrue(validate_calibration(offsets, self.GEOMETRY, mode="buy")[0])
        self.assertFalse(validate_calibration(offsets, self.GEOMETRY, mode="artefatos")[0])

    def test_ignores_the_category_setup_used_by_the_regular_buy_tab(self):
        offsets = self.offsets_com(ARTEFATOS_REQUIRED_KEYS)
        offsets["cat_ativo"] = True
        offsets["cat_sequence"] = ["ARMAS"]
        offsets["cat_enabled"] = {"ARMAS": True, "ARTEFATO": False}

        valido, motivo = validate_calibration(offsets, self.GEOMETRY, mode="artefatos")

        self.assertTrue(valido, motivo)


class HudArtefatosTests(unittest.TestCase):
    def test_running_is_reported_as_active(self):
        estado = interface.build_mini_hud_state(artefatos_running=True)

        self.assertEqual(estado["operation"], "ARTEFATOS ATIVO")
        self.assertTrue(estado["active"])

    def test_paused_is_reported_as_inactive(self):
        estado = interface.build_mini_hud_state(artefatos_paused=True)

        self.assertEqual(estado["operation"], "ARTEFATOS EM PAUSA")
        self.assertFalse(estado["active"])

    def test_other_operations_keep_their_labels(self):
        self.assertEqual(
            interface.build_mini_hud_state(running=True)["operation"], "COMPRA ATIVA"
        )
        self.assertEqual(
            interface.build_mini_hud_state()["operation"], "AUTOMAÇÃO PARADA"
        )


class InterfaceArtefatosTests(unittest.TestCase):
    OUTRAS_AUTOMACOES = (
        "running",
        "sell_running",
        "cycle_running",
        "fechando_ordens",
        "shopping_running",
        "remover_pedidos_running",
    )

    @staticmethod
    def make_gui(quantidade="5"):
        gui = interface.AlbionBotGUI.__new__(interface.AlbionBotGUI)
        gui.key_info = {"modulesEnforced": False}
        gui.running = False
        gui.buy_paused = False
        gui.sell_running = False
        gui.cycle_running = False
        gui.fechando_ordens = False
        gui.shopping_running = False
        gui.shopping_paused = False
        gui.shopping_items = [{"nome": "Machado", "tier": 5, "status": "pendente"}]
        gui.remover_pedidos_running = False
        gui.artefatos_running = False
        gui.artefatos_paused = False
        gui.root = MagicMock()
        gui.salvar_ajustes_financeiros = MagicMock(return_value=True)
        gui.validar_calibragem_para_modo = MagicMock(return_value=True)
        gui.minimizar_para_execucao = MagicMock()
        gui.modulo_liberado = MagicMock(return_value=True)
        gui.atualizar_botao_artefatos = MagicMock()
        gui.artefatos_module_status_lbl = MagicMock()
        gui.artefatos_quantidade_entry = MagicMock()
        gui.artefatos_quantidade_entry.get.return_value = quantidade
        gui.log = MagicMock()
        return gui

    def iniciar(self, gui):
        with patch("builtins.open", mock_open()), patch(
            "interface.json.dump"
        ) as dump, patch("interface.load_settings", return_value={}), patch(
            "interface.save_settings"
        ) as save, patch("interface.messagebox") as caixa:
            gui.iniciar_artefatos()
        return dump, save, caixa

    def test_start_saves_quantity_and_sends_artefatos_mode(self):
        gui = self.make_gui("5")

        dump, save, _ = self.iniciar(gui)

        self.assertTrue(gui.artefatos_running)
        self.assertFalse(gui.artefatos_paused)
        gui.validar_calibragem_para_modo.assert_called_once_with("artefatos")
        gui.minimizar_para_execucao.assert_called_once_with()
        self.assertEqual(save.call_args.args[1]["artefatos_quantidade"], 5)
        dump.assert_called_once_with(
            {"run": True, "mode": "artefatos", "auto_cycle": False, "preserve_position": False},
            unittest.mock.ANY,
        )

    def test_start_is_blocked_by_an_invalid_quantity(self):
        for invalida in ("0", "-2", "abc", "", "1.5"):
            with self.subTest(quantidade=invalida):
                gui = self.make_gui(invalida)

                dump, save, caixa = self.iniciar(gui)

                self.assertFalse(gui.artefatos_running)
                dump.assert_not_called()
                save.assert_not_called()
                caixa.showwarning.assert_called_once()
                gui.validar_calibragem_para_modo.assert_not_called()

    def test_start_is_blocked_while_another_automation_runs(self):
        for atributo in self.OUTRAS_AUTOMACOES:
            with self.subTest(automacao=atributo):
                gui = self.make_gui()
                setattr(gui, atributo, True)

                dump, _, caixa = self.iniciar(gui)

                self.assertFalse(gui.artefatos_running)
                dump.assert_not_called()
                caixa.showwarning.assert_called_once()

    def test_start_is_blocked_by_incomplete_calibration(self):
        gui = self.make_gui()
        gui.validar_calibragem_para_modo.return_value = False

        dump, _, _ = self.iniciar(gui)

        self.assertFalse(gui.artefatos_running)
        dump.assert_not_called()

    def test_pause_preserves_position(self):
        gui = self.make_gui()
        gui.artefatos_running = True

        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.pausar_artefatos()

        self.assertFalse(gui.artefatos_running)
        self.assertTrue(gui.artefatos_paused)
        dump.assert_called_once_with(
            {"run": False, "mode": "artefatos", "auto_cycle": False, "preserve_position": True},
            unittest.mock.ANY,
        )

    def test_resume_restarts_from_the_saved_position(self):
        gui = self.make_gui()
        gui.artefatos_paused = True

        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.continuar_artefatos()

        self.assertTrue(gui.artefatos_running)
        self.assertFalse(gui.artefatos_paused)
        dump.assert_called_once_with(
            {"run": True, "mode": "artefatos", "auto_cycle": False, "preserve_position": True},
            unittest.mock.ANY,
        )

    def test_resume_does_nothing_when_not_paused(self):
        gui = self.make_gui()

        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.continuar_artefatos()

        self.assertFalse(gui.artefatos_running)
        dump.assert_not_called()

    def test_stop_discards_the_saved_position(self):
        gui = self.make_gui()
        gui.artefatos_running = True

        with patch("builtins.open", mock_open()), patch("interface.json.dump") as dump:
            gui.parar_artefatos()

        self.assertFalse(gui.artefatos_running)
        self.assertFalse(gui.artefatos_paused)
        dump.assert_called_once_with(
            {"run": False, "mode": "buy", "auto_cycle": False, "preserve_position": False},
            unittest.mock.ANY,
        )

    def test_emergency_stop_clears_artefatos_state(self):
        gui = self.make_gui()
        gui.artefatos_running = True
        gui.artefatos_paused = True
        for nome in (
            "atualizar_botao_inicial",
            "atualizar_botao_venda",
            "atualizar_botao_ciclo",
            "atualizar_botao_shopping",
            "card_status",
            "shopping_module_status_lbl",
            "edit_status_lbl",
            "sell_module_status_lbl",
            "cycle_module_status_lbl",
            "_set_cycle_stage",
        ):
            setattr(gui, nome, MagicMock())

        with patch("builtins.open", mock_open()):
            gui.pause_bot()

        self.assertFalse(gui.artefatos_running)
        self.assertFalse(gui.artefatos_paused)
        gui.atualizar_botao_artefatos.assert_called()
        gui.artefatos_module_status_lbl.config.assert_called()

    def test_running_artefatos_counts_as_an_active_automation(self):
        gui = self.make_gui()
        self.assertFalse(gui.automacao_em_execucao())

        gui.artefatos_running = True

        self.assertTrue(gui.automacao_em_execucao())

    def test_f6_pauses_and_resumes_artefatos(self):
        gui = self.make_gui()
        gui.pausar_artefatos = MagicMock()
        gui.continuar_artefatos = MagicMock()

        gui.artefatos_running = True
        gui._mini_toggle_pause_resume()
        gui.pausar_artefatos.assert_called_once_with()
        gui.continuar_artefatos.assert_not_called()

        gui.artefatos_running = False
        gui.artefatos_paused = True
        gui._mini_toggle_pause_resume()
        gui.continuar_artefatos.assert_called_once_with()

    def test_f7_starts_artefatos_from_its_own_tab(self):
        gui = self.make_gui()
        gui.current_tab = "ARTEFATOS"
        gui.iniciar_artefatos = MagicMock()
        gui.toggle_bot = MagicMock()

        gui.iniciar_via_atalho()

        gui.iniciar_artefatos.assert_called_once_with()
        gui.toggle_bot.assert_not_called()

    def test_other_automations_refuse_to_start_while_artefatos_runs(self):
        iniciadores = (
            "toggle_bot",
            "iniciar_bot_venda",
            "toggle_cycle_bot",
            "iniciar_shopping",
            "iniciar_remover_pedidos",
            "toggle_fechamento",
        )
        for nome in iniciadores:
            with self.subTest(iniciador=nome):
                gui = self.make_gui()
                gui.artefatos_running = True

                with patch("builtins.open", mock_open()), patch(
                    "interface.json.dump"
                ) as dump, patch("interface.messagebox") as caixa:
                    getattr(gui, nome)()

                dump.assert_not_called()
                caixa.showwarning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
