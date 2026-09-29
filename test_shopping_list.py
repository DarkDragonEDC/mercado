import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

import bot


class RemoverQualificadorTierTests(unittest.TestCase):
    """A busca do mercado por si só não distingue itens diferentes que
    compartilham parte do nome (ex.: "Lança do Adepto" vs "Lança Garceira do
    Adepto"), então o nome base (sem o qualificador de tier) precisa bater
    exatamente entre o que foi digitado na lista e o que foi lido no jogo."""

    def test_strips_tier_qualifier_word(self):
        self.assertEqual(bot.remover_qualificador_tier("Lança do Adepto"), "lanca")
        self.assertEqual(bot.remover_qualificador_tier("Robe de Erudito do Mestre"), "robe erudito")

    def test_distinguishes_items_sharing_a_common_prefix_word(self):
        alvo = bot.remover_qualificador_tier("Lança")
        self.assertEqual(alvo, bot.remover_qualificador_tier("Lança do Adepto"))
        self.assertNotEqual(alvo, bot.remover_qualificador_tier("Lança Garceira do Adepto"))
        self.assertNotEqual(alvo, bot.remover_qualificador_tier("Lança Trina do Adepto"))
        self.assertNotEqual(alvo, bot.remover_qualificador_tier("Lança-virotes do Adepto"))
        self.assertNotEqual(
            alvo, bot.remover_qualificador_tier("Cabeça de Lança Protetora do Adepto")
        )

    def test_matches_regardless_of_which_tier_word_is_present(self):
        base = bot.remover_qualificador_tier("Robe de Erudito")
        for tier_word in ("Novato", "Iniciante", "Adepto", "Perito", "Mestre", "Grão-Mestre", "Ancião"):
            with self.subTest(tier_word=tier_word):
                self.assertEqual(base, bot.remover_qualificador_tier(f"Robe de Erudito do {tier_word}"))

    def test_ignores_case_and_accents(self):
        self.assertEqual(
            bot.remover_qualificador_tier("LANÇA do adepto"),
            bot.remover_qualificador_tier("lanca DO ADEPTO"),
        )


class NomesBaseCorrespondemTests(unittest.TestCase):
    """Bug real visto ao vivo: o OCR leu "Erudito" como "€rudito" (E confundido
    com o símbolo de euro); como a normalização descarta caracteres não-ASCII,
    o nome base virou "robe rudito" em vez de "robe erudito", e uma
    comparação exata nunca batia -- travando a lista inteira em "Robe de
    Erudito" mesmo quando o item certo estava aberto na tela."""

    def test_accepts_the_real_ocr_misread_case(self):
        lido = bot.remover_qualificador_tier("Robe de €rudito do Adepto")
        alvo = bot.remover_qualificador_tier("Robe de Erudito")
        self.assertEqual(lido, "robe rudito")
        self.assertEqual(alvo, "robe erudito")
        self.assertTrue(bot.nomes_base_correspondem(lido, alvo))

    def test_still_rejects_genuinely_different_items(self):
        alvo = bot.remover_qualificador_tier("Lança")
        self.assertFalse(bot.nomes_base_correspondem(
            alvo, bot.remover_qualificador_tier("Lança Garceira do Adepto")
        ))
        self.assertFalse(bot.nomes_base_correspondem(
            alvo, bot.remover_qualificador_tier("Cabeça de Lança Protetora do Adepto")
        ))

    def test_accepts_exact_match(self):
        alvo = bot.remover_qualificador_tier("Lança")
        self.assertTrue(bot.nomes_base_correspondem(
            alvo, bot.remover_qualificador_tier("Lança do Adepto")
        ))

    def test_rejects_when_either_side_is_empty(self):
        self.assertFalse(bot.nomes_base_correspondem("", "robe erudito"))
        self.assertFalse(bot.nomes_base_correspondem("robe erudito", ""))
        self.assertFalse(bot.nomes_base_correspondem("", ""))


