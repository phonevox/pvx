import unittest
from unittest.mock import patch

import questionary

from pvx.interactive.screens.theme_settings import ThemeScreen


class ThemeScreenTest(unittest.TestCase):
    # tema tem 3 eixos independentes (cor, símbolos, formato) -- primeiro
    # pergunta o eixo, depois o preset desse eixo. Redesenha o mesmo nível
    # (None) após aplicar, igual auto-menu, pra dar pra ajustar mais de um
    # eixo na mesma visita.
    @patch("pvx.interactive.screens.theme_settings.config.set_theme_name")
    @patch("pvx.interactive.screens.theme_settings.ask_select", side_effect=["cor", "verde"])
    def test_choosing_cor_then_a_preset_persists_it(self, mock_ask_select, mock_set_theme):
        result = ThemeScreen().render()
        self.assertIsNone(result)
        mock_set_theme.assert_called_once_with("verde")

    @patch("pvx.interactive.screens.theme_settings.config.set_symbol_set_name")
    @patch("pvx.interactive.screens.theme_settings.ask_select", side_effect=["símbolos", "ascii"])
    def test_choosing_simbolos_then_a_preset_persists_it(self, mock_ask_select, mock_set_symbols):
        result = ThemeScreen().render()
        self.assertIsNone(result)
        mock_set_symbols.assert_called_once_with("ascii")

    @patch("pvx.interactive.screens.theme_settings.config.set_format_name")
    @patch("pvx.interactive.screens.theme_settings.ask_select", side_effect=["formato", "simples"])
    def test_choosing_formato_then_a_preset_persists_it(self, mock_ask_select, mock_set_format):
        result = ThemeScreen().render()
        self.assertIsNone(result)
        mock_set_format.assert_called_once_with("simples")

    @patch("pvx.interactive.screens.theme_settings.ask_select", return_value="voltar")
    def test_voltar_at_axis_level_returns_back(self, mock_ask_select):
        self.assertEqual(ThemeScreen().render(), "BACK")

    @patch("pvx.interactive.screens.theme_settings.ask_select", return_value=None)
    def test_none_at_axis_level_returns_back(self, mock_ask_select):
        self.assertEqual(ThemeScreen().render(), "BACK")

    @patch("pvx.interactive.screens.theme_settings.config.set_theme_name")
    @patch("pvx.interactive.screens.theme_settings.ask_select", side_effect=["cor", "voltar"])
    def test_voltar_at_preset_level_redraws_the_axis_menu(self, mock_ask_select, mock_set_theme):
        result = ThemeScreen().render()
        self.assertIsNone(result)
        mock_set_theme.assert_not_called()

    @patch("pvx.interactive.screens.theme_settings.config.set_theme_name")
    @patch("pvx.interactive.screens.theme_settings.ask_select", side_effect=["cor", None])
    def test_none_at_preset_level_redraws_the_axis_menu(self, mock_ask_select, mock_set_theme):
        result = ThemeScreen().render()
        self.assertIsNone(result)
        mock_set_theme.assert_not_called()

    # achado ao vivo: sem clear() entre as duas perguntas, "pvx > tema > cor"
    # (já respondida) ficava presa na tela com "pvx > tema > cor >" duplicada
    # embaixo -- mesma causa já documentada no auto-menu de root.py.
    @patch("pvx.interactive.screens.theme_settings.config.set_theme_name")
    @patch("pvx.interactive.screens.theme_settings.widgets.clear")
    @patch("pvx.interactive.screens.theme_settings.ask_select", side_effect=["cor", "verde"])
    def test_clears_screen_between_axis_and_preset_prompts(self, mock_ask_select, mock_clear, mock_set_theme):
        ThemeScreen().render()
        mock_clear.assert_called_once()

    @patch("pvx.interactive.screens.theme_settings.ask_select", return_value="voltar")
    def test_every_axis_has_a_preview_description(self, mock_ask_select):
        ThemeScreen().render()
        choices = mock_ask_select.call_args.args[1]
        for value in ("cor", "símbolos", "formato"):
            choice = next(c for c in choices if isinstance(c, questionary.Choice) and c.value == value)
            self.assertTrue(choice.description, msg=f"{value} sem description")

    @patch("pvx.interactive.screens.theme_settings.config.set_symbol_set_name")
    @patch("pvx.interactive.screens.theme_settings.ask_select", side_effect=["símbolos", "voltar"])
    def test_every_preset_has_a_preview_description(self, mock_ask_select, mock_set_symbols):
        ThemeScreen().render()
        choices = mock_ask_select.call_args_list[1].args[1]
        for value in ("padrão", "ascii", "geométrico"):
            choice = next(c for c in choices if isinstance(c, questionary.Choice) and c.value == value)
            self.assertTrue(choice.description, msg=f"{value} sem description")


if __name__ == "__main__":
    unittest.main()
