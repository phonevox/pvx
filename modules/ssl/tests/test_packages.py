import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

import packages


class InstallTest(unittest.TestCase):
    @patch("packages.subprocess.run")
    def test_rhel_installs_epel_modssl_and_certbot(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        packages.install("rhel")
        args = mock_run.call_args.args[0]
        self.assertEqual(args[:2], ["yum", "install"])
        self.assertIn("python3-certbot-apache", args)

    @patch("packages.subprocess.run")
    def test_debian_updates_then_installs(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        packages.install("debian")
        calls = [c.args[0] for c in mock_run.call_args_list]
        self.assertEqual(calls[0], ["apt-get", "update"])
        self.assertEqual(calls[1][:2], ["apt-get", "install"])
        self.assertIn("certbot", calls[1])
        self.assertIn("apache2", calls[1])

    @patch("packages.subprocess.run")
    def test_raises_on_failure(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="", stderr="deu ruim")
        with self.assertRaises(packages.PackageError):
            packages.install("rhel")

    def test_raises_for_an_unsupported_distro(self):
        with self.assertRaises(packages.PackageError):
            packages.install(None)


if __name__ == "__main__":
    unittest.main()
