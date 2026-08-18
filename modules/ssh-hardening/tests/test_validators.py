import unittest

from validators import validate_port, validate_public_key, validate_username


class ValidateUsernameTest(unittest.TestCase):
    def test_accepts_lowercase_letters_digits_underscore_hyphen(self):
        self.assertTrue(validate_username("phonevox"))
        self.assertTrue(validate_username("dev_user-2"))

    def test_rejects_name_starting_with_digit_or_hyphen(self):
        self.assertFalse(validate_username("2fast"))
        self.assertFalse(validate_username("-user"))

    def test_rejects_uppercase(self):
        self.assertFalse(validate_username("Phonevox"))

    def test_rejects_longer_than_32_chars(self):
        self.assertFalse(validate_username("a" * 33))

    def test_accepts_exactly_32_chars(self):
        self.assertTrue(validate_username("a" * 32))

    def test_rejects_empty(self):
        self.assertFalse(validate_username(""))


class ValidatePublicKeyTest(unittest.TestCase):
    def test_accepts_ssh_rsa_with_comment(self):
        self.assertTrue(validate_public_key("ssh-rsa AAAAB3NzaC1yc2EAAA MAIN@PHONEVOX"))

    def test_accepts_ed25519_without_comment(self):
        self.assertTrue(validate_public_key("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAA"))

    def test_accepts_ecdsa_variants(self):
        self.assertTrue(validate_public_key("ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTIt"))

    def test_rejects_unknown_key_type(self):
        self.assertFalse(validate_public_key("ssh-dss AAAAB3NzaC1kc3MAAA"))

    def test_rejects_missing_body(self):
        self.assertFalse(validate_public_key("ssh-rsa"))

    def test_rejects_empty(self):
        self.assertFalse(validate_public_key(""))


class ValidatePortTest(unittest.TestCase):
    def test_accepts_valid_range(self):
        self.assertTrue(validate_port("1"))
        self.assertTrue(validate_port("21122"))
        self.assertTrue(validate_port("65535"))

    def test_rejects_zero_and_above_max(self):
        self.assertFalse(validate_port("0"))
        self.assertFalse(validate_port("65536"))

    def test_rejects_non_digit(self):
        self.assertFalse(validate_port("22a"))
        self.assertFalse(validate_port(""))
        self.assertFalse(validate_port("-1"))


if __name__ == "__main__":
    unittest.main()
