import unittest
from unittest.mock import patch

import sshd_service


class RestartTest(unittest.TestCase):
    @patch("sshd_service.subprocess.run")
    def test_restarts_sshd_unit_when_it_exists(self, mock_run):
        mock_run.return_value.returncode = 0
        self.assertEqual(sshd_service.restart(), "sshd")
        mock_run.assert_called_once_with(["systemctl", "restart", "sshd"], capture_output=True)

    def test_falls_back_to_ssh_unit_on_debian(self):
        # Debian/Ubuntu chamam a unit de "ssh", não "sshd" -- não dá pra
        # assumir o nome sem testar.
        with patch("sshd_service.subprocess.run") as mock_run:
            mock_run.side_effect = [
                type("R", (), {"returncode": 1})(),
                type("R", (), {"returncode": 0})(),
            ]
            self.assertEqual(sshd_service.restart(), "ssh")
        commands = [c.args[0] for c in mock_run.call_args_list]
        self.assertEqual(commands, [["systemctl", "restart", "sshd"], ["systemctl", "restart", "ssh"]])

    @patch("sshd_service.subprocess.run")
    def test_none_when_neither_unit_exists(self, mock_run):
        mock_run.return_value.returncode = 1
        self.assertIsNone(sshd_service.restart())

    @patch("sshd_service.subprocess.run", side_effect=OSError)
    def test_none_when_systemctl_is_unavailable(self, mock_run):
        self.assertIsNone(sshd_service.restart())


if __name__ == "__main__":
    unittest.main()
