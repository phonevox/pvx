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
        # achado ao vivo (testando com firewalld real): sem --permanent aqui,
        # o --reload no fim de sync() descarta a regra silenciosamente --
        # tudo que sync() monta precisa ser permanent, só o reload final
        # promove pro runtime de uma vez.
        self.assertIn("--permanent", insert_call.args[0])
        self.assertIn("--add-rich-rule", insert_call.args[0])
        rule = insert_call.args[0][insert_call.args[0].index("--add-rich-rule") + 1]
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

        listing_call = mock_run.call_args_list[0]
        remove_call = mock_run.call_args_list[1]
        self.assertIn("--permanent", listing_call.args[0])
        self.assertIn("--permanent", remove_call.args[0])
        self.assertIn("--remove-rich-rule", remove_call.args[0])
        self.assertEqual(
            remove_call.args[0][remove_call.args[0].index("--remove-rich-rule") + 1], other_rule,
        )

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


class ExpectedRuleCountTest(unittest.TestCase):
    def test_counts_ips_plus_one_rule_per_port_with_explicit_protocol(self):
        result = fwd.expected_rule_count(
            ip_accept=[("1.2.3.4", "")], ip_deny=[("5.6.7.8", "")],
            port_accept=[("5060/udp", "SIP")], port_deny=[],
        )
        # 1 (ip_accept) + 1 (ip_deny) + 1 (icmp) + 1 (porta c/ protocolo)
        self.assertEqual(result, 4)

    def test_port_without_protocol_expands_to_two_rules(self):
        result = fwd.expected_rule_count(
            ip_accept=[], ip_deny=[], port_accept=[], port_deny=[("20-23", "")],
        )
        self.assertEqual(result, 3)  # icmp + tcp + udp


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


