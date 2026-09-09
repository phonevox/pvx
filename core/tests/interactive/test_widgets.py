import time
import unittest
from unittest.mock import call, patch

from pvx.interactive import theme, widgets
from pvx.interactive.widgets import (
    BANNER,
    banner,
    breadcrumb,
    check_result,
    checkbox_answer,
    clear,
    crash,
    description,
    failed,
    item,
    message,
    pause,
    print_module_list,
    section,
    select_answer,
    spinner,
    state,
    step,
    step_with_log,
    success,
    title,
    warning,
)
from pvx.interactive.widgets import _ElapsedColumn, _module_status_line


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


class ModuleStatusLineTest(unittest.TestCase):
    # achado ao vivo: status de módulo não é resultado de ação nenhuma --
    # check_result()/title() (rodada anterior) confundiam navegação com
    # conteúdo e gritavam "SUCESSO" sem ação nenhuma ter rodado. Bola
    # colorida no lugar do rótulo: verde = tudo certo (atualizado, à frente
    # do registry, ou só local -- nenhum desses é problema), amarela =
    # atualização disponível, cinza vazia = não instalado (versão "-").
    def test_up_to_date_gets_a_green_ball(self):
        row = {"name": "dummy", "installed_version": "1.0.0", "latest_version": "1.0.0", "status": "atualizado"}
        line = _module_status_line(row, name_width=10)
        self.assertTrue(line.plain.startswith("● dummy"))
        self.assertIn("1.0.0", line.plain)
        self.assertEqual(line.spans[0].style, theme.ACCENT_COLORS["verde"])

    def test_ahead_of_registry_also_gets_a_green_ball(self):
        row = {"name": "magnus", "installed_version": "1.2.0", "latest_version": "1.1.0", "status": "à frente do registry"}
        line = _module_status_line(row, name_width=10)
        self.assertEqual(line.spans[0].style, theme.ACCENT_COLORS["verde"])

    def test_local_module_also_gets_a_green_ball(self):
        row = {"name": "custom", "installed_version": "0.1.0", "latest_version": "-", "status": "local"}
        line = _module_status_line(row, name_width=10)
        self.assertEqual(line.spans[0].style, theme.ACCENT_COLORS["verde"])

    def test_update_available_gets_a_yellow_ball_and_shows_the_arrow(self):
        row = {"name": "ssl", "installed_version": "0.1.1", "latest_version": "0.1.2", "status": "atualização disponível"}
        line = _module_status_line(row, name_width=10)
        self.assertEqual(line.spans[0].style, theme.ACCENT_COLORS["amarelo"])
        self.assertIn("0.1.1", line.plain)
        self.assertIn("0.1.2", line.plain)
        self.assertIn("->", line.plain)

    def test_not_installed_gets_a_hollow_ball_and_a_dash_for_version(self):
        row = {"name": "zabbix", "installed_version": "-", "latest_version": "1.0.0", "status": "disponível"}
        line = _module_status_line(row, name_width=10)
        self.assertTrue(line.plain.startswith("○ zabbix"))
        self.assertTrue(line.plain.endswith("-"))
        self.assertNotIn("1.0.0", line.plain)


class PrintModuleListTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.Console")
    @patch("pvx.interactive.widgets.section")
    def test_shows_a_single_catalogo_section(self, mock_section, mock_console_cls):
        rows = [{"name": "dummy", "installed_version": "1.0.0", "latest_version": "1.0.0", "status": "atualizado"}]
        print_module_list(rows)
        mock_section.assert_called_once_with("Catálogo")

    @patch("pvx.interactive.widgets.Console")
    def test_prints_the_legend_a_blank_line_and_one_line_per_module(self, mock_console_cls):
        rows = [
            {"name": "a", "installed_version": "1.0.0", "latest_version": "1.0.0", "status": "atualizado"},
            {"name": "b", "installed_version": "-", "latest_version": "1.0.0", "status": "disponível"},
        ]
        print_module_list(rows)
        # section("Catálogo") + legenda + linha em branco + 2 módulos.
        self.assertEqual(mock_console_cls.return_value.print.call_count, 5)

    @patch("pvx.interactive.widgets.Console")
    def test_legend_mentions_all_three_states_in_one_line(self, mock_console_cls):
        print_module_list([])
        legend = mock_console_cls.return_value.print.call_args_list[1].args[0]
        self.assertIn("atualizado", legend.plain)
        self.assertIn("atualização disponível", legend.plain)
        self.assertIn("não instalado", legend.plain)
        self.assertEqual(legend.plain.count("\n"), 0)


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


class SelectAnswerTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.Console")
    def test_prints_qmark_message_and_chosen_title(self, mock_console_cls):
        select_answer("Type:", "PABX (Asterisk)")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "? Type: PABX (Asterisk)")

    @patch("pvx.interactive.widgets.Console")
    def test_shows_nenhum_when_title_is_none(self, mock_console_cls):
        select_answer("Type:", None)
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertTrue(printed.plain.endswith("nenhum"))


class CheckboxAnswerTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.Console")
    def test_prints_qmark_message_and_joined_selection(self, mock_console_cls):
        checkbox_answer("Selecione:", ["a", "b"])
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "? Selecione: a, b")

    @patch("pvx.interactive.widgets.Console")
    def test_shows_nenhum_when_selection_is_empty(self, mock_console_cls):
        checkbox_answer("Selecione:", [])
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertTrue(printed.plain.endswith("nenhum"))


class MessageTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.click.echo")
    def test_prints_text_surrounded_by_blank_lines(self, mock_echo):
        message("nenhum módulo instalado.")
        self.assertEqual(
            mock_echo.call_args_list,
            [call(), call("nenhum módulo instalado."), call()],
        )


class SuccessTest(unittest.TestCase):
    # formato default é "modern" ("[<simbolo>] <texto>") -- sem detail, cai no
    # fallback da categoria como texto.
    @patch("pvx.interactive.widgets.Console")
    def test_prints_category_alone_when_no_detail(self, mock_console_cls):
        success()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[✓] sucesso")

    @patch("pvx.interactive.widgets.Console")
    def test_detail_replaces_the_fallback_text(self, mock_console_cls):
        success("dummy instalado.")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[✓] dummy instalado.")

    @patch("pvx.interactive.widgets.Console")
    def test_symbol_is_bold_green(self, mock_console_cls):
        success()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.spans[0].style, "bold green")


class FailedTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.Console")
    def test_prints_category_alone_when_no_detail(self, mock_console_cls):
        failed()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[✗] erro")

    @patch("pvx.interactive.widgets.Console")
    def test_detail_replaces_the_fallback_text(self, mock_console_cls):
        failed("erro de rede.")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[✗] erro de rede.")

    @patch("pvx.interactive.widgets.Console")
    def test_symbol_is_bold_red(self, mock_console_cls):
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


_PADRAO_SYMBOLS = {"warning": "⚠", "section": "▸", "item": "•"}


class CheckResultTest(unittest.TestCase):
    # três níveis (não só ok/not-ok): usado onde uma checagem pode reprovar sem
    # bloquear o processo (ex.: RAM baixa no preflight do netinstall -- é aviso,
    # não erro) -- amarelo/símbolo próprio distingue isso de uma falha de verdade.
    # achado ao vivo: tinha layout fixo, alheio ao "formato" do tema -- agora
    # passa pelo mesmo _print_outcome de success/failed/warning.
    @patch("pvx.interactive.widgets.Console")
    def test_ok_is_green_with_check_mark(self, mock_console_cls):
        check_result("root: ok", "ok")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[✓] root: ok")
        self.assertEqual(printed.spans[0].style, "bold green")

    @patch("pvx.interactive.widgets.theme.current_symbols", return_value=_PADRAO_SYMBOLS)
    @patch("pvx.interactive.widgets.Console")
    def test_warn_uses_the_themed_warning_symbol(self, mock_console_cls, mock_symbols):
        check_result("RAM: atenção (768 MB)", "warn")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[⚠] RAM: atenção (768 MB)")
        self.assertEqual(printed.spans[0].style, "bold yellow")

    @patch("pvx.interactive.widgets.Console")
    def test_error_is_red_with_the_failed_mark(self, mock_console_cls):
        check_result("instalação prévia: falha", "error")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[✗] instalação prévia: falha")
        self.assertEqual(printed.spans[0].style, "bold red")


class WarningTest(unittest.TestCase):
    # reprova/alerta sem ser nem sucesso nem falha (ex.: IP da sessão sem
    # failsafe confirmado) -- terceiro estado visual ao lado de success()/failed().
    # símbolo vem do tema (SYMBOL_SETS) -- mockado aqui pro preset "padrão", que é
    # o default de config.get_symbol_set_name().
    @patch("pvx.interactive.widgets.theme.current_symbols", return_value=_PADRAO_SYMBOLS)
    @patch("pvx.interactive.widgets.Console")
    def test_prints_category_alone_when_no_detail(self, mock_console_cls, mock_symbols):
        warning()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[⚠] aviso")

    @patch("pvx.interactive.widgets.theme.current_symbols", return_value=_PADRAO_SYMBOLS)
    @patch("pvx.interactive.widgets.Console")
    def test_detail_replaces_the_fallback_text(self, mock_console_cls, mock_symbols):
        warning("rode `apply` de novo.")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "[⚠] rode `apply` de novo.")

    @patch("pvx.interactive.widgets.theme.current_symbols", return_value=_PADRAO_SYMBOLS)
    @patch("pvx.interactive.widgets.Console")
    def test_symbol_is_bold_yellow(self, mock_console_cls, mock_symbols):
        warning()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.spans[0].style, "bold yellow")


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

    @patch("pvx.interactive.widgets.theme.current_symbols", return_value=_PADRAO_SYMBOLS)
    def test_warning_also_aligns_with_success_and_failed(self, mock_symbols):
        with patch("pvx.interactive.widgets.Console") as mock_console_cls:
            warning("x")
            warning_line = mock_console_cls.return_value.print.call_args.args[0].plain
        with patch("pvx.interactive.widgets.Console") as mock_console_cls:
            failed("x")
            failed_line = mock_console_cls.return_value.print.call_args.args[0].plain

        self.assertEqual(warning_line.index("x"), failed_line.index("x"))


