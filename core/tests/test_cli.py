import unittest
from unittest.mock import patch

from click.testing import CliRunner

from pvx.cli import build_cli, cli
from pvx.version import __version__


class CliRootTest(unittest.TestCase):
    def test_version_flag_prints_version_and_exits_zero(self):
        result = CliRunner().invoke(cli, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(__version__, result.output)

    def test_help_flag_exits_zero(self):
        result = CliRunner().invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)

    @patch("pvx.cli.build_info.describe", return_value="nightly, a1b2c3d")
    def test_version_flag_shows_build_channel_when_present(self, mock_describe):
        result = CliRunner().invoke(build_cli(), ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("nightly, a1b2c3d", result.output)


if __name__ == "__main__":
    unittest.main()
