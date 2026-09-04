import unittest
from unittest.mock import mock_open, patch

import issabel_info

ASTERISK_CONF = """
[directories](!)
astetcdir => /etc/asterisk
astspooldir => /var/spool/asterisk
astlogdir => /var/log/asterisk
"""


class FindSpooldirTest(unittest.TestCase):
    def test_parses_the_astspooldir_line(self):
        with patch("issabel_info.open", mock_open(read_data=ASTERISK_CONF)):
            self.assertEqual(issabel_info.find_spooldir(), "/var/spool/asterisk")

    def test_none_when_the_file_is_unreadable(self):
        with patch("issabel_info.open", side_effect=OSError):
            self.assertIsNone(issabel_info.find_spooldir())

    def test_none_when_the_key_is_absent(self):
        with patch("issabel_info.open", mock_open(read_data="[directories](!)\nastetcdir => /etc/asterisk\n")):
            self.assertIsNone(issabel_info.find_spooldir())


class StoragePercentTest(unittest.TestCase):
    def test_computes_percent_of_total_disk(self):
        with patch("issabel_info.os.path.isdir", return_value=True), \
             patch("issabel_info.os.walk", return_value=[("/var/spool/asterisk/monitor", [], ["a.wav", "b.wav"])]), \
             patch("issabel_info.os.path.getsize", side_effect=[1000, 2000]):
            percent = issabel_info.storage_percent("/var/spool/asterisk/monitor", disk_total_bytes=30000)
        self.assertAlmostEqual(percent, 10.0)

    def test_none_when_the_directory_does_not_exist(self):
        with patch("issabel_info.os.path.isdir", return_value=False):
            self.assertIsNone(issabel_info.storage_percent("/nope", disk_total_bytes=1000))

    def test_none_when_disk_total_is_zero_or_unknown(self):
        with patch("issabel_info.os.path.isdir", return_value=True), \
             patch("issabel_info.os.walk", return_value=[]):
            self.assertIsNone(issabel_info.storage_percent("/x", disk_total_bytes=0))

    def test_skips_files_it_cannot_stat(self):
        # técnico logado como não-root pode não ter permissão em alguns
        # arquivos de gravação -- ignora aquele arquivo e soma o resto.
        with patch("issabel_info.os.path.isdir", return_value=True), \
             patch("issabel_info.os.walk", return_value=[("/x", [], ["a", "b"])]), \
             patch("issabel_info.os.path.getsize", side_effect=[OSError(), 5000]):
            percent = issabel_info.storage_percent("/x", disk_total_bytes=10000)
        self.assertAlmostEqual(percent, 50.0)


class StorageBytesTest(unittest.TestCase):
    def test_sums_file_sizes_under_the_directory(self):
        with patch("issabel_info.os.path.isdir", return_value=True), \
             patch("issabel_info.os.walk", return_value=[("/x", [], ["a", "b"])]), \
             patch("issabel_info.os.path.getsize", side_effect=[1000, 2000]):
            self.assertEqual(issabel_info.storage_bytes("/x"), 3000)

    def test_none_when_the_directory_does_not_exist(self):
        with patch("issabel_info.os.path.isdir", return_value=False):
            self.assertIsNone(issabel_info.storage_bytes("/nope"))

    def test_skips_files_it_cannot_stat(self):
        with patch("issabel_info.os.path.isdir", return_value=True), \
             patch("issabel_info.os.walk", return_value=[("/x", [], ["a", "b"])]), \
             patch("issabel_info.os.path.getsize", side_effect=[OSError(), 5000]):
            self.assertEqual(issabel_info.storage_bytes("/x"), 5000)


class RecordingsBytesTest(unittest.TestCase):
    def test_joins_spooldir_with_monitor_and_delegates(self):
        with patch("issabel_info.find_spooldir", return_value="/var/spool/asterisk"), \
             patch("issabel_info.storage_bytes", return_value=12345) as mock_storage:
            result = issabel_info.recordings_bytes()
        mock_storage.assert_called_once_with("/var/spool/asterisk/monitor")
        self.assertEqual(result, 12345)

    def test_none_when_spooldir_is_unknown(self):
        with patch("issabel_info.find_spooldir", return_value=None):
            self.assertIsNone(issabel_info.recordings_bytes())


class DialerBytesTest(unittest.TestCase):
    def test_delegates_to_storage_bytes_with_the_fixed_path(self):
        with patch("issabel_info.storage_bytes", return_value=999) as mock_storage:
            result = issabel_info.dialer_bytes()
        mock_storage.assert_called_once_with(issabel_info.DIALER_DIR)
        self.assertEqual(result, 999)


class RecordingsPercentTest(unittest.TestCase):
    def test_joins_spooldir_with_monitor_and_delegates(self):
        with patch("issabel_info.find_spooldir", return_value="/var/spool/asterisk"), \
             patch("issabel_info.storage_percent", return_value=12.3) as mock_storage:
            percent = issabel_info.recordings_percent(disk_total_bytes=1000)
        mock_storage.assert_called_once_with("/var/spool/asterisk/monitor", 1000)
        self.assertEqual(percent, 12.3)

    def test_none_when_spooldir_is_unknown(self):
        with patch("issabel_info.find_spooldir", return_value=None):
            self.assertIsNone(issabel_info.recordings_percent(disk_total_bytes=1000))


class DialerPercentTest(unittest.TestCase):
    def test_delegates_to_storage_percent_with_the_fixed_path(self):
        with patch("issabel_info.storage_percent", return_value=4.2) as mock_storage:
            percent = issabel_info.dialer_percent(disk_total_bytes=1000)
        mock_storage.assert_called_once_with(issabel_info.DIALER_DIR, 1000)
        self.assertEqual(percent, 4.2)


if __name__ == "__main__":
    unittest.main()
