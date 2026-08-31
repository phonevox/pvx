import unittest
from unittest.mock import MagicMock, patch

import install_steps


class RepoRpmUrlTest(unittest.TestCase):
    def test_builds_url_from_version_and_os_major(self):
        url = install_steps.repo_rpm_url("5.0", "8")
        self.assertEqual(
            url, "https://repo.zabbix.com/zabbix/5.0/rhel/8/x86_64/zabbix-release-latest.el8.noarch.rpm"
        )


class InstallRepoTest(unittest.TestCase):
    @patch("install_steps.os_ops.run_cmd", return_value=True)
    def test_installs_the_repo_rpm(self, mock_run_cmd):
        self.assertTrue(install_steps.install_repo("5.0", "8"))
        mock_run_cmd.assert_called_once_with([
            "dnf", "install", "-y",
            "https://repo.zabbix.com/zabbix/5.0/rhel/8/x86_64/zabbix-release-latest.el8.noarch.rpm",
        ])


class InstallAgentTest(unittest.TestCase):
    @patch("install_steps.os_ops.run_cmd", return_value=True)
    def test_installs_the_given_package(self, mock_run_cmd):
        self.assertTrue(install_steps.install_agent("zabbix-agent2"))
        mock_run_cmd.assert_called_once_with(["dnf", "install", "-y", "zabbix-agent2"])


class EnableAndStartTest(unittest.TestCase):
    @patch("install_steps.os_ops.run_cmd", return_value=True)
    def test_enables_then_restarts_the_service(self, mock_run_cmd):
        self.assertTrue(install_steps.enable_and_start("zabbix-agent2"))
        mock_run_cmd.assert_any_call(["systemctl", "enable", "zabbix-agent2"])
        mock_run_cmd.assert_any_call(["systemctl", "restart", "zabbix-agent2"])

    @patch("install_steps.os_ops.run_cmd")
    def test_returns_false_when_restart_fails_even_if_enable_worked(self, mock_run_cmd):
        mock_run_cmd.side_effect = [True, False]
        self.assertFalse(install_steps.enable_and_start("zabbix-agent2"))


class ServiceStatusTest(unittest.TestCase):
    # is-active/is-enabled devolvem o texto real no stdout (active/inactive/failed,
    # enabled/disabled) mesmo com exit code != 0 -- por isso usa subprocess.run direto
    # em vez de os_ops.run_cmd (que só devolve bool do returncode).
    @patch("install_steps.subprocess.run")
    def test_reports_active_and_enabled(self, mock_run):
        mock_run.side_effect = [MagicMock(stdout="active\n"), MagicMock(stdout="enabled\n")]
        status = install_steps.service_status("zabbix-agent2")
        self.assertEqual(status, {"active": "active", "enabled": "enabled"})
        mock_run.assert_any_call(["systemctl", "is-active", "zabbix-agent2"], capture_output=True, text=True)
        mock_run.assert_any_call(["systemctl", "is-enabled", "zabbix-agent2"], capture_output=True, text=True)

    @patch("install_steps.subprocess.run")
    def test_reports_inactive_and_disabled(self, mock_run):
        mock_run.side_effect = [MagicMock(stdout="inactive\n"), MagicMock(stdout="disabled\n")]
        status = install_steps.service_status("zabbix-agent2")
        self.assertEqual(status, {"active": "inactive", "enabled": "disabled"})


if __name__ == "__main__":
    unittest.main()
