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


class FakeCrashingModule(PvxModule):
    name = "crashy"
    version = "0.1.0"

    def cli_group(self):
        @click.group()
        def group():
            pass

        @group.command()
        def boom():
            raise RuntimeError("algo quebrou de verdade")

        return group


class FakeAbortingModule(PvxModule):
    name = "aborty"
    version = "0.1.0"

    def cli_group(self):
        @click.group()
        def group():
            pass

        @group.command()
        def cancel():
            raise KeyboardInterrupt()

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
    # sem isso, TODO teste bateria de verdade no registry/core-manifest via
    # update_check.pending_notices() (rede real, lenta e não-determinística)
    # -- default silencioso aqui, testes específicos abaixo sobrescrevem.
    def setUp(self):
        patcher = patch("pvx.interactive.screens.root.update_check.pending_notices", return_value=[])
        self.mock_pending_notices = patcher.start()
        self.addCleanup(patcher.stop)

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_selecting_sair_exits(self, mock_ask_select, mock_discover):
        result = RootScreen().render()
        self.assertEqual(result, "EXIT")

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
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
        return_value={"crashy": FakeCrashingModule()},
    )
    @patch("pvx.interactive.screens.root.widgets.pause")
    @patch("pvx.interactive.screens.root.widgets.crash")
    @patch("pvx.interactive.screens.root.ask_select", side_effect=["crashy", "boom", None])
    def test_unhandled_exception_shows_crash_instead_of_killing_the_session(
        self, mock_ask_select, mock_crash, mock_pause, mock_discover
    ):
        # achado ao vivo: um módulo estourando qualquer exceção que não seja
        # ClickException (ex.: CalledProcessError de um subprocess) derrubava
        # a sessão inteira do menu com traceback cru -- sem cor, fácil de
        # perder no meio do resto da saída.
        result = RootScreen().render()
        self.assertIsNone(result)
        mock_crash.assert_called_once()
        self.assertIn("algo quebrou de verdade", mock_crash.call_args.args[0])
        mock_pause.assert_called_once()

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"aborty": FakeAbortingModule()},
    )
    @patch("pvx.interactive.screens.root.widgets.crash")
    @patch("pvx.interactive.screens.root.ask_select", side_effect=["aborty", "cancel"])
    def test_ctrl_c_inside_a_module_command_closes_pvx_instead_of_crashing(
        self, mock_ask_select, mock_crash, mock_discover
    ):
        # achado ao vivo: ctrl-c dentro de um prompt (ask_password) vira
        # click.exceptions.Abort (via cmd.main() do click) -- o except
        # Exception genérico tratava isso como crash de módulo (traceback na
        # tela) em vez de fechar o pvx, que é o comportamento documentado
        # (NAV_HINT: "ctrl-c fecha o pvx").
        with self.assertRaises(click.exceptions.Abort):
            RootScreen().render()
        mock_crash.assert_not_called()

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
    @patch("pvx.interactive.screens.root.ask_select", return_value="módulos")
    def test_selecting_modulos_pushes_modules_screen(self, mock_ask_select, mock_discover):
        self.assertEqual(RootScreen().render(), "modules")

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="logs")
    def test_selecting_logs_pushes_logs_screen(self, mock_ask_select, mock_discover):
        self.assertEqual(RootScreen().render(), "logs")

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="tema")
    def test_selecting_tema_pushes_theme_screen(self, mock_ask_select, mock_discover):
        self.assertEqual(RootScreen().render(), "theme")

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_choices_are_grouped_under_system_and_modules_separators(
        self, mock_ask_select, mock_discover
    ):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        system_index = next(
            i for i, c in enumerate(choices)
            if isinstance(c, questionary.Separator) and c.line == "Sistema"
        )
        modules_index = next(
            i for i, c in enumerate(choices)
            if isinstance(c, questionary.Separator) and c.line == "Módulos"
        )
        self.assertLess(system_index, _index_of_value(choices, "módulos"))
        self.assertLess(modules_index, _index_of_value(choices, "dummy"))

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_section_items_are_indented(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        modulos = next(c for c in choices if isinstance(c, questionary.Choice) and c.value == "módulos")
        dummy = next(c for c in choices if isinstance(c, questionary.Choice) and c.value == "dummy")
        self.assertTrue(modulos.title.startswith("  "))
        self.assertTrue(dummy.title.startswith("  "))

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_every_sistema_item_has_a_description(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]
        for value in ("módulos", "logs", "tema", "versão", "atualizar", "sair"):
            choice = next(c for c in choices if isinstance(c, questionary.Choice) and c.value == value)
            self.assertTrue(choice.description, msg=f"{value} sem description")

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_sair_is_the_last_item_of_the_sistema_group(self, mock_ask_select, mock_discover):
        # "sair" mora dentro do grupo Sistema (último item), não mais
        # separado sozinho no fim da lista inteira.
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        modules_index = next(
            i for i, c in enumerate(choices)
            if isinstance(c, questionary.Separator) and c.line == "Módulos"
        )
        sair_index = _index_of_value(choices, "sair")
        self.assertLess(sair_index, modules_index)
        self.assertTrue(choices[sair_index].title.startswith("  "))

    @patch(
        "pvx.interactive.screens.root.discover_installed_modules",
        return_value={"dummy": FakeDummyModule()},
    )
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_blank_line_separates_system_and_modules_sections(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]

        modules_index = next(
            i for i, c in enumerate(choices)
            if isinstance(c, questionary.Separator) and c.line == "Módulos"
        )
        self.assertIsInstance(choices[modules_index - 1], questionary.Separator)
        self.assertEqual(choices[modules_index - 1].line, " ")

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.widgets.pause")
    @patch("pvx.interactive.screens.root.widgets.message")
    @patch("pvx.interactive.screens.root.build_info.describe", return_value=None)
    @patch("pvx.interactive.screens.root.ask_select", return_value="versão")
    def test_selecting_versao_shows_the_version_and_stays_at_root(
        self, mock_ask_select, mock_describe, mock_message, mock_pause, mock_discover
    ):
        result = RootScreen().render()
        self.assertIsNone(result)
        mock_message.assert_called_once()
        self.assertIn("pvx", mock_message.call_args.args[0].lower())
        mock_pause.assert_called_once()

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.widgets.pause")
    @patch("pvx.interactive.screens.root.widgets.success")
    @patch("pvx.interactive.screens.root.self_update.self_update", return_value="0.3.0")
    @patch("pvx.interactive.screens.root.build_info.describe", return_value=None)
    @patch("pvx.interactive.screens.root.ask_select", return_value="atualizar")
    def test_selecting_atualizar_runs_self_update_without_confirm_on_official_build(
        self, mock_ask_select, mock_describe, mock_self_update, mock_success, mock_pause, mock_discover
    ):
        result = RootScreen().render()
        self.assertIsNone(result)
        mock_self_update.assert_called_once()
        mock_success.assert_called_once()
        mock_pause.assert_called_once()

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.self_update.self_update")
    @patch("pvx.interactive.screens.root.ask_confirm", return_value=False)
    @patch("pvx.interactive.screens.root.build_info.describe", return_value="nightly, abc123")
    @patch("pvx.interactive.screens.root.ask_select", return_value="atualizar")
    def test_atualizar_asks_confirmation_on_nightly_build_and_bails_out_if_declined(
        self, mock_ask_select, mock_describe, mock_ask_confirm, mock_self_update, mock_discover
    ):
        result = RootScreen().render()
        self.assertIsNone(result)
        mock_ask_confirm.assert_called_once()
        mock_self_update.assert_not_called()

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.widgets.pause")
    @patch("pvx.interactive.screens.root.widgets.failed")
    @patch("pvx.interactive.screens.root.self_update.self_update", side_effect=PermissionError())
    @patch("pvx.interactive.screens.root.build_info.describe", return_value=None)
    @patch("pvx.interactive.screens.root.ask_select", return_value="atualizar")
    def test_atualizar_shows_failed_when_not_root(
        self, mock_ask_select, mock_describe, mock_self_update, mock_failed, mock_pause, mock_discover
    ):
        result = RootScreen().render()
        self.assertIsNone(result)
        mock_failed.assert_called_once()
        mock_pause.assert_called_once()

    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_no_modules_separator_when_none_installed(self, mock_ask_select, mock_discover):
        RootScreen().render()
        choices = mock_ask_select.call_args.args[1]
        self.assertFalse(
            any(isinstance(c, questionary.Separator) and c.line == "Módulos" for c in choices)
        )


class RootScreenUpdateNoticeTest(unittest.TestCase):
    # aviso de atualização pendente (core e/ou módulo) -- só no menu
    # interativo (aqui), nunca na CLI direta (nem passa por RootScreen).
    @patch("pvx.interactive.screens.root.widgets.warning")
    @patch(
        "pvx.interactive.screens.root.update_check.pending_notices",
        return_value=["core: atualização disponível (0.2.25 -> 0.2.26)"],
    )
    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_shows_a_warning_per_pending_notice(
        self, mock_ask_select, mock_discover, mock_notices, mock_warning
    ):
        RootScreen().render()
        mock_warning.assert_called_once_with("core: atualização disponível (0.2.25 -> 0.2.26)")

    @patch("pvx.interactive.screens.root.widgets.warning")
    @patch("pvx.interactive.screens.root.update_check.pending_notices", return_value=[])
    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={})
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_no_warning_when_nothing_pending(self, mock_ask_select, mock_discover, mock_notices, mock_warning):
        RootScreen().render()
        mock_warning.assert_not_called()

    @patch("pvx.interactive.screens.root.widgets.warning")
    @patch(
        "pvx.interactive.screens.root.update_check.pending_notices",
        return_value=["core: atualização disponível (0.2.25 -> 0.2.26)", "firewall: atualização disponível (0.2.10 -> 0.2.11)"],
    )
    @patch("pvx.interactive.screens.root.discover_installed_modules", return_value={"firewall": object()})
    @patch("pvx.interactive.screens.root.ask_select", return_value="sair")
    def test_passes_installed_modules_and_shows_every_notice(
        self, mock_ask_select, mock_discover, mock_notices, mock_warning
    ):
        RootScreen().render()
        mock_notices.assert_called_once_with(mock_discover.return_value)
        self.assertEqual(mock_warning.call_count, 2)


if __name__ == "__main__":
    unittest.main()
