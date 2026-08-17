import unittest
from unittest.mock import patch

import status


class GetStatusTest(unittest.TestCase):
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_iptables_protected(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertEqual(result["engine"], "iptables")
        self.assertEqual(result["session_ip"], "203.0.113.9")
        self.assertEqual(result["rule_count"], 7)
        self.assertEqual(result["protection"], "protegido")

    @patch("status.iptables_engine.failsafe_present", return_value=False)
    @patch("status.iptables_engine.count_input_rules", return_value=0)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_iptables_not_yet_synced(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertEqual(result["protection"], "não sincronizado")

    @patch("status.iptables_engine.count_input_rules", return_value=0)
    @patch("status.session_ip.detect_session_ip", return_value=None)
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_undetectable_session_ip(self, mock_resolve, mock_ip, mock_count):
        result = status.get_status(engine=None)
        self.assertIsNone(result["session_ip"])
        self.assertEqual(result["protection"], "IP da sessão não detectável")

    @patch("status.firewalld_engine.failsafe_present", return_value=True)
    @patch("status.firewalld_engine.count_rich_rules", return_value=3)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="firewalld")
    def test_dispatches_to_firewalld(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertEqual(result["engine"], "firewalld")
        self.assertEqual(result["rule_count"], 3)
        self.assertEqual(result["protection"], "protegido")
        mock_count.assert_called_once_with("pvxfw")
        mock_failsafe.assert_called_once_with("pvxfw", "203.0.113.9")


if __name__ == "__main__":
    unittest.main()
