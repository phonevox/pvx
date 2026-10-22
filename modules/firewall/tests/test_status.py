import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import status


class GetStatusTest(unittest.TestCase):
    def setUp(self):
        # chamado incondicionalmente em todo get_status() agora -- sem isso
        # os testes que não mockam explicitamente bateriam um systemctl de
        # verdade.
        patcher = patch("status.systemd_unit.is_enabled", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        # idem -- a checagem de engine concorrente agora chama
        # service_is_active pro engine QUE NÃO é o escolhido, em todo
        # get_status(). Default: nenhum concorrente ativo.
        competing_patcher = patch("status.engine_detect.service_is_active", return_value=False)
        competing_patcher.start()
        self.addCleanup(competing_patcher.stop)

        # idem -- dropped_counters() agora é chamado incondicionalmente no
        # caminho iptables.
        counters_patcher = patch(
            "status.iptables_engine.dropped_counters", return_value={"packets": 0, "bytes": 0},
        )
        counters_patcher.start()
        self.addCleanup(counters_patcher.stop)

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_iptables_synced_and_protected(self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertEqual(result["engine"], "iptables")
        self.assertEqual(result["session_ip"], "203.0.113.9")
        self.assertEqual(result["rule_count"], 7)
        self.assertTrue(result["synced"])
        self.assertTrue(result["failsafe_ok"])

    @patch("status.iptables_engine.failsafe_present", return_value=False)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=0)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_iptables_not_yet_synced(self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertFalse(result["synced"])
        self.assertFalse(result["failsafe_ok"])

    @patch("status.iptables_engine.failsafe_present", return_value=False)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=5)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_synced_but_current_session_ip_not_covered_by_failsafe(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe
    ):
        # sincronizado (tem regras), mas o failsafe não cobre o IP ATUAL da
        # sessão (ex.: IP mudou desde o último sync) -- os dois sinais são
        # independentes, nunca dá pra assumir um a partir do outro.
        result = status.get_status(engine=None)
        self.assertTrue(result["synced"])
        self.assertFalse(result["failsafe_ok"])

    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=0)
    @patch("status.session_ip.detect_session_ip", return_value=None)
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_undetectable_session_ip(self, mock_resolve, mock_ip, mock_count, mock_configured):
        result = status.get_status(engine=None)
        self.assertIsNone(result["session_ip"])
        self.assertFalse(result["synced"])
        self.assertFalse(result["failsafe_ok"])

    @patch("status.sync.resolve_firewalld_zone", return_value=("pvxfw", True))
    @patch("status.firewalld_engine.failsafe_present", return_value=True)
    @patch("status.firewalld_engine.count_rich_rules", return_value=3)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="firewalld")
    def test_dispatches_to_firewalld(self, mock_resolve, mock_ip, mock_count, mock_failsafe, mock_zone):
        result = status.get_status(engine=None)
        self.assertEqual(result["engine"], "firewalld")
        self.assertEqual(result["rule_count"], 3)
        self.assertTrue(result["synced"])
        self.assertTrue(result["failsafe_ok"])
        self.assertEqual(result["firewalld_zone"], "pvxfw")
        mock_count.assert_called_once_with("pvxfw")
        mock_failsafe.assert_called_once_with("pvxfw", "203.0.113.9")

    # achado ao vivo: numa central MagnusBilling, `check` lia sempre a zona "pvxfw"
    # (100% inerte lá) e reportava "sincronizado" mesmo sem nenhum pacote de verdade
    # passando por ali -- agora lê a zona que sync.run() de fato usaria.
    @patch("status.sync.resolve_firewalld_zone", return_value=("public", False))
    @patch("status.firewalld_engine.failsafe_present", return_value=True)
    @patch("status.firewalld_engine.count_rich_rules", return_value=5)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="firewalld")
    def test_reads_the_magnus_public_zone_instead_of_the_inert_own_zone(
        self, mock_resolve, mock_ip, mock_count, mock_failsafe, mock_zone
    ):
        result = status.get_status(engine=None)
        self.assertEqual(result["firewalld_zone"], "public")
        mock_count.assert_called_once_with("public")
        mock_failsafe.assert_called_once_with("public", "203.0.113.9")

    @patch("status.sync.resolve_firewalld_zone", return_value=("pvxfw", True))
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_firewalld_zone_is_none_for_the_iptables_engine(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_zone
    ):
        result = status.get_status(engine=None)
        self.assertIsNone(result["firewalld_zone"])
        mock_zone.assert_not_called()

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_iptables_engine_active_mirrors_synced(self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe):
        # iptables não tem daemon próprio -- "ativo" é exatamente "tem regra
        # carregada no kernel", o mesmo sinal que "synced".
        result = status.get_status(engine=None)
        self.assertTrue(result["engine_active"])

    @patch("status.firewalld_engine.failsafe_present", return_value=True)
    @patch("status.firewalld_engine.count_rich_rules", return_value=3)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="firewalld")
    @patch("status.engine_detect.service_is_active")
    def test_firewalld_engine_active_reflects_the_live_service(
        self, mock_active, mock_resolve, mock_ip, mock_count, mock_failsafe
    ):
        # sinal independente de "synced": regras podem estar configuradas
        # mesmo com o daemon do firewalld parado (nada sendo de fato aplicado).
        mock_active.return_value = False
        result = status.get_status(engine=None)
        self.assertFalse(result["engine_active"])
        # agora também é chamado pra checar o engine concorrente (iptables) --
        # só o "firewalld" aqui importa pra esse teste.
        mock_active.assert_any_call("firewalld")

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_boot_persistent_reflects_the_systemd_unit(self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe):
        with patch("status.systemd_unit.is_enabled", return_value=False):
            result = status.get_status(engine=None)
        self.assertFalse(result["boot_persistent"])

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_lists_are_none_without_a_base_dir(self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertIsNone(result["lists"])

    @patch("status.iptables_engine.rules_match_expected", return_value=True)
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_lists_are_read_from_the_base_dir_when_given(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_matches
    ):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ip_accept.conf").write_text("203.0.113.1  # confiavel\n")
            result = status.get_status(engine=None, base_dir=tmp)
        self.assertEqual(result["lists"]["ip_accept"], [("203.0.113.1", "confiavel")])
        self.assertIn("ip_deny", result["lists"])
        self.assertIn("port_accept", result["lists"])
        self.assertIn("port_deny", result["lists"])

    @patch("status.iptables_engine.rules_match_expected", return_value=True)
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_never_writes_config_files_just_from_a_check(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_matches
    ):
        # achado na revisão: check não exige root (test_status_does_not_
        # require_root), mas lists.read_list com seed= grava as listas
        # padrão em disco quando o arquivo ainda não existe -- um usuário
        # sem permissão em /etc/pvx tomaria um PermissionError cru numa
        # consulta que devia ser só leitura.
        with tempfile.TemporaryDirectory() as tmp:
            result = status.get_status(engine=None, base_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertEqual(result["lists"]["ip_accept"], [])

    @patch("status.iptables_engine.rules_match_expected", return_value=True)
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=4)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_configured_and_expected_rule_counts_for_iptables(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_matches
    ):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ip_accept.conf").write_text("203.0.113.1\n203.0.113.2\n")
            result = status.get_status(engine=None, base_dir=tmp)
        self.assertEqual(result["configured_rule_count"], 4)
        # 2 ips + 1 (catch-all do chain de portas) -- nenhuma porta configurada
        self.assertEqual(result["expected_rule_count"], 3)

    def test_rule_counts_are_none_without_a_base_dir(self):
        with patch("status.sync.resolve_engine", return_value="iptables"), \
             patch("status.iptables_engine.count_input_rules", return_value=0), \
             patch("status.iptables_engine.count_configured_rules", return_value=0), \
             patch("status.iptables_engine.failsafe_present", return_value=False), \
             patch("status.session_ip.detect_session_ip", return_value=None):
            result = status.get_status(engine=None)
        self.assertIsNone(result["expected_rule_count"])

    @patch("status.sync.resolve_firewalld_zone", return_value=("pvxfw", True))
    @patch("status.firewalld_engine.failsafe_present", return_value=True)
    @patch("status.firewalld_engine.count_rich_rules", return_value=3)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="firewalld")
    def test_configured_rule_count_reuses_rule_count_for_firewalld(
        self, mock_resolve, mock_ip, mock_count, mock_failsafe, mock_zone
    ):
        result = status.get_status(engine=None)
        self.assertEqual(result["configured_rule_count"], 3)

    # achado ao vivo: rule_count>0 (a chain INPUT não está vazia) não quer
    # dizer que as regras aplicadas são as da config atual -- `synced`
    # reportava ATIVO com o firewall basicamente deixando tudo passar,
    # porque nunca comparava o conteúdo de verdade contra o esperado.
    @patch("status.iptables_engine.rules_match_expected", return_value=False)
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=4)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_synced_is_false_when_live_rules_dont_match_expected_content(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_matches
    ):
        with tempfile.TemporaryDirectory() as tmp:
            result = status.get_status(engine=None, base_dir=tmp)
        self.assertFalse(result["synced"])

    @patch("status.iptables_engine.rules_match_expected", return_value=True)
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=4)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_synced_stays_true_when_live_rules_match_expected_content(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_matches
    ):
        with tempfile.TemporaryDirectory() as tmp:
            result = status.get_status(engine=None, base_dir=tmp)
        self.assertTrue(result["synced"])

    # achado ao vivo: um segundo engine de firewall rodando junto (ex.:
    # firewalld ativo numa central onde pvx escolheu iptables) pode estar
    # reescrevendo/competindo pelas mesmas chains sem o pvx nunca saber --
    # `check` precisa avisar disso, não só assumir que o engine escolhido é
    # o único em jogo.
    @patch("status.iptables_engine.rules_match_expected", return_value=True)
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_warns_when_firewalld_is_also_active_alongside_iptables(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_matches
    ):
        with patch("status.engine_detect.service_is_active", return_value=True) as mock_active:
            result = status.get_status(engine=None)
        self.assertEqual(result["competing_engine"], "firewalld")
        mock_active.assert_called_once_with("firewalld")

    @patch("status.iptables_engine.rules_match_expected", return_value=True)
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_no_competing_engine_when_firewalld_is_inactive(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_matches
    ):
        result = status.get_status(engine=None)  # setUp já mocka service_is_active=False
        self.assertIsNone(result["competing_engine"])

    @patch("status.sync.resolve_firewalld_zone", return_value=("pvxfw", True))
    @patch("status.firewalld_engine.failsafe_present", return_value=True)
    @patch("status.firewalld_engine.count_rich_rules", return_value=3)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="firewalld")
    def test_warns_when_iptables_service_is_also_active_alongside_firewalld(
        self, mock_resolve, mock_ip, mock_count, mock_failsafe, mock_zone
    ):
        def fake_active(name):
            return name == "iptables"
        with patch("status.engine_detect.service_is_active", side_effect=fake_active):
            result = status.get_status(engine=None)
        self.assertEqual(result["competing_engine"], "iptables")

    @patch("status.iptables_engine.dropped_counters", return_value={"packets": 142, "bytes": 11360})
    @patch("status.iptables_engine.rules_match_expected", return_value=True)
    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_configured_rules", return_value=0)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_exposes_dropped_packet_and_byte_counters_for_iptables(
        self, mock_resolve, mock_ip, mock_count, mock_configured, mock_failsafe, mock_matches, mock_counters
    ):
        result = status.get_status(engine=None)
        self.assertEqual(result["dropped_counters"], {"packets": 142, "bytes": 11360})

    @patch("status.sync.resolve_firewalld_zone", return_value=("pvxfw", True))
    @patch("status.firewalld_engine.failsafe_present", return_value=True)
    @patch("status.firewalld_engine.count_rich_rules", return_value=3)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="firewalld")
    def test_dropped_counters_are_none_for_firewalld_for_now(
        self, mock_resolve, mock_ip, mock_count, mock_failsafe, mock_zone
    ):
        result = status.get_status(engine=None)
        self.assertIsNone(result["dropped_counters"])


if __name__ == "__main__":
    unittest.main()
