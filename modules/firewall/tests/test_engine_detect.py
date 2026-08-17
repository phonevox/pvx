import unittest
from unittest.mock import MagicMock, patch

import engine_detect


class DetectEngineTest(unittest.TestCase):
    @patch("engine_detect.subprocess.run")
    @patch("engine_detect.shutil.which")
    def test_firewalld_when_installed_and_running(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: "/usr/bin/firewall-cmd" if name == "firewall-cmd" else None
        mock_run.return_value = MagicMock(stdout="active\n")
        self.assertEqual(engine_detect.detect_engine(), "firewalld")

    @patch("engine_detect.subprocess.run")
    @patch("engine_detect.shutil.which")
    def test_iptables_when_firewalld_installed_but_not_running(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(stdout="inactive\n")
        self.assertEqual(engine_detect.detect_engine(), "iptables")

    @patch("engine_detect.subprocess.run")
    @patch("engine_detect.shutil.which")
    def test_iptables_when_firewalld_not_installed_at_all(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: "/usr/sbin/iptables" if name == "iptables" else None
        self.assertEqual(engine_detect.detect_engine(), "iptables")
        mock_run.assert_not_called()

    @patch("engine_detect.subprocess.run")
    @patch("engine_detect.shutil.which", return_value=None)
    def test_raises_when_neither_is_available(self, mock_which, mock_run):
        with self.assertRaises(RuntimeError):
            engine_detect.detect_engine()

    @patch("engine_detect.subprocess.run", side_effect=OSError)
    @patch("engine_detect.shutil.which")
    def test_treats_systemctl_failure_as_not_running(self, mock_which, mock_run):
        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        self.assertEqual(engine_detect.detect_engine(), "iptables")


if __name__ == "__main__":
    unittest.main()
