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


if __name__ == "__main__":
    unittest.main()
