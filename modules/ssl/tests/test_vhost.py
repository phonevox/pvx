import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import vhost


class ConfPathTest(unittest.TestCase):
    def test_joins_conf_dir_and_domain(self):
        self.assertEqual(vhost.conf_path("/etc/apache2/sites-available", "example.com"),
                          "/etc/apache2/sites-available/example.com.conf")


class ExistsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_false_when_absent(self):
        self.assertFalse(vhost.exists(self._tmp.name, "example.com"))

    def test_true_when_present(self):
        (Path(self._tmp.name) / "example.com.conf").write_text("x")
        self.assertTrue(vhost.exists(self._tmp.name, "example.com"))


class CreateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    @patch("vhost.subprocess.run")
    def test_writes_a_virtualhost_with_domain_and_email(self, mock_run):
        path = vhost.create(self._tmp.name, "example.com", "suporte@phonevox.com.br", "rhel")
        content = Path(path).read_text()
        self.assertIn("ServerName example.com", content)
        self.assertIn("ServerAdmin suporte@phonevox.com.br", content)

    @patch("vhost.subprocess.run")
    def test_enables_the_site_on_debian(self, mock_run):
        vhost.create(self._tmp.name, "example.com", "suporte@phonevox.com.br", "debian")
        mock_run.assert_called_once_with(["a2ensite", "example.com"], capture_output=True)

    @patch("vhost.subprocess.run")
    def test_does_not_call_a2ensite_on_rhel(self, mock_run):
        vhost.create(self._tmp.name, "example.com", "suporte@phonevox.com.br", "rhel")
        mock_run.assert_not_called()


class RemoveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    @patch("vhost.subprocess.run")
    def test_deletes_the_conf_file(self, mock_run):
        path = Path(self._tmp.name) / "example.com.conf"
        path.write_text("x")
        vhost.remove(self._tmp.name, "example.com", "rhel")
        self.assertFalse(path.exists())

    @patch("vhost.subprocess.run")
    def test_disables_the_site_on_debian_before_removing(self, mock_run):
        (Path(self._tmp.name) / "example.com.conf").write_text("x")
        vhost.remove(self._tmp.name, "example.com", "debian")
        mock_run.assert_called_once_with(["a2dissite", "example.com"], capture_output=True)

    @patch("vhost.subprocess.run")
    def test_safe_when_file_is_already_absent(self, mock_run):
        vhost.remove(self._tmp.name, "example.com", "rhel")  # não deve levantar


class ReloadApacheTest(unittest.TestCase):
    @patch("vhost.subprocess.run")
    def test_reloads_the_given_service(self, mock_run):
        vhost.reload_apache("apache2")
        mock_run.assert_called_once_with(["systemctl", "reload", "apache2"], capture_output=True)


if __name__ == "__main__":
    unittest.main()