class SelecionarCategoriaCompraProgramadaTests(unittest.TestCase):
    """O dropdown "Categoria" de dentro do painel de busca da Compra
    Programada abre no mesmo local de tela do menu de categorias do modo de
    compra normal (confirmado ao vivo), então reaproveita os mesmos pontos
    calibrados (cat_clique_principal + cat_clique_<categoria>)."""

    def test_returns_false_for_unknown_category(self):
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_point") as resolve, \
             patch("bot.safe_click") as click:
            ok, erro = bot.selecionar_categoria_compra_programada(None, {}, "Categoria Inexistente")
        self.assertFalse(ok)
        self.assertIn("desconhecida", erro)
        resolve.assert_not_called()
        click.assert_not_called()

    def test_returns_false_when_main_menu_not_calibrated(self):
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_point", return_value=None), \
             patch("bot.safe_click") as click:
            ok, erro = bot.selecionar_categoria_compra_programada(None, {}, "ARMAS")
        self.assertFalse(ok)
        self.assertIn("não calibrado", erro)
        click.assert_not_called()

    def test_returns_false_when_category_point_not_calibrated(self):
        # 1a chamada resolve o clique do menu principal (cat_clique_principal),
        # 2a chamada resolve o clique da categoria especifica -- so a segunda
        # falha aqui, simulando "Abrir menu Categorias" calibrado mas
        # "cat_clique_armas" ainda nao.
        respostas = iter([(100, 100), None])
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_point", side_effect=lambda *a, **k: next(respostas)), \
             patch("bot.safe_click") as click:
            ok, erro = bot.selecionar_categoria_compra_programada(None, {}, "ARMAS")
        self.assertFalse(ok)
        self.assertIn("cat_clique_armas", erro)
        click.assert_not_called()

    def test_clicks_menu_then_category_and_succeeds(self):
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_point", return_value=(100, 100)), \
             patch("bot.safe_click", return_value=True) as click, \
             patch("bot.smart_sleep"):
            ok, erro = bot.selecionar_categoria_compra_programada(None, {}, "armas")
        self.assertTrue(ok)
        self.assertEqual(erro, "")
        self.assertEqual(click.call_count, 2)

    def test_returns_false_when_click_is_blocked(self):
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_point", return_value=(100, 100)), \
             patch("bot.safe_click", return_value=False), \
             patch("bot.smart_sleep"):
            ok, erro = bot.selecionar_categoria_compra_programada(None, {}, "ARMAS")
        self.assertFalse(ok)
        self.assertIn("bloqueado", erro)


