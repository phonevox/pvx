import unittest
from unittest.mock import patch

import click

from pvx.interactive.screens.root import RootScreen
from pvx.modules.base import PvxModule


class FakeDummyModule(PvxModule):
    name = "dummy"
    version = "0.1.0"

    def cli_group(self):
        @click.group()
        def group():
            pass

        @group.command()
        def hello():
            click.echo("hello from dummy")

        return group


class RootScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="Sair")
    def test_selecting_sair_exits(self, mock_ask_select, mock_discover):
        result = RootScreen().render()
        self.assertEqual(result, "EXIT")

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch(
        "pvx.interactive.screens.root.ask_select",
        side_effect=["dummy", "hello"],
    )
    def test_module_without_interactive_entry_runs_command_inline(
        self, mock_ask_select, mock_discover
    ):
        # sem interactive_entry() (M7) -> auto-menu inline, sem push de tela.
        result = RootScreen().render()
        self.assertIsNone(result)
        self.assertEqual(mock_ask_select.call_count, 2)


if __name__ == "__main__":
    unittest.main()
