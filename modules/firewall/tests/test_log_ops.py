import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import log_ops


class EnableDisableTest(unittest.TestCase):
    def test_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(log_ops.is_enabled(tmp))

    def test_enable_creates_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_ops.enable(tmp)
            self.assertTrue(log_ops.is_enabled(tmp))

    def test_disable_removes_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_ops.enable(tmp)
            log_ops.disable(tmp)
            self.assertFalse(log_ops.is_enabled(tmp))

    def test_disable_is_safe_when_never_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_ops.disable(tmp)  # não explode mesmo sem marker

    def test_enable_creates_the_state_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "state"
            log_ops.enable(target)
            self.assertTrue(log_ops.is_enabled(target))


class ReadLinesTest(unittest.TestCase):
    @patch("log_ops.subprocess.run")
    def test_filters_only_lines_with_known_prefixes(self, mock_run):
        mock_run.return_value = MagicMock(stdout=(
            "Oct 07 10:00:00 host kernel: some unrelated kernel line\n"
            "Oct 07 10:00:01 host kernel: pvx-fw-deny: IN=eth0 SRC=1.2.3.4\n"
            "Oct 07 10:00:02 host kernel: pvx-fw-port: IN=eth0 SRC=5.6.7.8\n"
        ))
        lines = log_ops.read_lines(tail=100)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all("pvx-fw-" in line for line in lines))

    @patch("log_ops.subprocess.run")
    def test_empty_when_journal_unavailable(self, mock_run):
        mock_run.side_effect = OSError("journalctl não encontrado")
        self.assertEqual(log_ops.read_lines(tail=50), [])


if __name__ == "__main__":
    unittest.main()
