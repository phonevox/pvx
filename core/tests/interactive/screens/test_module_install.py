import unittest
from unittest.mock import patch

from pvx.interactive.screens.module_install import ModuleInstallScreen

SOURCES = ["Registry oficial", "Outro repositório (URL)", "Voltar"]
_ROWS = [
    {"name": "dummy", "installed_version": "-", "latest_version": "0.1.0", "status": "disponível"},
    {
        "name": "ssh-hardening", "installed_version": "-", "latest_version": "0.1.0",
        "status": "disponível",
    },
]


class ModuleInstallScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=["dummy"])
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Registry oficial")
    def test_installs_selected_module_from_official_registry(
        self, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install
    ):
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_install.assert_called_once_with("dummy", "https://registry.pvx.dev/index.json")
        self.assertEqual(mock_checkbox.call_args.args[1], ["dummy", "ssh-hardening"])

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch(
        "pvx.interactive.screens.module_install.ask_checkbox",
        return_value=["dummy", "ssh-hardening"],
    )
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Registry oficial")
    def test_installs_every_module_checked(
        self, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install
    ):
        ModuleInstallScreen().render()
        self.assertEqual(mock_install.call_count, 2)

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=["dummy"])
    @patch(
        "pvx.interactive.screens.module_install.ask_text",
        return_value="https://meurepo.com/index.json",
    )
    @patch(
        "pvx.interactive.screens.module_install.ask_select",
        return_value="Outro repositório (URL)",
    )
    def test_installs_from_custom_repository(
        self, mock_ask_select, mock_ask_text, mock_checkbox, mock_list_modules, mock_install
    ):
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_install.assert_called_once_with("dummy", "https://meurepo.com/index.json")

    @patch("pvx.interactive.screens.module_install.ask_select", return_value=None)
    def test_none_source_selection_returns_back(self, mock_ask_select):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Voltar")
    def test_selecting_voltar_returns_back_without_installing(self, mock_ask_select, mock_install):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")
        mock_install.assert_not_called()

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.ask_text",
        return_value=None,
    )
    @patch(
        "pvx.interactive.screens.module_install.ask_select",
        return_value="Outro repositório (URL)",
    )
    def test_none_custom_index_url_returns_back_without_installing(
        self, mock_ask_select, mock_ask_text, mock_install
    ):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")
        mock_install.assert_not_called()

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=None)
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Registry oficial")
    def test_cancelling_checkbox_returns_back_without_installing(
        self, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install
    ):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")
        mock_install.assert_not_called()

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=[])
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Registry oficial")
    def test_confirming_with_nothing_checked_returns_back_without_installing(
        self, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install
    ):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")
        mock_install.assert_not_called()

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=[])
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Registry oficial")
    def test_no_modules_available_shows_message_and_returns_back(
        self, mock_ask_select, mock_list_modules, mock_url, mock_install
    ):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")
        mock_install.assert_not_called()

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=["dummy"])
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Registry oficial")
    @patch("pvx.interactive.screens.module_install.widgets.spinner")
    def test_shows_spinner_while_installing(
        self, mock_spinner, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install
    ):
        ModuleInstallScreen().render()
        mock_spinner.assert_called_once()

    @patch("pvx.interactive.screens.module_install.click.echo")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch(
        "pvx.interactive.screens.module_install.listing.list_modules",
        side_effect=RuntimeError("não foi possível acessar o registry"),
    )
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="Registry oficial")
    def test_network_failure_shows_message_and_returns_back(
        self, mock_ask_select, mock_list_modules, mock_url, mock_echo
    ):
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        self.assertTrue(
            any("não foi possível acessar o registry" in str(c) for c in mock_echo.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
