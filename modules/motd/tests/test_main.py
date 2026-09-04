import unittest
from unittest.mock import patch

from click.testing import CliRunner

from main import cli, gather_data


class GatherDataTest(unittest.TestCase):
    def _patched(self, **overrides):
        defaults = dict(
            disk_usage={"percent": 42.0, "used_gb": 8.0, "total_gb": 19.0},
            memory_usage={"ram_percent": 33.0, "ram_total_mb": 16000, "swap_percent": 0.0},
            load_average=(1.54, 1.06, 0.80),
            cpu_usage_percent=18.0,
            uptime_human="up 18 minutos",
            hostname="vps-c645d1bd",
            machine_id="85f2f39884ec462091a9b6ceb865b659",
            os_pretty_name="Rocky Linux 8.10 (Green Obsidian)",
            ip_addresses=["51.79.70.39"],
            open_sessions=2,
            timezone_name="America/Sao_Paulo",
            daemon_status={"installed": True, "running": True},
            find_spooldir=None,
            find_logdir=None,
            version="Asterisk 18.20.1",
            active_calls=1,
            storage_percent=0.1,
            storage_bytes=1500 * 1024,
            recordings_percent=4.6,
            recordings_bytes=880 * 1024 * 1024,
            dialer_percent=0.1,
            dialer_bytes=1024 * 1024,
            autobackup_status={"username": "empresa", "script": "issabel", "cron_minute": "25", "cron_hour": "2"},
        )
        defaults.update(overrides)
        return (
            patch("main.system_info.disk_usage", return_value=defaults["disk_usage"]),
            patch("main.system_info.memory_usage", return_value=defaults["memory_usage"]),
            patch("main.system_info.load_average", return_value=defaults["load_average"]),
            patch("main.system_info.cpu_usage_percent", return_value=defaults["cpu_usage_percent"]),
            patch("main.system_info.uptime_human", return_value=defaults["uptime_human"]),
            patch("main.system_info.hostname", return_value=defaults["hostname"]),
            patch("main.system_info.machine_id", return_value=defaults["machine_id"]),
            patch("main.system_info.os_pretty_name", return_value=defaults["os_pretty_name"]),
            patch("main.system_info.ip_addresses", return_value=defaults["ip_addresses"]),
            patch("main.system_info.open_sessions", return_value=defaults["open_sessions"]),
            patch("main.system_info.timezone_name", return_value=defaults["timezone_name"]),
            patch("main.services.daemon_status", return_value=defaults["daemon_status"]),
            patch("main.issabel_info.find_spooldir", return_value=defaults["find_spooldir"]),
            patch("main.asterisk_info.find_logdir", return_value=defaults["find_logdir"]),
            patch("main.asterisk_info.version", return_value=defaults["version"]),
            patch("main.asterisk_info.active_calls", return_value=defaults["active_calls"]),
            patch("main.issabel_info.storage_percent", return_value=defaults["storage_percent"]),
            patch("main.issabel_info.storage_bytes", return_value=defaults["storage_bytes"]),
            patch("main.issabel_info.recordings_percent", return_value=defaults["recordings_percent"]),
            patch("main.issabel_info.recordings_bytes", return_value=defaults["recordings_bytes"]),
            patch("main.issabel_info.dialer_percent", return_value=defaults["dialer_percent"]),
            patch("main.issabel_info.dialer_bytes", return_value=defaults["dialer_bytes"]),
            patch("main.autobackup_info.status", return_value=defaults["autobackup_status"]),
        )

    def _run(self, **overrides):
        patches = self._patched(**overrides)
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return gather_data()

    def test_includes_the_basic_system_facts(self):
        data = self._run()
        self.assertEqual(data["hostname"], "vps-c645d1bd")
        self.assertEqual(data["cpu_percent"], 18.0)
        self.assertEqual(data["ram_percent"], 33.0)
        self.assertEqual(data["disk_percent"], 42.0)

    def test_asterisk_details_omitted_when_asterisk_is_not_installed(self):
        data = self._run(daemon_status={"installed": False, "running": False})
        self.assertIsNone(data["asterisk_details"])

    def test_asterisk_details_present_when_asterisk_is_installed(self):
        data = self._run()
        self.assertIsNotNone(data["asterisk_details"])
        self.assertEqual(data["asterisk_details"]["version"], "Asterisk 18.20.1")
        self.assertEqual(data["asterisk_details"]["recordings_percent"], 4.6)
        self.assertEqual(data["asterisk_details"]["recordings_bytes"], 880 * 1024 * 1024)
        self.assertEqual(data["asterisk_details"]["dialer_percent"], 0.1)
        self.assertEqual(data["asterisk_details"]["dialer_bytes"], 1024 * 1024)

    def test_asterisk_logs_uses_the_found_logdir(self):
        data = self._run(find_logdir="/var/log/asterisk", storage_percent=1.2, storage_bytes=999)
        self.assertEqual(data["asterisk_details"]["logs_percent"], 1.2)
        self.assertEqual(data["asterisk_details"]["logs_bytes"], 999)

    def test_asterisk_logs_none_without_a_logdir(self):
        data = self._run(find_logdir=None)
        self.assertIsNone(data["asterisk_details"]["logs_percent"])
        self.assertIsNone(data["asterisk_details"]["logs_bytes"])

    def test_includes_the_health_facts(self):
        data = self._run()
        self.assertEqual(data["autobackup"]["username"], "empresa")


