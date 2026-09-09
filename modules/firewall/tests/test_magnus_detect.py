import unittest
from unittest.mock import patch

import magnus_detect


class IsMagnusbillingTest(unittest.TestCase):
    @patch("magnus_detect.os.path.isdir", return_value=True)
    def test_true_when_mbilling_web_dir_present(self, mock_isdir):
        self.assertTrue(magnus_detect.is_magnusbilling())
        mock_isdir.assert_called_once_with("/var/www/html/mbilling")

    @patch("magnus_detect.os.path.isdir", return_value=False)
    def test_false_when_absent(self, mock_isdir):
        self.assertFalse(magnus_detect.is_magnusbilling())


if __name__ == "__main__":
    unittest.main()
