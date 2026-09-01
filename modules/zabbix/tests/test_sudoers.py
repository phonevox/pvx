import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import sudoers


class WriteRulesTest(unittest.TestCase):
    def test_writes_one_nopasswd_line_per_command(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "pvx-zabbix"
            sudoers.write_rules(str(path), "zabbix", ["/opt/scripts/a.sh", "/opt/scripts/b.sh"])
            content = path.read_text()
            self.assertIn("zabbix ALL=(root) NOPASSWD: /opt/scripts/a.sh", content)
            self.assertIn("zabbix ALL=(root) NOPASSWD: /opt/scripts/b.sh", content)

    def test_never_grants_blanket_access(self):
        # o script bash antigo dava %zabbix ALL=(ALL) NOPASSWD: ALL -- nunca mais.
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "pvx-zabbix"
            sudoers.write_rules(str(path), "zabbix", ["/opt/scripts/a.sh"])
            self.assertNotIn("ALL=(ALL)", path.read_text())

    def test_sets_restrictive_permissions(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "pvx-zabbix"
            sudoers.write_rules(str(path), "zabbix", ["/opt/scripts/a.sh"])
            self.assertEqual(oct(path.stat().st_mode)[-3:], "440")

    def test_removes_file_when_no_commands_need_root(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "pvx-zabbix"
            path.write_text("stale")
            sudoers.write_rules(str(path), "zabbix", [])
            self.assertFalse(path.exists())


class RemoveTest(unittest.TestCase):
    def test_safe_when_file_absent(self):
        sudoers.remove("/does/not/exist")


class LegacyRuleTest(unittest.TestCase):
    # rastro do pzabbix (script bash antigo): ele escrevia essa linha direto no
    # /etc/sudoers principal, sem escopo nenhum -- acesso root irrestrito.
    def test_detects_the_old_unscoped_line(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sudoers"
            path.write_text("root ALL=(ALL) ALL\n%zabbix ALL=(ALL) NOPASSWD: ALL\n")
            self.assertTrue(sudoers.detect_legacy_rule(str(path)))

    def test_false_when_line_is_absent(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sudoers"
            path.write_text("root ALL=(ALL) ALL\n")
            self.assertFalse(sudoers.detect_legacy_rule(str(path)))

    def test_false_when_file_is_unreadable_or_missing(self):
        self.assertFalse(sudoers.detect_legacy_rule("/does/not/exist"))

    def test_removes_only_the_legacy_line_keeps_the_rest(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sudoers"
            path.write_text("root ALL=(ALL) ALL\n%zabbix ALL=(ALL) NOPASSWD: ALL\nDefaults secure_path=x\n")
            self.assertTrue(sudoers.remove_legacy_rule(str(path)))
            content = path.read_text()
            self.assertNotIn("%zabbix ALL=(ALL) NOPASSWD: ALL", content)
            self.assertIn("root ALL=(ALL) ALL", content)
            self.assertIn("Defaults secure_path=x", content)

    def test_returns_false_when_there_is_nothing_to_remove(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sudoers"
            path.write_text("root ALL=(ALL) ALL\n")
            self.assertFalse(sudoers.remove_legacy_rule(str(path)))


if __name__ == "__main__":
    unittest.main()
