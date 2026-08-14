import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backup import backup_config, restore_config


class BackupConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.config_path = Path(self._tmp.name) / "sshd_config"
        self.config_path.write_text("Port 22\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_a_backup_file_with_the_same_content(self):
        backup_path = backup_config(str(self.config_path))

        self.assertTrue(Path(backup_path).exists())
        self.assertEqual(Path(backup_path).read_text(), "Port 22\n")

    def test_backup_file_name_is_derived_from_the_original(self):
        backup_path = backup_config(str(self.config_path))

        self.assertTrue(Path(backup_path).name.startswith("sshd_config.bak."))

    def test_does_not_modify_the_original_file(self):
        backup_config(str(self.config_path))

        self.assertEqual(self.config_path.read_text(), "Port 22\n")


class RestoreConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.config_path = Path(self._tmp.name) / "sshd_config"

    def tearDown(self):
        self._tmp.cleanup()

    def test_restore_overwrites_target_with_backup_content(self):
        backup_path = Path(self._tmp.name) / "sshd_config.bak.20260101_000000"
        backup_path.write_text("Port 22\n")
        self.config_path.write_text("Port 21122\nPermitRootLogin no\n")

        restore_config(str(self.config_path), str(backup_path))

        self.assertEqual(self.config_path.read_text(), "Port 22\n")


if __name__ == "__main__":
    unittest.main()
