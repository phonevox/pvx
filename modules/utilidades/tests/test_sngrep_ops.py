import os
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

import sngrep_ops


class DetectDistroTest(unittest.TestCase):
    @patch("os.path.exists", side_effect=lambda p: p == "/etc/alpine-release")
    def test_detects_alpine(self, mock_exists):
        self.assertEqual(sngrep_ops.detect_distro(), "alpine")

    @patch("os.path.exists", side_effect=lambda p: p == "/etc/redhat-release")
    def test_detects_rhel(self, mock_exists):
        self.assertEqual(sngrep_ops.detect_distro(), "rhel")

    @patch("os.path.exists", side_effect=lambda p: p == "/etc/debian_version")
    def test_detects_debian(self, mock_exists):
        self.assertEqual(sngrep_ops.detect_distro(), "debian")

    @patch("os.path.exists", return_value=False)
    def test_returns_none_for_unknown(self, mock_exists):
        self.assertIsNone(sngrep_ops.detect_distro())


class IsInstalledTest(unittest.TestCase):
    @patch("sngrep_ops.shutil.which", return_value="/usr/bin/sngrep")
    def test_true_when_binary_found(self, mock_which):
        self.assertTrue(sngrep_ops.is_installed())

    @patch("sngrep_ops.shutil.which", return_value=None)
    def test_false_when_binary_missing(self, mock_which):
        self.assertFalse(sngrep_ops.is_installed())


class InstallTest(unittest.TestCase):
    @patch("sngrep_ops.subprocess.run")
    def test_rhel_adds_epel_then_installs(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        sngrep_ops.install("rhel")
        calls = [c.args[0] for c in mock_run.call_args_list]
        self.assertEqual(calls[0], ["yum", "install", "-y", "epel-release"])
        self.assertEqual(calls[1], ["yum", "install", "-y", "sngrep"])

    @patch("sngrep_ops.subprocess.run")
    def test_debian_updates_then_installs(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        sngrep_ops.install("debian")
        calls = [c.args[0] for c in mock_run.call_args_list]
        self.assertEqual(calls[0], ["apt-get", "update"])
        self.assertEqual(calls[1], ["apt-get", "install", "-y", "sngrep"])

    @patch("sngrep_ops.subprocess.run")
    def test_alpine_installs_directly(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        sngrep_ops.install("alpine")
        calls = [c.args[0] for c in mock_run.call_args_list]
        self.assertEqual(calls, [["apk", "add", "sngrep"]])

    @patch("sngrep_ops.subprocess.run")
    def test_raises_on_failure(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="", stderr="deu ruim")
        with self.assertRaises(sngrep_ops.SngrepError):
            sngrep_ops.install("rhel")

    def test_raises_for_an_unsupported_distro(self):
        with self.assertRaises(sngrep_ops.SngrepError):
            sngrep_ops.install(None)


if __name__ == "__main__":
    unittest.main()
