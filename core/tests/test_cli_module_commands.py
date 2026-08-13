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
    def test_root_install_alias_calls_same_command(self, mock_install):
        result = CliRunner().invoke(build_cli(), ["install", "dummy"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_install.assert_called_once()


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


class LogsCommandTest(unittest.TestCase):
    @patch("pvx.cli.viewer.read_log", return_value="conteúdo do log")
    def test_logs_command_prints_log_content(self, mock_read_log):
        result = CliRunner().invoke(build_cli(), ["logs", "dummy"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("conteúdo do log", result.output)
        mock_read_log.assert_called_once_with("dummy", lines=None)


if __name__ == "__main__":
    unittest.main()
