import unittest
from unittest.mock import patch

from click.testing import CliRunner

from pvx.modules.base import PvxModule


class FakeDummyModule(PvxModule):
    name = "dummy"
    version = "0.1.0"

    def cli_group(self):
        import click

        @click.group()
        def group():
            pass

        @group.command()
        def hello():
            click.echo("hello from dummy")

        return group


class CliDynamicDispatchTest(unittest.TestCase):
    @patch("pvx.cli.discover_installed_modules")
    def test_installed_module_command_is_dispatched(self, mock_discover):
        mock_discover.return_value = {"dummy": FakeDummyModule()}

        from pvx.cli import build_cli

        result = CliRunner().invoke(build_cli(), ["dummy", "hello"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello from dummy", result.output)


if __name__ == "__main__":
    unittest.main()
