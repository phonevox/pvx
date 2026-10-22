import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import webhook_ops


class SetGetClearTest(unittest.TestCase):
    def test_none_when_never_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(webhook_ops.get(tmp))

    def test_set_then_get_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            webhook_ops.set_url(tmp, "https://hooks.example.com/abc")
            self.assertEqual(webhook_ops.get(tmp), "https://hooks.example.com/abc")

    def test_clear_removes_the_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            webhook_ops.set_url(tmp, "https://hooks.example.com/abc")
            webhook_ops.clear(tmp)
            self.assertIsNone(webhook_ops.get(tmp))

    def test_clear_is_safe_when_never_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            webhook_ops.clear(tmp)  # não explode

    def test_set_creates_the_state_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "state"
            webhook_ops.set_url(target, "https://hooks.example.com/abc")
            self.assertEqual(webhook_ops.get(target), "https://hooks.example.com/abc")


class NotifyTest(unittest.TestCase):
    def test_fails_cleanly_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, reason = webhook_ops.notify(tmp, "evento", "detalhe")
        self.assertFalse(ok)
        self.assertIsNotNone(reason)

    @patch("webhook_ops.urllib.request.urlopen")
    def test_posts_json_with_event_and_detail(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = MagicMock()
        with tempfile.TemporaryDirectory() as tmp:
            webhook_ops.set_url(tmp, "https://hooks.example.com/abc")
            ok, reason = webhook_ops.notify(tmp, "check_drift", "regras divergentes")
        self.assertTrue(ok)
        self.assertIsNone(reason)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://hooks.example.com/abc")
        self.assertIn(b"check_drift", request.data)
        self.assertIn(b"regras divergentes", request.data)

    @patch("webhook_ops.urllib.request.urlopen", side_effect=urllib.error.URLError("sem rede"))
    def test_network_failure_never_raises(self, mock_urlopen):
        with tempfile.TemporaryDirectory() as tmp:
            webhook_ops.set_url(tmp, "https://hooks.example.com/abc")
            ok, reason = webhook_ops.notify(tmp, "evento")
        self.assertFalse(ok)
        self.assertIsNotNone(reason)


if __name__ == "__main__":
    unittest.main()
