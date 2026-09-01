import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sudoers import build_rule, install_rule, remove_rule, validate_rule_syntax


class BuildRuleTest(unittest.TestCase):
    def test_builds_passwordless_sudo_rule_for_the_given_user(self):
        self.assertEqual(build_rule("phonevox"), "phonevox ALL=(ALL) NOPASSWD: ALL\n")


class ValidateRuleSyntaxTest(unittest.TestCase):
    def test_accepts_a_syntactically_valid_rule(self):
        self.assertTrue(validate_rule_syntax("phonevox ALL=(ALL) NOPASSWD: ALL\n"))

    def test_rejects_a_syntactically_invalid_rule(self):
        self.assertFalse(validate_rule_syntax("isso nao eh uma regra valida\n"))


class InstallRuleTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    @patch("sudoers.os.chown")
    def test_writes_the_rule_file_with_correct_permissions(self, mock_chown):
        result = install_rule("phonevox", sudoers_dir=self._tmp.name)

        rule_path = Path(self._tmp.name) / "phonevox"
        self.assertTrue(result)
        self.assertEqual(rule_path.read_text(), "phonevox ALL=(ALL) NOPASSWD: ALL\n")
        self.assertEqual(oct(rule_path.stat().st_mode)[-3:], "440")
        mock_chown.assert_called_once_with(str(rule_path), 0, 0)

    @patch("sudoers.validate_rule_syntax", return_value=False)
    def test_refuses_to_install_an_invalid_rule(self, mock_validate):
        result = install_rule("phonevox", sudoers_dir=self._tmp.name)

        self.assertFalse(result)
        self.assertFalse((Path(self._tmp.name) / "phonevox").exists())

    def test_is_idempotent_when_the_exact_rule_already_exists(self):
        rule_path = Path(self._tmp.name) / "phonevox"
        rule_path.write_text("phonevox ALL=(ALL) NOPASSWD: ALL\n")
        rule_path.chmod(0o440)

        with patch("sudoers.os.chown") as mock_chown:
            result = install_rule("phonevox", sudoers_dir=self._tmp.name)

        self.assertTrue(result)
        mock_chown.assert_not_called()


class RemoveRuleTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_removes_an_existing_rule_file(self):
        rule_path = Path(self._tmp.name) / "phonevox"
        rule_path.write_text("phonevox ALL=(ALL) NOPASSWD: ALL\n")

        remove_rule("phonevox", sudoers_dir=self._tmp.name)

        self.assertFalse(rule_path.exists())

    def test_is_a_no_op_when_the_rule_never_existed(self):
        remove_rule("phonevox", sudoers_dir=self._tmp.name)


if __name__ == "__main__":
    unittest.main()
