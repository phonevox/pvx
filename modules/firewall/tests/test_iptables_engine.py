import unittest
from unittest.mock import MagicMock, patch

import defaults
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


class CountConfiguredRulesTest(unittest.TestCase):
    # count_input_rules() só olha a INPUT (failsafe/established/icmp/3 jumps
    # -- sempre ~5 linhas) -- não diz nada sobre quantas entradas
    # configuradas (ip_accept/ip_deny/port_*) de fato viraram regra. As
    # entradas de verdade ficam nas chains próprias (ptrusted/pdenyip/pdrop).
    @patch("iptables_engine.chain_exists", return_value=True)
    @patch("iptables_engine.subprocess.run")
    def test_sums_rules_across_the_three_dedicated_chains(self, mock_run, mock_exists):
        header = "Chain x (policy -)\nnum  target     prot opt source               destination\n"
        mock_run.side_effect = [
            _run_result(stdout=header + "1    ACCEPT     all  --  1.2.3.4  0.0.0.0/0\n"),
            _run_result(stdout=header + "1    DROP     all  --  5.6.7.8  0.0.0.0/0\n2    DROP     all  --  9.9.9.9  0.0.0.0/0\n"),
            _run_result(stdout=header),
        ]
        self.assertEqual(ipt.count_configured_rules(), 3)

    @patch("iptables_engine.chain_exists", return_value=False)
    def test_zero_when_chains_do_not_exist_yet(self, mock_exists):
        self.assertEqual(ipt.count_configured_rules(), 0)


class ExpectedRuleCountTest(unittest.TestCase):
    def test_counts_ips_plus_one_rule_per_port_with_explicit_protocol(self):
        result = ipt.expected_rule_count(
            ip_accept=[("1.2.3.4", "")], ip_deny=[("5.6.7.8", "")],
            port_accept=[("5060/udp", "SIP")], port_deny=[],
        )
        # 1 (ip_accept) + 1 (ip_deny) + 1 (porta c/ protocolo) + 1 (catch-all final)
        self.assertEqual(result, 4)

    def test_port_without_protocol_expands_to_two_rules(self):
        result = ipt.expected_rule_count(
            ip_accept=[], ip_deny=[], port_accept=[], port_deny=[("20-23", "")],
        )
        self.assertEqual(result, 3)  # tcp + udp + catch-all


class ExpectedRulesTest(unittest.TestCase):
    def test_builds_ordered_rule_list_across_chains(self):
        rules = ipt.expected_rules(
            ip_accept=[("189.124.85.75", "PHONEVOX")],
            ip_deny=[("1.2.3.4", "banido")],
            port_accept=[("5060/udp", "SIP")],
            port_deny=[("80/tcp", "HTTP")],
        )
        self.assertIn((defaults.IPTABLES_TRUSTED_CHAIN, ["-s", "189.124.85.75", "-j", "ACCEPT"]), rules)
        self.assertIn((defaults.IPTABLES_DENY_CHAIN, ["-s", "1.2.3.4", "-j", "DROP"]), rules)
        self.assertIn((defaults.IPTABLES_PORT_CHAIN, ["-p", "tcp", "--dport", "80", "-j", "DROP"]), rules)
        self.assertIn((defaults.IPTABLES_PORT_CHAIN, ["-p", "udp", "--dport", "5060", "-j", "ACCEPT"]), rules)
        self.assertEqual(rules[-1], (defaults.IPTABLES_PORT_CHAIN, ["-j", "DROP"]))  # catch-all sempre por último


class ExpectedRulesLoggingTest(unittest.TestCase):
    def test_log_rules_omitted_by_default(self):
        rules = ipt.expected_rules(ip_accept=[], ip_deny=[("1.2.3.4", "")], port_accept=[], port_deny=[])
        self.assertEqual(
            [args for chain, args in rules if chain == defaults.IPTABLES_DENY_CHAIN],
            [["-s", "1.2.3.4", "-j", "DROP"]],
        )

    def test_log_rule_precedes_each_drop_when_enabled(self):
        rules = ipt.expected_rules(
            ip_accept=[], ip_deny=[("1.2.3.4", "")], port_accept=[], port_deny=[("80/tcp", "")], log_enabled=True,
        )
        deny_chain_rules = [args for chain, args in rules if chain == defaults.IPTABLES_DENY_CHAIN]
        self.assertEqual(
            deny_chain_rules,
            [
                ["-s", "1.2.3.4", "-m", "limit", "--limit", defaults.IPTABLES_LOG_RATE_LIMIT,
                 "-j", "LOG", "--log-prefix", defaults.LOG_PREFIX_DENY],
                ["-s", "1.2.3.4", "-j", "DROP"],
            ],
        )
        port_chain_rules = [args for chain, args in rules if chain == defaults.IPTABLES_PORT_CHAIN]
        # port_deny (log+drop) + catch-all (log+drop)
        self.assertEqual(len(port_chain_rules), 4)
        self.assertEqual(
            port_chain_rules[-2],
            ["-m", "limit", "--limit", defaults.IPTABLES_LOG_RATE_LIMIT, "-j", "LOG", "--log-prefix", defaults.LOG_PREFIX_PORT],
        )
        self.assertEqual(port_chain_rules[-1], ["-j", "DROP"])


