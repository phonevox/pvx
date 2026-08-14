import unittest
from unittest.mock import patch

from pvx.interactive.screens.module_update import ModuleUpdateScreen


class ModuleUpdateScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.module_update.installer.install")
    @patch(
        "pvx.interactive.screens.module_update.config.registry_index_url",
        return_value="https://example.com/index.json",
    )
    @patch("pvx.interactive.screens.module_update.ask_select", return_value="dummy")
    @patch(
        "pvx.interactive.screens.module_update.discover_installed_modules",
        return_value={"dummy": object(), "other": object()},
    )
    def test_selecting_single_module_updates_it(
        self, mock_discover, mock_ask_select, mock_url, mock_install
    ):
        result = ModuleUpdateScreen().render()
        self.assertEqual(result, "BACK")
        mock_install.assert_called_once_with("dummy", "https://example.com/index.json")

    @patch("pvx.interactive.screens.module_update.installer.install")
    @patch(
        "pvx.interactive.screens.module_update.config.registry_index_url",
        return_value="https://example.com/index.json",
    )
    @patch("pvx.interactive.screens.module_update.ask_select", return_value="Todos")
    @patch(
        "pvx.interactive.screens.module_update.discover_installed_modules",
        return_value={"dummy": object(), "other": object()},
    )
    def test_selecting_todos_updates_every_installed_module(
        self, mock_discover, mock_ask_select, mock_url, mock_install
    ):
        result = ModuleUpdateScreen().render()
        self.assertEqual(result, "BACK")
        self.assertEqual(mock_install.call_count, 2)

    @patch("pvx.interactive.screens.module_update.ask_select", return_value=None)
    @patch(
        "pvx.interactive.screens.module_update.discover_installed_modules",
        return_value={"dummy": object()},
    )
    def test_none_selection_returns_back(self, mock_discover, mock_ask_select):
        self.assertEqual(ModuleUpdateScreen().render(), "BACK")

    @patch("pvx.interactive.screens.module_update.ask_select")
    @patch("pvx.interactive.screens.module_update.widgets.pause")
    @patch("pvx.interactive.screens.module_update.discover_installed_modules", return_value={})
    def test_no_installed_modules_shows_pause_and_returns_back(
        self, mock_discover, mock_pause, mock_ask_select
    ):
        result = ModuleUpdateScreen().render()
        self.assertEqual(result, "BACK")
        mock_pause.assert_called_once()
        mock_ask_select.assert_not_called()

    @patch("pvx.interactive.screens.module_update.installer.install")
    @patch("pvx.interactive.screens.module_update.ask_select", return_value="Voltar")
    @patch(
        "pvx.interactive.screens.module_update.discover_installed_modules",
        return_value={"dummy": object()},
    )
    def test_selecting_voltar_returns_back_without_updating(
        self, mock_discover, mock_ask_select, mock_install
    ):
        self.assertEqual(ModuleUpdateScreen().render(), "BACK")
        mock_install.assert_not_called()

    @patch("pvx.interactive.screens.module_update.installer.install")
    @patch(
        "pvx.interactive.screens.module_update.config.registry_index_url",
        return_value="https://example.com/index.json",
    )
    @patch("pvx.interactive.screens.module_update.ask_select", return_value="dummy")
    @patch(
        "pvx.interactive.screens.module_update.discover_installed_modules",
        return_value={"dummy": object()},
    )
    @patch("pvx.interactive.screens.module_update.widgets.spinner")
    def test_shows_spinner_while_updating(
        self, mock_spinner, mock_discover, mock_ask_select, mock_url, mock_install
    ):
        ModuleUpdateScreen().render()
        mock_spinner.assert_called_once()

    @patch("pvx.interactive.screens.module_update.click.echo")
    @patch(
        "pvx.interactive.screens.module_update.installer.install",
        side_effect=RuntimeError("não foi possível acessar o registry"),
    )
    @patch("pvx.interactive.screens.module_update.ask_select", return_value="dummy")
    @patch(
        "pvx.interactive.screens.module_update.discover_installed_modules",
        return_value={"dummy": object()},
    )
    def test_network_failure_shows_message_and_returns_back(
        self, mock_discover, mock_ask_select, mock_install, mock_echo
    ):
        result = ModuleUpdateScreen().render()
        self.assertEqual(result, "BACK")
        self.assertTrue(
            any("não foi possível acessar o registry" in str(c) for c in mock_echo.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
