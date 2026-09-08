import unittest
from unittest.mock import patch

import system_detect


class DetectDistroTest(unittest.TestCase):
    @patch("system_detect.os.path.exists")
    def test_rhel_marker_present(self, mock_exists):
        mock_exists.side_effect = lambda p: p == "/etc/redhat-release"
        self.assertEqual(system_detect.detect_distro(), "rhel")

    @patch("system_detect.os.path.exists")
    def test_debian_marker_present(self, mock_exists):
        mock_exists.side_effect = lambda p: p == "/etc/debian_version"
        self.assertEqual(system_detect.detect_distro(), "debian")

    @patch("system_detect.os.path.exists", return_value=False)
    def test_neither_marker_present(self, mock_exists):
        self.assertIsNone(system_detect.detect_distro())


class ApacheInfoTest(unittest.TestCase):
    def test_rhel_uses_httpd(self):
        info = system_detect.apache_info("rhel")
        self.assertEqual(info["service"], "httpd")
        self.assertEqual(info["conf_dir"], "/etc/httpd/conf.d")

    def test_debian_uses_apache2(self):
        info = system_detect.apache_info("debian")
        self.assertEqual(info["service"], "apache2")
        self.assertEqual(info["conf_dir"], "/etc/apache2/sites-available")

    def test_unknown_distro_returns_none(self):
        self.assertIsNone(system_detect.apache_info(None))


if __name__ == "__main__":
    unittest.main()
