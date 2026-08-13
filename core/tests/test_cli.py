import unittest

from click.testing import CliRunner

from pvx.cli import cli
from pvx.version import __version__


class CliRootTest(unittest.TestCase):
    def test_version_flag_prints_version_and_exits_zero(self):
        result = CliRunner().invoke(cli, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(__version__, result.output)

    def test_help_flag_exits_zero(self):
        result = CliRunner().invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
