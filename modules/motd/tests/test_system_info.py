import unittest
from unittest.mock import mock_open, patch

import system_info

PROC_STAT_1 = "cpu  100 0 50 800 20 0 0 0 0 0\n"
PROC_STAT_2 = "cpu  120 0 60 880 30 0 0 0 0 0\n"

PROC_LOADAVG = "1.54 1.06 0.80 2/512 12345\n"

PROC_MEMINFO = (
    "MemTotal:       16384000 kB\n"
    "MemFree:         5000000 kB\n"
    "MemAvailable:   10000000 kB\n"
    "SwapTotal:       2048000 kB\n"
    "SwapFree:        2048000 kB\n"
)

PROC_UPTIME = "125042.30 987654.32\n"

OS_RELEASE = 'NAME="Rocky Linux"\nPRETTY_NAME="Rocky Linux 8.10 (Green Obsidian)"\n'


class CpuUsagePercentTest(unittest.TestCase):
    def test_computes_percent_from_the_delta_between_two_samples(self):
        with patch(
            "system_info.open",
            side_effect=[mock_open(read_data=PROC_STAT_1).return_value, mock_open(read_data=PROC_STAT_2).return_value],
        ), patch("system_info.time.sleep") as mock_sleep:
            percent = system_info.cpu_usage_percent(interval=0.1)
        mock_sleep.assert_called_once_with(0.1)
        # idle1 = 800+20 = 820, total1 = 970 ; idle2 = 880+30 = 910, total2 = 1090
        # delta idle = 90, delta total = 120 -> uso = (1 - 90/120) * 100 = 25%
        self.assertAlmostEqual(percent, 25.0, places=1)

    def test_never_divides_by_zero_when_the_sample_is_degenerate(self):
        with patch(
            "system_info.open",
            side_effect=[mock_open(read_data=PROC_STAT_1).return_value, mock_open(read_data=PROC_STAT_1).return_value],
        ), patch("system_info.time.sleep"):
            percent = system_info.cpu_usage_percent()
        self.assertEqual(percent, 0.0)


class LoadAverageTest(unittest.TestCase):
    def test_parses_the_three_load_values(self):
        with patch("system_info.open", mock_open(read_data=PROC_LOADAVG)):
            self.assertEqual(system_info.load_average(), (1.54, 1.06, 0.80))


class MemoryUsageTest(unittest.TestCase):
    def test_computes_ram_and_swap_percent(self):
        with patch("system_info.open", mock_open(read_data=PROC_MEMINFO)):
            info = system_info.memory_usage()
        self.assertEqual(info["ram_total_mb"], 16384000 // 1024)
        self.assertAlmostEqual(info["ram_percent"], (1 - 10000000 / 16384000) * 100, places=1)
        self.assertEqual(info["swap_percent"], 0.0)


class DiskUsageTest(unittest.TestCase):
    def test_computes_percent_used_and_human_sizes(self):
        with patch("system_info.shutil.disk_usage", return_value=(100 * 2**30, 42 * 2**30, 58 * 2**30)):
            info = system_info.disk_usage("/")
        self.assertEqual(info["percent"], 42.0)
        self.assertEqual(info["used_gb"], 42.0)
        self.assertEqual(info["total_gb"], 100.0)


class UptimeHumanTest(unittest.TestCase):
    def test_formats_days_hours_minutes(self):
        with patch("system_info.open", mock_open(read_data=PROC_UPTIME)):
            self.assertEqual(system_info.uptime_human(), "up 1 dia, 10 horas, 44 minutos")

    def test_formats_minutes_only_when_under_an_hour(self):
        with patch("system_info.open", mock_open(read_data="125.0 0\n")):
            self.assertEqual(system_info.uptime_human(), "up 2 minutos")

    def test_shows_zero_minutes_instead_of_nothing(self):
        with patch("system_info.open", mock_open(read_data="10.0 0\n")):
            self.assertEqual(system_info.uptime_human(), "up 0 minutos")


class HostnameTest(unittest.TestCase):
    def test_returns_the_socket_hostname(self):
        with patch("system_info.socket.gethostname", return_value="vps-c645d1bd"):
            self.assertEqual(system_info.hostname(), "vps-c645d1bd")


class MachineIdTest(unittest.TestCase):
    def test_reads_and_strips_machine_id(self):
        with patch("system_info.open", mock_open(read_data="85f2f39884ec462091a9b6ceb865b659\n")):
            self.assertEqual(system_info.machine_id(), "85f2f39884ec462091a9b6ceb865b659")

    def test_none_when_unreadable(self):
        with patch("system_info.open", side_effect=OSError):
            self.assertIsNone(system_info.machine_id())


class OsPrettyNameTest(unittest.TestCase):
    def test_extracts_pretty_name_from_os_release(self):
        with patch("system_info.open", mock_open(read_data=OS_RELEASE)):
            self.assertEqual(system_info.os_pretty_name(), "Rocky Linux 8.10 (Green Obsidian)")

    def test_none_when_unreadable(self):
        with patch("system_info.open", side_effect=OSError):
            self.assertIsNone(system_info.os_pretty_name())


class IpAddressesTest(unittest.TestCase):
    def test_splits_the_hostname_dash_i_output(self):
        with patch("system_info.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "51.79.70.39 10.0.0.5 \n"
            self.assertEqual(system_info.ip_addresses(), ["51.79.70.39", "10.0.0.5"])

    def test_empty_list_when_the_command_is_unavailable(self):
        with patch("system_info.subprocess.run", side_effect=OSError):
            self.assertEqual(system_info.ip_addresses(), [])


class OpenSessionsTest(unittest.TestCase):
    def test_counts_who_lines(self):
        with patch("system_info.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "phonevox pts/0\nphonevox pts/1\n"
            self.assertEqual(system_info.open_sessions(), 2)

    def test_zero_when_the_command_is_unavailable(self):
        with patch("system_info.subprocess.run", side_effect=OSError):
            self.assertEqual(system_info.open_sessions(), 0)


class TimezoneNameTest(unittest.TestCase):
    def test_reads_the_localtime_symlink_target(self):
        with patch("system_info.os.readlink", return_value="/usr/share/zoneinfo/America/Sao_Paulo"):
            self.assertEqual(system_info.timezone_name(), "America/Sao_Paulo")

    def test_falls_back_to_timedatectl_when_no_symlink(self):
        with patch("system_info.os.readlink", side_effect=OSError), \
             patch("system_info.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "America/Sao_Paulo\n"
            self.assertEqual(system_info.timezone_name(), "America/Sao_Paulo")

    def test_none_when_nothing_works(self):
        with patch("system_info.os.readlink", side_effect=OSError), \
             patch("system_info.subprocess.run", side_effect=OSError):
            self.assertIsNone(system_info.timezone_name())


if __name__ == "__main__":
    unittest.main()
