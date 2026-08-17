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
        self.assertEqual(result, {"engine": "iptables", "session_ip": "203.0.113.9"})

        kwargs = mock_engine_sync.call_args.kwargs
        self.assertEqual(kwargs["failsafe_ip"], "203.0.113.9")
        self.assertIn(("127.0.0.1", "LOCALHOST"), kwargs["ip_accept"])
        self.assertTrue((self.base_dir / "ip_accept.conf").exists())

    @patch("sync.firewalld_engine.sync")
    @patch("sync.session_ip.detect_session_ip", return_value="203.0.113.9")
    def test_dispatches_to_firewalld(self, mock_ip, mock_engine_sync):
        sync.run(self.base_dir, engine="firewalld", force=False)
        mock_engine_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
