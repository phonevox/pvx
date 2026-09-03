import unittest
from unittest.mock import patch

from pvx.interactive.screens.module_install import ModuleInstallScreen

SOURCES = ["registry oficial", "outro repositório (URL)", "voltar"]
_ROWS = [
    {"name": "dummy", "installed_version": "-", "latest_version": "0.1.0", "status": "disponível"},
    {
        "name": "ssh-hardening", "installed_version": "-", "latest_version": "0.1.0",
        "status": "disponível",
    },
]


class ModuleInstallScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.module_install.widgets.pause")
    @patch("pvx.interactive.screens.module_install.widgets.success")
    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=["dummy"])
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="registry oficial")
    def test_installs_selected_module_from_official_registry(
        self, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install, mock_success,
        mock_pause,
    ):
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_install.assert_called_once_with("dummy", "https://registry.pvx.dev/index.json")
        self.assertEqual(mock_checkbox.call_args.args[1], ["dummy", "ssh-hardening"])
        mock_success.assert_called_once_with("dummy instalado.")
        mock_pause.assert_called_once_with()

    @patch("pvx.interactive.screens.module_install.widgets.pause")
    @patch("pvx.interactive.screens.module_install.widgets.success")
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
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="registry oficial")
    def test_installs_every_module_checked(
        self, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install, mock_success,
        mock_pause,
    ):
        ModuleInstallScreen().render()
        self.assertEqual(mock_install.call_count, 2)
        self.assertEqual(mock_success.call_count, 2)
        mock_pause.assert_called_once_with()

    @patch("pvx.interactive.screens.module_install.widgets.pause")
    @patch("pvx.interactive.screens.module_install.widgets.failed")
    @patch(
        "pvx.interactive.screens.module_install.installer.install",
        side_effect=RuntimeError("checksum não bate"),
    )
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=["dummy"])
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="registry oficial")
    def test_install_failure_shows_failed_per_module(
        self, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install, mock_failed,
        mock_pause,
    ):
        # achado ao vivo: a tela voltava direto pro menu anterior sem pausar --
        # sucesso/falha de cada módulo sumiam antes do usuário conseguir ler.
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_failed.assert_called_once_with("checksum não bate")
        mock_pause.assert_called_once_with()

    @patch("pvx.interactive.screens.module_install.widgets.pause")
    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=["dummy"])
    @patch(
        "pvx.interactive.screens.module_install.ask_text",
        return_value="https://meurepo.com/index.json",
    )
    @patch(
        "pvx.interactive.screens.module_install.ask_select",
        return_value="outro repositório (URL)",
    )
    def test_installs_from_custom_repository(
        self, mock_ask_select, mock_ask_text, mock_checkbox, mock_list_modules, mock_install, mock_pause
    ):
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        mock_install.assert_called_once_with("dummy", "https://meurepo.com/index.json")
        mock_pause.assert_called_once_with()

    @patch("pvx.interactive.screens.module_install.ask_select", return_value=None)
    def test_none_source_selection_returns_back(self, mock_ask_select):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="voltar")
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
        return_value="outro repositório (URL)",
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
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="registry oficial")
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
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="registry oficial")
    def test_confirming_with_nothing_checked_returns_back_without_installing(
        self, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install
    ):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")
        mock_install.assert_not_called()

    @patch("pvx.interactive.screens.module_install.widgets.pause")
    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=[])
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="registry oficial")
    def test_no_modules_available_shows_message_and_returns_back(
        self, mock_ask_select, mock_list_modules, mock_url, mock_install, mock_pause
    ):
        self.assertEqual(ModuleInstallScreen().render(), "BACK")
        mock_install.assert_not_called()
        mock_pause.assert_called_once_with()

    @patch("pvx.interactive.screens.module_install.installer.install")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch("pvx.interactive.screens.module_install.listing.list_modules", return_value=_ROWS)
    @patch("pvx.interactive.screens.module_install.ask_checkbox", return_value=["dummy"])
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="registry oficial")
    @patch("pvx.interactive.screens.module_install.widgets.spinner")
    def test_shows_spinner_while_installing(
        self, mock_spinner, mock_ask_select, mock_checkbox, mock_list_modules, mock_url, mock_install
    ):
        ModuleInstallScreen().render()
        mock_spinner.assert_called_once()

    @patch("pvx.interactive.screens.module_install.widgets.pause")
    @patch("pvx.interactive.screens.module_install.click.echo")
    @patch(
        "pvx.interactive.screens.module_install.config.registry_index_url",
        return_value="https://registry.pvx.dev/index.json",
    )
    @patch(
        "pvx.interactive.screens.module_install.listing.list_modules",
        side_effect=RuntimeError("não foi possível acessar o registry"),
    )
    @patch("pvx.interactive.screens.module_install.ask_select", return_value="registry oficial")
    def test_network_failure_shows_message_and_returns_back(
        self, mock_ask_select, mock_list_modules, mock_url, mock_echo, mock_pause
    ):
        result = ModuleInstallScreen().render()
        self.assertEqual(result, "BACK")
        self.assertTrue(
            any("não foi possível acessar o registry" in str(c) for c in mock_echo.call_args_list)
        )
        mock_pause.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
