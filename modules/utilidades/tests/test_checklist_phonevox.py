import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from pvx import config as pvx_config

import checklist_phonevox


class SslCheckTest(unittest.TestCase):
    @patch("checklist_phonevox.os.path.isdir", return_value=False)
    def test_no_live_dir_is_a_warning(self, mock_isdir):
        result = checklist_phonevox.check_ssl()
        self.assertEqual(result["level"], "warn")
        self.assertIn("nenhum certificado", result["value"])

    @patch("checklist_phonevox.os.listdir", return_value=[])
    @patch("checklist_phonevox.os.path.isdir", return_value=True)
    def test_live_dir_without_domains_is_a_warning(self, mock_isdir, mock_listdir):
        result = checklist_phonevox.check_ssl()
        self.assertEqual(result["level"], "warn")

    @patch("checklist_phonevox._days_until_expiry", return_value=60)
    @patch("checklist_phonevox.os.path.isdir", return_value=True)
    @patch("checklist_phonevox.os.listdir", return_value=["central.example.com"])
    def test_plenty_of_time_left_is_ok(self, mock_listdir, mock_isdir_list, mock_days):
        with patch("checklist_phonevox.os.path.isdir", side_effect=[True, True]):
            result = checklist_phonevox.check_ssl()
        self.assertEqual(result["level"], "ok")
        self.assertIn("central.example.com", result["value"])
        self.assertIn("60", result["value"])

    @patch("checklist_phonevox._days_until_expiry", return_value=-3)
    @patch("checklist_phonevox.os.listdir", return_value=["central.example.com"])
    def test_expired_is_an_error(self, mock_listdir, mock_days):
        with patch("checklist_phonevox.os.path.isdir", side_effect=[True, True]):
            result = checklist_phonevox.check_ssl()
        self.assertEqual(result["level"], "error")
        self.assertIn("expirado", result["value"])

    @patch("checklist_phonevox._days_until_expiry", return_value=None)
    @patch("checklist_phonevox.os.listdir", return_value=["central.example.com"])
    def test_unreadable_certificate_is_a_warning(self, mock_listdir, mock_days):
        with patch("checklist_phonevox.os.path.isdir", side_effect=[True, True]):
            result = checklist_phonevox.check_ssl()
        self.assertEqual(result["level"], "warn")

    @patch("checklist_phonevox._days_until_expiry", side_effect=[30, 5])
    @patch("checklist_phonevox.os.listdir", return_value=["a.example.com", "b.example.com"])
    def test_reports_the_most_urgent_domain_when_there_are_several(self, mock_listdir, mock_days):
        with patch("checklist_phonevox.os.path.isdir", side_effect=[True, True, True]):
            result = checklist_phonevox.check_ssl()
        self.assertIn("b.example.com", result["value"])
        self.assertIn("5", result["value"])


class DaysUntilExpiryTest(unittest.TestCase):
    @patch("checklist_phonevox.os.path.exists", return_value=False)
    def test_missing_cert_file_returns_none(self, mock_exists):
        self.assertIsNone(checklist_phonevox._days_until_expiry("x.example.com"))

    @patch("checklist_phonevox.os.path.exists", return_value=True)
    def test_parses_openssl_enddate_output(self, mock_exists):
        future = datetime.now(timezone.utc) + timedelta(days=10)
        raw = future.strftime("%b %d %H:%M:%S %Y GMT")
        fake_result = MagicMock(returncode=0, stdout=f"notAfter={raw}\n")
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            days_left = checklist_phonevox._days_until_expiry("x.example.com")
        self.assertIn(days_left, (9, 10))

    @patch("checklist_phonevox.os.path.exists", return_value=True)
    def test_openssl_failure_returns_none(self, mock_exists):
        fake_result = MagicMock(returncode=1, stdout="")
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            self.assertIsNone(checklist_phonevox._days_until_expiry("x.example.com"))


class AutobackupCheckTest(unittest.TestCase):
    def test_not_configured_is_a_warning(self):
        result = checklist_phonevox.check_autobackup()
        self.assertEqual(result["level"], "warn")

    def test_configured_shows_the_cron_schedule(self):
        path = pvx_config.modules_dir() / "autobackup" / "state" / "state.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"cron_minute": "25", "cron_hour": "2"}))
        result = checklist_phonevox.check_autobackup()
        self.assertEqual(result["level"], "ok")
        self.assertIn("25 2 * * *", result["value"])


