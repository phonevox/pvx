import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit.sh"

_STUBS = {
    "ss": 'printf "%s\\n" "$FAKE_SS"',
    "iptables": 'printf "%s\\n" "$FAKE_IPT"',
    "firewall-cmd": (
        'case "$1" in\n'
        '  --state) [ "$FAKE_FWD" = running ] && echo running || exit 252 ;;\n'
        '  --list-ports) echo "$FAKE_FWD_PORTS" ;;\n'
        '  --list-services) echo "$FAKE_FWD_SERVICES" ;;\n'
        'esac'
    ),
}


def _run_check(ss="", iptables="-P INPUT ACCEPT", firewalld=None, fwd_ports="", fwd_services=""):
    with tempfile.TemporaryDirectory() as stub_dir:
        for name, body in _STUBS.items():
            path = Path(stub_dir) / name
            path.write_text(f"#!/bin/sh\n{body}\n")
            path.chmod(0o755)
        env = dict(
            os.environ, FAKE_SS=ss, FAKE_IPT=iptables, FAKE_FWD=firewalld or "",
            FAKE_FWD_PORTS=fwd_ports, FAKE_FWD_SERVICES=fwd_services,
        )
        result = subprocess.run(
            [shutil.which("bash"), "-c",
             f'AUDIT_NO_MAIN=1 source "{SCRIPT}"; PATH="{stub_dir}:$PATH"; '
             'check_admin_ports; printf "%s\\n" "${F_MSG[@]:-}"'],
            capture_output=True, text=True, env=env,
        )
    return result.stdout


class CheckAdminPortsTest(unittest.TestCase):
    def test_flags_mysql_listening_publicly_without_firewall(self):
        out = _run_check(ss="LISTEN 0 80 0.0.0.0:3306 0.0.0.0:*")
        self.assertIn("3306", out)

    def test_ignores_port_listening_only_on_loopback(self):
        out = _run_check(ss="LISTEN 0 80 127.0.0.1:3306 0.0.0.0:*")
        self.assertNotIn("3306", out)

    def test_ignores_port_dropped_by_iptables_rule(self):
        out = _run_check(
            ss="LISTEN 0 80 0.0.0.0:3306 0.0.0.0:*",
            iptables="-P INPUT ACCEPT\n-A pdrop -p tcp -m tcp --dport 3306 -j DROP",
        )
        self.assertNotIn("3306", out)

    def test_ignores_when_input_policy_is_drop(self):
        out = _run_check(ss="LISTEN 0 80 0.0.0.0:3306 0.0.0.0:*", iptables="-P INPUT DROP")
        self.assertNotIn("3306", out)

    def test_flags_ami_opened_in_firewalld(self):
        out = _run_check(ss="LISTEN 0 5 0.0.0.0:5038 0.0.0.0:*", firewalld="running", fwd_ports="5038/tcp")
        self.assertIn("5038", out)

    def test_ignores_when_firewalld_does_not_open_the_port(self):
        out = _run_check(ss="LISTEN 0 5 0.0.0.0:5038 0.0.0.0:*", firewalld="running", fwd_ports="5060/udp")
        self.assertNotIn("5038", out)


if __name__ == "__main__":
    unittest.main()
