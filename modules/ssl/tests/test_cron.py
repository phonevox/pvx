import unittest
from unittest.mock import MagicMock, patch

import cron

MARKER = cron.MARKER


class FindManagedEntryTest(unittest.TestCase):
    def test_finds_the_line_right_after_the_marker(self):
        lines = ["0 3 * * * outro-job.sh", MARKER, "0 3 * * * certbot renew --quiet"]
        self.assertEqual(cron.find_managed_entry(lines), (2, "0 3 * * * certbot renew --quiet"))

    def test_none_when_marker_absent(self):
        self.assertIsNone(cron.find_managed_entry(["0 3 * * * outro-job.sh"]))

    def test_none_when_marker_is_the_last_line(self):
        self.assertIsNone(cron.find_managed_entry(["0 3 * * * outro-job.sh", MARKER]))


class ReadWriteCrontabTest(unittest.TestCase):
    @patch("cron.subprocess.run")
    def test_read_splits_stdout_into_lines(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="a\nb\n")
        self.assertEqual(cron.read_crontab(), ["a", "b"])

    @patch("cron.subprocess.run")
    def test_read_returns_empty_when_user_has_no_crontab(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        self.assertEqual(cron.read_crontab(), [])

    @patch("cron.subprocess.run")
    def test_write_pipes_lines_joined_by_newline_into_crontab(self, mock_run):
        cron.write_crontab(["a", "b"])
        mock_run.assert_called_once_with(["crontab", "-"], input="a\nb\n", text=True, check=True)


class EnsureScheduledTest(unittest.TestCase):
    @patch("cron.write_crontab")
    @patch("cron.read_crontab", return_value=[])
    def test_adds_marker_and_command_when_absent(self, mock_read, mock_write):
        added = cron.ensure_scheduled("apache2")
        self.assertTrue(added)
        written = mock_write.call_args.args[0]
        self.assertIn(MARKER, written)
        self.assertTrue(any("certbot renew --quiet --deploy-hook" in line for line in written))
        self.assertTrue(any("apache2" in line for line in written))

    @patch("cron.write_crontab")
    @patch("cron.read_crontab")
    def test_does_not_duplicate_when_already_scheduled(self, mock_read, mock_write):
        mock_read.return_value = [MARKER, "0 3 * * * certbot renew --quiet --deploy-hook 'x'"]
        added = cron.ensure_scheduled("apache2")
        self.assertFalse(added)
        mock_write.assert_not_called()


class RemoveScheduledTest(unittest.TestCase):
    @patch("cron.write_crontab")
    @patch("cron.read_crontab")
    def test_removes_marker_and_command(self, mock_read, mock_write):
        mock_read.return_value = ["0 3 * * * outro-job.sh", MARKER, "0 3 * * * certbot renew"]
        removed = cron.remove_scheduled()
        self.assertTrue(removed)
        mock_write.assert_called_once_with(["0 3 * * * outro-job.sh"])

    @patch("cron.write_crontab")
    @patch("cron.read_crontab", return_value=["0 3 * * * outro-job.sh"])
    def test_noop_when_nothing_scheduled(self, mock_read, mock_write):
        removed = cron.remove_scheduled()
        self.assertFalse(removed)
        mock_write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
