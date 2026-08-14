import unittest
from unittest.mock import patch

import click
import questionary

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

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="Módulos")
    def test_selecting_modulos_pushes_modules_screen(self, mock_ask_select, mock_discover):
        self.assertEqual(RootScreen().render(), "modules")

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="Logs")
    def test_selecting_logs_pushes_logs_screen(self, mock_ask_select, mock_discover):
        self.assertEqual(RootScreen().render(), "logs")

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="Tema")
    def test_selecting_tema_pushes_theme_screen(self, mock_ask_select, mock_discover):
        self.assertEqual(RootScreen().render(), "theme")

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.ask_select", return_value="Sair")
    def test_choices_are_grouped_under_system_and_modules_separators(
        self, mock_ask_select, mock_discover
    ):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        system_index = next(
            i for i, c in enumerate(choices)
            if isinstance(c, questionary.Separator) and c.line == "SYSTEM"
        )
        modules_index = next(
            i for i, c in enumerate(choices)
            if isinstance(c, questionary.Separator) and c.line == "MODULES"
        )
        self.assertLess(system_index, choices.index("Módulos"))
        self.assertLess(modules_index, choices.index("dummy"))
        self.assertLess(choices.index("dummy"), choices.index("Sair"))

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="Sair")
    def test_no_modules_separator_when_none_installed(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]
        self.assertFalse(
            any(isinstance(c, questionary.Separator) and c.line == "MODULES" for c in choices)
        )


if __name__ == "__main__":
    unittest.main()
