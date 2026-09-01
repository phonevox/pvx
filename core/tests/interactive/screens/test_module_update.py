import unittest
from unittest.mock import patch

from pvx.interactive.screens.module_update import ModuleUpdateScreen


class ModuleUpdateScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.module_update.widgets.pause")
    @patch("pvx.interactive.screens.module_update.widgets.success")
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
        self, mock_discover, mock_ask_select, mock_url, mock_install, mock_success, mock_pause
    ):
        result = ModuleUpdateScreen().render()
        self.assertEqual(result, "BACK")
        mock_install.assert_called_once_with("dummy", "https://example.com/index.json")
        mock_success.assert_called_once_with("dummy atualizado.")
        mock_pause.assert_called_once_with()

    @patch("pvx.interactive.screens.module_update.widgets.pause")
    @patch("pvx.interactive.screens.module_update.widgets.success")
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
        self, mock_discover, mock_ask_select, mock_url, mock_install, mock_success, mock_pause
    ):
        result = ModuleUpdateScreen().render()
        self.assertEqual(result, "BACK")
        self.assertEqual(mock_install.call_count, 2)
        self.assertEqual(mock_success.call_count, 2)
        mock_pause.assert_called_once_with()


    @patch("pvx.interactive.screens.module_update.ask_select", return_value=None)
    @patch(
        "pvx.interactive.screens.module_update.discover_installed_modules",
        return_value={"dummy": object()},
    )
    def test_none_selection_returns_back(self, mock_discover, mock_ask_select):
        self.assertEqual(ModuleUpdateScreen().render(), "BACK")

    @patch("pvx.interactive.screens.module_update.ask_select")
    @patch("pvx.interactive.screens.module_update.widgets.pause")
    @patch("pvx.interactive.screens.module_update.widgets.message")
    @patch("pvx.interactive.screens.module_update.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.module_update.widgets.breadcrumb")
    def test_no_installed_modules_shows_pause_and_returns_back(
        self, mock_breadcrumb, mock_discover, mock_message, mock_pause, mock_ask_select
    ):
        result = ModuleUpdateScreen().render()
        self.assertEqual(result, "BACK")
        mock_breadcrumb.assert_called_once_with("pvx > módulos > atualizar")
        mock_message.assert_called_once_with("nenhum módulo instalado.")
        mock_pause.assert_called_once_with()
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

    @patch("pvx.interactive.screens.module_update.widgets.pause")
    @patch("pvx.interactive.screens.module_update.widgets.failed")
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
        self, mock_discover, mock_ask_select, mock_install, mock_failed, mock_pause
    ):
        # achado ao vivo: a tela voltava direto pro menu anterior sem pausar --
        # sucesso/falha de cada módulo sumiam da tela antes do usuário ler.
        result = ModuleUpdateScreen().render()
        self.assertEqual(result, "BACK")
        mock_failed.assert_called_once_with("não foi possível acessar o registry")
        mock_pause.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