class RemoveConflictingPortsTest(unittest.TestCase):
    # achado ao vivo (MagnusBilling): o instalador do Magnus abre porta 22/tcp pra
    # QUALQUER origem via --add-port simples na zona "public" -- isso é avaliado
    # ANTES da nossa rich-rule de port_deny (prioridade positiva), então o allow
    # do Magnus sempre ganha e a 22 fica acessível de fora mesmo com "20-23" no
    # port_deny. Só dá pra fazer o port_deny valer de verdade removendo a porta
    # aberta do Magnus quando ela cai dentro de uma faixa que a gente bloqueia.
    @patch("firewalld_engine.subprocess.run")
    def test_removes_an_existing_port_that_falls_inside_a_denied_range(self, mock_run):
        listing = _run_result(stdout="22/tcp 80/tcp 443/tcp\n")
        mock_run.side_effect = [listing, _run_result()]

        fwd.remove_conflicting_ports("public", [("20-23", "ftp/ssh/telnet")])

        remove_call = mock_run.call_args_list[1]
        self.assertIn("--remove-port", remove_call.args[0])
        self.assertEqual(remove_call.args[0][remove_call.args[0].index("--remove-port") + 1], "22/tcp")

    @patch("firewalld_engine.subprocess.run")
    def test_keeps_ports_outside_any_denied_range(self, mock_run):
        listing = _run_result(stdout="5060/udp\n")
        mock_run.side_effect = [listing]

        fwd.remove_conflicting_ports("public", [("20-23", "ftp/ssh/telnet")])

        self.assertEqual(mock_run.call_count, 1)  # só o --list-ports, nada removido

    @patch("firewalld_engine.subprocess.run")
    def test_respects_the_protocol_in_the_deny_spec(self, mock_run):
        listing = _run_result(stdout="22/udp\n")
        mock_run.side_effect = [listing]

        fwd.remove_conflicting_ports("public", [("22/tcp", "SSH")])  # só tcp -- 22/udp não bate

        self.assertEqual(mock_run.call_count, 1)

    @patch("firewalld_engine.subprocess.run")
    def test_no_op_when_zone_has_no_plain_ports(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        fwd.remove_conflicting_ports("public", [("20-23", "x")])
        self.assertEqual(mock_run.call_count, 1)


class RemoveConflictingServicesTest(unittest.TestCase):
    # achado ao vivo (MagnusBilling): além da porta 22/tcp simples, a zona "public"
    # também tem o SERVIÇO nomeado "ssh" (mecanismo separado de --list-ports,
    # também avaliado antes das rich-rules) -- reabria a 22 mesmo depois da porta
    # simples já ter sido removida.
    @patch("firewalld_engine.subprocess.run")
    def test_removes_a_service_whose_port_falls_inside_a_denied_range(self, mock_run):
        services_listing = _run_result(stdout="dhcpv6-client ssh\n")
        ssh_info = _run_result(stdout="ssh\n  ports: 22/tcp\n  protocols: \n")
        dhcp_info = _run_result(stdout="dhcpv6-client\n  ports: 546/udp\n  protocols: \n")
        mock_run.side_effect = [services_listing, dhcp_info, ssh_info, _run_result()]

        fwd.remove_conflicting_services("public", [("20-23", "x")])

        remove_call = mock_run.call_args_list[-1]
        self.assertIn("--remove-service", remove_call.args[0])
        self.assertEqual(remove_call.args[0][remove_call.args[0].index("--remove-service") + 1], "ssh")

    @patch("firewalld_engine.subprocess.run")
    def test_keeps_services_outside_any_denied_range(self, mock_run):
        services_listing = _run_result(stdout="dhcpv6-client\n")
        dhcp_info = _run_result(stdout="dhcpv6-client\n  ports: 546/udp\n  protocols: \n")
        mock_run.side_effect = [services_listing, dhcp_info]

        fwd.remove_conflicting_services("public", [("20-23", "x")])

        self.assertEqual(mock_run.call_count, 2)  # list-services + info-service, nada removido

    @patch("firewalld_engine.subprocess.run")
    def test_no_op_when_zone_has_no_services(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        fwd.remove_conflicting_services("public", [("20-23", "x")])
        self.assertEqual(mock_run.call_count, 1)


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

        add_calls = [c.args[0] for c in mock_run.call_args_list if "--add-rich-rule" in c.args[0]]
        rules = [args[args.index("--add-rich-rule") + 1] for args in add_calls]
        # achado ao vivo (testando com firewalld real): sem --permanent aqui,
        # o --reload no fim de sync() descartava toda regra silenciosamente.
        self.assertTrue(all("--permanent" in args for args in add_calls))
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

    @patch("firewalld_engine.remove_conflicting_services")
    @patch("firewalld_engine.remove_conflicting_ports")
    @patch("firewalld_engine.clear_zone_except_failsafe")
    @patch("firewalld_engine.ensure_zone")
    @patch("firewalld_engine.subprocess.run")
    def test_never_touches_foreign_ports_of_its_own_zone(
        self, mock_run, mock_ensure, mock_clear, mock_remove_ports, mock_remove_services
    ):
        # a zona própria (pvxfw) nunca tem porta/serviço de outra ferramenta pra
        # reconciliar -- isso só existe integrando numa zona alheia.
        mock_run.return_value = _run_result(returncode=0)
        fwd.sync(ip_accept=[], ip_deny=[], port_accept=[], port_deny=[("20-23", "x")], failsafe_ip=None)
        mock_remove_ports.assert_not_called()
        mock_remove_services.assert_not_called()

    @patch("firewalld_engine.remove_conflicting_services")
    @patch("firewalld_engine.remove_conflicting_ports")
    @patch("firewalld_engine.clear_zone_except_failsafe")
    @patch("firewalld_engine.insert_failsafe", return_value=True)
    @patch("firewalld_engine.ensure_zone")
    @patch("firewalld_engine.subprocess.run")
    def test_reconciles_ports_and_services_when_integrating_into_a_foreign_zone(
        self, mock_run, mock_ensure, mock_failsafe, mock_clear, mock_remove_ports, mock_remove_services
    ):
        mock_run.return_value = _run_result(returncode=0)
        fwd.sync(
            ip_accept=[], ip_deny=[], port_accept=[], port_deny=[("20-23", "x")],
            failsafe_ip="203.0.113.9", zone="public", manage_zone=False,
        )
        mock_remove_ports.assert_called_once_with("public", [("20-23", "x")])
        mock_remove_services.assert_called_once_with("public", [("20-23", "x")])

    @patch("firewalld_engine.clear_zone_except_failsafe")
    @patch("firewalld_engine.insert_failsafe", return_value=True)
    @patch("firewalld_engine.ensure_zone")
    @patch("firewalld_engine.subprocess.run")
    def test_syncs_into_a_foreign_zone_without_taking_it_over(
        self, mock_run, mock_ensure, mock_failsafe, mock_clear
    ):
        # manage_zone=False -- nunca cria/define target/vira default-zone de uma
        # zona que não é nossa.
        mock_run.return_value = _run_result(returncode=0)
        fwd.sync(
            ip_accept=[("189.124.85.75", "PHONEVOX")], ip_deny=[], port_accept=[], port_deny=[],
            failsafe_ip="203.0.113.9", zone="public", manage_zone=False,
        )
        mock_ensure.assert_not_called()
        mock_failsafe.assert_called_once_with("public", "203.0.113.9")
        expected_failsafe_rule = fwd._rich_rule(fwd.defaults.FIREWALLD_PRIORITY_FAILSAFE, source="203.0.113.9")
        mock_clear.assert_called_once_with("public", expected_failsafe_rule)
        add_calls = [c.args[0] for c in mock_run.call_args_list if "--add-rich-rule" in c.args[0]]
        self.assertTrue(all(args[args.index("--zone") + 1] == "public" for args in add_calls))


if __name__ == "__main__":
    unittest.main()
