import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import fail2ban_ops

STATUS = "Status\n|- Number of jail:\t2\n`- Jail list:\tasterisk-tcp, sshd\n"


def _result(stdout="", returncode=0, stderr=""):
    return MagicMock(stdout=stdout, returncode=returncode, stderr=stderr)


def _jail_status(banned):
    return _result(
        "Status for the jail: x\n|- Filter\n`- Actions\n"
        f"   |- Currently banned:\t{len(banned)}\n   `- Banned IP list:\t{' '.join(banned)}\n"
    )


class AvailableTest(unittest.TestCase):
    @patch("fail2ban_ops.shutil.which", return_value=None)
    def test_unavailable_without_fail2ban_client(self, mock_which):
        self.assertFalse(fail2ban_ops.available())

    @patch("fail2ban_ops.subprocess.run", return_value=_result(returncode=255))
    @patch("fail2ban_ops.shutil.which", return_value="/usr/bin/fail2ban-client")
    def test_unavailable_when_server_does_not_answer_ping(self, mock_which, mock_run):
        self.assertFalse(fail2ban_ops.available())


class ParseTest(unittest.TestCase):
    @patch("fail2ban_ops.subprocess.run", return_value=_result(STATUS))
    def test_active_jails_parses_status(self, mock_run):
        self.assertEqual(fail2ban_ops.active_jails(), ["asterisk-tcp", "sshd"])

    @patch("fail2ban_ops.subprocess.run", return_value=_jail_status(["1.2.3.4", "168.195.176.30"]))
    def test_banned_ips_parses_jail_status(self, mock_run):
        self.assertEqual(fail2ban_ops.banned_ips("sshd"), ["1.2.3.4", "168.195.176.30"])


class RenderOverrideTest(unittest.TestCase):
    # formato validado contra o parser real do fail2ban 1.0.2: %(known/...)s
    # no [DEFAULT] quebra a config inteira (recursão de interpolação) --
    # DEFAULT leva o valor puro, só as seções de jail usam known/ (mantém o
    # ignoreip que o Issabel já define por jail em jail.d/issabel.conf).
    def test_render_appends_trusted_to_known_ignoreip_per_jail(self):
        text = fail2ban_ops.render_override(["sshd"], ["10.0.0.0/8", "1.2.3.4"])
        self.assertIn("[DEFAULT]\nignoreip = 10.0.0.0/8 1.2.3.4\n", text)
        self.assertIn("[sshd]\nignoreip = %(known/ignoreip)s 10.0.0.0/8 1.2.3.4\n", text)
        default_block = text.split("[DEFAULT]", 1)[1].split("[sshd]", 1)[0]
        self.assertNotIn("known/", default_block)


class SyncTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "pvx-firewall.local"

    def tearDown(self):
        self._tmp.cleanup()

    def _fake_run(self, reload_rc=0):
        calls = []

        def fake(args, **kwargs):
            calls.append(args[1:])
            if args[1:] == ["ping"]:
                return _result("Server replied: pong")
            if args[1:] == ["status"]:
                return _result("Status\n`- Jail list:\tasterisk-tcp\n")
            if args[1:] == ["status", "asterisk-tcp"]:
                return _jail_status(["178.33.95.117", "168.195.176.30"])
            if args[1] == "reload":
                return _result(returncode=reload_rc, stderr="boom" if reload_rc else "")
            return _result()
        return fake, calls

    @patch("fail2ban_ops.shutil.which", return_value="/usr/bin/fail2ban-client")
    def test_sync_writes_override_reloads_and_unbans_trusted(self, mock_which):
        fake, calls = self._fake_run()
        with patch("fail2ban_ops.subprocess.run", side_effect=fake):
            result = fail2ban_ops.sync(["168.195.176.0/22"], path=self.path)
        self.assertIn("[asterisk-tcp]", self.path.read_text())
        self.assertIn(["reload", "--restart"], calls)
        self.assertIn(["set", "asterisk-tcp", "unbanip", "168.195.176.30"], calls)
        self.assertNotIn(["set", "asterisk-tcp", "unbanip", "178.33.95.117"], calls)
        self.assertEqual(result["unbanned"], ["168.195.176.30"])
        self.assertEqual(result["jails"], 1)

    @patch("fail2ban_ops.shutil.which", return_value=None)
    def test_sync_does_nothing_when_fail2ban_is_absent(self, mock_which):
        self.assertIsNone(fail2ban_ops.sync(["1.2.3.4"], path=self.path))
        self.assertFalse(self.path.exists())

    @patch("fail2ban_ops.shutil.which", return_value="/usr/bin/fail2ban-client")
    def test_sync_raises_with_stderr_when_reload_fails(self, mock_which):
        fake, _ = self._fake_run(reload_rc=1)
        with patch("fail2ban_ops.subprocess.run", side_effect=fake):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                fail2ban_ops.sync(["1.2.3.4"], path=self.path)

    @patch("fail2ban_ops.shutil.which", return_value="/usr/bin/fail2ban-client")
    def test_is_synced_true_only_when_override_matches_current_trusted(self, mock_which):
        fake, _ = self._fake_run()
        with patch("fail2ban_ops.subprocess.run", side_effect=fake):
            self.assertFalse(fail2ban_ops.is_synced(["1.2.3.4"], path=self.path))
            fail2ban_ops.sync(["1.2.3.4"], path=self.path)
            self.assertTrue(fail2ban_ops.is_synced(["1.2.3.4"], path=self.path))
            self.assertFalse(fail2ban_ops.is_synced(["1.2.3.4", "5.6.7.8"], path=self.path))

    @patch("fail2ban_ops.shutil.which", return_value=None)
    def test_is_synced_is_none_when_fail2ban_is_absent(self, mock_which):
        self.assertIsNone(fail2ban_ops.is_synced(["1.2.3.4"], path=self.path))


if __name__ == "__main__":
    unittest.main()