class SshHardeningCheckTest(unittest.TestCase):
    def test_not_applied_is_a_warning(self):
        result = checklist_phonevox.check_ssh_hardening()
        self.assertEqual(result["level"], "warn")

    def test_applied_with_valid_config_is_ok(self):
        state_dir = pvx_config.modules_dir() / "ssh-hardening" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "apply-1.json").write_text(json.dumps({"config_valid": True}))
        result = checklist_phonevox.check_ssh_hardening()
        self.assertEqual(result["level"], "ok")

    def test_applied_with_invalid_config_is_a_warning(self):
        state_dir = pvx_config.modules_dir() / "ssh-hardening" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "apply-1.json").write_text(json.dumps({"config_valid": False}))
        result = checklist_phonevox.check_ssh_hardening()
        self.assertEqual(result["level"], "warn")

    def test_uses_the_most_recent_record(self):
        state_dir = pvx_config.modules_dir() / "ssh-hardening" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "apply-1.json").write_text(json.dumps({"config_valid": False}))
        (state_dir / "apply-2.json").write_text(json.dumps({"config_valid": True}))
        result = checklist_phonevox.check_ssh_hardening()
        self.assertEqual(result["level"], "ok")


class ZabbixCheckTest(unittest.TestCase):
    def test_not_configured_is_a_warning(self):
        result = checklist_phonevox.check_zabbix()
        self.assertEqual(result["level"], "warn")

    def test_configured_shows_the_hostname(self):
        state_dir = pvx_config.modules_dir() / "zabbix" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "agent_variant.txt").write_text("agent2")
        with patch(
            "checklist_phonevox._read_params", return_value={"Hostname": "vps-x"},
        ):
            result = checklist_phonevox.check_zabbix()
        self.assertEqual(result["level"], "ok")
        self.assertIn("vps-x", result["value"])

    def test_audit_script_not_added_is_a_warning(self):
        result = checklist_phonevox.check_zabbix_audit_script()
        self.assertEqual(result["level"], "warn")

    def test_audit_script_added_is_ok(self):
        state_dir = pvx_config.modules_dir() / "zabbix" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "scripts.json").write_text(json.dumps({"audit": {"command": "x"}}))
        result = checklist_phonevox.check_zabbix_audit_script()
        self.assertEqual(result["level"], "ok")


class AutobloqueadorCheckTest(unittest.TestCase):
    def test_not_configured_is_a_warning(self):
        with patch("checklist_phonevox._AUTOBLOQUEADOR_STATE", Path("/tmp/does-not-exist-pvx.json")):
            result = checklist_phonevox.check_autobloqueador()
        self.assertEqual(result["level"], "warn")

    def test_configured_shows_the_type(self):
        fake_path = MagicMock()
        with patch("checklist_phonevox._read_json", return_value={"type": "pabx"}):
            result = checklist_phonevox.check_autobloqueador()
        self.assertEqual(result["level"], "ok")
        self.assertIn("pabx", result["value"])


class FirewallBootCheckTest(unittest.TestCase):
    def test_enabled_is_ok(self):
        fake_result = MagicMock(stdout="enabled\n")
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            result = checklist_phonevox.check_firewall_boot()
        self.assertEqual(result["level"], "ok")

    def test_disabled_is_a_warning(self):
        fake_result = MagicMock(stdout="disabled\n")
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            result = checklist_phonevox.check_firewall_boot()
        self.assertEqual(result["level"], "warn")

    def test_missing_systemctl_is_a_warning_not_a_crash(self):
        with patch("checklist_phonevox.subprocess.run", side_effect=OSError()):
            result = checklist_phonevox.check_firewall_boot()
        self.assertEqual(result["level"], "warn")


