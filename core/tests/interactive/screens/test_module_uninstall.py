import unittest
from unittest.mock import patch

from pvx.interactive.screens.module_uninstall import ModuleUninstallScreen


class ModuleUninstallScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.module_uninstall.installer.uninstall")
    @patch("pvx.interactive.screens.module_uninstall.ask_confirm", return_value=True)
    @patch("pvx.interactive.screens.module_uninstall.ask_select", return_value="dummy")
    @patch(
        "pvx.interactive.screens.module_uninstall.discover_installed_modules",
        return_value={"dummy": object()},
    )
    def test_confirmed_removal_calls_uninstall(
        self, mock_discover, mock_ask_select, mock_ask_confirm, mock_uninstall
    ):
        result = ModuleUninstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_uninstall.assert_called_once_with("dummy")

    @patch("pvx.interactive.screens.module_uninstall.installer.uninstall")
    @patch("pvx.interactive.screens.module_uninstall.ask_confirm", return_value=False)
    @patch("pvx.interactive.screens.module_uninstall.ask_select", return_value="dummy")
    @patch(
        "pvx.interactive.screens.module_uninstall.discover_installed_modules",
        return_value={"dummy": object()},
    )
    def test_declined_confirmation_does_not_uninstall(
        self, mock_discover, mock_ask_select, mock_ask_confirm, mock_uninstall
    ):
        result = ModuleUninstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_uninstall.assert_not_called()

    @patch("pvx.interactive.screens.module_uninstall.ask_select", return_value=None)
    @patch(
        "pvx.interactive.screens.module_uninstall.discover_installed_modules",
        return_value={"dummy": object()},
    )
    def test_none_selection_returns_back(self, mock_discover, mock_ask_select):
        self.assertEqual(ModuleUninstallScreen().render(), "BACK")

    @patch("pvx.interactive.screens.module_uninstall.installer.uninstall")
    @patch("pvx.interactive.screens.module_uninstall.ask_select", return_value="Voltar")
    @patch(
        "pvx.interactive.screens.module_uninstall.discover_installed_modules",
        return_value={"dummy": object()},
    )
    def test_selecting_voltar_returns_back_without_uninstalling(
        self, mock_discover, mock_ask_select, mock_uninstall
    ):
        self.assertEqual(ModuleUninstallScreen().render(), "BACK")
        mock_uninstall.assert_not_called()


if __name__ == "__main__":
    unittest.main()
