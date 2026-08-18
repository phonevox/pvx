import unittest

from validators import parse_port_spec, validate_cidr


class ParsePortSpecTest(unittest.TestCase):
    def test_single_port_no_protocol(self):
        self.assertEqual(parse_port_spec("80"), {"start": 80, "end": 80, "protocol": None})

    def test_single_port_with_protocol(self):
        self.assertEqual(parse_port_spec("5060/udp"), {"start": 5060, "end": 5060, "protocol": "udp"})

    def test_range_with_protocol(self):
        self.assertEqual(
            parse_port_spec("10000-20000/udp"), {"start": 10000, "end": 20000, "protocol": "udp"}
        )

    def test_range_without_protocol(self):
        self.assertEqual(parse_port_spec("20-23"), {"start": 20, "end": 23, "protocol": None})

    def test_rejects_unknown_protocol(self):
        with self.assertRaises(ValueError):
            parse_port_spec("80/http")

    def test_rejects_out_of_range_port(self):
        with self.assertRaises(ValueError):
            parse_port_spec("70000")
        with self.assertRaises(ValueError):
            parse_port_spec("0")

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            parse_port_spec("100-50")

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            parse_port_spec("abc")


class ValidateCidrTest(unittest.TestCase):
    def test_accepts_bare_ip_as_implicit_slash_32(self):
        self.assertTrue(validate_cidr("189.124.85.75"))

    def test_accepts_cidr_notation(self):
        self.assertTrue(validate_cidr("10.0.0.0/8"))
        self.assertTrue(validate_cidr("192.168.0.0/16"))
        self.assertTrue(validate_cidr("189.124.85.152/29"))

    def test_rejects_dotted_decimal_mask(self):
        self.assertFalse(validate_cidr("10.0.0.0/255.0.0.0"))

    def test_rejects_invalid_address(self):
        self.assertFalse(validate_cidr("999.1.1.1"))

    def test_rejects_ipv6(self):
        self.assertFalse(validate_cidr("::1"))

    def test_rejects_prefix_out_of_range(self):
        self.assertFalse(validate_cidr("10.0.0.0/33"))


if __name__ == "__main__":
    unittest.main()
