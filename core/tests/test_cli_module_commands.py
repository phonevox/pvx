import unittest
from unittest.mock import patch

import click
from click.testing import CliRunner

from pvx.cli import build_cli


class FakeModule:
    def cli_group(self):
        @click.group()
        def group():
            pass

        return group


class ModuleInstallCommandTest(unittest.TestCase):
    @patch("pvx.cli.installer.install")
    def test_module_install_calls_installer(self, mock_install):
        result = CliRunner().invoke(build_cli(), ["module", "install", "dummy"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertEqual(mock_install.call_args.args[0], "dummy")

    @patch("pvx.cli.installer.install")
    @patch("pvx.cli.widgets.spinner")
    def test_module_install_shows_spinner(self, mock_spinner, mock_install):
        result = CliRunner().invoke(build_cli(), ["module", "install", "dummy"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_spinner.assert_called_once()

    @patch("pvx.cli.installer.install")
    def test_root_install_alias_calls_same_command(self, mock_install):
        result = CliRunner().invoke(build_cli(), ["install", "dummy"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_install.assert_called_once()

    @patch(
        "pvx.cli.installer.install",
        side_effect=RuntimeError("não foi possível acessar o registry (nome não resolvido)"),
    )
    def test_network_failure_shows_clean_message_no_traceback(self, mock_install):
        result = CliRunner().invoke(build_cli(), ["module", "install", "dummy"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("não foi possível acessar o registry", result.output)

    @patch("pvx.cli._core_logger")
    @patch("pvx.cli.installer.install")
    def test_logs_success(self, mock_install, mock_logger):
        CliRunner().invoke(build_cli(), ["module", "install", "dummy"])
        mock_logger.return_value.info.assert_called_once()
        self.assertIn("dummy", mock_logger.return_value.info.call_args.args[0])

    @patch("pvx.cli._core_logger")
    @patch("pvx.cli.installer.install", side_effect=RuntimeError("falhou"))
    def test_logs_failure(self, mock_install, mock_logger):
        CliRunner().invoke(build_cli(), ["module", "install", "dummy"])
        mock_logger.return_value.error.assert_called_once()
        self.assertIn("dummy", mock_logger.return_value.error.call_args.args[0])


class ModuleUpdateCommandTest(unittest.TestCase):
    @patch("pvx.cli.installer.install")
    @patch(
        "pvx.cli.discover_installed_modules",
        return_value={"dummy": FakeModule(), "other": FakeModule()},
    )
    def test_update_all_reinstalls_every_installed_module(self, mock_discover, mock_install):
        result = CliRunner().invoke(build_cli(), ["module", "update", "--all"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertEqual(mock_install.call_count, 2)

    @patch("pvx.cli.installer.install")
    @patch("pvx.cli.widgets.spinner")
    @patch("pvx.cli.discover_installed_modules", return_value={"dummy": FakeModule()})
    def test_update_shows_spinner(self, mock_discover, mock_spinner, mock_install):
        result = CliRunner().invoke(build_cli(), ["module", "update", "dummy"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_spinner.assert_called_once()

    @patch(
        "pvx.cli.installer.install",
        side_effect=RuntimeError("não foi possível acessar o registry (nome não resolvido)"),
    )
    def test_network_failure_shows_clean_message_no_traceback(self, mock_install):
        result = CliRunner().invoke(build_cli(), ["module", "update", "dummy"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("não foi possível acessar o registry", result.output)

    @patch("pvx.cli._core_logger")
    @patch("pvx.cli.installer.install")
    def test_logs_success(self, mock_install, mock_logger):
        CliRunner().invoke(build_cli(), ["module", "update", "dummy"])
        mock_logger.return_value.info.assert_called_once()
        self.assertIn("dummy", mock_logger.return_value.info.call_args.args[0])

    @patch("pvx.cli._core_logger")
    @patch("pvx.cli.installer.install", side_effect=RuntimeError("falhou"))
    def test_logs_failure(self, mock_install, mock_logger):
        CliRunner().invoke(build_cli(), ["module", "update", "dummy"])
        mock_logger.return_value.error.assert_called_once()


class ModuleUninstallCommandTest(unittest.TestCase):
    @patch("pvx.cli.installer.uninstall")
    def test_uninstall_requires_confirmation(self, mock_uninstall):
        CliRunner().invoke(build_cli(), ["module", "uninstall", "dummy"], input="n\n")
        mock_uninstall.assert_not_called()

    @patch("pvx.cli.installer.uninstall")
    def test_uninstall_yes_flag_skips_confirmation(self, mock_uninstall):
        result = CliRunner().invoke(build_cli(), ["module", "uninstall", "dummy", "--yes"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_uninstall.assert_called_once_with("dummy")

    def test_uninstall_has_no_root_alias(self):
        result = CliRunner().invoke(build_cli(), ["uninstall", "dummy", "--yes"])
        self.assertNotEqual(result.exit_code, 0)

    @patch("pvx.cli._core_logger")
    @patch("pvx.cli.installer.uninstall")
    def test_logs_success(self, mock_uninstall, mock_logger):
        CliRunner().invoke(build_cli(), ["module", "uninstall", "dummy", "--yes"])
        mock_logger.return_value.info.assert_called_once()
        self.assertIn("dummy", mock_logger.return_value.info.call_args.args[0])


class ModuleListCommandTest(unittest.TestCase):
    @patch(
        "pvx.cli.listing.list_modules",
        return_value=[
            {
                "name": "dummy",
                "installed_version": "1.0.0",
                "latest_version": "1.1.0",
                "status": "atualização disponível",
            },
            {
                "name": "ssh-hardening",
                "installed_version": "-",
                "latest_version": "1.0.0",
                "status": "disponível",
            },
        ],
    )
    def test_lists_modules_in_a_table(self, mock_list_modules):
        result = CliRunner().invoke(build_cli(), ["module", "list"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("dummy", result.output)
        self.assertIn("ssh-hardening", result.output)
        self.assertIn("atualização disponível", result.output)
        self.assertIn("disponível", result.output)

    @patch(
        "pvx.cli.listing.list_modules",
        side_effect=RuntimeError("não foi possível acessar o registry (nome não resolvido)"),
    )
    def test_network_failure_shows_clean_message_no_traceback(self, mock_list_modules):
        result = CliRunner().invoke(build_cli(), ["module", "list"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("não foi possível acessar o registry", result.output)


if __name__ == "__main__":
    unittest.main()
