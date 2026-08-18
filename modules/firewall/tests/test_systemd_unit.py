import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import systemd_unit


class RenderUnitTest(unittest.TestCase):
    def test_contains_oneshot_and_exec_start_with_pvx_bin(self):
        content = systemd_unit.render_unit("/usr/local/bin/pvx")
        self.assertIn("Type=oneshot", content)
        self.assertIn("RemainAfterExit=yes", content)
        self.assertIn("After=network-online.target", content)
        self.assertIn("Wants=network-online.target", content)
        self.assertIn("WantedBy=multi-user.target", content)
        self.assertIn("ExecStart=/usr/local/bin/pvx firewall sync --force --yes", content)


class InstallTest(unittest.TestCase):
    def test_dry_run_returns_content_without_writing_or_calling_systemctl(self):
        with tempfile.TemporaryDirectory() as tmp:
            unit_path = Path(tmp) / "pvx-firewall.service"
            with patch("systemd_unit.subprocess.run") as mock_run:
                content = systemd_unit.install(unit_path=unit_path, dry_run=True)
            self.assertFalse(unit_path.exists())
            mock_run.assert_not_called()
            self.assertIn("ExecStart", content)

    @patch("systemd_unit.subprocess.run")
    def test_writes_unit_and_enables_it(self, mock_run):
        with tempfile.TemporaryDirectory() as tmp:
            unit_path = Path(tmp) / "pvx-firewall.service"
            systemd_unit.install(unit_path=unit_path, dry_run=False)

            self.assertTrue(unit_path.exists())
            self.assertIn("ExecStart", unit_path.read_text())

            commands = [c.args[0] for c in mock_run.call_args_list]
            self.assertIn(["systemctl", "daemon-reload"], commands)
            self.assertIn(["systemctl", "enable", "pvx-firewall.service"], commands)


if __name__ == "__main__":
    unittest.main()
