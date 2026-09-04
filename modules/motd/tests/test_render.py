import unittest

import render


class BarColorTest(unittest.TestCase):
    def test_green_below_every_threshold(self):
        self.assertEqual(render.bar_color(10), "green")

    def test_yellow_at_the_middle_threshold(self):
        self.assertEqual(render.bar_color(85), "yellow")

    def test_red_at_the_top_threshold(self):
        self.assertEqual(render.bar_color(95), "red")

    def test_boundary_values_use_the_higher_threshold(self):
        self.assertEqual(render.bar_color(80), "yellow")
        self.assertEqual(render.bar_color(90), "red")


class RenderBarTest(unittest.TestCase):
    def test_full_width_filled_at_100_percent(self):
        bar = render.render_bar(100, width=10)
        self.assertIn("#" * 10, bar)
        self.assertNotIn("-", bar)
        self.assertIn("100%", bar)

    def test_half_filled_at_50_percent(self):
        bar = render.render_bar(50, width=10)
        self.assertIn("#" * 5, bar)
        self.assertIn("-" * 5, bar)
        self.assertIn("50%", bar)

    def test_clamps_values_outside_0_100(self):
        self.assertIn("0%", render.render_bar(-5, width=10))
        self.assertIn("100%", render.render_bar(150, width=10))

    def test_uses_the_color_matching_the_percent(self):
        bar = render.render_bar(95, width=10)
        self.assertIn("[red]", bar)

    def test_percent_is_padded_so_trailing_text_lines_up(self):
        # achado ao vivo: "0%" (1 char) e "52%" (2 chars) faziam o "|" que
        # vem depois cair em colunas diferentes entre CPU/RAM/Disk. cor fixa
        # aqui pra isolar só o efeito do padding do número (a cor por si só
        # já teria comprimentos diferentes: "green" vs "red").
        one_digit = render.render_bar(0, width=10, color="green")
        two_digits = render.render_bar(52, width=10, color="green")
        three_digits = render.render_bar(100, width=10, color="green")
        suffix_position = len(one_digit.split("%")[0])
        self.assertEqual(suffix_position, len(two_digits.split("%")[0]))
        self.assertEqual(suffix_position, len(three_digits.split("%")[0]))

    def test_explicit_color_overrides_the_percent_based_one(self):
        bar = render.render_bar(5, width=10, color="red")
        self.assertIn("[red]", bar)
        self.assertNotIn("[green]", bar)


