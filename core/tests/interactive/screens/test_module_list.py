import unittest
from unittest.mock import patch

from pvx.interactive.screens.module_list import ModuleListScreen


class ModuleListScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.module_list.widgets.pause")
    @patch("pvx.interactive.screens.module_list.widgets.print_modules_table")
    @patch(
        "pvx.interactive.screens.module_list.listing.list_modules",
        return_value=[
            {"name": "dummy", "installed_version": "1.0.0", "latest_version": "1.0.0", "status": "atualizado"}
        ],
    )
    @patch(
        "pvx.interactive.screens.module_list.config.registry_index_url",
        return_value="https://example.com/index.json",
    )
    @patch("pvx.interactive.screens.module_list.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.module_list.widgets.spinner")
    @patch("pvx.interactive.screens.module_list.widgets.breadcrumb")
    def test_shows_table_then_pause_and_returns_back(
        self, mock_breadcrumb, mock_spinner, mock_discover, mock_url, mock_list_modules,
        mock_print_table, mock_pause,
    ):
        result = ModuleListScreen().render()
        self.assertEqual(result, "BACK")
        mock_breadcrumb.assert_called_once_with("pvx > módulos > listar")
        mock_spinner.assert_called_once()
        mock_print_table.assert_called_once_with(mock_list_modules.return_value)
        mock_pause.assert_called_once_with()

    @patch("pvx.interactive.screens.module_list.widgets.pause")
    @patch("pvx.interactive.screens.module_list.widgets.message")
    @patch(
        "pvx.interactive.screens.module_list.listing.list_modules",
        side_effect=RuntimeError("não foi possível acessar o registry"),
    )
    @patch(
        "pvx.interactive.screens.module_list.config.registry_index_url",
        return_value="https://example.com/index.json",
    )
    @patch("pvx.interactive.screens.module_list.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.module_list.widgets.breadcrumb")
    def test_network_failure_shows_message_and_returns_back(
        self, mock_breadcrumb, mock_discover, mock_url, mock_list_modules, mock_message, mock_pause
    ):
        result = ModuleListScreen().render()
        self.assertEqual(result, "BACK")
        mock_breadcrumb.assert_called_once_with("pvx > módulos > listar")
        mock_message.assert_called_once_with("não foi possível acessar o registry")
        mock_pause.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
