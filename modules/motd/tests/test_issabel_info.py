import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
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


class StorageBytesTest(unittest.TestCase):
    # achado ao vivo: os.walk + os.path.getsize por arquivo, em Python, era o
    # gargalo real do motd -- numa central de produção com anos de gravação de
    # chamada (dezenas de milhares de arquivos), isso deixava o login lento pra
    # caramba. du nativo (C, otimizado) resolve isso sem trocar o resultado.
    def test_sums_real_files_under_the_directory_via_du(self):
        # du reporta uso real em disco (bloco a bloco), não a soma exata de
        # bytes de conteúdo -- nunca fica abaixo do conteúdo real, só igual ou
        # arredondado pra cima (tamanho de bloco varia por filesystem/SO).
        with TemporaryDirectory() as tmp:
            Path(tmp, "a.wav").write_bytes(b"x" * 1000)
            Path(tmp, "b.wav").write_bytes(b"x" * 2000)
            size = issabel_info.storage_bytes(tmp)
        self.assertGreaterEqual(size, 3000)

    def test_none_when_the_directory_does_not_exist(self):
        with patch("issabel_info.os.path.isdir", return_value=False):
            self.assertIsNone(issabel_info.storage_bytes("/nope"))

    @patch("issabel_info.subprocess.run")
    def test_none_when_du_fails(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="", stderr="deu ruim")
        with patch("issabel_info.os.path.isdir", return_value=True):
            self.assertIsNone(issabel_info.storage_bytes("/x"))

    @patch("issabel_info.subprocess.run", side_effect=OSError)
    def test_none_when_du_is_unavailable(self, mock_run):
        with patch("issabel_info.os.path.isdir", return_value=True):
            self.assertIsNone(issabel_info.storage_bytes("/x"))


class StoragePercentTest(unittest.TestCase):
    @patch("issabel_info.storage_bytes", return_value=3000)
    def test_computes_percent_of_total_disk(self, mock_bytes):
        self.assertAlmostEqual(issabel_info.storage_percent("/x", disk_total_bytes=30000), 10.0)

    @patch("issabel_info.storage_bytes", return_value=None)
    def test_none_when_storage_bytes_is_none(self, mock_bytes):
        self.assertIsNone(issabel_info.storage_percent("/nope", disk_total_bytes=1000))

    @patch("issabel_info.storage_bytes", return_value=100)
    def test_none_when_disk_total_is_zero_or_unknown(self, mock_bytes):
        self.assertIsNone(issabel_info.storage_percent("/x", disk_total_bytes=0))


class StorageInfoTest(unittest.TestCase):
    # dedup: bytes e percent do mesmo path numa chamada só -- achado ao vivo,
    # recordings/dialer/logs cada um chamava storage_bytes duas vezes (uma via
    # *_bytes(), outra via *_percent()), dobrando à toa o número de `du`.
    @patch("issabel_info.storage_bytes", return_value=3000)
    def test_computes_bytes_and_percent_from_a_single_call(self, mock_bytes):
        size, percent = issabel_info.storage_info("/x", disk_total_bytes=30000)
        mock_bytes.assert_called_once_with("/x")
        self.assertEqual(size, 3000)
        self.assertAlmostEqual(percent, 10.0)

    @patch("issabel_info.storage_bytes", return_value=None)
    def test_percent_is_none_when_bytes_is_none(self, mock_bytes):
        size, percent = issabel_info.storage_info("/nope", disk_total_bytes=1000)
        self.assertIsNone(size)
        self.assertIsNone(percent)


class RecordingsInfoTest(unittest.TestCase):
    def test_joins_spooldir_with_monitor_and_delegates(self):
        with patch("issabel_info.find_spooldir", return_value="/var/spool/asterisk"), \
             patch("issabel_info.storage_info", return_value=(12345, 4.6)) as mock_info:
            size, percent = issabel_info.recordings_info(disk_total_bytes=1000)
        mock_info.assert_called_once_with("/var/spool/asterisk/monitor", 1000)
        self.assertEqual((size, percent), (12345, 4.6))

    def test_none_when_spooldir_is_unknown(self):
        with patch("issabel_info.find_spooldir", return_value=None):
            self.assertEqual(issabel_info.recordings_info(disk_total_bytes=1000), (None, None))


class DialerInfoTest(unittest.TestCase):
    def test_delegates_to_storage_info_with_the_fixed_path(self):
        with patch("issabel_info.storage_info", return_value=(999, 0.1)) as mock_info:
            size, percent = issabel_info.dialer_info(disk_total_bytes=1000)
        mock_info.assert_called_once_with(issabel_info.DIALER_DIR, 1000)
        self.assertEqual((size, percent), (999, 0.1))


if __name__ == "__main__":
    unittest.main()