class FirewallBaseIpsCheckTest(unittest.TestCase):
    def _write_ip_accept(self, entries):
        path = pvx_config.modules_dir() / "firewall" / "state" / "ip_accept.conf"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(entries) + "\n")

    def test_warns_when_the_file_does_not_exist_yet(self):
        result = checklist_phonevox.check_firewall_base_ips()
        self.assertEqual(result["level"], "warn")

    def test_ok_when_every_base_ip_is_covered(self):
        # achado ao vivo: técnico perdeu acesso porque um `ip accept` numa
        # central sem ip_accept.conf ainda apagou os IPs base da Phonevox.
        self._write_ip_accept([
            f"{ip}  # base" for ip in checklist_phonevox._FIREWALL_BASE_IPS
        ] + ["45.162.8.0/24  # cliente"])
        result = checklist_phonevox.check_firewall_base_ips()
        self.assertEqual(result["level"], "ok")

    def test_warns_when_a_base_ip_is_missing(self):
        self._write_ip_accept(["45.162.8.0/24  # cliente"])
        result = checklist_phonevox.check_firewall_base_ips()
        self.assertEqual(result["level"], "warn")
        self.assertIn("trust-phonevox", result["value"])

    def test_new_phonevox_ip_is_part_of_the_base_set(self):
        self.assertIn("145.223.92.246", checklist_phonevox._FIREWALL_BASE_IPS)

    def test_a_covering_supernet_counts_as_present(self):
        self._write_ip_accept(["0.0.0.0/0  # tudo"])
        result = checklist_phonevox.check_firewall_base_ips()
        self.assertEqual(result["level"], "ok")


class FirewallSyncedCheckTest(unittest.TestCase):
    # achado ao vivo: parsear o texto formatado de `pvx firewall check`
    # (scraping de "status: ativo") quebrou quando o formato de exibição
    # mudou -- `--json` é o contrato estável entre os dois módulos, nunca
    # muda com o tema/formato de exibição escolhido pelo usuário.
    def test_ok_when_synced(self):
        fake_result = MagicMock(stdout=json.dumps({"engine_active": True, "synced": True}))
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result) as mock_run:
            result = checklist_phonevox.check_firewall_synced()
        self.assertEqual(result["level"], "ok")
        self.assertIn("--json", mock_run.call_args.args[0])

    def test_warns_when_not_synced(self):
        fake_result = MagicMock(stdout=json.dumps({"engine_active": True, "synced": False}))
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            result = checklist_phonevox.check_firewall_synced()
        self.assertEqual(result["level"], "warn")

    def test_warns_when_engine_is_not_active(self):
        fake_result = MagicMock(stdout=json.dumps({"engine_active": False, "synced": True}))
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            result = checklist_phonevox.check_firewall_synced()
        self.assertEqual(result["level"], "warn")

    def test_warns_when_pvx_firewall_check_is_unavailable(self):
        with patch("checklist_phonevox.subprocess.run", side_effect=OSError()):
            result = checklist_phonevox.check_firewall_synced()
        self.assertEqual(result["level"], "warn")

    def test_warns_when_output_is_not_valid_json(self):
        fake_result = MagicMock(stdout="not json")
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            result = checklist_phonevox.check_firewall_synced()
        self.assertEqual(result["level"], "warn")


class FirewallGeobanCheckTest(unittest.TestCase):
    def test_ok_when_geoban_is_enabled(self):
        fake_result = MagicMock(stdout=json.dumps({"lists": {"geo_accept": [["BR", "Brasil"]]}}))
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            result = checklist_phonevox.check_firewall_geoban()
        self.assertEqual(result["level"], "ok")
        self.assertIn("BR", result["value"])

    def test_warns_when_geoban_is_disabled(self):
        fake_result = MagicMock(stdout=json.dumps({"lists": {"geo_accept": []}}))
        with patch("checklist_phonevox.subprocess.run", return_value=fake_result):
            result = checklist_phonevox.check_firewall_geoban()
        self.assertEqual(result["level"], "warn")
        self.assertIn("geo enable", result["value"])

    def test_warns_when_pvx_firewall_check_is_unavailable(self):
        with patch("checklist_phonevox.subprocess.run", side_effect=OSError()):
            result = checklist_phonevox.check_firewall_geoban()
        self.assertEqual(result["level"], "warn")