class BuildingCliGroupTest(unittest.TestCase):
    def test_building_the_cli_group_alone_does_not_touch_the_logger(self):
        with patch("main.MotdModule.get_logger") as mock_logger:
            cli.cli_group()
        mock_logger.assert_not_called()


class ShowCommandTest(unittest.TestCase):
    def test_renders_and_prints_the_banner(self):
        with patch("main.gather_data", return_value={"fake": "data"}) as mock_gather, \
             patch("main.render.build_banner", return_value="banner") as mock_build, \
             patch("main.Console") as mock_console_cls:
            result = CliRunner().invoke(cli.cli_group(), ["show"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_gather.assert_called_once()
        mock_build.assert_called_once_with({"fake": "data"})
        mock_console_cls.return_value.print.assert_called_once_with("banner")

    def test_pauses_after_showing(self):
        # widgets.pause() já se protege sozinho via sys.argv (nunca pausa em
        # CLI direta -- ver widgets.py) -- chamar sem gate aqui é o certo, é
        # o que deixa a barra visível ao navegar até "motd > show" no menu
        # interativo, sem sumir imediatamente com o redraw do auto-menu.
        with patch("main.gather_data", return_value={}), \
             patch("main.render.build_banner", return_value="banner"), \
             patch("main.Console"), \
             patch("main.widgets.pause") as mock_pause:
            CliRunner().invoke(cli.cli_group(), ["show"])
        mock_pause.assert_called_once_with()

    def test_never_touches_the_logger(self):
        with patch("main.gather_data", return_value={}), \
             patch("main.render.build_banner", return_value="banner"), \
             patch("main.Console"), \
             patch("main.MotdModule.get_logger") as mock_logger:
            CliRunner().invoke(cli.cli_group(), ["show"])
        mock_logger.assert_not_called()


class InstallCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False, confirm=True, result=None):
        result = result or {"backup_dir": None, "backed_up": []}
        with patch("main._is_interactive", return_value=is_tty), \
             patch("main.ask_confirm", return_value=confirm), \
             patch("main.profile_hook.install", return_value=result) as mock_install, \
             patch("main.MotdModule.get_logger"), \
             patch("main.widgets.pause") as mock_pause:
            cli_result = CliRunner().invoke(cli.cli_group(), args)
            return cli_result, mock_install, mock_pause

    def test_yes_flag_installs_without_asking(self):
        result, mock_install, _ = self._invoke(["install", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_install.assert_called_once()

    def test_headless_without_yes_is_an_error(self):
        with patch("main.profile_hook.install") as mock_install:
            result = CliRunner().invoke(cli.cli_group(), ["install"])
        self.assertNotEqual(result.exit_code, 0)
        mock_install.assert_not_called()

    def test_interactive_confirms_before_installing(self):
        result, mock_install, mock_pause = self._invoke(["install"], is_tty=True, confirm=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_install.assert_called_once()
        mock_pause.assert_called_once_with()

    def test_interactive_declining_does_not_install(self):
        result, mock_install, _ = self._invoke(["install"], is_tty=True, confirm=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_install.assert_not_called()

    def test_does_not_pause_when_not_interactive(self):
        _, _, mock_pause = self._invoke(["install", "--yes"], is_tty=False)
        mock_pause.assert_not_called()


class UninstallCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False, confirm=True, already_installed=True):
        with patch("main._is_interactive", return_value=is_tty), \
             patch("main.ask_confirm", return_value=confirm), \
             patch("main.profile_hook.is_installed", return_value=already_installed), \
             patch("main.profile_hook.uninstall") as mock_uninstall, \
             patch("main.MotdModule.get_logger"), \
             patch("main.widgets.pause") as mock_pause:
            cli_result = CliRunner().invoke(cli.cli_group(), args)
            return cli_result, mock_uninstall, mock_pause

    def test_nothing_to_do_when_not_installed(self):
        result, mock_uninstall, _ = self._invoke(["uninstall", "--yes"], already_installed=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_uninstall.assert_not_called()

    def test_yes_flag_removes_without_asking(self):
        result, mock_uninstall, _ = self._invoke(["uninstall", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_uninstall.assert_called_once()

    def test_headless_without_yes_is_an_error(self):
        with patch("main.profile_hook.is_installed", return_value=True), \
             patch("main.profile_hook.uninstall") as mock_uninstall:
            result = CliRunner().invoke(cli.cli_group(), ["uninstall"])
        self.assertNotEqual(result.exit_code, 0)
        mock_uninstall.assert_not_called()

    def test_interactive_declining_does_not_remove(self):
        result, mock_uninstall, _ = self._invoke(["uninstall"], is_tty=True, confirm=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_uninstall.assert_not_called()


if __name__ == "__main__":
    unittest.main()