class ExpectedRulesGeoTest(unittest.TestCase):
    def test_geo_chain_omitted_by_default(self):
        rules = ipt.expected_rules(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[])
        self.assertEqual([args for chain, args in rules if chain == defaults.IPTABLES_GEO_CHAIN], [])

    def test_geo_chain_has_match_set_return_then_catch_all_drop_when_enabled(self):
        rules = ipt.expected_rules(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], geo_enabled=True)
        geo_rules = [args for chain, args in rules if chain == defaults.IPTABLES_GEO_CHAIN]
        self.assertEqual(
            geo_rules,
            [
                ["-m", "set", "--match-set", defaults.GEO_IPSET_NAME, "src", "-j", "RETURN"],
                ["-j", "DROP"],
            ],
        )


class ExpectedRuleCountLoggingTest(unittest.TestCase):
    def test_counts_log_rules_when_enabled(self):
        without_log = ipt.expected_rule_count(
            ip_accept=[], ip_deny=[("1.2.3.4", "")], port_accept=[], port_deny=[("80/tcp", "")],
        )
        with_log = ipt.expected_rule_count(
            ip_accept=[], ip_deny=[("1.2.3.4", "")], port_accept=[], port_deny=[("80/tcp", "")], log_enabled=True,
        )
        self.assertEqual(without_log, 3)  # ip_deny + port_deny + catch-all
        self.assertEqual(with_log, without_log + 3)  # log do deny + log do port_deny + log do catch-all

    def test_counts_the_geo_chain_when_enabled(self):
        without_geo = ipt.expected_rule_count(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[])
        with_geo = ipt.expected_rule_count(
            ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], geo_enabled=True,
        )
        self.assertEqual(with_geo, without_geo + 2)  # match-set RETURN + catch-all DROP


class RulesMatchExpectedTest(unittest.TestCase):
    def _mock_chains(self, mock_run, per_chain_stdout):
        def fake_run(args, **kwargs):
            chain = args[2]
            return _run_result(stdout=per_chain_stdout.get(chain, f"-N {chain}\n"), returncode=0)
        mock_run.side_effect = fake_run

    @patch("iptables_engine.subprocess.run")
    def test_true_when_live_rules_mirror_expected_exactly(self, mock_run):
        self._mock_chains(mock_run, {
            defaults.IPTABLES_TRUSTED_CHAIN: "-N ptrusted\n-A ptrusted -s 189.124.85.75 -j ACCEPT\n",
            defaults.IPTABLES_PORT_CHAIN: "-N pdrop\n-A pdrop -j DROP\n",
        })
        self.assertTrue(ipt.rules_match_expected(
            ip_accept=[("189.124.85.75", "")], ip_deny=[], port_accept=[], port_deny=[],
        ))

    @patch("iptables_engine.subprocess.run")
    def test_false_when_a_chain_is_missing_the_expected_rule(self, mock_run):
        # catch-all sumiu de pdrop -- sem ele, portas não cobertas por
        # port_accept ficariam abertas pro mundo.
        self._mock_chains(mock_run, {})
        self.assertFalse(ipt.rules_match_expected(
            ip_accept=[], ip_deny=[], port_accept=[], port_deny=[],
        ))

    @patch("iptables_engine.subprocess.run")
    def test_true_with_logging_enabled_matches_quoted_log_prefix(self, mock_run):
        # iptables -S devolve --log-prefix entre aspas quando o valor tem
        # espaço -- a comparação tem que reproduzir essa mesma forma, senão
        # dá falso negativo (reporta divergência onde não há nenhuma).
        self._mock_chains(mock_run, {
            defaults.IPTABLES_DENY_CHAIN: (
                "-N pdenyip\n"
                f'-A pdenyip -s 1.2.3.4 -m limit --limit {defaults.IPTABLES_LOG_RATE_LIMIT} '
                f'-j LOG --log-prefix "{defaults.LOG_PREFIX_DENY}"\n'
                "-A pdenyip -s 1.2.3.4 -j DROP\n"
            ),
            defaults.IPTABLES_PORT_CHAIN: (
                "-N pdrop\n"
                f'-A pdrop -m limit --limit {defaults.IPTABLES_LOG_RATE_LIMIT} '
                f'-j LOG --log-prefix "{defaults.LOG_PREFIX_PORT}"\n'
                "-A pdrop -j DROP\n"
            ),
        })
        self.assertTrue(ipt.rules_match_expected(
            ip_accept=[], ip_deny=[("1.2.3.4", "")], port_accept=[], port_deny=[], log_enabled=True,
        ))

    @patch("iptables_engine.subprocess.run")
    def test_true_with_geo_enabled_matches_the_geo_chain(self, mock_run):
        self._mock_chains(mock_run, {
            defaults.IPTABLES_GEO_CHAIN: (
                "-N pgeo\n"
                f"-A pgeo -m set --match-set {defaults.GEO_IPSET_NAME} src -j RETURN\n"
                "-A pgeo -j DROP\n"
            ),
            defaults.IPTABLES_PORT_CHAIN: "-N pdrop\n-A pdrop -j DROP\n",
        })
        self.assertTrue(ipt.rules_match_expected(
            ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], geo_enabled=True,
        ))

    @patch("iptables_engine.subprocess.run")
    def test_false_when_geo_chain_is_missing_its_rules(self, mock_run):
        self._mock_chains(mock_run, {})
        self.assertFalse(ipt.rules_match_expected(
            ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], geo_enabled=True,
        ))

    @patch("iptables_engine.subprocess.run")
    def test_false_when_rule_order_differs(self, mock_run):
        # achado ao vivo: o catch-all tem que ser a ÚLTIMA regra -- se virar
        # a primeira (mesmo conjunto de linhas, ordem diferente), o accept
        # que vem depois nunca é avaliado. Comparação tem que ser sensível a
        # ordem, não só ao conjunto de regras presentes.
        self._mock_chains(mock_run, {
            defaults.IPTABLES_PORT_CHAIN: "-N pdrop\n-A pdrop -j DROP\n-A pdrop -p tcp --dport 80 -j ACCEPT\n",
        })
        self.assertFalse(ipt.rules_match_expected(
            ip_accept=[], ip_deny=[], port_accept=[("80/tcp", "")], port_deny=[],
        ))


