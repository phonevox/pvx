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


def _index_of_value(choices, value):
    return next(
        i for i, c in enumerate(choices)
        if (c.value if isinstance(c, questionary.Choice) else c) == value
    )


class RootScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="Sair")
    def test_selecting_sair_exits(self, mock_ask_select, mock_discover):
        result = RootScreen().render()
        self.assertEqual(result, "EXIT")

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="Sair")
    @patch("pvx.interactive.screens.root.widgets.banner")
    def test_shows_banner(self, mock_banner, mock_ask_select, mock_discover):
        RootScreen().render()
        mock_banner.assert_called_once()

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
        self.assertLess(system_index, _index_of_value(choices, "Módulos"))
        self.assertLess(modules_index, _index_of_value(choices, "dummy"))
        self.assertLess(_index_of_value(choices, "dummy"), choices.index("Sair"))

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.ask_select", return_value="Sair")
    def test_section_items_are_indented(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        modulos = next(c for c in choices if isinstance(c, questionary.Choice) and c.value == "Módulos")
        dummy = next(c for c in choices if isinstance(c, questionary.Choice) and c.value == "dummy")
        self.assertTrue(modulos.title.startswith("  "))
        self.assertTrue(dummy.title.startswith("  "))

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.ask_select", return_value="Sair")
    def test_sair_has_its_own_separator(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        sair_index = choices.index("Sair")
        self.assertIsInstance(choices[sair_index - 1], questionary.Separator)

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
