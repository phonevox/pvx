import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from apply import apply
from plan import build_plan


def _generate_hostkey(directory):
    hostkey_path = Path(directory) / "hostkey"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(hostkey_path), "-N", "", "-q"], check=True
    )
    return hostkey_path


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.config_path = Path(self._tmp.name) / "sshd_config"
        self.sudoers_dir = Path(self._tmp.name) / "sudoers.d"
        self.sudoers_dir.mkdir()
        self.state_dir = Path(self._tmp.name) / "state"
        self.hostkey_path = _generate_hostkey(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_valid_config(self, extra=""):
        self.config_path.write_text(f"Port 22\nHostKey {self.hostkey_path}\n{extra}")

    def test_returns_not_applied_when_plan_is_none(self):
        result = apply(None, str(self.config_path), str(self.sudoers_dir), str(self.state_dir))
        self.assertFalse(result["applied"])

    @patch("apply.user_setup.set_password")
    def test_locks_root_sets_password_and_directive(self, mock_set_password):
        self._write_valid_config()
        plan = build_plan(
            lock_root=True, root_password="rootpass",
            create_user=False, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )

        result = apply(plan, str(self.config_path), str(self.sudoers_dir), str(self.state_dir))

        self.assertTrue(result["applied"])
        self.assertTrue(result["config_valid"])
        self.assertIn("PermitRootLogin no", self.config_path.read_text())
        mock_set_password.assert_called_once_with("root", "rootpass")

    @patch("apply.user_setup.set_password")
    @patch("apply.user_setup.setup_authorized_key")
    @patch("apply.sudoers.install_rule")
    @patch("apply.user_setup.add_to_admin_group")
    @patch("apply.user_setup.create_user")
    def test_creates_user_and_wires_group_sudoers_and_key(
        self, mock_create_user, mock_add_group, mock_install_rule, mock_setup_key, mock_set_password
    ):
        self._write_valid_config()
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=True, username="phonevox", public_key="ssh-rsa AAAA test", allow_password=True,
            user_password="userpass",
            change_port=False, port=None,
        )

        result = apply(plan, str(self.config_path), str(self.sudoers_dir), str(self.state_dir))

        self.assertTrue(result["applied"])
        mock_create_user.assert_called_once_with("phonevox")
        mock_add_group.assert_called_once_with("phonevox")
        mock_install_rule.assert_called_once_with("phonevox", sudoers_dir=str(self.sudoers_dir))
        mock_setup_key.assert_called_once_with("/home/phonevox", "phonevox", "ssh-rsa AAAA test")
        mock_set_password.assert_called_once_with("phonevox", "userpass")

    def test_changes_port_directive(self):
        self._write_valid_config()
        plan = build_plan(
            lock_root=False, root_password=None,
            create_user=False, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=True, port="2222",
        )

        result = apply(plan, str(self.config_path), str(self.sudoers_dir), str(self.state_dir))

        self.assertTrue(result["applied"])
        self.assertIn("Port 2222", self.config_path.read_text())

    def test_rolls_back_when_resulting_config_is_invalid(self):
        self.config_path.write_text("Port 22\n")  # sem HostKey -- sshd -t sempre falha nisso
        plan = build_plan(
            lock_root=True, root_password="rootpass",
            create_user=False, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )

        with patch("apply.user_setup.set_password"):
            result = apply(plan, str(self.config_path), str(self.sudoers_dir), str(self.state_dir))

        self.assertTrue(result["applied"])
        self.assertFalse(result["config_valid"])
        self.assertEqual(self.config_path.read_text(), "Port 22\n")

    @patch("apply.user_setup.set_password")
    def test_writes_application_record_with_secure_permissions(self, mock_set_password):
        self._write_valid_config()
        plan = build_plan(
            lock_root=True, root_password="rootpass",
            create_user=False, username=None, public_key=None, allow_password=False, user_password=None,
            change_port=False, port=None,
        )

        result = apply(plan, str(self.config_path), str(self.sudoers_dir), str(self.state_dir))

        record_path = Path(result["record_path"])
        self.assertTrue(record_path.exists())
        self.assertEqual(oct(record_path.stat().st_mode)[-3:], "600")
        record = json.loads(record_path.read_text())
        self.assertEqual(record["plan"]["root_password"], "rootpass")


if __name__ == "__main__":
    unittest.main()
