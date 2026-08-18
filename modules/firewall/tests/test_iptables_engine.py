import unittest
from unittest.mock import MagicMock, patch

import iptables_engine as ipt


def _run_result(stdout="", returncode=0):
    return MagicMock(stdout=stdout, returncode=returncode)


class ChainExistsTest(unittest.TestCase):
    @patch("iptables_engine.subprocess.run")
    def test_true_when_chain_lists_successfully(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        self.assertTrue(ipt.chain_exists("ptrusted"))

    @patch("iptables_engine.subprocess.run")
    def test_false_when_chain_listing_fails(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertFalse(ipt.chain_exists("ptrusted"))


class EnsureChainTest(unittest.TestCase):
    @patch("iptables_engine.chain_exists", return_value=False)
    @patch("iptables_engine.subprocess.run")
    def test_creates_chain_when_absent(self, mock_run, mock_exists):
        ipt.ensure_chain("ptrusted")
        mock_run.assert_called_once_with(["iptables", "-N", "ptrusted"], capture_output=True, text=True, check=True)

    @patch("iptables_engine.chain_exists", return_value=True)
    @patch("iptables_engine.subprocess.run")
    def test_flushes_chain_when_already_present(self, mock_run, mock_exists):
        ipt.ensure_chain("ptrusted")
        mock_run.assert_called_once_with(["iptables", "-F", "ptrusted"], capture_output=True, text=True, check=True)


class FailsafeTest(unittest.TestCase):
    @patch("iptables_engine.subprocess.run")
    def test_inserts_failsafe_rule_when_absent_and_confirms_it(self, mock_run):
        mock_run.side_effect = [_run_result(returncode=1), _run_result(), _run_result(returncode=0)]
        result = ipt.insert_failsafe("189.124.85.75")
        self.assertTrue(result)
        insert_call = mock_run.call_args_list[1]
        self.assertEqual(
            insert_call.args[0], ["iptables", "-I", "INPUT", "1", "-s", "189.124.85.75", "-j", "ACCEPT"]
        )

    @patch("iptables_engine.subprocess.run")
    def test_reports_failure_when_rule_cannot_be_confirmed_after_insert(self, mock_run):
        mock_run.side_effect = [_run_result(returncode=1), _run_result(), _run_result(returncode=1)]
        self.assertFalse(ipt.insert_failsafe("189.124.85.75"))

    @patch("iptables_engine.subprocess.run")
    def test_skips_insert_when_rule_already_present(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        self.assertTrue(ipt.insert_failsafe("189.124.85.75"))
        self.assertEqual(mock_run.call_count, 1)  # só o -C, nunca tenta inserir de novo


class ClearInputExceptFailsafeTest(unittest.TestCase):
    @patch("iptables_engine.subprocess.run")
    def test_deletes_every_rule_except_the_one_matching_the_failsafe_ip(self, mock_run):
        listing = _run_result(stdout=(
            "Chain INPUT (policy DROP)\n"
            "num  target     prot opt source               destination\n"
            "1    ACCEPT     all  --  189.124.85.75        0.0.0.0/0\n"
            "2    ACCEPT     all  --  0.0.0.0/0            0.0.0.0/0            state RELATED,ESTABLISHED\n"
            "3    DROP       all  --  1.2.3.4              0.0.0.0/0\n"
        ))
        mock_run.side_effect = [listing, _run_result(), _run_result()]

        ipt.clear_input_except_failsafe("189.124.85.75")

        delete_calls = mock_run.call_args_list[1:]
        deleted_lines = [c.args[0][3] for c in delete_calls]
        self.assertEqual(sorted(deleted_lines), ["2", "3"])

    @patch("iptables_engine.subprocess.run")
    def test_deletes_everything_when_no_failsafe_ip(self, mock_run):
        listing = _run_result(stdout=(
            "Chain INPUT (policy DROP)\n"
            "num  target     prot opt source               destination\n"
            "1    ACCEPT     all  --  0.0.0.0/0            0.0.0.0/0            state RELATED,ESTABLISHED\n"
        ))
        mock_run.side_effect = [listing, _run_result()]

        ipt.clear_input_except_failsafe(None)

        self.assertEqual(mock_run.call_count, 2)


class BuildPortRuleArgsTest(unittest.TestCase):
    def test_single_port_uses_dport(self):
        self.assertEqual(
            ipt.port_rule_args({"start": 80, "end": 80, "protocol": "tcp"}),
            ["-p", "tcp", "--dport", "80"],
        )

    def test_range_uses_colon_syntax(self):
        self.assertEqual(
            ipt.port_rule_args({"start": 10000, "end": 20000, "protocol": "udp"}),
            ["-p", "udp", "--dport", "10000:20000"],
        )

    def test_no_protocol_defaults_to_tcp_and_udp(self):
        self.assertEqual(
            ipt.port_rule_args({"start": 20, "end": 23, "protocol": None}),
            [["-p", "tcp", "--dport", "20:23"], ["-p", "udp", "--dport", "20:23"]],
        )


class CountInputRulesTest(unittest.TestCase):
    @patch("iptables_engine.subprocess.run")
    def test_counts_rule_lines_excluding_header(self, mock_run):
        mock_run.return_value = _run_result(stdout=(
            "Chain INPUT (policy DROP)\n"
            "num  target     prot opt source               destination\n"
            "1    ACCEPT     all  --  189.124.85.75        0.0.0.0/0\n"
            "2    ACCEPT     all  --  0.0.0.0/0            0.0.0.0/0\n"
        ))
        self.assertEqual(ipt.count_input_rules(), 2)


class SyncTest(unittest.TestCase):
    @patch("iptables_engine.clear_input_except_failsafe")
    @patch("iptables_engine.insert_failsafe", return_value=True)
    @patch("iptables_engine.subprocess.run")
    def test_populates_chains_and_input_jump_order(self, mock_run, mock_failsafe, mock_clear):
        mock_run.return_value = _run_result(returncode=0)  # ensure_chain's chain_exists check

        ipt.sync(
            ip_accept=[("189.124.85.75", "PHONEVOX")],
            ip_deny=[("1.2.3.4", "banido")],
            port_accept=[("5060/udp", "SIP")],
            port_deny=[("80/tcp", "HTTP")],
            failsafe_ip="203.0.113.9",
        )

        mock_failsafe.assert_called_once_with("203.0.113.9")
        mock_clear.assert_called_once_with("203.0.113.9")

        commands = [c.args[0] for c in mock_run.call_args_list]
        self.assertIn(["iptables", "-A", "ptrusted", "-s", "189.124.85.75", "-j", "ACCEPT"], commands)
        self.assertIn(["iptables", "-A", "pdenyip", "-s", "1.2.3.4", "-j", "DROP"], commands)
        self.assertIn(["iptables", "-A", "pdrop", "-p", "udp", "--dport", "5060", "-j", "ACCEPT"], commands)
        self.assertIn(["iptables", "-A", "pdrop", "-p", "tcp", "--dport", "80", "-j", "DROP"], commands)
        self.assertIn(["iptables", "-A", "pdrop", "-j", "DROP"], commands)  # catch-all no fim

        # ordem do INPUT: established -> icmp -> pdenyip -> ptrusted -> pdrop
        jump_targets = [c[-1] for c in commands if c[:3] == ["iptables", "-A", "INPUT"]]
        self.assertEqual(jump_targets[-3:], ["pdenyip", "ptrusted", "pdrop"])

    @patch("iptables_engine.clear_input_except_failsafe")
    @patch("iptables_engine.insert_failsafe", return_value=False)
    @patch("iptables_engine.subprocess.run")
    def test_aborts_without_clearing_when_failsafe_cannot_be_confirmed(
        self, mock_run, mock_failsafe, mock_clear
    ):
        with self.assertRaises(RuntimeError):
            ipt.sync(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], failsafe_ip="203.0.113.9")
        mock_clear.assert_not_called()

    @patch("iptables_engine.clear_input_except_failsafe")
    @patch("iptables_engine.subprocess.run")
    def test_skips_failsafe_entirely_when_no_session_ip(self, mock_run, mock_clear):
        mock_run.return_value = _run_result(returncode=0)
        ipt.sync(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], failsafe_ip=None)
        mock_clear.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
