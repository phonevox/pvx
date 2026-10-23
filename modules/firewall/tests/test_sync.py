import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import defaults
import sync


class ResolveEngineTest(unittest.TestCase):
    def test_explicit_engine_skips_detection(self):
        self.assertEqual(sync.resolve_engine("firewalld"), "firewalld")

    @patch("sync.engine_detect.detect_engine", return_value="iptables")
    def test_detects_when_not_given(self, mock_detect):
        self.assertEqual(sync.resolve_engine(None), "iptables")
        mock_detect.assert_called_once()


class RunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self._tmp.name)
        # chamado incondicionalmente em todo run() agora, nos dois engines --
        # sem isso os testes bateriam no fail2ban-client de verdade.
        f2b_patcher = patch("sync.fail2ban_ops.sync", return_value=None)
        self.mock_f2b_sync = f2b_patcher.start()
        self.addCleanup(f2b_patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()

    @patch("sync.session_ip.detect_session_ip", return_value=None)
    def test_raises_without_force_when_session_ip_undetectable(self, mock_ip):
        with self.assertRaises(RuntimeError):
            sync.run(self.base_dir, engine="iptables", force=False)

    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value=None)
    def test_proceeds_without_failsafe_when_forced(self, mock_ip, mock_engine_sync):
        result = sync.run(self.base_dir, engine="iptables", force=True)
        self.assertIsNone(result["session_ip"])
        mock_engine_sync.assert_called_once()
        self.assertIsNone(mock_engine_sync.call_args.kwargs["failsafe_ip"])

    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_dispatches_to_iptables_with_seeded_lists(self, mock_ip, mock_engine_sync):
        result = sync.run(self.base_dir, engine="iptables", force=False)
        self.assertEqual(
            result, {"engine": "iptables", "session_ip": "203.0.113.9", "firewalld_zone": None, "fail2ban": None},
        )

        kwargs = mock_engine_sync.call_args.kwargs
        self.assertEqual(kwargs["failsafe_ip"], "203.0.113.9")
        self.assertIn(("127.0.0.1", "LOCALHOST"), kwargs["ip_accept"])
        self.assertTrue((self.base_dir / "ip_accept.conf").exists())

    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_run_syncs_fail2ban_with_trusted_ips(self, mock_ip, mock_engine_sync):
        self.mock_f2b_sync.return_value = {"jails": 1, "trusted": 2, "unbanned": []}
        result = sync.run(self.base_dir, engine="iptables", force=False)
        trusted = self.mock_f2b_sync.call_args.args[0]
        self.assertIn("127.0.0.1", trusted)
        self.assertEqual(result["fail2ban"], {"jails": 1, "trusted": 2, "unbanned": []})

    @patch("sync.magnus_detect.is_magnusbilling", return_value=False)
    @patch("sync.firewalld_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_run_syncs_fail2ban_on_firewalld_too(self, mock_ip, mock_engine_sync, mock_magnus):
        sync.run(self.base_dir, engine="firewalld", force=False)
        self.mock_f2b_sync.assert_called_once()

    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_run_does_not_fail_when_fail2ban_sync_errors(self, mock_ip, mock_engine_sync):
        self.mock_f2b_sync.side_effect = RuntimeError("reload falhou")
        result = sync.run(self.base_dir, engine="iptables", force=False)
        self.assertEqual(result["fail2ban"], {"error": "reload falhou"})

    @patch("sync.magnus_detect.is_magnusbilling", return_value=False)
    @patch("sync.firewalld_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_dispatches_to_firewalld(self, mock_ip, mock_engine_sync, mock_magnus):
        sync.run(self.base_dir, engine="firewalld", force=False)
        mock_engine_sync.assert_called_once()

    @patch("sync.magnus_detect.is_magnusbilling", return_value=False)
    @patch("sync.firewalld_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_uses_the_own_zone_when_not_magnus(self, mock_ip, mock_engine_sync, mock_magnus):
        sync.run(self.base_dir, engine="firewalld", force=False)
        kwargs = mock_engine_sync.call_args.kwargs
        self.assertEqual(kwargs["zone"], "pvxfw")
        self.assertTrue(kwargs["manage_zone"])

    # achado ao vivo: numa central MagnusBilling, a zona própria (pvxfw) fica inerte
    # (o instalador do Magnus já vincula a interface real à zona "public" dele) --
    # sync passa a mirar direto na "public", sem tomar posse dela.
    @patch("sync.magnus_detect.is_magnusbilling", return_value=True)
    @patch("sync.firewalld_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_targets_the_magnus_public_zone_without_managing_it(self, mock_ip, mock_engine_sync, mock_magnus):
        result = sync.run(self.base_dir, engine="firewalld", force=False)
        kwargs = mock_engine_sync.call_args.kwargs
        self.assertEqual(kwargs["zone"], "public")
        self.assertFalse(kwargs["manage_zone"])
        self.assertEqual(result["firewalld_zone"], "public")

    @patch("sync.magnus_detect.is_magnusbilling", return_value=True)
    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_magnus_detection_never_affects_the_iptables_engine(self, mock_ip, mock_engine_sync, mock_magnus):
        result = sync.run(self.base_dir, engine="iptables", force=False)
        self.assertNotIn("zone", mock_engine_sync.call_args.kwargs)
        self.assertIsNone(result["firewalld_zone"])

    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_log_enabled_is_off_by_default(self, mock_ip, mock_engine_sync):
        sync.run(self.base_dir, engine="iptables", force=False)
        self.assertFalse(mock_engine_sync.call_args.kwargs["log_enabled"])

    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_log_enabled_follows_the_marker_file(self, mock_ip, mock_engine_sync):
        import log_ops
        log_ops.enable(self.base_dir)
        sync.run(self.base_dir, engine="iptables", force=False)
        self.assertTrue(mock_engine_sync.call_args.kwargs["log_enabled"])

    @patch("sync.magnus_detect.is_magnusbilling", return_value=False)
    @patch("sync.firewalld_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_log_enabled_never_passed_to_the_firewalld_engine(self, mock_ip, mock_engine_sync, mock_magnus):
        sync.run(self.base_dir, engine="firewalld", force=False)
        self.assertNotIn("log_enabled", mock_engine_sync.call_args.kwargs)

    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_geo_disabled_when_no_countries_configured(self, mock_ip, mock_engine_sync):
        sync.run(self.base_dir, engine="iptables", force=False)
        self.assertFalse(mock_engine_sync.call_args.kwargs["geo_enabled"])

    @patch("sync.ipset_ops.replace_members")
    @patch("sync.ipset_ops.available", return_value=True)
    @patch("sync.geoip_ops.read_cached_ranges")
    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_geo_enabled_builds_the_ipset_from_cached_ranges(
        self, mock_ip, mock_engine_sync, mock_cached, mock_available, mock_replace
    ):
        (self.base_dir / "geo_accept.conf").write_text("BR\n")

        def fake_cached(base_dir, country):
            return {"BR": ["1.2.3.0/24", "5.6.7.0/24"]}[country]
        mock_cached.side_effect = fake_cached

        sync.run(self.base_dir, engine="iptables", force=False)

        self.assertTrue(mock_engine_sync.call_args.kwargs["geo_enabled"])
        mock_replace.assert_called_once_with(defaults.GEO_IPSET_NAME, ["1.2.3.0/24", "5.6.7.0/24"])

    @patch("sync.geoip_ops.read_cached_ranges", return_value=[])
    @patch("sync.ipset_ops.available", return_value=True)
    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_raises_when_a_configured_country_has_no_cached_ranges_yet(
        self, mock_ip, mock_engine_sync, mock_available, mock_cached
    ):
        (self.base_dir / "geo_accept.conf").write_text("BR\n")
        with self.assertRaisesRegex(RuntimeError, "geo refresh"):
            sync.run(self.base_dir, engine="iptables", force=False)
        mock_engine_sync.assert_not_called()

    @patch("sync.ipset_ops.available", return_value=False)
    @patch("sync.iptables_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_raises_when_ipset_binary_is_unavailable(self, mock_ip, mock_engine_sync, mock_available):
        (self.base_dir / "geo_accept.conf").write_text("BR\n")
        with self.assertRaisesRegex(RuntimeError, "ipset"):
            sync.run(self.base_dir, engine="iptables", force=False)
        mock_engine_sync.assert_not_called()

    @patch("sync.magnus_detect.is_magnusbilling", return_value=False)
    @patch("sync.firewalld_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_geo_never_passed_to_the_firewalld_engine(self, mock_ip, mock_engine_sync, mock_magnus):
        sync.run(self.base_dir, engine="firewalld", force=False)
        self.assertNotIn("geo_enabled", mock_engine_sync.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
