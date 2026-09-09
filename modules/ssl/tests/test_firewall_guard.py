import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

import firewall_guard


def _proc(returncode=0, stdout=""):
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class OpenPortTest(unittest.TestCase):
    @patch("firewall_guard.subprocess.run")
    @patch("firewall_guard.shutil.which", return_value=None)
    def test_opens_firewalld_when_active(self, mock_which, mock_run):
        mock_run.return_value = _proc(returncode=0)  # systemctl is-active -> ok
        opened = firewall_guard.open_port(80)
        self.assertIn("firewalld", opened)
        args_list = [c.args[0] for c in mock_run.call_args_list]
        self.assertIn(["firewall-cmd", "--add-port", "80/tcp"], args_list)

    @patch("firewall_guard.subprocess.run")
    @patch("firewall_guard.shutil.which", return_value=None)
    def test_skips_firewalld_when_inactive(self, mock_which, mock_run):
        mock_run.return_value = _proc(returncode=3)  # systemctl is-active -> inactive
        opened = firewall_guard.open_port(80)
        self.assertEqual(opened, [])

    @patch("firewall_guard.subprocess.run")
    @patch("firewall_guard.shutil.which", return_value="/usr/sbin/ufw")
    def test_opens_ufw_when_active(self, mock_which, mock_run):
        def fake_run(args, **kwargs):
            if args[:2] == ["systemctl", "is-active"]:
                return _proc(returncode=3)
            if args[:2] == ["ufw", "status"]:
                return _proc(returncode=0, stdout="Status: active\n")
            return _proc(returncode=0)

        mock_run.side_effect = fake_run
        opened = firewall_guard.open_port(80)
        self.assertIn("ufw", opened)
        args_list = [c.args[0] for c in mock_run.call_args_list]
        self.assertIn(["ufw", "allow", "80/tcp"], args_list)

    @patch("firewall_guard.subprocess.run")
    @patch("firewall_guard.shutil.which", return_value=None)
    def test_never_flushes_or_disables_anything(self, mock_which, mock_run):
        # achado da revisão do script-base: nada aqui pode fazer flush/disable -- só
        # abre uma regra pontual, nunca mexe no estado geral do firewall.
        mock_run.return_value = _proc(returncode=0)
        firewall_guard.open_port(80)
        for call_args in mock_run.call_args_list:
            args = call_args.args[0]
            self.assertNotIn("-F", args)
            self.assertNotIn("disable", args)
            self.assertNotIn("stop", args)

    @patch("firewall_guard.subprocess.run")
    @patch("firewall_guard.shutil.which", return_value="/usr/sbin/iptables")
    def test_inserts_a_scoped_iptables_accept_rule_when_none_exists(self, mock_which, mock_run):
        # achado ao vivo: firewalld/ufw inativos os dois, mas regras iptables cruas
        # (sem serviço nenhum pra detectar) bloqueavam a 80 mesmo assim -- o
        # script-base cobria isso com "iptables -F" (destrutivo); aqui é uma regra
        # pontual, reversível, no topo da INPUT.
        def fake_run(args, **kwargs):
            if args[:2] == ["systemctl", "is-active"]:
                return _proc(returncode=3)
            if args[:3] == ["iptables", "-C", "INPUT"]:
                return _proc(returncode=1)  # regra ainda não existe
            return _proc(returncode=0)

        mock_run.side_effect = fake_run
        opened = firewall_guard.open_port(80)
        self.assertIn("iptables", opened)
        args_list = [c.args[0] for c in mock_run.call_args_list]
        self.assertIn(["iptables", "-I", "INPUT", "1", "-p", "tcp", "--dport", "80", "-j", "ACCEPT"], args_list)

    @patch("firewall_guard.subprocess.run")
    @patch("firewall_guard.shutil.which", return_value="/usr/sbin/iptables")
    def test_does_not_duplicate_an_already_present_iptables_rule(self, mock_which, mock_run):
        def fake_run(args, **kwargs):
            if args[:2] == ["systemctl", "is-active"]:
                return _proc(returncode=3)
            if args[:3] == ["iptables", "-C", "INPUT"]:
                return _proc(returncode=0)  # já existe
            return _proc(returncode=0)

        mock_run.side_effect = fake_run
        opened = firewall_guard.open_port(80)
        self.assertNotIn("iptables", opened)
        args_list = [c.args[0] for c in mock_run.call_args_list]
        self.assertNotIn(["iptables", "-I", "INPUT", "1", "-p", "tcp", "--dport", "80", "-j", "ACCEPT"], args_list)

    @patch("firewall_guard.subprocess.run")
    @patch("firewall_guard.shutil.which", return_value=None)
    def test_skips_iptables_entirely_when_binary_is_absent(self, mock_which, mock_run):
        mock_run.return_value = _proc(returncode=3)
        opened = firewall_guard.open_port(80)
        self.assertNotIn("iptables", opened)


class ClosePortTest(unittest.TestCase):
    @patch("firewall_guard.subprocess.run")
    def test_removes_only_what_was_opened(self, mock_run):
        mock_run.return_value = _proc(returncode=0)
        firewall_guard.close_port(80, ["firewalld"])
        args_list = [c.args[0] for c in mock_run.call_args_list]
        self.assertEqual(args_list, [["firewall-cmd", "--remove-port", "80/tcp"]])

    @patch("firewall_guard.subprocess.run")
    def test_noop_when_nothing_was_opened(self, mock_run):
        firewall_guard.close_port(80, [])
        mock_run.assert_not_called()

    @patch("firewall_guard.subprocess.run")
    def test_removes_the_iptables_rule_when_it_was_opened(self, mock_run):
        mock_run.return_value = _proc(returncode=0)
        firewall_guard.close_port(80, ["iptables"])
        args_list = [c.args[0] for c in mock_run.call_args_list]
        self.assertEqual(args_list, [["iptables", "-D", "INPUT", "-p", "tcp", "--dport", "80", "-j", "ACCEPT"]])


class TemporarilyOpenTest(unittest.TestCase):
    @patch("firewall_guard.close_port")
    @patch("firewall_guard.open_port", return_value=["firewalld"])
    def test_closes_what_it_opened_even_when_the_body_raises(self, mock_open, mock_close):
        with self.assertRaises(RuntimeError):
            with firewall_guard.temporarily_open(80):
                raise RuntimeError("boom")
        mock_close.assert_called_once_with(80, ["firewalld"])

    @patch("firewall_guard.close_port")
    @patch("firewall_guard.open_port", return_value=[])
    def test_closes_after_a_normal_run(self, mock_open, mock_close):
        with firewall_guard.temporarily_open(80):
            pass
        mock_close.assert_called_once_with(80, [])


if __name__ == "__main__":
    unittest.main()
