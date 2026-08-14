import unittest
from unittest.mock import call, patch

from pvx.interactive import theme
from pvx.interactive.widgets import (
    BANNER,
    banner,
    breadcrumb,
    clear,
    message,
    pause,
    print_modules_table,
    spinner,
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
    @patch("pvx.interactive.widgets.click.pause")
    @patch("pvx.interactive.widgets.Console")
    def test_prints_standard_message_in_gray_then_waits_for_a_keypress(
        self, mock_console_cls, mock_pause
    ):
        pause()
        mock_console_cls.return_value.print.assert_called_once_with(
            "pressione enter pra continuar...", style=theme.SEPARATOR_COLOR, highlight=False
        )
        mock_pause.assert_called_once_with("")


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


if __name__ == "__main__":
    unittest.main()
