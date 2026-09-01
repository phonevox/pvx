import time
import unittest
from unittest.mock import call, patch

from pvx.interactive import theme
from pvx.interactive.widgets import (
    BANNER,
    banner,
    breadcrumb,
    check_result,
    clear,
    crash,
    failed,
    message,
    pause,
    print_modules_table,
    spinner,
    state,
    step,
    step_with_log,
    success,
)
from pvx.interactive.widgets import _ElapsedColumn


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


class StepTest(unittest.TestCase):
    # como spinner(), mas cronometra o bloco -- usado onde quem chama precisa
    # anunciar quanto a etapa demorou (ver widgets.success(f"... ({elapsed}s)")).
    @patch("pvx.interactive.widgets.Progress")
    def test_starts_and_stops_progress_around_the_block(self, mock_progress_cls):
        mock_progress = mock_progress_cls.return_value
        with step("Instalando pacotes..."):
            pass
        mock_progress.start.assert_called_once()
        mock_progress.add_task.assert_called_once_with("Instalando pacotes...", total=None)
        mock_progress.stop.assert_called_once()

    @patch("pvx.interactive.widgets.Progress")
    def test_elapsed_measures_the_block_duration(self, mock_progress_cls):
        with step("Instalando pacotes...") as s:
            time.sleep(0.05)
        self.assertGreaterEqual(s.elapsed, 0.05)

    @patch("pvx.interactive.widgets.theme.current_accent_color", return_value="#0087ff")
    @patch("pvx.interactive.widgets.Progress")
    def test_spinner_column_uses_theme_accent_color(self, mock_progress_cls, mock_accent):
        with step("x"):
            pass
        spinner_column = mock_progress_cls.call_args.args[0]
        self.assertEqual(spinner_column.spinner.style, "#0087ff")


class ElapsedColumnTest(unittest.TestCase):
    # rich.progress.TimeElapsedColumn mostra "0:05:02" (hora sem zero à
    # esquerda) -- formato fixo HH:MM:SS fica mais fácil de escanear.
    def test_pads_hours_minutes_and_seconds_to_two_digits(self):
        task = type("Task", (), {"finished": False, "elapsed": 3723, "finished_time": None})()
        self.assertEqual(_ElapsedColumn().render(task).plain, "01:02:03")

    def test_shows_placeholder_when_not_started_yet(self):
        task = type("Task", (), {"finished": False, "elapsed": None, "finished_time": None})()
        self.assertEqual(_ElapsedColumn().render(task).plain, "--:--:--")


class StepWithLogTest(unittest.TestCase):
    # como step(), mas com um rastro das últimas N linhas de saída em cinza embaixo do
    # spinner (docker-build-style) -- pra etapas longas onde "rodando..." mudo por
    # minutos não diz nada sobre o que tá de fato acontecendo.
    @patch("pvx.interactive.widgets.Live")
    def test_starts_and_stops_live_around_the_block(self, mock_live_cls):
        mock_live = mock_live_cls.return_value
        with step_with_log("Instalando pacotes..."):
            pass
        mock_live.__enter__.assert_called_once()
        mock_live.__exit__.assert_called_once()

    @patch("pvx.interactive.widgets.Live")
    def test_elapsed_measures_the_block_duration(self, mock_live_cls):
        with step_with_log("Instalando pacotes...") as s:
            time.sleep(0.02)
        self.assertGreaterEqual(s.elapsed, 0.02)

    @patch("pvx.interactive.widgets.Live")
    def test_feed_refreshes_the_live_display(self, mock_live_cls):
        mock_live = mock_live_cls.return_value
        with step_with_log("Instalando pacotes...") as s:
            s.feed("Preparing transaction...")
        mock_live.update.assert_called()

    @patch("pvx.interactive.widgets.Live")
    def test_tail_keeps_only_the_last_n_lines(self, mock_live_cls):
        with step_with_log("Instalando pacotes...", tail=3) as s:
            for i in range(5):
                s.feed(f"linha {i}")
        self.assertEqual(list(s._lines), ["linha 2", "linha 3", "linha 4"])


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


class CrashTest(unittest.TestCase):
    # catch global: exceção não tratada em qualquer comando (menu ou CLI
    # direta) mostra o traceback cru em vermelho em vez de deixar passar em
    # branco/preto igual qualquer outra saída -- precisa saltar aos olhos.
    @patch("pvx.interactive.widgets.Console")
    def test_prints_the_full_traceback_text(self, mock_console_cls):
        tb = "Traceback (most recent call last):\n  File ...\nValueError: boom"
        crash(tb)
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, tb)

    @patch("pvx.interactive.widgets.Console")
    def test_is_red(self, mock_console_cls):
        crash("boom")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.spans[0].style, "red")


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


class CheckResultTest(unittest.TestCase):
    # três níveis (não só ok/not-ok): usado onde uma checagem pode reprovar sem
    # bloquear o processo (ex.: RAM baixa no preflight do netinstall -- é aviso,
    # não erro) -- amarelo/símbolo próprio distingue isso de uma falha de verdade.
    @patch("pvx.interactive.widgets.Console")
    def test_ok_is_green_with_check_mark(self, mock_console_cls):
        check_result("root: ok", "ok")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "✓ root: ok")
        self.assertEqual(printed.spans[0].style, "bold green")

    @patch("pvx.interactive.widgets.Console")
    def test_warn_is_yellow_with_a_different_mark(self, mock_console_cls):
        check_result("RAM: atenção (768 MB)", "warn")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "! RAM: atenção (768 MB)")
        self.assertEqual(printed.spans[0].style, "bold yellow")

    @patch("pvx.interactive.widgets.Console")
    def test_error_is_red_with_the_failed_mark(self, mock_console_cls):
        check_result("instalação prévia: falha", "error")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "✗ instalação prévia: falha")
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