class ChainDropCountersTest(unittest.TestCase):
    @patch("iptables_engine.subprocess.run")
    def test_sums_only_drop_target_rules(self, mock_run):
        mock_run.return_value = _run_result(stdout=(
            "Chain pdrop (1 references)\n"
            "    pkts      bytes target     prot opt in     out     source               destination\n"
            "       5      400 ACCEPT     udp  --  *      *       0.0.0.0/0            0.0.0.0/0            udp dpt:5060\n"
            "      42     3360 DROP       tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:80\n"
            "     100     8000 DROP       all  --  *      *       0.0.0.0/0            0.0.0.0/0\n"
        ))
        self.assertEqual(ipt.chain_drop_counters("pdrop"), {"packets": 142, "bytes": 11360})

    @patch("iptables_engine.subprocess.run")
    def test_zero_when_chain_listing_fails(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertEqual(ipt.chain_drop_counters("pdrop"), {"packets": 0, "bytes": 0})


class DroppedCountersTest(unittest.TestCase):
    @patch("iptables_engine.chain_drop_counters")
    def test_sums_across_deny_ip_and_port_chains(self, mock_counters):
        # pdenyip e pdrop são as duas chains que de fato dropam pacote hoje --
        # ptrusted só tem ACCEPT, não entra na conta.
        def fake(chain):
            return {
                defaults.IPTABLES_DENY_CHAIN: {"packets": 10, "bytes": 1000},
                defaults.IPTABLES_PORT_CHAIN: {"packets": 5, "bytes": 500},
            }[chain]
        mock_counters.side_effect = fake
        self.assertEqual(ipt.dropped_counters(), {"packets": 15, "bytes": 1500})


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
    @patch("iptables_engine.insert_failsafe", return_value=True)
    @patch("iptables_engine.subprocess.run")
    def test_geo_chain_is_created_and_jumped_to_between_trusted_and_port_when_enabled(
        self, mock_run, mock_failsafe, mock_clear
    ):
        mock_run.return_value = _run_result(returncode=0)

        ipt.sync(
            ip_accept=[], ip_deny=[], port_accept=[], port_deny=[],
            failsafe_ip="203.0.113.9", geo_enabled=True,
        )

        commands = [c.args[0] for c in mock_run.call_args_list]
        # chain_exists (mockado como sempre-existente aqui) faz ensure_chain
        # flushar em vez de criar -- o que importa é que ela é preparada.
        self.assertIn(["iptables", "-F", "pgeo"], commands)
        jump_targets = [c[-1] for c in commands if c[:3] == ["iptables", "-A", "INPUT"]]
        self.assertEqual(jump_targets[-4:], ["pdenyip", "ptrusted", "pgeo", "pdrop"])

    @patch("iptables_engine.clear_input_except_failsafe")
    @patch("iptables_engine.insert_failsafe", return_value=True)
    @patch("iptables_engine.subprocess.run")
    def test_geo_chain_is_not_created_or_jumped_to_by_default(self, mock_run, mock_failsafe, mock_clear):
        mock_run.return_value = _run_result(returncode=0)

        ipt.sync(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[], failsafe_ip="203.0.113.9")

        commands = [c.args[0] for c in mock_run.call_args_list]
        self.assertNotIn(["iptables", "-N", "pgeo"], commands)
        self.assertNotIn(["iptables", "-F", "pgeo"], commands)
        jump_targets = [c[-1] for c in commands if c[:3] == ["iptables", "-A", "INPUT"]]
        self.assertNotIn("pgeo", jump_targets)

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
