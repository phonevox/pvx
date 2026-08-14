import unittest
from unittest.mock import patch

from pvx.interactive.screens.logs import LogsScreen


class LogsScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.logs.viewer.read_log", return_value="conteúdo do log")
    @patch("pvx.interactive.screens.logs.ask_select", return_value="dummy")
    @patch("pvx.interactive.screens.logs.discover_installed_modules", return_value={"dummy": object()})
    def test_selecting_module_shows_its_log(self, mock_discover, mock_ask_select, mock_read_log):
        result = LogsScreen().render()
        self.assertEqual(result, "BACK")
        mock_read_log.assert_called_once_with("dummy", lines=None)

    @patch("pvx.interactive.screens.logs.ask_select", return_value=None)
    @patch("pvx.interactive.screens.logs.discover_installed_modules", return_value={"dummy": object()})
    def test_none_selection_returns_back(self, mock_discover, mock_ask_select):
        self.assertEqual(LogsScreen().render(), "BACK")

    @patch("pvx.interactive.screens.logs.viewer.read_log")
    @patch("pvx.interactive.screens.logs.ask_select", return_value="Voltar")
    @patch("pvx.interactive.screens.logs.discover_installed_modules", return_value={"dummy": object()})
    def test_selecting_voltar_returns_back_without_reading_log(
        self, mock_discover, mock_ask_select, mock_read_log
    ):
        self.assertEqual(LogsScreen().render(), "BACK")
        mock_read_log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