class TitleTest(unittest.TestCase):
    # título de tela com moldura -- caractere vem do tema (BORDERS), texto
    # centralizado em negrito, tudo na cor de destaque do tema.
    @patch("pvx.interactive.widgets.theme.current_border_char", return_value="═")
    @patch("pvx.interactive.widgets.theme.current_accent_color", return_value="#0087ff")
    @patch("pvx.interactive.widgets.Console")
    def test_prints_bar_centered_text_and_bar_in_accent_color(self, mock_console_cls, mock_accent, mock_format):
        title("pvx > firewall > check")
        calls = mock_console_cls.return_value.print.call_args_list
        self.assertEqual(len(calls), 3)

        top, middle, bottom = (call.args[0] for call in calls)
        self.assertEqual(top.plain, bottom.plain)
        self.assertEqual(top.spans[0].style, "#0087ff")
        self.assertEqual(bottom.spans[0].style, "#0087ff")
        self.assertIn("pvx > firewall > check", middle.plain)
        self.assertEqual(middle.spans[0].style, "bold #0087ff")


class SectionTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.theme.current_symbols", return_value=_PADRAO_SYMBOLS)
    @patch("pvx.interactive.widgets.theme.current_accent_color", return_value="#0087ff")
    @patch("pvx.interactive.widgets.Console")
    def test_prints_marker_and_text_bold_in_accent_color(self, mock_console_cls, mock_accent, mock_symbols):
        section("IPs confiáveis")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "▸ IPs confiáveis")
        self.assertEqual(printed.spans[0].style, "bold #0087ff")


class DescriptionTest(unittest.TestCase):
    def test_prints_indented_dim_text(self, ):
        with patch("pvx.interactive.widgets.Console") as mock_console_cls:
            description("Lista de IPs com acesso total.")
            printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "  Lista de IPs com acesso total.")
        self.assertEqual(printed.spans[0].style, theme.SEPARATOR_COLOR)

    def test_accepts_a_custom_color(self):
        with patch("pvx.interactive.widgets.Console") as mock_console_cls:
            description("atualizado", color="bold green")
            printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.spans[0].style, "bold green")


class ItemTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.theme.current_symbols", return_value=_PADRAO_SYMBOLS)
    @patch("pvx.interactive.widgets.theme.current_accent_color", return_value="#0087ff")
    @patch("pvx.interactive.widgets.Console")
    def test_prints_bullet_in_accent_color_and_plain_text(self, mock_console_cls, mock_accent, mock_symbols):
        item("189.124.85.75")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "  • 189.124.85.75")
        self.assertEqual(printed.spans[0].style, "#0087ff")

    @patch("pvx.interactive.widgets.theme.current_symbols", return_value=_PADRAO_SYMBOLS)
    @patch("pvx.interactive.widgets.theme.current_accent_color", return_value="#0087ff")
    @patch("pvx.interactive.widgets.Console")
    def test_appends_dim_comment_when_given(self, mock_console_cls, mock_accent, mock_symbols):
        item("189.124.85.75", comment="PHONEVOX PRINCIPAL")
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "  • 189.124.85.75  # PHONEVOX PRINCIPAL")