class HumanSizeTest(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(render.human_size(500), "500B")

    def test_kilobytes(self):
        self.assertEqual(render.human_size(2048), "2.0K")

    def test_megabytes(self):
        self.assertEqual(render.human_size(880 * 1024 * 1024), "880.0M")

    def test_gigabytes(self):
        self.assertEqual(render.human_size(4.6 * 1024**3), "4.6G")


class SizeColorTest(unittest.TestCase):
    def test_green_under_1gb(self):
        self.assertEqual(render.size_color(500 * 1024**2), "green")

    def test_yellow_from_1gb(self):
        self.assertEqual(render.size_color(1024**3), "yellow")

    def test_red_from_5gb(self):
        self.assertEqual(render.size_color(5 * 1024**3), "red")


class BarWithSizeTest(unittest.TestCase):
    def test_shows_bar_and_human_size_together(self):
        result = render.bar_with_size(4.6, 880 * 1024 * 1024)
        self.assertIn("5%", result)  # 4.6 arredondado
        self.assertIn("880.0M", result)

    def test_color_reflects_absolute_size_not_the_percent(self):
        # 0.1% de um disco gigante ainda pode ser 6GB de gravação -- a cor
        # tem que vir do tamanho absoluto, não do %.
        result = render.bar_with_size(0.1, 6 * 1024**3)
        self.assertIn("[red]", result)

    def test_na_when_percent_is_unknown(self):
        self.assertEqual(render.bar_with_size(None, 1000), "N/A")

    def test_na_when_bytes_are_unknown(self):
        self.assertEqual(render.bar_with_size(5.0, None), "N/A")


class LineAlignmentTest(unittest.TestCase):
    def test_all_health_lines_put_the_colon_at_the_same_column(self):
        # achado ao vivo: rótulos de tamanhos diferentes caindo em colunas
        # diferentes -- todo rótulo do health panel usa o mesmo padding.
        lines = [
            render.daemon_line("asterisk", {"installed": True, "running": True}),
            render.autobackup_line(None),
        ]
        colon_positions = {line.index(":") for line in lines}
        self.assertEqual(len(colon_positions), 1)


class DaemonLineTest(unittest.TestCase):
    def test_online_when_installed_and_running(self):
        line = render.daemon_line("asterisk", {"installed": True, "running": True})
        self.assertIn("online", line)
        self.assertIn("[green]", line)

    def test_offline_when_installed_but_not_running(self):
        line = render.daemon_line("asterisk", {"installed": True, "running": False})
        self.assertIn("offline", line)
        self.assertIn("[red]", line)

    def test_not_available_when_not_installed(self):
        line = render.daemon_line("mariadb", {"installed": False, "running": False})
        self.assertIn("not available", line)
        self.assertIn("[yellow]", line)


class AutobackupLineTest(unittest.TestCase):
    def test_configured(self):
        line = render.autobackup_line({
            "username": "empresa", "script": "issabel", "cron_minute": "25", "cron_hour": "2",
        })
        self.assertIn("empresa", line)
        self.assertIn("2:25", line)
        self.assertIn("[green]", line)

    def test_not_configured(self):
        line = render.autobackup_line(None)
        self.assertIn("não configurado", line)
        self.assertIn("[yellow]", line)


class BuildBannerTest(unittest.TestCase):
    BASE_DATA = {
        "hostname": "vps-c645d1bd",
        "os_pretty_name": "Rocky Linux 8.10 (Green Obsidian)",
        "machine_id": "85f2f39884ec462091a9b6ceb865b659",
        "ips": ["51.79.70.39"],
        "open_sessions": 2,
        "server_date": "2026-09-04 08:59:18",
        "timezone": "America/Sao_Paulo",
        "uptime": "up 18 minutos",
        "load_average": (1.54, 1.06, 0.80),
        "cpu_percent": 18.0,
        "ram_percent": 33.0,
        "swap_percent": 0.0,
        "disk_percent": 42.0,
        "disk_used_gb": 8.0,
        "disk_total_gb": 19.0,
        "asterisk": {"installed": True, "running": True},
        "mariadb": {"installed": True, "running": True},
        "asterisk_details": None,
        "autobackup": {"username": "empresa", "script": "issabel", "cron_minute": "25", "cron_hour": "2"},
    }

    def _rendered_text(self, data):
        return render.render_to_text(render.build_banner(data), width=120)

    def test_includes_the_core_system_facts(self):
        text = self._rendered_text(self.BASE_DATA)
        self.assertIn("vps-c645d1bd", text)
        self.assertIn("Rocky Linux 8.10", text)
        self.assertIn("America/Sao_Paulo", text)

    def test_includes_the_phonevox_header(self):
        text = self._rendered_text(self.BASE_DATA)
        self.assertIn("PHONEVOX GROUP TECHNOLOGY", text)
        self.assertIn("phonevox.com", text)
        self.assertIn("suporte@phonevox.com.br", text)

    def test_uptime_gets_its_own_row_instead_of_wrapping_the_cpu_line(self):
        # achado ao vivo: uptime colado na linha do CPU quebrava no meio
        # ("... up 1 dia, 17 horas, 49" numa linha, "minutos" na próxima).
        data = dict(self.BASE_DATA, uptime="up 1 dia, 17 horas, 49 minutos")
        text = self._rendered_text(data)
        cpu_line = next(line for line in text.splitlines() if "CPU" in line)
        self.assertNotIn("up 1 dia", cpu_line)
        self.assertIn("up 1 dia, 17 horas, 49 minutos", text)

    def test_asterisk_section_omitted_when_not_installed(self):
        data = dict(self.BASE_DATA, asterisk={"installed": False, "running": False}, asterisk_details=None)
        text = self._rendered_text(data)
        self.assertNotIn("Active Calls", text)

    def test_asterisk_section_shows_bars_with_size_for_recordings_logs_and_dialer(self):
        data = dict(self.BASE_DATA, asterisk_details={
            "version": "Asterisk 18.20.1", "active_calls": 1,
            "recordings_percent": 4.6, "recordings_bytes": 880 * 1024 * 1024,
            "logs_percent": 0.1, "logs_bytes": 1500 * 1024,
            "dialer_percent": None, "dialer_bytes": None,
        })
        text = self._rendered_text(data)
        self.assertIn("Asterisk 18.20.1", text)
        self.assertIn("5%", text)  # 4.6 arredondado
        self.assertIn("880.0M", text)
        self.assertIn("N/A", text)  # dialer indisponível

    def test_no_issabel_panel_anymore(self):
        text = self._rendered_text(self.BASE_DATA)
        self.assertNotIn("issabel", text.lower())

    def test_no_services_panel_anymore(self):
        # asterisk/mariadb migraram pro health -- não existe mais um painel
        # "services" separado.
        text = self._rendered_text(self.BASE_DATA)
        self.assertNotIn("╭─ services", text)

    def test_health_panel_includes_installed_daemons(self):
        text = self._rendered_text(self.BASE_DATA)
        self.assertIn("health", text.lower())
        self.assertIn("asterisk", text)
        self.assertIn("mariadb", text)
        self.assertIn("empresa", text)

    def test_health_panel_omits_asterisk_when_not_installed(self):
        data = dict(self.BASE_DATA, asterisk={"installed": False, "running": False}, asterisk_details=None)
        text = self._rendered_text(data)
        health_section = text[text.lower().index("health"):]
        self.assertNotIn("asterisk", health_section)

    def test_health_panel_omits_mariadb_when_not_installed(self):
        data = dict(self.BASE_DATA, mariadb={"installed": False, "running": False})
        text = self._rendered_text(data)
        health_section = text[text.lower().index("health"):]
        self.assertNotIn("mariadb", health_section)

    def test_panels_stack_vertically(self):
        # pedido ao vivo: nada de lado a lado -- um embaixo do outro.
        text = self._rendered_text(self.BASE_DATA)
        system_line = next(line for line in text.splitlines() if "system" in line)
        self.assertNotIn("health", system_line)

    def test_panels_share_the_same_width(self):
        # pedido ao vivo: limite de largura no tamanho do "system", pra não
        # ficar caixa desencontrada empilhada.
        text = self._rendered_text(self.BASE_DATA)
        top_borders = [line for line in text.splitlines() if line.startswith("╭")]
        widths = {len(line) for line in top_borders}
        self.assertEqual(len(widths), 1)


if __name__ == "__main__":
    unittest.main()
