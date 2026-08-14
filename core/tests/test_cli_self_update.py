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


if __name__ == "__main__":
    unittest.main()
