import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from main import cli


class MainTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name)
        self._state_patch = patch("main._state_dir", return_value=self.state_dir)
        self._state_patch.start()

    def tearDown(self):
        self._state_patch.stop()
        self._tmp.cleanup()

    def _invoke(self, args, is_root=True):
        with patch("main.os.geteuid", return_value=0 if is_root else 1000):
            return CliRunner().invoke(cli.cli_group(), args)


class RootCheckTest(MainTestCase):
    def test_refuses_mutating_command_without_root(self):
        result = self._invoke(["port-accept", "80/tcp"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("root", result.output.lower())

    def test_status_does_not_require_root(self):
        with patch("main.status_module.get_status", return_value={
            "engine": "iptables", "rule_count": 0, "session_ip": None, "protection": "x",
        }):
            result = self._invoke(["status"], is_root=False)
        self.assertEqual(result.exit_code, 0)


class PortCommandsTest(MainTestCase):
    def test_accept_rejects_invalid_spec(self):
        result = self._invoke(["port-accept", "not-a-port"])
        self.assertNotEqual(result.exit_code, 0)

    def test_accept_then_list_shows_entry(self):
        self._invoke(["port-accept", "8080/tcp", "--comment", "custom"])
        result = self._invoke(["port-list"])
        self.assertIn("8080/tcp", result.output)
        self.assertIn("custom", result.output)

    def test_remove_reports_error_when_not_present(self):
        result = self._invoke(["port-remove", "9999/tcp"])
        self.assertNotEqual(result.exit_code, 0)

    def test_remove_removes_from_whichever_list_has_it(self):
        self._invoke(["port-deny", "23/tcp"])
        result = self._invoke(["port-remove", "23/tcp"])
        self.assertEqual(result.exit_code, 0)
        listing = self._invoke(["port-list"])
        self.assertNotIn("23/tcp", listing.output)


class IpCommandsTest(MainTestCase):
    def test_accept_rejects_invalid_cidr(self):
        result = self._invoke(["ip-accept", "not-an-ip"])
        self.assertNotEqual(result.exit_code, 0)

    def test_deny_refuses_when_it_would_self_ban(self):
        with patch("main.session_ip.detect_session_ip", return_value="203.0.113.9"):
            result = self._invoke(["ip-deny", "203.0.113.0/24"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("force", result.output.lower())

    def test_deny_allows_self_ban_with_force(self):
        with patch("main.session_ip.detect_session_ip", return_value="203.0.113.9"):
            result = self._invoke(["ip-deny", "203.0.113.0/24", "--force"])
        self.assertEqual(result.exit_code, 0)

    def test_accept_then_list_shows_entry(self):
        self._invoke(["ip-accept", "198.51.100.5", "--comment", "escritório"])
        result = self._invoke(["ip-list"])
        self.assertIn("198.51.100.5", result.output)


class StatusCommandTest(MainTestCase):
    def test_prints_engine_and_protection(self):
        with patch("main.status_module.get_status", return_value={
            "engine": "iptables", "rule_count": 5, "session_ip": "203.0.113.9", "protection": "protegido",
        }):
            result = self._invoke(["status"])
        self.assertIn("iptables", result.output)
        self.assertIn("protegido", result.output)


class SyncCommandTest(MainTestCase):
    def test_requires_confirmation_without_yes(self):
        with patch("main.ask_confirm", return_value=False):
            result = self._invoke(["sync"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("cancelada", result.output.lower())

    @patch("main.sync_module.run", return_value={"engine": "iptables", "session_ip": "203.0.113.9"})
    def test_syncs_with_yes_flag(self, mock_run):
        result = self._invoke(["sync", "--yes"])
        self.assertEqual(result.exit_code, 0)
        mock_run.assert_called_once()

    @patch("main.sync_module.run", side_effect=RuntimeError("boom"))
    def test_reports_failure(self, mock_run):
        result = self._invoke(["sync", "--yes"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("boom", result.output)


class StartOnBootTest(MainTestCase):
    def test_dry_run_prints_unit_content(self):
        with patch("main.systemd_unit.install", return_value="[Unit]\n...") as mock_install:
            result = self._invoke(["start-on-boot", "--dry-run"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("[Unit]", result.output)
        mock_install.assert_called_once_with(pvx_bin="/usr/local/bin/pvx", dry_run=True)

    def test_installs_and_reports_success(self):
        with patch("main.systemd_unit.install", return_value="content"):
            result = self._invoke(["start-on-boot"])
        self.assertEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
