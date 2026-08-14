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


if __name__ == "__main__":
    unittest.main()
