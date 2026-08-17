import unittest

from validators import parse_csv4, parse_sftp, validate_url


class ParseSftpTest(unittest.TestCase):
    def test_parses_user_host_with_default_port(self):
        self.assertEqual(parse_sftp("root@10.0.0.1"), {"user": "root", "host": "10.0.0.1", "port": 22})

    def test_parses_user_host_with_explicit_port(self):
        self.assertEqual(
            parse_sftp("root@10.0.0.1:2222"), {"user": "root", "host": "10.0.0.1", "port": 2222}
        )

    def test_rejects_missing_at_sign(self):
        with self.assertRaises(ValueError):
            parse_sftp("10.0.0.1")

    def test_rejects_empty_user_or_host(self):
        with self.assertRaises(ValueError):
            parse_sftp("@10.0.0.1")
        with self.assertRaises(ValueError):
            parse_sftp("root@")


class ValidateUrlTest(unittest.TestCase):
    def test_accepts_http_and_https_with_no_path(self):
        self.assertTrue(validate_url("http://erp.example.com"))
        self.assertTrue(validate_url("https://erp.example.com:8080"))

    def test_rejects_missing_scheme(self):
        self.assertFalse(validate_url("erp.example.com"))

    def test_rejects_trailing_slash_or_path(self):
        self.assertFalse(validate_url("https://erp.example.com/"))
        self.assertFalse(validate_url("https://erp.example.com/api"))


class ParseCsv4Test(unittest.TestCase):
    def test_splits_four_values(self):
        self.assertEqual(
            parse_csv4("1,2,3,4", ("a", "b", "c", "d")), ("1", "2", "3", "4")
        )

    def test_empty_segment_preserves_existing_value(self):
        self.assertEqual(
            parse_csv4(",2,,4", ("a", "b", "c", "d")), ("a", "2", "c", "4")
        )

    def test_empty_string_preserves_all_existing_values(self):
        self.assertEqual(parse_csv4("", ("a", "b", "c", "d")), ("a", "b", "c", "d"))

    def test_none_preserves_all_existing_values(self):
        self.assertEqual(parse_csv4(None, ("a", "b", "c", "d")), ("a", "b", "c", "d"))


if __name__ == "__main__":
    unittest.main()
