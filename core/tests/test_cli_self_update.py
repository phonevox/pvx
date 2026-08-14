import unittest
from unittest.mock import patch

from click.testing import CliRunner

from pvx.cli import build_cli


class SelfUpdateCommandTest(unittest.TestCase):
    @patch("pvx.cli.self_update.self_update", return_value="0.2.0")
    def test_self_update_calls_self_update_and_reports_version(self, mock_self_update):
        result = CliRunner().invoke(build_cli(), ["self-update"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("0.2.0", result.output)

    @patch("pvx.cli.self_update.self_update", side_effect=PermissionError)
    def test_self_update_permission_error_shows_clear_message(self, mock_self_update):
        result = CliRunner().invoke(build_cli(), ["self-update"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("sudo", result.output.lower())

    @patch("pvx.cli.self_update.self_update", return_value="0.1.0")
    @patch("pvx.cli.build_info.describe", return_value="nightly, a1b2c3d")
    def test_declining_confirmation_on_local_build_skips_update(
        self, mock_describe, mock_self_update
    ):
        result = CliRunner().invoke(build_cli(), ["self-update"], input="n\n")
        mock_self_update.assert_not_called()

    @patch("pvx.cli.self_update.self_update", return_value="0.1.0")
    @patch("pvx.cli.build_info.describe", return_value="nightly, a1b2c3d")
    def test_confirming_on_local_build_proceeds_with_update(
        self, mock_describe, mock_self_update
    ):
        result = CliRunner().invoke(build_cli(), ["self-update"], input="y\n")
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_self_update.assert_called_once()

    @patch("pvx.cli.self_update.self_update", return_value="0.1.0")
    @patch("pvx.cli.build_info.describe", return_value=None)
    def test_no_confirmation_needed_for_official_build(self, mock_describe, mock_self_update):
        result = CliRunner().invoke(build_cli(), ["self-update"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_self_update.assert_called_once()

    @patch("pvx.cli.self_update.self_update", return_value="0.1.0")
    @patch("pvx.cli.build_info.describe", return_value=None)
    @patch("pvx.cli.widgets.spinner")
    def test_self_update_shows_spinner(self, mock_spinner, mock_describe, mock_self_update):
        result = CliRunner().invoke(build_cli(), ["self-update"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_spinner.assert_called_once()


class SelfUninstallCommandTest(unittest.TestCase):
    @patch("pvx.cli.self_update.uninstall")
    def test_requires_confirmation(self, mock_uninstall):
        result = CliRunner().invoke(build_cli(), ["self-uninstall"], input="n\n")
        mock_uninstall.assert_not_called()

    @patch("pvx.cli.self_update.uninstall")
    def test_yes_flag_skips_confirmation(self, mock_uninstall):
        result = CliRunner().invoke(build_cli(), ["self-uninstall", "--yes"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_uninstall.assert_called_once_with(purge=False)

    @patch("pvx.cli.self_update.uninstall")
    def test_purge_flag_passed_through(self, mock_uninstall):
        result = CliRunner().invoke(build_cli(), ["self-uninstall", "--yes", "--purge"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_uninstall.assert_called_once_with(purge=True)


if __name__ == "__main__":
    unittest.main()
