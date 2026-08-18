import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sshd_validate import apply_with_rollback, validate_config


def _generate_hostkey(directory):
    hostkey_path = Path(directory) / "hostkey"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(hostkey_path), "-N", "", "-q"], check=True
    )
    return hostkey_path


class ValidateConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.hostkey_path = _generate_hostkey(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_config(self, name, content):
        path = Path(self._tmp.name) / name
        path.write_text(content)
        return str(path)

    def test_accepts_a_syntactically_valid_config(self):
        config_path = self._write_config("valid", f"Port 22\nHostKey {self.hostkey_path}\n")
        self.assertTrue(validate_config(config_path))

    def test_rejects_a_config_with_an_unknown_directive(self):
        config_path = self._write_config("invalid", "ThisIsNotARealDirective banana\n")
        self.assertFalse(validate_config(config_path))


class ApplyWithRollbackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.hostkey_path = _generate_hostkey(self._tmp.name)
        self.config_path = Path(self._tmp.name) / "sshd_config"
        self.backup_path = Path(self._tmp.name) / "sshd_config.bak"

    def tearDown(self):
        self._tmp.cleanup()

    def test_keeps_the_config_when_it_is_valid(self):
        self.backup_path.write_text("Port 22\n")
        self.config_path.write_text(f"Port 21122\nHostKey {self.hostkey_path}\n")

        result = apply_with_rollback(str(self.config_path), str(self.backup_path))

        self.assertTrue(result)
        self.assertIn("Port 21122", self.config_path.read_text())

    def test_restores_the_backup_when_the_config_is_invalid(self):
        self.backup_path.write_text("Port 22\n")
        self.config_path.write_text("ThisIsNotARealDirective banana\n")

        result = apply_with_rollback(str(self.config_path), str(self.backup_path))

        self.assertFalse(result)
        self.assertEqual(self.config_path.read_text(), "Port 22\n")


if __name__ == "__main__":
    unittest.main()
