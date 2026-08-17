import unittest
from unittest.mock import call, patch

from pvx.interactive import theme
from pvx.interactive.widgets import (
    BANNER,
    banner,
    breadcrumb,
    clear,
    failed,
    message,
    pause,
    print_modules_table,
    spinner,
    state,
    success,
)


class ClearTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.click.clear")
    def test_delegates_to_click_clear(self, mock_clear):
        clear()
        mock_clear.assert_called_once()


class SpinnerTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.theme.current_accent_color", return_value="#0087ff")
    @patch("pvx.interactive.widgets.Console")
    def test_spinner_uses_theme_accent_color_text_stays_normal(self, mock_console_cls, mock_accent):
        spinner("Instalando módulo...")
        mock_console_cls.return_value.status.assert_called_once_with(
            "Instalando módulo...", spinner_style="#0087ff"
        )


class BannerTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.theme.current_accent_color", return_value="#0087ff")
    @patch("pvx.interactive.widgets.Console")
    def test_prints_banner_in_theme_accent_color(self, mock_console_cls, mock_accent):
        banner()
        mock_console_cls.return_value.print.assert_called_once_with(BANNER + "\n", style="#0087ff")


class PrintModulesTableTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.Console")
    def test_prints_a_table_with_one_column_per_field(self, mock_console_cls):
        rows = [
            {"name": "dummy", "installed_version": "1.0.0", "latest_version": "1.1.0", "status": "atualização disponível"},
        ]
        print_modules_table(rows)

        mock_console_cls.return_value.print.assert_called_once()
        table = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(len(table.columns), 4)


class PauseTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.sys.argv", ["pvx"])
    @patch("pvx.interactive.widgets.click.pause")
    @patch("pvx.interactive.widgets.Console")
    def test_prints_standard_message_in_gray_then_waits_for_a_keypress(
        self, mock_console_cls, mock_pause
    ):
        # sys.argv == ["pvx"] -- é assim que o processo inteiro roda quando
        # foi lançado sem argumentos (menu interativo, ver __main__.py).
        pause()
        mock_console_cls.return_value.print.assert_called_once_with(
            "pressione enter pra continuar...", style=theme.SEPARATOR_COLOR, highlight=False
        )
        mock_pause.assert_called_once_with("")

    @patch("pvx.interactive.widgets.sys.argv", ["pvx", "firewall", "status"])
    @patch("pvx.interactive.widgets.click.pause")
    @patch("pvx.interactive.widgets.Console")
    def test_no_ops_when_invoked_via_direct_cli(self, mock_console_cls, mock_pause):
        # bug reportado ao vivo: "pause NUNCA deve ocorrer quando ta
        # chamando pela CLI direto" -- `sys.stdin.isatty()` dava falso
        # positivo (terminal real também é tty na CLI direta, não só no
        # menu); sys.argv com mais de 1 item é o sinal correto de "não fui
        # lançado pelo menu interativo".
        pause()
        mock_console_cls.return_value.print.assert_not_called()
        mock_pause.assert_not_called()


class BreadcrumbTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.Console")
    def test_prints_breadcrumb_with_colored_question_mark_prefix(self, mock_console_cls):
        breadcrumb("pvx > módulos > listar")

        mock_console_cls.return_value.print.assert_called_once()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "? pvx > módulos > listar")
        self.assertEqual(printed.spans[0].style, "#5f819d")


class MessageTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.click.echo")
    def test_prints_text_surrounded_by_blank_lines(self, mock_echo):
        message("nenhum módulo instalado.")
        self.assertEqual(
            mock_echo.call_args_list,
            [call(), call("nenhum módulo instalado."), call()],
        )


class SuccessTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.Console")
    def test_prints_label_alone_when_no_detail(self, mock_console_cls):
        success()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "✓ sucesso!")

    @patch("pvx.interactive.widgets.Console")
    def test_appends_detail_inline_after_the_label(self, mock_console_cls):
        success("dummy instalado.")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertTrue(printed.plain.startswith("✓ sucesso!"))
        self.assertTrue(printed.plain.endswith("dummy instalado."))

    @patch("pvx.interactive.widgets.Console")
    def test_label_is_bold_green(self, mock_console_cls):
        success()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.spans[0].style, "bold green")


class FailedTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.Console")
    def test_prints_label_alone_when_no_detail(self, mock_console_cls):
        failed()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "✗ falha!")

    @patch("pvx.interactive.widgets.Console")
    def test_appends_detail_inline_after_the_label(self, mock_console_cls):
        failed("erro de rede.")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertTrue(printed.plain.startswith("✗ falha!"))
        self.assertTrue(printed.plain.endswith("erro de rede."))

    @patch("pvx.interactive.widgets.Console")
    def test_label_is_bold_red(self, mock_console_cls):
        failed()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.spans[0].style, "bold red")


class StateTest(unittest.TestCase):
    # distinto de success()/failed(): reporta um FATO/estado (ex.: "status"
    # de uma consulta), não o resultado de uma ação -- por isso sem o rótulo
    # "sucesso!"/"falha!" (usar isso numa consulta é semanticamente errado,
    # não houve ação nenhuma pra "ter sucesso" ou "falhar").
    @patch("pvx.interactive.widgets.Console")
    def test_prints_text_in_green_when_ok(self, mock_console_cls):
        state("sincronizado -- 6 regra(s) ativa(s)", ok=True)
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "sincronizado -- 6 regra(s) ativa(s)")
        self.assertEqual(printed.spans[0].style, "bold green")

    @patch("pvx.interactive.widgets.Console")
    def test_prints_text_in_red_when_not_ok(self, mock_console_cls):
        state("não sincronizado", ok=False)
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.spans[0].style, "bold red")


class SuccessFailedAlignmentTest(unittest.TestCase):
    def test_detail_starts_at_the_same_column_for_both(self):
        # "✓ sucesso!" e "✗ falha!" têm tamanhos diferentes -- o texto
        # extra precisa começar na mesma coluna nos dois, senão usados em
        # sequência (ex.: instalando vários módulos) fica desalinhado.
        with patch("pvx.interactive.widgets.Console") as mock_console_cls:
            success("x")
            success_line = mock_console_cls.return_value.print.call_args.args[0].plain
        with patch("pvx.interactive.widgets.Console") as mock_console_cls:
            failed("x")
            failed_line = mock_console_cls.return_value.print.call_args.args[0].plain

        self.assertEqual(success_line.index("x"), failed_line.index("x"))


if __name__ == "__main__":
    unittest.main()
