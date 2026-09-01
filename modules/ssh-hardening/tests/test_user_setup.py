import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from user_setup import (
    add_to_admin_group,
    create_user,
    delete_user,
    detect_admin_group,
    set_password,
    setup_authorized_key,
    user_exists,
)


class UserExistsTest(unittest.TestCase):
    def test_returns_true_for_a_real_user(self):
        self.assertTrue(user_exists("root"))

    def test_returns_false_for_a_nonexistent_user(self):
        self.assertFalse(user_exists("definitely-not-a-real-user-xyz"))


class CreateUserTest(unittest.TestCase):
    @patch("user_setup.user_exists", return_value=True)
    @patch("user_setup.subprocess.run")
    def test_skips_creation_when_user_already_exists(self, mock_run, mock_exists):
        result = create_user("phonevox")
        self.assertFalse(result)
        mock_run.assert_not_called()

    @patch("user_setup.user_exists", return_value=False)
    @patch("user_setup.subprocess.run")
    def test_creates_user_with_home_and_shell_when_absent(self, mock_run, mock_exists):
        result = create_user("phonevox")
        self.assertTrue(result)
        mock_run.assert_called_once_with(["useradd", "-m", "-s", "/bin/bash", "phonevox"], check=True)


class DeleteUserTest(unittest.TestCase):
    @patch("user_setup.user_exists", return_value=True)
    @patch("user_setup.subprocess.run")
    def test_deletes_the_user_and_home_dir(self, mock_run, mock_exists):
        delete_user("phonevox")
        mock_run.assert_called_once_with(["userdel", "-r", "phonevox"], check=True)

    @patch("user_setup.user_exists", return_value=False)
    @patch("user_setup.subprocess.run")
    def test_skips_when_user_does_not_exist(self, mock_run, mock_exists):
        delete_user("phonevox")
        mock_run.assert_not_called()


class DetectAdminGroupTest(unittest.TestCase):
    # achado ao vivo: Debian/Ubuntu não tem grupo wheel (usam sudo) -- usermod
    # -aG wheel estourava CalledProcessError sem esse fallback.
    @patch("user_setup.grp.getgrnam")
    def test_prefers_wheel_when_it_exists(self, mock_getgrnam):
        mock_getgrnam.side_effect = lambda name: object() if name == "wheel" else _raise_key_error()
        self.assertEqual(detect_admin_group(), "wheel")

    @patch("user_setup.grp.getgrnam")
    def test_falls_back_to_sudo_when_wheel_is_absent(self, mock_getgrnam):
        mock_getgrnam.side_effect = lambda name: object() if name == "sudo" else _raise_key_error()
        self.assertEqual(detect_admin_group(), "sudo")

    @patch("user_setup.grp.getgrnam", side_effect=KeyError)
    def test_none_when_neither_group_exists(self, mock_getgrnam):
        self.assertIsNone(detect_admin_group())


def _raise_key_error():
    raise KeyError("group not found")


class AddToAdminGroupTest(unittest.TestCase):
    @patch("user_setup.subprocess.run")
    def test_adds_user_to_the_given_group(self, mock_run):
        result = add_to_admin_group("phonevox", group="sudo")
        self.assertTrue(result)
        mock_run.assert_called_once_with(["usermod", "-aG", "sudo", "phonevox"], check=True)

    @patch("user_setup.subprocess.run")
    @patch("user_setup.detect_admin_group", return_value="sudo")
    def test_auto_detects_group_when_not_given(self, mock_detect, mock_run):
        add_to_admin_group("phonevox")
        mock_run.assert_called_once_with(["usermod", "-aG", "sudo", "phonevox"], check=True)

    @patch("user_setup.subprocess.run")
    @patch("user_setup.detect_admin_group", return_value=None)
    def test_does_nothing_when_no_admin_group_exists(self, mock_detect, mock_run):
        result = add_to_admin_group("phonevox")
        self.assertFalse(result)
        mock_run.assert_not_called()


class SetPasswordTest(unittest.TestCase):
    @patch("user_setup.subprocess.run")
    def test_sets_password_via_chpasswd(self, mock_run):
        set_password("phonevox", "s3cr3t")
        mock_run.assert_called_once_with(["chpasswd"], input="phonevox:s3cr3t\n", text=True, check=True)


class SetupAuthorizedKeyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home_dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    @patch("user_setup.subprocess.run")
    def test_creates_ssh_dir_and_authorized_keys_with_correct_permissions(self, mock_run):
        setup_authorized_key(self.home_dir, "phonevox", "ssh-rsa AAAA test")

        ssh_dir = Path(self.home_dir) / ".ssh"
        authorized_keys = ssh_dir / "authorized_keys"
        self.assertEqual(oct(ssh_dir.stat().st_mode)[-3:], "700")
        self.assertEqual(oct(authorized_keys.stat().st_mode)[-3:], "600")
        self.assertEqual(authorized_keys.read_text(), "ssh-rsa AAAA test\n")

    @patch("user_setup.subprocess.run")
    def test_does_not_duplicate_an_already_present_key(self, mock_run):
        ssh_dir = Path(self.home_dir) / ".ssh"
        ssh_dir.mkdir(mode=0o700)
        (ssh_dir / "authorized_keys").write_text("ssh-rsa AAAA test\n")

        setup_authorized_key(self.home_dir, "phonevox", "ssh-rsa AAAA test")

        self.assertEqual((ssh_dir / "authorized_keys").read_text(), "ssh-rsa AAAA test\n")

    @patch("user_setup.subprocess.run")
    def test_chowns_the_ssh_directory_to_the_user(self, mock_run):
        setup_authorized_key(self.home_dir, "phonevox", "ssh-rsa AAAA test")

        ssh_dir = Path(self.home_dir) / ".ssh"
        mock_run.assert_called_once_with(["chown", "-R", "phonevox:phonevox", str(ssh_dir)], check=True)


if __name__ == "__main__":
    unittest.main()
