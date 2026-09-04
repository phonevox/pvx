import unittest
from unittest.mock import mock_open, patch

import services


class IsInstalledTest(unittest.TestCase):
    def test_true_when_which_finds_it(self):
        with patch("services.shutil.which", return_value="/usr/sbin/asterisk"):
            self.assertTrue(services.is_installed("asterisk"))

    def test_false_when_which_finds_nothing(self):
        with patch("services.shutil.which", return_value=None):
            self.assertFalse(services.is_installed("asterisk"))


class IsProcessRunningTest(unittest.TestCase):
    def test_finds_a_matching_process_by_comm(self):
        def fake_open(path, *a, **kw):
            content = {"/proc/1/comm": "systemd\n", "/proc/42/comm": "asterisk\n"}[path]
            return mock_open(read_data=content).return_value

        with patch("services.os.listdir", return_value=["1", "42", "self", "cpuinfo"]), \
             patch("services.open", side_effect=fake_open):
            self.assertTrue(services.is_process_running("asterisk"))

    def test_false_when_no_process_matches(self):
        with patch("services.os.listdir", return_value=["1"]), \
             patch("services.open", mock_open(read_data="bash\n")):
            self.assertFalse(services.is_process_running("asterisk"))

    def test_skips_processes_it_cannot_read(self):
        # técnico logado como usuário não-root pode não ter permissão de ler
        # /proc/<pid>/comm de processos de outros usuários -- ignora e segue.
        def fake_open(path, *a, **kw):
            if path == "/proc/1/comm":
                raise PermissionError()
            return mock_open(read_data="asterisk\n").return_value

        with patch("services.os.listdir", return_value=["1", "2"]), \
             patch("services.open", side_effect=fake_open):
            self.assertTrue(services.is_process_running("asterisk"))

    def test_false_when_proc_is_unreadable(self):
        with patch("services.os.listdir", side_effect=OSError):
            self.assertFalse(services.is_process_running("asterisk"))


class DaemonStatusTest(unittest.TestCase):
    def test_not_installed_when_no_candidate_binary_exists(self):
        with patch("services.is_installed", return_value=False):
            result = services.daemon_status(("mysql", "mariadb"), "mysqld")
        self.assertEqual(result, {"installed": False, "running": False})

    def test_installed_and_running(self):
        with patch("services.is_installed", return_value=True), \
             patch("services.is_process_running", return_value=True):
            result = services.daemon_status(("asterisk",), "asterisk")
        self.assertEqual(result, {"installed": True, "running": True})

    def test_installed_but_not_running(self):
        with patch("services.is_installed", return_value=True), \
             patch("services.is_process_running", return_value=False):
            result = services.daemon_status(("asterisk",), "asterisk")
        self.assertEqual(result, {"installed": True, "running": False})




if __name__ == "__main__":
    unittest.main()
