import json
import unittest
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

import system_info


class ReadOsReleaseTest(unittest.TestCase):
    def test_parses_key_value_pairs(self):
        with NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write('ID="rocky"\nVERSION_ID="8.10"\n')
            path = f.name
        self.assertEqual(system_info.read_os_release(path), {"ID": "rocky", "VERSION_ID": "8.10"})

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(system_info.read_os_release("/does/not/exist"), {})


class OsIdTest(unittest.TestCase):
    def test_returns_lowercase_id(self):
        self.assertEqual(system_info.os_id({"ID": "Rocky"}), "rocky")

    def test_empty_when_missing(self):
        self.assertEqual(system_info.os_id({}), "")


class OsLabelTest(unittest.TestCase):
    def test_combines_id_and_version(self):
        self.assertEqual(system_info.os_label({"ID": "rocky", "VERSION_ID": "8.10"}), "rocky-8.10")


class MachineIdTest(unittest.TestCase):
    def test_reads_and_strips(self):
        with NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("abc123\n")
            path = f.name
        self.assertEqual(system_info.machine_id(path), "abc123")

    def test_missing_file_returns_empty_string(self):
        self.assertEqual(system_info.machine_id("/does/not/exist"), "")


class DetectProviderTest(unittest.TestCase):
    def _mock_response(self, org):
        response = MagicMock()
        response.read.return_value = json.dumps({"org": org}).encode()
        response.__enter__.return_value = response
        return response

    @patch("system_info.urllib.request.urlopen")
    def test_detects_ovh(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response("AS16276 OVH SAS")
        self.assertEqual(system_info.detect_provider(), "ovh")

    @patch("system_info.urllib.request.urlopen")
    def test_detects_qnax(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response("QNAX Servers")
        self.assertEqual(system_info.detect_provider(), "qnax")

    @patch("system_info.urllib.request.urlopen")
    def test_detects_aws(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response("AS16509 Amazon.com, Inc.")
        self.assertEqual(system_info.detect_provider(), "aws")

    @patch("system_info.urllib.request.urlopen")
    def test_defaults_to_local_when_unrecognized(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response("Some Other Host")
        self.assertEqual(system_info.detect_provider(), "local")

    @patch("system_info.urllib.request.urlopen", side_effect=OSError)
    def test_defaults_to_local_on_network_failure(self, mock_urlopen):
        self.assertEqual(system_info.detect_provider(), "local")


class DetectHostnameTest(unittest.TestCase):
    def test_ovh_extracts_vps_pattern(self):
        self.assertEqual(system_info.detect_hostname("ovh", "vps-da2bcebf.ovh.net"), "vps-da2bcebf")

    def test_qnax_extracts_srv_pattern(self):
        self.assertEqual(system_info.detect_hostname("qnax", "SRV-1699030926"), "SRV-1699030926")

    @patch("system_info.machine_id", return_value="fallback-id")
    def test_ovh_pattern_not_found_falls_back_to_machine_id(self, mock_machine_id):
        self.assertEqual(system_info.detect_hostname("ovh", "some-other-name"), "fallback-id")

    @patch("system_info.machine_id", return_value="fallback-id")
    def test_local_provider_uses_machine_id(self, mock_machine_id):
        self.assertEqual(system_info.detect_hostname("local", "whatever"), "fallback-id")


class AsteriskVersionTest(unittest.TestCase):
    @patch("system_info.shutil.which", return_value=None)
    def test_none_when_asterisk_not_installed(self, mock_which):
        self.assertIsNone(system_info.asterisk_version())

    @patch("system_info.subprocess.run")
    @patch("system_info.shutil.which", return_value="/usr/sbin/asterisk")
    def test_parses_major_version(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(stdout="Asterisk 18.19.0, Copyright (C) 1999 - 2022\n")
        self.assertEqual(system_info.asterisk_version(), "18")

    @patch("system_info.subprocess.run")
    @patch("system_info.shutil.which", return_value="/usr/sbin/asterisk")
    def test_none_when_output_is_unparseable(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(stdout="huh?\n")
        self.assertIsNone(system_info.asterisk_version())


if __name__ == "__main__":
    unittest.main()