class FirewallAdminPortsCheckTest(unittest.TestCase):
    def _check(self, port_accept, port_deny):
        payload = {"lists": {"port_accept": port_accept, "port_deny": port_deny}}
        with patch("checklist_phonevox.subprocess.run", return_value=MagicMock(stdout=json.dumps(payload))):
            return checklist_phonevox.check_firewall_admin_ports()

    def test_ok_with_the_default_lists(self):
        result = self._check([["5060/udp", "SIP"]], [["3306/tcp", "MySQL"], ["5038/tcp", "AMI"]])
        self.assertEqual(result["level"], "ok")

    def test_ok_when_not_listed_anywhere(self):
        result = self._check([["5060/udp", "SIP"]], [])
        self.assertEqual(result["level"], "ok")

    def test_error_when_mysql_is_accepted_and_not_denied(self):
        result = self._check([["3306/tcp", "MySQL"]], [])
        self.assertEqual(result["level"], "error")
        self.assertIn("3306", result["value"])

    def test_error_when_a_range_without_protocol_opens_ami(self):
        result = self._check([["5000-5100", "range"]], [])
        self.assertEqual(result["level"], "error")
        self.assertIn("5038", result["value"])

    def test_deny_wins_over_accept(self):
        result = self._check([["3306/tcp", "MySQL"]], [["3306/tcp", "MySQL"]])
        self.assertEqual(result["level"], "ok")

    def test_warns_when_pvx_firewall_check_is_unavailable(self):
        with patch("checklist_phonevox.subprocess.run", side_effect=OSError()):
            result = checklist_phonevox.check_firewall_admin_ports()
        self.assertEqual(result["level"], "warn")

    def test_admin_ports_check_is_in_the_checklist(self):
        self.assertIn(checklist_phonevox.check_firewall_admin_ports, checklist_phonevox.CHECKS)


class FirewallAsteriskIpsCheckTest(unittest.TestCase):
    def _write_ip_accept(self, entries):
        path = pvx_config.modules_dir() / "firewall" / "state" / "ip_accept.conf"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(entries) + "\n")

    def test_ok_when_asterisk_has_no_connected_ips(self):
        with patch("checklist_phonevox._asterisk_cli", return_value=None):
            result = checklist_phonevox.check_firewall_asterisk_ips()
        self.assertEqual(result["level"], "ok")

    def test_ok_when_every_connected_ip_is_trusted(self):
        self._write_ip_accept(["198.51.100.0/24  # cliente"])
        with patch(
            "checklist_phonevox._asterisk_cli",
            side_effect=lambda cmd, **kw: "198.51.100.9\n" if cmd == "sip show peers" else None,
        ):
            result = checklist_phonevox.check_firewall_asterisk_ips()
        self.assertEqual(result["level"], "ok")

    def test_warns_about_connected_ips_outside_the_whitelist(self):
        # o caso real que motivou esse check: um IP registrado no Asterisk
        # que nunca foi liberado no firewall -- acesso pode cair a qualquer
        # momento que o firewall for reaplicado.
        self._write_ip_accept(["10.0.0.0/8"])
        with patch(
            "checklist_phonevox._asterisk_cli",
            side_effect=lambda cmd, **kw: "198.51.100.9\n" if cmd == "sip show peers" else None,
        ):
            result = checklist_phonevox.check_firewall_asterisk_ips()
        self.assertEqual(result["level"], "warn")
        self.assertIn("198.51.100.9", result["value"])

    def test_ok_when_ip_accept_file_does_not_exist_yet_and_nothing_connected(self):
        with patch("checklist_phonevox._asterisk_cli", return_value=None):
            result = checklist_phonevox.check_firewall_asterisk_ips()
        self.assertEqual(result["level"], "ok")


class RunAllTest(unittest.TestCase):
    def test_runs_every_check_in_order(self):
        results = checklist_phonevox.run_all()
        rules = [r["rule"] for r in results]
        self.assertEqual(len(results), len(checklist_phonevox.CHECKS))
        self.assertEqual(rules[0], "SSL")
        self.assertTrue(any("Firewall" in rule for rule in rules))

    def test_every_result_has_the_four_expected_fields(self):
        for result in checklist_phonevox.run_all():
            self.assertEqual(set(result.keys()), {"rule", "description", "value", "level"})

    def test_zabbix_contributes_two_adjacent_items(self):
        # zabbix (config) e zabbix_audit_script são checks separados, mas
        # ficam um logo depois do outro na ordem de exibição.
        results = checklist_phonevox.run_all()
        rules = [r["rule"] for r in results]
        zabbix_indexes = [i for i, rule in enumerate(rules) if rule.startswith("Zabbix")]
        self.assertEqual(zabbix_indexes, [zabbix_indexes[0], zabbix_indexes[0] + 1])


if __name__ == "__main__":
    unittest.main()
