import unittest
from unittest.mock import mock_open, patch

import asterisk_info

ASTERISK_CONF = """
[directories](!)
astetcdir => /etc/asterisk
astspooldir => /var/spool/asterisk
astlogdir => /var/log/asterisk
"""


class VersionTest(unittest.TestCase):
    def test_returns_the_first_two_tokens_of_the_cli_output(self):
        with patch("asterisk_info.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Asterisk 18.20.1 built by mockbuild @ ...\n"
            self.assertEqual(asterisk_info.version(), "Asterisk 18.20.1")

    def test_none_when_asterisk_is_not_reachable(self):
        with patch("asterisk_info.subprocess.run", side_effect=OSError):
            self.assertIsNone(asterisk_info.version())

    def test_none_on_nonzero_exit(self):
        with patch("asterisk_info.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            self.assertIsNone(asterisk_info.version())


class ActiveCallsTest(unittest.TestCase):
    def test_parses_the_active_calls_count(self):
        output = "1 active channel\n1 active call\n1 call processed\n"
        with patch("asterisk_info.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = output
            self.assertEqual(asterisk_info.active_calls(), 1)

    def test_none_when_the_line_is_missing(self):
        with patch("asterisk_info.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "0 active channels\n"
            self.assertIsNone(asterisk_info.active_calls())

    def test_none_when_asterisk_is_not_reachable(self):
        with patch("asterisk_info.subprocess.run", side_effect=OSError):
            self.assertIsNone(asterisk_info.active_calls())


class FindLogdirTest(unittest.TestCase):
    def test_parses_the_astlogdir_line(self):
        with patch("asterisk_info.open", mock_open(read_data=ASTERISK_CONF)):
            self.assertEqual(asterisk_info.find_logdir(), "/var/log/asterisk")

    def test_none_when_the_file_is_unreadable(self):
        with patch("asterisk_info.open", side_effect=OSError):
            self.assertIsNone(asterisk_info.find_logdir())

    def test_none_when_the_key_is_absent(self):
        with patch("asterisk_info.open", mock_open(read_data="[directories](!)\nastetcdir => /etc/asterisk\n")):
            self.assertIsNone(asterisk_info.find_logdir())


if __name__ == "__main__":
    unittest.main()
