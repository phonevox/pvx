import subprocess
import unittest
from unittest.mock import MagicMock, patch

import firewalld_engine as fwd


def _run_result(stdout="", returncode=0):
    return MagicMock(stdout=stdout, returncode=returncode)


class ZoneExistsTest(unittest.TestCase):
    @patch("firewalld_engine.subprocess.run")
    def test_true_when_zone_info_succeeds(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        self.assertTrue(fwd.zone_exists("pvxfw"))

    @patch("firewalld_engine.subprocess.run")
    def test_false_when_zone_info_fails(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertFalse(fwd.zone_exists("pvxfw"))


class EnsureZoneTest(unittest.TestCase):
    @patch("firewalld_engine.zone_exists", return_value=False)
    @patch("firewalld_engine.subprocess.run")
    def test_creates_zone_when_absent_then_sets_target_and_default(self, mock_run, mock_exists):
        fwd.ensure_zone("pvxfw")
        commands = [c.args[0] for c in mock_run.call_args_list]
        self.assertIn(["firewall-cmd", "--permanent", "--new-zone", "pvxfw"], commands)
        self.assertIn(["firewall-cmd", "--reload"], commands)
        self.assertIn(["firewall-cmd", "--permanent", "--zone", "pvxfw", "--set-target", "DROP"], commands)
        self.assertIn(["firewall-cmd", "--set-default-zone", "pvxfw"], commands)

    @patch("firewalld_engine.zone_exists", return_value=True)
    @patch("firewalld_engine.subprocess.run")
    def test_skips_creation_when_zone_already_present(self, mock_run, mock_exists):
        fwd.ensure_zone("pvxfw")
        commands = [c.args[0] for c in mock_run.call_args_list]
        self.assertNotIn(["firewall-cmd", "--permanent", "--new-zone", "pvxfw"], commands)
        self.assertIn(["firewall-cmd", "--permanent", "--zone", "pvxfw", "--set-target", "DROP"], commands)


class FailsafeTest(unittest.TestCase):
    @patch("firewalld_engine.subprocess.run")
    def test_inserts_failsafe_rich_rule_when_absent_and_confirms_it(self, mock_run):
        mock_run.side_effect = [_run_result(returncode=1), _run_result(), _run_result(returncode=0)]
        result = fwd.insert_failsafe("pvxfw", "189.124.85.75")
        self.assertTrue(result)
        insert_call = mock_run.call_args_list[1]
        self.assertEqual(insert_call.args[0][:3], ["firewall-cmd", "--zone", "pvxfw"])
        self.assertEqual(insert_call.args[0][3], "--add-rich-rule")
        rule = insert_call.args[0][4]
        self.assertIn('priority="-2000"', rule)
        self.assertIn('source address="189.124.85.75"', rule)
        self.assertIn("accept", rule)

    @patch("firewalld_engine.subprocess.run")
    def test_reports_failure_when_rule_cannot_be_confirmed_after_insert(self, mock_run):
        mock_run.side_effect = [_run_result(returncode=1), _run_result(), _run_result(returncode=1)]
        self.assertFalse(fwd.insert_failsafe("pvxfw", "189.124.85.75"))

    @patch("firewalld_engine.subprocess.run")
    def test_skips_insert_when_rule_already_present(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        self.assertTrue(fwd.insert_failsafe("pvxfw", "189.124.85.75"))
        self.assertEqual(mock_run.call_count, 1)


class ClearZoneExceptFailsafeTest(unittest.TestCase):
    @patch("firewalld_engine.subprocess.run")
    def test_removes_every_rich_rule_except_the_failsafe(self, mock_run):
        failsafe_rule = 'rule priority="-2000" family="ipv4" source address="189.124.85.75" accept'
        other_rule = 'rule priority="200" family="ipv4" port port="5060" protocol="udp" accept'
        listing = _run_result(stdout=f"{failsafe_rule}\n{other_rule}\n")
        mock_run.side_effect = [listing, _run_result()]

        fwd.clear_zone_except_failsafe("pvxfw", failsafe_rule)

        remove_call = mock_run.call_args_list[1]
        self.assertEqual(remove_call.args[0], ["firewall-cmd", "--zone", "pvxfw", "--remove-rich-rule", other_rule])

    @patch("firewalld_engine.subprocess.run")
    def test_removes_everything_when_no_failsafe_rule(self, mock_run):
        listing = _run_result(stdout='rule priority="200" family="ipv4" port port="80" protocol="tcp" accept\n')
        mock_run.side_effect = [listing, _run_result()]
        fwd.clear_zone_except_failsafe("pvxfw", None)
        self.assertEqual(mock_run.call_count, 2)


class PortRuleArgsTest(unittest.TestCase):
    def test_single_port_native_range(self):
        self.assertEqual(
            fwd.port_rule_args({"start": 80, "end": 80, "protocol": "tcp"}),
            [("80", "tcp")],
        )

    def test_range_uses_hyphen_syntax(self):
        self.assertEqual(
            fwd.port_rule_args({"start": 10000, "end": 20000, "protocol": "udp"}),
            [("10000-20000", "udp")],
        )

    def test_no_protocol_defaults_to_tcp_and_udp(self):
        self.assertEqual(
            fwd.port_rule_args({"start": 20, "end": 23, "protocol": None}),
            [("20-23", "tcp"), ("20-23", "udp")],
        )


class CountRichRulesTest(unittest.TestCase):
    @patch("firewalld_engine.subprocess.run")
    def test_counts_non_blank_lines(self, mock_run):
        mock_run.return_value = _run_result(stdout=(
            'rule priority="-2000" family="ipv4" source address="189.124.85.75" accept\n'
            'rule priority="200" family="ipv4" port port="5060" protocol="udp" accept\n'
        ))
        self.assertEqual(fwd.count_rich_rules("pvxfw"), 2)

    @patch("firewalld_engine.subprocess.run")
    def test_returns_zero_when_zone_does_not_exist_yet(self, mock_run):
        # antes do primeiro sync a zona pvxfw nem existe -- --list-rich-rules
        # falha; com check=True isso levantaria CalledProcessError de verdade
        # (comportamento real do subprocess.run), não pode virar exceção
        # crua no status -- daí o fake_run respeitar o kwarg "check" de
        # verdade, não só devolver um returncode fixo.
        def fake_run(args, **kwargs):
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, args)
            return _run_result(returncode=1)

        mock_run.side_effect = fake_run
        self.assertEqual(fwd.count_rich_rules("pvxfw"), 0)


class FailsafePresentTest(unittest.TestCase):
    @patch("firewalld_engine.subprocess.run")
    def test_true_when_query_succeeds(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        self.assertTrue(fwd.failsafe_present("pvxfw", "189.124.85.75"))

    @patch("firewalld_engine.subprocess.run")
    def test_false_when_query_fails(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertFalse(fwd.failsafe_present("pvxfw", "189.124.85.75"))


class SyncTest(unittest.TestCase):
    @patch("firewalld_engine.clear_zone_except_failsafe")
    @patch("firewalld_engine.insert_failsafe", return_value=True)
    @patch("firewalld_engine.ensure_zone")
    @patch("firewalld_engine.subprocess.run")
    def test_populates_zone_with_rich_rules(self, mock_run, mock_ensure, mock_failsafe, mock_clear):
        mock_run.return_value = _run_result(returncode=0)

        fwd.sync(
            ip_accept=[("189.124.85.75", "PHONEVOX")],
            ip_deny=[("1.2.3.4", "banido")],
            port_accept=[("5060/udp", "SIP")],
            port_deny=[("80/tcp", "HTTP")],
            failsafe_ip="203.0.113.9",
        )

        mock_ensure.assert_called_once_with("pvxfw")
        mock_failsafe.assert_called_once_with("pvxfw", "203.0.113.9")
        mock_clear.assert_called_once()

        rules = [
            c.args[0][4] for c in mock_run.call_args_list if c.args[0][3:4] == ["--add-rich-rule"]
        ]
        self.assertTrue(any('source address="189.124.85.75"' in r and "accept" in r for r in rules))
        self.assertTrue(any('source address="1.2.3.4"' in r and "drop" in r for r in rules))
        self.assertTrue(any('port="5060"' in r and 'protocol="udp"' in r and "accept" in r for r in rules))
        self.assertTrue(any('port="80"' in r and 'protocol="tcp"' in r and "drop" in r for r in rules))
        self.assertTrue(any("icmp" in r for r in rules))

        self.assertIn(["firewall-cmd", "--reload"], [c.args[0] for c in mock_run.call_args_list])

    @patch("firewalld_engine.clear_zone_except_failsafe")
    @patch("firewalld_engine.insert_failsafe", return_value=False)
    @patch("firewalld_engine.ensure_zone")
    @patch("firewalld_engine.subprocess.run")
    def test_aborts_without_clearing_when_failsafe_cannot_be_confirmed(
        self, mock_run, mock_ensure, mock_failsafe, mock_clear
    ):
        with self.assertRaises(RuntimeError):
            fwd.sync(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], failsafe_ip="203.0.113.9")
        mock_clear.assert_not_called()

    @patch("firewalld_engine.clear_zone_except_failsafe")
    @patch("firewalld_engine.ensure_zone")
    @patch("firewalld_engine.subprocess.run")
    def test_skips_failsafe_entirely_when_no_session_ip(self, mock_run, mock_ensure, mock_clear):
        mock_run.return_value = _run_result(returncode=0)
        fwd.sync(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], failsafe_ip=None)
        mock_clear.assert_called_once_with("pvxfw", None)


if __name__ == "__main__":
    unittest.main()
