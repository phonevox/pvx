import os
import unittest
from unittest.mock import MagicMock, patch

import session_ip


class DetectSessionIpTest(unittest.TestCase):
    def setUp(self):
        self._old_ssh_client = os.environ.get("SSH_CLIENT")

    def tearDown(self):
        if self._old_ssh_client is None:
            os.environ.pop("SSH_CLIENT", None)
        else:
            os.environ["SSH_CLIENT"] = self._old_ssh_client

    @patch("session_ip.subprocess.run")
    def test_uses_ssh_client_ip_when_who_m_has_no_match(self, mock_run):
        os.environ["SSH_CLIENT"] = "189.124.85.75 54321 22"
        mock_run.return_value = MagicMock(stdout="rocky  pts/0  2026-08-17 10:00\n")
        self.assertEqual(session_ip.detect_session_ip(), "189.124.85.75")

    @patch("session_ip.subprocess.run")
    def test_who_m_overrides_ssh_client_when_present(self, mock_run):
        os.environ["SSH_CLIENT"] = "189.124.85.75 54321 22"
        mock_run.return_value = MagicMock(stdout="rocky  pts/0  2026-08-17 10:00 (203.0.113.9)\n")
        self.assertEqual(session_ip.detect_session_ip(), "203.0.113.9")

    @patch("session_ip.subprocess.run")
    def test_returns_none_when_neither_present(self, mock_run):
        os.environ.pop("SSH_CLIENT", None)
        mock_run.return_value = MagicMock(stdout="")
        self.assertIsNone(session_ip.detect_session_ip())

    @patch("session_ip.subprocess.run")
    def test_returns_none_when_candidate_is_not_a_valid_ip(self, mock_run):
        os.environ["SSH_CLIENT"] = "not-an-ip 54321 22"
        mock_run.return_value = MagicMock(stdout="")
        self.assertIsNone(session_ip.detect_session_ip())

    @patch("session_ip.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_ssh_client_ip_when_who_command_is_unavailable(self, mock_run):
        os.environ["SSH_CLIENT"] = "189.124.85.75 54321 22"
        self.assertEqual(session_ip.detect_session_ip(), "189.124.85.75")


if __name__ == "__main__":
    unittest.main()
