import unittest
from unittest.mock import patch

import asterisk_ips

SIP_PEERS_OUTPUT = """Name/username             Host                                    Dyn Forcerport ACL Port     Status
1001                      192.168.1.50                             D                      5060     Unmonitored
trunk1                    203.0.113.5                                                     5060     OK (15 ms)
2 sip peers [Monitored: 1 online, 0 offline Unmonitored: 1 online, 0 offline]
"""

PJSIP_ENDPOINTS_OUTPUT = """ Endpoint:  1001                                                    Not in use    0 of inf
        Aor:  1001                                                    1
      Contact:  1001/sip:1001@198.51.100.9:5060                     5a6f Avail        10.014
 Endpoint:  1002                                                    Unavailable   0 of inf
"""

SIP_REGISTRY_OUTPUT = """Host                                    dnsmgr Username       Refresh State                Reg.Time
203.0.113.5:5060                       N      trunk1         105 Registered            Fri, 01 Jan 2026
"""


class DiscoverAsteriskIpsTest(unittest.TestCase):
    @patch("asterisk_ips._cli")
    def test_extracts_ips_from_all_three_sources(self, mock_cli):
        mock_cli.side_effect = lambda cmd, **kw: {
            "sip show peers": SIP_PEERS_OUTPUT,
            "pjsip show endpoints": PJSIP_ENDPOINTS_OUTPUT,
            "sip show registry": SIP_REGISTRY_OUTPUT,
        }.get(cmd)

        found = asterisk_ips.discover_asterisk_ips()

        self.assertEqual(found.get("192.168.1.50"), "sip show peers")
        self.assertEqual(found.get("203.0.113.5"), "sip show peers")  # primeira fonte que achou, vence
        self.assertEqual(found.get("198.51.100.9"), "pjsip show endpoints")

    @patch("asterisk_ips._cli", return_value=None)
    def test_empty_when_asterisk_is_unreachable(self, mock_cli):
        self.assertEqual(asterisk_ips.discover_asterisk_ips(), {})

    @patch("asterisk_ips._cli")
    def test_ignores_placeholder_addresses(self, mock_cli):
        mock_cli.side_effect = lambda cmd, **kw: (
            "Host: 0.0.0.0:0 (Unspecified)\n" if cmd == "sip show peers" else None
        )
        self.assertEqual(asterisk_ips.discover_asterisk_ips(), {})


class CliTest(unittest.TestCase):
    @patch("asterisk_ips.subprocess.run", side_effect=OSError("asterisk não encontrado"))
    def test_returns_none_when_asterisk_binary_is_missing(self, mock_run):
        self.assertIsNone(asterisk_ips._cli("core show version"))


if __name__ == "__main__":
    unittest.main()
