import json
import os
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pvx import config, update_check


class FakeInstalled:
    def __init__(self, version):
        self.version = version


class PendingNoticesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._old_home = os.environ.get("PVX_HOME")
        os.environ["PVX_HOME"] = self._tmp.name

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("PVX_HOME", None)
        else:
            os.environ["PVX_HOME"] = self._old_home
        self._tmp.cleanup()

    @patch("pvx.update_check.listing.list_modules", return_value=[])
    @patch("pvx.update_check._fetch_core_latest", return_value="99.0.0")
    def test_notifies_when_a_newer_core_is_available(self, mock_fetch, mock_list):
        notices = update_check.pending_notices({})
        self.assertTrue(any("core" in n.lower() for n in notices))

    @patch("pvx.update_check.listing.list_modules", return_value=[])
    @patch("pvx.update_check._fetch_core_latest", return_value="0.0.1")
    def test_no_core_notice_when_already_up_to_date_or_ahead(self, mock_fetch, mock_list):
        # achado ao vivo (listing.py): deploy fora do registry deixa a
        # versão instalada mais nova que a publicada -- não é "atualização".
        notices = update_check.pending_notices({})
        self.assertFalse(any("core" in n.lower() for n in notices))

    @patch(
        "pvx.update_check.listing.list_modules",
        return_value=[
            {
                "name": "firewall", "installed_version": "0.2.10", "latest_version": "0.2.11",
                "status": "atualização disponível",
            },
            {"name": "ssl", "installed_version": "0.1.2", "latest_version": "0.1.2", "status": "atualizado"},
        ],
    )
    @patch("pvx.update_check._fetch_core_latest", return_value="0.0.1")
    def test_notifies_only_modules_with_update_available(self, mock_fetch, mock_list):
        installed = {"firewall": FakeInstalled("0.2.10"), "ssl": FakeInstalled("0.1.2")}
        notices = update_check.pending_notices(installed)
        self.assertEqual(len(notices), 1)
        self.assertIn("firewall", notices[0])
        self.assertNotIn("ssl", notices[0])

    @patch(
        "pvx.update_check.listing.list_modules",
        return_value=[
            {
                "name": "firewall", "installed_version": "0.2.1", "latest_version": "0.2.11",
                "status": "atualização disponível",
            },
            {
                "name": "zabbix", "installed_version": "0.2.0", "latest_version": "0.2.2",
                "status": "atualização disponível",
            },
            {"name": "ssl", "installed_version": "0.1.2", "latest_version": "0.1.2", "status": "atualizado"},
        ],
    )
    @patch("pvx.update_check._fetch_core_latest", return_value="0.0.1")
    def test_multiple_outdated_modules_collapse_into_a_single_line(self, mock_fetch, mock_list):
        # achado ao vivo: um aviso por módulo lotava o banner (7+ linhas numa
        # central com vários módulos pendentes) -- uma linha só, com a
        # contagem e os nomes, dá a mesma informação sem amontoar a tela.
        installed = {"firewall": FakeInstalled("0.2.1"), "zabbix": FakeInstalled("0.2.0"), "ssl": FakeInstalled("0.1.2")}
        notices = update_check.pending_notices(installed)
        self.assertEqual(len(notices), 1)
        self.assertIn("firewall", notices[0])
        self.assertIn("zabbix", notices[0])
        self.assertIn("2", notices[0])
        self.assertIn("atualizações disponíveis", notices[0])
        self.assertNotIn("(ões)", notices[0])
        self.assertNotIn("(is)", notices[0])

    @patch(
        "pvx.update_check.listing.list_modules",
        return_value=[
            {
                "name": "firewall", "installed_version": "0.2.1", "latest_version": "0.2.11",
                "status": "atualização disponível",
            },
            {"name": "ssl", "installed_version": "0.1.2", "latest_version": "0.1.2", "status": "atualizado"},
        ],
    )
    @patch("pvx.update_check._fetch_core_latest", return_value="0.0.1")
    def test_single_outdated_module_uses_singular_wording(self, mock_fetch, mock_list):
        # achado ao vivo: "atualização(ões) disponível(is)" com parênteses de
        # dicionário ficou feio -- singular/plural de verdade, sem "(ões)".
        installed = {"firewall": FakeInstalled("0.2.1"), "ssl": FakeInstalled("0.1.2")}
        notices = update_check.pending_notices(installed)
        self.assertIn("1 atualização disponível", notices[0])
        self.assertNotIn("(ões)", notices[0])
        self.assertNotIn("(is)", notices[0])

    @patch("pvx.update_check.listing.list_modules", return_value=[])
    @patch("pvx.update_check._fetch_core_latest", side_effect=OSError("timeout"))
    def test_network_failure_is_silent_not_raised(self, mock_fetch, mock_list):
        notices = update_check.pending_notices({})
        self.assertEqual(notices, [])

    @patch("pvx.update_check.listing.list_modules", side_effect=RuntimeError("registry fora do ar"))
    @patch("pvx.update_check._fetch_core_latest", return_value="0.0.1")
    def test_registry_failure_for_modules_is_also_silent(self, mock_fetch, mock_list):
        notices = update_check.pending_notices({"firewall": FakeInstalled("0.2.10")})
        self.assertEqual(notices, [])

    @patch("pvx.update_check.listing.list_modules", return_value=[])
    @patch("pvx.update_check._fetch_core_latest", return_value="99.0.0")
    def test_second_call_within_ttl_uses_cache_not_network(self, mock_fetch, mock_list):
        update_check.pending_notices({})
        mock_fetch.reset_mock()
        update_check.pending_notices({})
        mock_fetch.assert_not_called()

    @patch("pvx.update_check.listing.list_modules", return_value=[])
    @patch("pvx.update_check._fetch_core_latest", return_value="99.0.0")
    def test_force_bypasses_the_cache(self, mock_fetch, mock_list):
        update_check.pending_notices({})
        mock_fetch.reset_mock()
        update_check.pending_notices({}, force=True)
        mock_fetch.assert_called_once()

    @patch("pvx.update_check.listing.list_modules", return_value=[])
    @patch("pvx.update_check._fetch_core_latest", return_value="99.0.0")
    def test_clear_cache_makes_the_next_call_recompute(self, mock_fetch, mock_list):
        # achado ao vivo: trocar o core.pyz (self-update) não muda o TTL do
        # cache -- um aviso calculado pela lógica ANTIGA (ex.: formato de
        # linha diferente) continuava sendo servido até o cache expirar
        # sozinho, mesmo já rodando o core novo.
        update_check.pending_notices({})
        mock_fetch.reset_mock()
        update_check.clear_cache()
        update_check.pending_notices({})
        mock_fetch.assert_called_once()

    def test_clear_cache_is_a_no_op_when_there_is_no_cache_yet(self):
        update_check.clear_cache()

    @patch("pvx.update_check.listing.list_modules", return_value=[])
    @patch("pvx.update_check._fetch_core_latest", return_value="99.0.0")
    def test_expired_cache_triggers_a_new_check(self, mock_fetch, mock_list):
        update_check.pending_notices({})
        cache_path = config.update_check_cache_path()
        data = json.loads(cache_path.read_text())
        data["checked_at"] = time.time() - update_check._CACHE_TTL_SECONDS - 1
        cache_path.write_text(json.dumps(data))
        mock_fetch.reset_mock()
        update_check.pending_notices({})
        mock_fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
