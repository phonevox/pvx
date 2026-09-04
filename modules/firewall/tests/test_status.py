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

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_iptables_synced_and_protected(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertEqual(result["engine"], "iptables")
        self.assertEqual(result["session_ip"], "203.0.113.9")
        self.assertEqual(result["rule_count"], 7)
        self.assertTrue(result["synced"])
        self.assertTrue(result["failsafe_ok"])

    @patch("status.iptables_engine.failsafe_present", return_value=False)
    @patch("status.iptables_engine.count_input_rules", return_value=0)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_iptables_not_yet_synced(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertFalse(result["synced"])
        self.assertFalse(result["failsafe_ok"])

    @patch("status.iptables_engine.failsafe_present", return_value=False)
    @patch("status.iptables_engine.count_input_rules", return_value=5)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_synced_but_current_session_ip_not_covered_by_failsafe(
        self, mock_resolve, mock_ip, mock_count, mock_failsafe
    ):
        # sincronizado (tem regras), mas o failsafe não cobre o IP ATUAL da
        # sessão (ex.: IP mudou desde o último sync) -- os dois sinais são
        # independentes, nunca dá pra assumir um a partir do outro.
        result = status.get_status(engine=None)
        self.assertTrue(result["synced"])
        self.assertFalse(result["failsafe_ok"])

    @patch("status.iptables_engine.count_input_rules", return_value=0)
    @patch("status.session_ip.detect_session_ip", return_value=None)
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_undetectable_session_ip(self, mock_resolve, mock_ip, mock_count):
        result = status.get_status(engine=None)
        self.assertIsNone(result["session_ip"])
        self.assertFalse(result["synced"])
        self.assertFalse(result["failsafe_ok"])

    @patch("status.firewalld_engine.failsafe_present", return_value=True)
    @patch("status.firewalld_engine.count_rich_rules", return_value=3)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="firewalld")
    def test_dispatches_to_firewalld(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertEqual(result["engine"], "firewalld")
        self.assertEqual(result["rule_count"], 3)
        self.assertTrue(result["synced"])
        self.assertTrue(result["failsafe_ok"])
        mock_count.assert_called_once_with("pvxfw")
        mock_failsafe.assert_called_once_with("pvxfw", "203.0.113.9")

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_iptables_engine_active_mirrors_synced(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
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
        mock_active.assert_called_once_with("firewalld")

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_boot_persistent_reflects_the_systemd_unit(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        with patch("status.systemd_unit.is_enabled", return_value=False):
            result = status.get_status(engine=None)
        self.assertFalse(result["boot_persistent"])

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_lists_are_none_without_a_base_dir(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        result = status.get_status(engine=None)
        self.assertIsNone(result["lists"])

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_lists_are_read_from_the_base_dir_when_given(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ip_accept.conf").write_text("203.0.113.1  # confiavel\n")
            result = status.get_status(engine=None, base_dir=tmp)
        self.assertEqual(result["lists"]["ip_accept"], [("203.0.113.1", "confiavel")])
        self.assertIn("ip_deny", result["lists"])
        self.assertIn("port_accept", result["lists"])
        self.assertIn("port_deny", result["lists"])

    @patch("status.iptables_engine.failsafe_present", return_value=True)
    @patch("status.iptables_engine.count_input_rules", return_value=7)
    @patch("status.session_ip.detect_session_ip", return_value="203.0.113.9")
    @patch("status.sync.resolve_engine", return_value="iptables")
    def test_never_writes_config_files_just_from_a_check(self, mock_resolve, mock_ip, mock_count, mock_failsafe):
        # achado na revisão: check não exige root (test_status_does_not_
        # require_root), mas lists.read_list com seed= grava as listas
        # padrão em disco quando o arquivo ainda não existe -- um usuário
        # sem permissão em /etc/pvx tomaria um PermissionError cru numa
        # consulta que devia ser só leitura.
        with tempfile.TemporaryDirectory() as tmp:
            result = status.get_status(engine=None, base_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertEqual(result["lists"]["ip_accept"], [])


if __name__ == "__main__":
    unittest.main()
