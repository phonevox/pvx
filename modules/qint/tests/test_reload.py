import unittest
from unittest.mock import patch

import reload


class IsAsteriskAvailableTest(unittest.TestCase):
    @patch("reload.shutil.which", return_value="/usr/sbin/asterisk")
    def test_true_when_binary_is_found(self, mock_which):
        self.assertTrue(reload.is_asterisk_available())

    @patch("reload.shutil.which", return_value=None)
    def test_false_when_binary_is_missing(self, mock_which):
        self.assertFalse(reload.is_asterisk_available())


class ReloadDialplanTest(unittest.TestCase):
    @patch("reload.subprocess.run")
    @patch("reload.shutil.which", return_value="/usr/sbin/asterisk")
    def test_reloads_when_asterisk_binary_is_available(self, mock_which, mock_run):
        result = reload.reload_dialplan()
        self.assertTrue(result)
        mock_run.assert_called_once_with(["asterisk", "-rx", "dialplan reload"], check=True)

    @patch("reload.subprocess.run")
    @patch("reload.shutil.which", return_value=None)
    def test_skips_without_error_when_asterisk_binary_is_missing(self, mock_which, mock_run):
        result = reload.reload_dialplan()
        self.assertFalse(result)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
