import unittest
from unittest.mock import patch

import issabel_detect


class IsIssabelTest(unittest.TestCase):
    @patch("issabel_detect.os.path.exists", return_value=True)
    def test_true_when_marker_exists(self, mock_exists):
        self.assertTrue(issabel_detect.is_issabel())
        mock_exists.assert_called_once_with(issabel_detect.ISSABEL_MARKER_PATH)

    @patch("issabel_detect.os.path.exists", return_value=False)
    def test_false_when_marker_is_absent(self, mock_exists):
        self.assertFalse(issabel_detect.is_issabel())


if __name__ == "__main__":
    unittest.main()
