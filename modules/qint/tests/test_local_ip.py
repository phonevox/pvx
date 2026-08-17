import unittest
from unittest.mock import MagicMock, patch

import local_ip


class GuessLocalIpTest(unittest.TestCase):
    @patch("local_ip.socket.socket")
    def test_returns_the_local_address_the_kernel_would_route_through(self, mock_socket_cls):
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ("10.0.0.5", 12345)
        mock_socket_cls.return_value.__enter__.return_value = mock_socket

        self.assertEqual(local_ip.guess_local_ip(), "10.0.0.5")
        mock_socket.connect.assert_called_once_with(("8.8.8.8", 80))

    @patch("local_ip.socket.socket")
    def test_returns_empty_string_when_no_route_is_available(self, mock_socket_cls):
        mock_socket_cls.return_value.__enter__.side_effect = OSError
        self.assertEqual(local_ip.guess_local_ip(), "")


if __name__ == "__main__":
    unittest.main()
