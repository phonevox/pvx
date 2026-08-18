import unittest

from sshd_config import set_directive


class SetDirectiveTest(unittest.TestCase):
    def test_appends_directive_when_absent(self):
        result = set_directive("Port 22\n", "PermitRootLogin", "no")
        self.assertEqual(result, "Port 22\nPermitRootLogin no\n")

    def test_comments_out_existing_active_line_and_appends_new_one(self):
        result = set_directive("PermitRootLogin yes\nPort 22\n", "PermitRootLogin", "no")
        self.assertEqual(
            result,
            "#PermitRootLogin yes  # disabled by ssh-hardening\nPort 22\nPermitRootLogin no\n",
        )

    def test_is_idempotent_when_already_set_to_the_same_value(self):
        config = "Port 22\nPermitRootLogin no\n"
        result = set_directive(config, "PermitRootLogin", "no")
        self.assertEqual(result, config)

    def test_does_not_touch_already_commented_lines(self):
        result = set_directive("#PermitRootLogin yes\nPort 22\n", "PermitRootLogin", "no")
        self.assertEqual(result, "#PermitRootLogin yes\nPort 22\nPermitRootLogin no\n")

    def test_matches_directive_case_insensitively(self):
        result = set_directive("permitrootlogin yes\n", "PermitRootLogin", "no")
        self.assertEqual(
            result, "#permitrootlogin yes  # disabled by ssh-hardening\nPermitRootLogin no\n"
        )

    def test_replaces_multiple_active_occurrences(self):
        result = set_directive("PermitRootLogin yes\nPort 22\nPermitRootLogin without-password\n", "PermitRootLogin", "no")
        self.assertEqual(
            result,
            "#PermitRootLogin yes  # disabled by ssh-hardening\n"
            "Port 22\n"
            "#PermitRootLogin without-password  # disabled by ssh-hardening\n"
            "PermitRootLogin no\n",
        )


if __name__ == "__main__":
    unittest.main()
