import unittest
from unittest.mock import patch

import reachability


class IsReachableTest(unittest.TestCase):
    @patch("reachability.socket.create_connection")
    def test_returns_true_when_connection_succeeds(self, mock_connect):
        self.assertTrue(reachability.is_reachable("10.0.0.1", 22))
        mock_connect.assert_called_once_with(("10.0.0.1", 22), timeout=6)

    @patch("reachability.socket.create_connection", side_effect=OSError)
    def test_returns_false_when_connection_fails(self, mock_connect):
        self.assertFalse(reachability.is_reachable("10.0.0.1", 22))


if __name__ == "__main__":
    unittest.main()
