import unittest
from unittest.mock import patch

from pvx.interactive.screens.module_install import ModuleInstallScreen


class ModuleInstallScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.ask_text", return_value="dummy")
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Registry oficial")
    def test_installs_from_official_registry(
        self, mock_ask_select, mock_ask_text, mock_url, mock_install
    ):
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_install.assert_called_once_with("dummy", "https://registry.pvx.dev/index.json")

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.ask_text",
        side_effect=["https://meurepo.com/index.json", "dummy"],
    )
    @patch(
        "pvx.interactive.screens.module_install.ask_select",
        return_value="Outro repositório (URL)",
    )
    def test_installs_from_custom_repository(self, mock_ask_select, mock_ask_text, mock_install):
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_install.assert_called_once_with("dummy", "https://meurepo.com/index.json")

    @patch("pvx.interactive.screens.module_install.ask_select", return_value=None)
    def test_none_source_selection_returns_back(self, mock_ask_select):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")


if __name__ == "__main__":
    unittest.main()