class PreviewOutcomeLineTest(unittest.TestCase):
    # preview_outcome_line() é o texto plano usado no on-hover de "pvx > tema >
    # formato" -- um teste por preset, sem depender do tema atual (símbolo e
    # categoria passados direto).
    def test_verbose_keeps_the_exclamation_label(self):
        self.assertEqual(widgets.preview_outcome_line("verbose", "✓", "sucesso"), "✓ sucesso!")
        self.assertEqual(widgets.preview_outcome_line("verbose", "✓", "sucesso", "ok"), "✓ sucesso! ok")

    def test_verbose_v2_drops_the_exclamation_and_brackets_the_symbol(self):
        self.assertEqual(widgets.preview_outcome_line("verbose-v2", "✓", "sucesso"), "[✓] sucesso")
        self.assertEqual(widgets.preview_outcome_line("verbose-v2", "✓", "sucesso", "ok"), "[✓] sucesso ok")

    def test_verbose_v2_full_color_has_the_same_text_as_v2(self):
        self.assertEqual(
            widgets.preview_outcome_line("verbose-v2-full-color", "✓", "sucesso", "ok"),
            widgets.preview_outcome_line("verbose-v2", "✓", "sucesso", "ok"),
        )

    def test_minimal_is_the_uppercase_category_with_no_symbol(self):
        self.assertEqual(widgets.preview_outcome_line("minimal", "✓", "sucesso"), "SUCESSO")
        self.assertEqual(widgets.preview_outcome_line("minimal", "✓", "sucesso", "ok"), "SUCESSO ok")

    def test_ultra_minimal_is_symbol_plus_category_fallback(self):
        self.assertEqual(widgets.preview_outcome_line("ultra-minimal", "✓", "sucesso"), "✓ sucesso")
        self.assertEqual(widgets.preview_outcome_line("ultra-minimal", "✓", "sucesso", "ok"), "✓ ok")

    def test_modern_is_bracketed_symbol_plus_category_fallback(self):
        self.assertEqual(widgets.preview_outcome_line("modern", "✓", "sucesso"), "[✓] sucesso")
        self.assertEqual(widgets.preview_outcome_line("modern", "✓", "sucesso", "ok"), "[✓] ok")

    def test_modern_colored_brackets_has_the_same_text_as_modern(self):
        self.assertEqual(
            widgets.preview_outcome_line("modern-colored-brackets", "✓", "sucesso", "ok"),
            widgets.preview_outcome_line("modern", "✓", "sucesso", "ok"),
        )

    def test_modern_full_color_has_the_same_text_as_modern(self):
        self.assertEqual(
            widgets.preview_outcome_line("modern-full-color", "✓", "sucesso", "ok"),
            widgets.preview_outcome_line("modern", "✓", "sucesso", "ok"),
        )

    def test_unknown_format_falls_back_to_modern(self):
        self.assertEqual(
            widgets.preview_outcome_line("isso-nao-existe", "✓", "sucesso"),
            widgets.preview_outcome_line("modern", "✓", "sucesso"),
        )


class LineFormatColorSpanTest(unittest.TestCase):
    # os "-full-color"/"-colored-brackets" existem só pra mudar QUANTO da linha
    # é colorido -- o texto já é coberto pelo teste de cima, aqui confere só o
    # span de estilo.
    def test_verbose_v2_colors_only_the_prefix_not_the_detail(self):
        line = widgets._LINE_BUILDERS["verbose-v2"]("✓", "sucesso", "bold green", "ok")
        self.assertEqual(line.spans[0].style, "bold green")
        self.assertNotEqual(line.plain[line.spans[0].end:].strip(), "")

    def test_verbose_v2_full_color_colors_the_whole_line(self):
        line = widgets._LINE_BUILDERS["verbose-v2-full-color"]("✓", "sucesso", "bold green", "ok")
        self.assertEqual(len(line.spans), 1)
        self.assertEqual(line.spans[0].end - line.spans[0].start, len(line.plain))

    def test_modern_colors_only_the_symbol(self):
        line = widgets._LINE_BUILDERS["modern"]("✓", "sucesso", "bold green", None)
        self.assertEqual(line.plain[line.spans[0].start:line.spans[0].end], "✓")

    def test_modern_colored_brackets_colors_symbol_and_brackets(self):
        line = widgets._LINE_BUILDERS["modern-colored-brackets"]("✓", "sucesso", "bold green", None)
        self.assertEqual(line.plain[line.spans[0].start:line.spans[0].end], "[✓]")

    def test_modern_full_color_colors_the_whole_line(self):
        line = widgets._LINE_BUILDERS["modern-full-color"]("✓", "sucesso", "bold green", "ok")
        self.assertEqual(len(line.spans), 1)
        self.assertEqual(line.spans[0].end - line.spans[0].start, len(line.plain))

    def test_minimal_colors_only_the_category(self):
        line = widgets._LINE_BUILDERS["minimal"]("✓", "sucesso", "bold green", "ok")
        self.assertEqual(line.plain[line.spans[0].start:line.spans[0].end], "SUCESSO")


class PrintOutcomeUsesConfiguredFormatTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.theme.current_line_format", return_value="verbose")
    @patch("pvx.interactive.widgets.Console")
    def test_success_respects_the_configured_line_format(self, mock_console_cls, mock_format):
        success()
        printed = mock_console_cls.return_value.print.call_args.args[0]
        self.assertEqual(printed.plain, "✓ sucesso!")


if __name__ == "__main__":
    unittest.main()
