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


class FakePickyModule(PvxModule):
    name = "picky"
    version = "0.1.0"

    def cli_group(self):
        @click.group()
        def group():
            pass

        @group.command()
        @click.argument("tipo")
        def prepare(tipo):
            click.echo(f"preparando {tipo}")

        return group


class FakeNestedModule(PvxModule):
    name = "nested"
    version = "0.1.0"

    def cli_group(self):
        @click.group()
        def group():
            pass

        @group.group()
        def port():
            pass

        @port.command()
        def accept():
            click.echo("port accepted")

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
        side_effect=["dummy", "hello", None],
    )
    def test_module_without_interactive_entry_runs_command_inline(
        self, mock_ask_select, mock_discover
    ):
        # sem interactive_entry() (M7) -> auto-menu inline, sem push de tela.
        # depois de rodar "hello", o menu redesenha o MESMO nível (bug
        # reportado: listar/rodar algo não pode chutar de volta pro root) --
        # só sai quando o usuário dá esc nesse nível (3º valor, None).
        result = RootScreen().render()
        self.assertIsNone(result)
        self.assertEqual(mock_ask_select.call_count, 3)

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.widgets.clear")
    @patch(
        "pvx.interactive.screens.root.ask_select",
        side_effect=["dummy", "hello", None],
    )
    def test_clears_screen_before_auto_menu_prompt(self, mock_ask_select, mock_clear, mock_discover):
        # 1x antes do primeiro prompt do auto-menu (header do módulo não pode
        # ficar preso na tela) + 1x depois de rodar "hello", antes de
        # redesenhar o mesmo nível de novo.
        RootScreen().render()
        self.assertEqual(mock_clear.call_count, 2)

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"picky": FakePickyModule()},
    )
    @patch("pvx.interactive.screens.root.widgets.pause")
    @patch("pvx.interactive.screens.root.widgets.message")
    @patch("pvx.interactive.screens.root.ask_select", side_effect=["picky", "prepare", None])
    def test_missing_required_argument_shows_message_instead_of_crashing(
        self, mock_ask_select, mock_message, mock_pause, mock_discover
    ):
        # auto-menu roda o comando via .main(standalone_mode=False) -- isso
        # faz o click propagar MissingParameter cru em vez de tratar; sem
        # esse guard, qualquer módulo com argumento obrigatório crasha a
        # sessão inteira do menu interativo.
        result = RootScreen().render()
        self.assertIsNone(result)
        mock_message.assert_called_once()
        mock_pause.assert_called_once()

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"nested": FakeNestedModule()},
    )
    @patch("pvx.interactive.screens.root.widgets.clear")
    @patch(
        "pvx.interactive.screens.root.ask_select",
        side_effect=["nested", "port", "accept", None, None],
    )
    def test_nested_group_is_navigated_into_and_leaf_runs(
        self, mock_ask_select, mock_clear, mock_discover
    ):
        # depois de "accept" rodar, redesenha "port >" de novo (1º None);
        # esc ali sobe pra "nested >" de novo (2º None) -- nunca pula pro
        # root sozinho.
        result = RootScreen().render()
        self.assertIsNone(result)
        self.assertEqual(mock_ask_select.call_count, 5)
        prompts = [c.args[0] for c in mock_ask_select.call_args_list]
        self.assertEqual(
            prompts,
            [
                "pvx >", "pvx > nested >", "pvx > nested > port >",
                "pvx > nested > port >", "pvx > nested >",
            ],
        )

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"nested": FakeNestedModule()},
    )
    @patch(
        "pvx.interactive.screens.root.ask_select",
        side_effect=["nested", "port", None, None],
    )
    def test_esc_inside_nested_group_returns_to_parent_menu_not_to_root(
        self, mock_ask_select, mock_discover
    ):
        # esc dentro de "port" só sai do "port", redesenha "nested >" de novo
        # -- não deve pular direto pra fora do módulo inteiro.
        result = RootScreen().render()
        self.assertIsNone(result)
        self.assertEqual(mock_ask_select.call_count, 4)
        prompts = [c.args[0] for c in mock_ask_select.call_args_list]
        self.assertEqual(prompts, ["pvx >", "pvx > nested >", "pvx > nested > port >", "pvx > nested >"])

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
    def test_sair_separator_is_a_blank_line_not_dashes(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        sair_index = choices.index("Sair")
        self.assertIsInstance(choices[sair_index - 1], questionary.Separator)
        self.assertEqual(choices[sair_index - 1].line, " ")

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.ask_select", return_value="Sair")
    def test_blank_line_separates_system_and_modules_sections(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        modules_index = next(
            i for i, c in enumerate(choices)
            if isinstance(c, questionary.Separator) and c.line == "MODULES"
        )
        self.assertIsInstance(choices[modules_index - 1], questionary.Separator)
        self.assertEqual(choices[modules_index - 1].line, " ")

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
