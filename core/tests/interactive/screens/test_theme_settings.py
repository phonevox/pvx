import unittest
from unittest.mock import patch

from pvx.interactive.screens.theme_settings import ThemeScreen


class ThemeScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.theme_settings.config.set_theme_name")
    @patch("pvx.interactive.screens.theme_settings.ask_select", return_value="verde")
    def test_selecting_a_theme_persists_it(self, mock_ask_select, mock_set_theme):
        result = ThemeScreen().render()
        self.assertEqual(result, "BACK")
        mock_set_theme.assert_called_once_with("verde")

    @patch("pvx.interactive.screens.theme_settings.ask_select", return_value="voltar")
    def test_voltar_returns_back(self, mock_ask_select):
        self.assertEqual(ThemeScreen().render(), "BACK")

    @patch("pvx.interactive.screens.theme_settings.ask_select", return_value=None)
    def test_none_returns_back(self, mock_ask_select):
        self.assertEqual(ThemeScreen().render(), "BACK")


if __name__ == "__main__":
    unittest.main()