class MediaSemanalDisponivelTests(unittest.TestCase):
    """Verificação opcional (VERIFICAR_MEDIA_SEMANAL_KEY): se o campo "Preço
    médio" do Histórico de mercado mostrar "Sem média disponível", o item
    não teve saída na última semana e a compra não deve ser feita."""

    def _patches_com_leitura(self, leitura):
        imagem = Image.new("RGB", (10, 10))
        reader = MagicMock()
        reader.readtext.return_value = leitura
        return [
            patch("bot.get_client_geometry", return_value=None),
            patch("bot.resolve_rect", return_value=(0, 0, 10, 10)),
            patch("bot.capture_region", return_value=imagem),
            patch("bot.get_reader", return_value=reader),
        ]

    def test_returns_none_when_region_not_calibrated(self):
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_rect", return_value=None):
            disponivel, motivo = bot.media_semanal_disponivel(None, {})
        self.assertIsNone(disponivel)
        self.assertIn("não calibrada", motivo)

    def test_returns_true_when_a_valid_average_price_is_read(self):
        patches = self._patches_com_leitura(["43.637"])
        with patches[0], patches[1], patches[2], patches[3]:
            disponivel, motivo = bot.media_semanal_disponivel(None, {})
        self.assertTrue(disponivel)
        self.assertEqual(motivo, "")

    def test_returns_false_for_explicit_no_average_text(self):
        patches = self._patches_com_leitura(["Sem média disponível"])
        with patches[0], patches[1], patches[2], patches[3]:
            disponivel, motivo = bot.media_semanal_disponivel(None, {})
        self.assertFalse(disponivel)
        self.assertIn("sem saída na última semana", motivo)

    def test_returns_false_for_unreadable_text(self):
        patches = self._patches_com_leitura(["???"])
        with patches[0], patches[1], patches[2], patches[3]:
            disponivel, motivo = bot.media_semanal_disponivel(None, {})
        self.assertFalse(disponivel)
        self.assertIn("não foi possível confirmar", motivo)

    def test_accepts_value_mixed_with_surrounding_label_text(self):
        # Bug real visto ao vivo: a área calibrada pega o rótulo junto do
        # valor (ex.: "6 h Preço médio: 20"), e limpar_num rejeita a leitura
        # inteira se sobrar qualquer letra -- bloqueando toda compra mesmo
        # com uma média válida. Precisa aceitar o dígito mesmo cercado de
        # texto.
        casos = [
            "6 h Preço médio: 20",
            "Preço médio: 3,859",
            "Preço médio: 128 k",
            "24 horas Preço médio: 43.637",
        ]
        for leitura_ocr in casos:
            with self.subTest(leitura=leitura_ocr):
                patches = self._patches_com_leitura([leitura_ocr])
                with patches[0], patches[1], patches[2], patches[3]:
                    disponivel, motivo = bot.media_semanal_disponivel(None, {})
                self.assertTrue(disponivel, f"deveria confirmar média em {leitura_ocr!r}")
                self.assertEqual(motivo, "")

    def test_still_rejects_no_average_text_even_with_surrounding_label(self):
        patches = self._patches_com_leitura(["6 h Preço médio: Sem média disponível"])
        with patches[0], patches[1], patches[2], patches[3]:
            disponivel, motivo = bot.media_semanal_disponivel(None, {})
        self.assertFalse(disponivel)
        self.assertIn("sem saída na última semana", motivo)


class ClipboardTextTests(unittest.TestCase):
    def _read_clipboard_text(self) -> str:
        from ctypes import wintypes

        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        self.assertTrue(user32.OpenClipboard(None))
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            self.assertTrue(handle)
            ptr = kernel32.GlobalLock(handle)
            self.assertTrue(ptr)
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def test_roundtrip_preserves_portuguese_accents(self):
        texto = "Armadura de Tecelão do Crepúsculo"
        self.assertTrue(bot.definir_texto_area_transferencia(texto))
        self.assertEqual(self._read_clipboard_text(), texto)


class ListaComprasPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = str(Path(self._tmpdir.name) / "lista_compras.json")
        self._patch = patch("bot.LISTA_COMPRAS_FILE", self.path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def test_missing_file_returns_empty_list(self):
        self.assertEqual(bot.carregar_lista_compras(), [])

    def test_roundtrip_preserves_items(self):
        itens = [
            {"nome": "Machado", "tier": 5, "encantamento": ".2", "quantidade": 10, "status": "pendente"},
        ]
        bot.salvar_lista_compras(itens)
        self.assertEqual(bot.carregar_lista_compras(), itens)

    def test_malformed_file_returns_empty_list(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write('{"itens": "nao é uma lista"}')
        self.assertEqual(bot.carregar_lista_compras(), [])


class ReverterProgressoNaoPausadoTests(unittest.TestCase):
    def test_reverts_only_items_that_were_pendente_before_this_run(self):
        status_inicial = {
            ("Machado", 5, ".2"): "pendente",
            ("Capa", 4, ".0"): "pedido_criado",
        }
        lista_atual = [
            {"nome": "Machado", "tier": 5, "encantamento": ".2", "status": "pedido_criado", "_tentativas": 2},
            {"nome": "Capa", "tier": 4, "encantamento": ".0", "status": "pedido_criado"},
        ]
        revertidos = bot.reverter_progresso_nao_pausado(status_inicial, lista_atual)
        self.assertEqual(revertidos, 1)
        self.assertEqual(lista_atual[0]["status"], "pendente")
        self.assertNotIn("_tentativas", lista_atual[0])
        self.assertEqual(lista_atual[1]["status"], "pedido_criado")

    def test_leaves_still_pendente_items_untouched(self):
        status_inicial = {("Machado", 5, ".2"): "pendente"}
        lista_atual = [
            {"nome": "Machado", "tier": 5, "encantamento": ".2", "status": "pendente"},
        ]
        revertidos = bot.reverter_progresso_nao_pausado(status_inicial, lista_atual)
        self.assertEqual(revertidos, 0)
        self.assertEqual(lista_atual[0]["status"], "pendente")

    def test_ignores_items_not_present_in_the_initial_snapshot(self):
        status_inicial: dict = {}
        lista_atual = [
            {"nome": "Novo Item", "tier": 6, "encantamento": ".1", "status": "pedido_criado"},
        ]
        revertidos = bot.reverter_progresso_nao_pausado(status_inicial, lista_atual)
        self.assertEqual(revertidos, 0)
        self.assertEqual(lista_atual[0]["status"], "pedido_criado")


class AjustarQuantidadePedidoTests(unittest.TestCase):
    """Cobre a versão simplificada: clica, cola e retorna -- sem confirmar por
    OCR (a confirmação real acontece via preço final × quantidade, ver
    ExecutarCliquesCompraProgramadaTests)."""

    def _patches(self, rect=(0, 0, 40, 20)):
        return [
            patch("bot.get_client_geometry", return_value=None),
            patch("bot.resolve_rect", return_value=rect),
            patch("bot.safe_click", return_value=True),
            patch("bot.definir_texto_area_transferencia", return_value=True),
            patch("bot.pyautogui.hotkey"),
            patch("bot.pyautogui.press"),
            patch("bot.smart_sleep"),
            patch("bot.pyautogui.moveTo"),
        ]

    def test_pastes_quantity_and_returns_success(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2] as click, patches[3] as clipboard, \
             patches[4] as hotkey, patches[5] as press, patches[6], patches[7] as move:
            ok, erro = bot._ajustar_quantidade_pedido(None, {}, 100)
        self.assertTrue(ok)
        self.assertEqual(erro, "")
        click.assert_called_once()
        clipboard.assert_called_once_with("100")
        hotkey.assert_any_call("ctrl", "a")
        hotkey.assert_any_call("ctrl", "v")
        press.assert_called_once_with("delete")
        move.assert_called_once()

    def test_returns_false_when_region_not_calibrated(self):
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_rect", return_value=None), \
             patch("bot.safe_click") as click:
            ok, erro = bot._ajustar_quantidade_pedido(None, {}, 10)
        self.assertFalse(ok)
        self.assertIn("não calibrada", erro)
        click.assert_not_called()

    def test_returns_false_when_click_is_blocked(self):
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_rect", return_value=(0, 0, 40, 20)), \
             patch("bot.safe_click", return_value=False), \
             patch("bot.definir_texto_area_transferencia") as clipboard:
            ok, erro = bot._ajustar_quantidade_pedido(None, {}, 10)
        self.assertFalse(ok)
        self.assertIn("bloqueado", erro)
        clipboard.assert_not_called()

    def test_returns_false_when_clipboard_fails(self):
        with patch("bot.get_client_geometry", return_value=None), \
             patch("bot.resolve_rect", return_value=(0, 0, 40, 20)), \
             patch("bot.safe_click", return_value=True), \
             patch("bot.definir_texto_area_transferencia", return_value=False), \
             patch("bot.pyautogui.hotkey") as hotkey, \
             patch("bot.pyautogui.press") as press, \
             patch("bot.pyautogui.moveTo"), \
             patch("bot.smart_sleep"):
            ok, erro = bot._ajustar_quantidade_pedido(None, {}, 10)
        self.assertFalse(ok)
        self.assertIn("área de transferência", erro)
        hotkey.assert_called_once_with("ctrl", "a")
        press.assert_called_once_with("delete")


class ExecutarCliquesCompraProgramadaTests(unittest.TestCase):
    """O campo 'Preço' no jogo mostra o TOTAL do pedido (preço unitário ×
    quantidade), então o valor esperado precisa ser multiplicado pela
    quantidade -- essa era a causa de a compra programada falhar sempre que a
    quantidade fosse maior que 1."""

    def _patch_ajuste_ok(self):
        return patch("bot._ajustar_quantidade_pedido", return_value=(True, ""))

    def test_expected_price_is_unit_price_not_multiplied_by_quantity(self):
        # Confirmado ao vivo: com Quantia=100, o campo Preco mostrou 2.361
        # (preco unitario), a Taxa mostrou 5.902 e o Total 242.002 -- so
        # batem como 2.361x100 + 2,5% sobre esse total. O campo Preco em si
        # nao muda com a quantidade, entao o valor esperado para a OCR e o
        # preco unitario, nao o total.
        with self._patch_ajuste_ok(), \
             patch("bot.clicar_offset", return_value=True), \
             patch("bot.smart_sleep"), \
             patch("bot._confirmar_preco_final_compra") as confirmar, \
             patch("bot.esperar_referencia_proxima_offset", return_value=True), \
             patch("bot.confirmar_sim", return_value=True), \
             patch("bot.esperar_referencia_sumir", return_value=True):
            confirmar.return_value = (30027, "")
            sucesso, preco_final, motivo = bot.executar_cliques_compra_programada(
                None, {}, 30026, 10
            )
        self.assertTrue(sucesso)
        self.assertEqual(preco_final, 30027)
        self.assertEqual(motivo, "")
        confirmar.assert_called_once_with(None, {}, 30027)

    def test_blocks_before_any_click_when_total_exceeds_limit(self):
        with self._patch_ajuste_ok() as ajustar, \
             patch("bot.clicar_offset") as clicar:
            sucesso, preco_final, motivo = bot.executar_cliques_compra_programada(
                None, {}, 30026, 10, valor_maximo_pedido=100000
            )
        self.assertFalse(sucesso)
        self.assertIsNone(preco_final)
        self.assertEqual(motivo, "limite_excedido")
        ajustar.assert_not_called()
        clicar.assert_not_called()

    def test_does_not_block_when_limit_is_zero(self):
        with self._patch_ajuste_ok(), \
             patch("bot.clicar_offset", return_value=True), \
             patch("bot.smart_sleep"), \
             patch("bot._confirmar_preco_final_compra", return_value=(30027, "")), \
             patch("bot.esperar_referencia_proxima_offset", return_value=True), \
             patch("bot.confirmar_sim", return_value=True), \
             patch("bot.esperar_referencia_sumir", return_value=True):
            sucesso, _preco_final, motivo = bot.executar_cliques_compra_programada(
                None, {}, 30026, 10, valor_maximo_pedido=0
            )
        self.assertTrue(sucesso)
        self.assertEqual(motivo, "")

    def test_does_not_block_when_total_is_within_limit(self):
        # total unitario x qtd = 30027*10 = 300270; taxa 2.5% = 7507;
        # 307777 esta dentro do limite de 400000
        with self._patch_ajuste_ok(), \
             patch("bot.clicar_offset", return_value=True), \
             patch("bot.smart_sleep"), \
             patch("bot._confirmar_preco_final_compra", return_value=(30027, "")), \
             patch("bot.esperar_referencia_proxima_offset", return_value=True), \
             patch("bot.confirmar_sim", return_value=True), \
             patch("bot.esperar_referencia_sumir", return_value=True):
            sucesso, _preco_final, motivo = bot.executar_cliques_compra_programada(
                None, {}, 30026, 10, valor_maximo_pedido=400000
            )
        self.assertTrue(sucesso)
        self.assertEqual(motivo, "")

    def test_returns_falha_when_quantity_adjustment_fails(self):
        with patch("bot._ajustar_quantidade_pedido", return_value=(False, "clique bloqueado")), \
             patch("bot.recuperar_ou_parar_compra") as recuperar, \
             patch("bot.clicar_offset") as clicar:
            sucesso, preco_final, motivo = bot.executar_cliques_compra_programada(
                None, {}, 30026, 10
            )
        self.assertFalse(sucesso)
        self.assertIsNone(preco_final)
        self.assertEqual(motivo, "falha")
        recuperar.assert_called_once()
        clicar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
