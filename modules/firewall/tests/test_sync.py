import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            result, {"engine": "iptables", "session_ip": "203.0.113.9", "firewalld_zone": None},
        )

        kwargs = mock_engine_sync.call_args.kwargs
        self.assertEqual(kwargs["failsafe_ip"], "203.0.113.9")
        self.assertIn(("127.0.0.1", "LOCALHOST"), kwargs["ip_accept"])
        self.assertTrue((self.base_dir / "ip_accept.conf").exists())

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


if __name__ == "__main__":
    unittest.main()
