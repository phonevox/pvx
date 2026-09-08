import unittest

import validators


class IsValidDomainTest(unittest.TestCase):
    def test_accepts_a_normal_domain(self):
        self.assertTrue(validators.is_valid_domain("central.falevox.com.br"))

    def test_accepts_a_single_subdomain_level(self):
        self.assertTrue(validators.is_valid_domain("example.com"))

    def test_rejects_a_bare_hostname_without_a_dot(self):
        self.assertFalse(validators.is_valid_domain("localhost"))

    def test_rejects_an_ip_address(self):
        # certbot/LE não emite certificado pra IP -- e aceitar um aqui mascara o erro
        # real (usuário quis dizer o domínio) com uma falha bem mais tarde, no certbot.
        self.assertFalse(validators.is_valid_domain("187.77.247.148"))

    def test_rejects_empty_string(self):
        self.assertFalse(validators.is_valid_domain(""))

    def test_rejects_a_value_with_a_path_separator(self):
        # o domínio vira parte de caminho real (/etc/letsencrypt/live/<dominio>/,
        # <dominio>.conf) -- isso é o que impede um path traversal ali.
        self.assertFalse(validators.is_valid_domain("../../etc/passwd"))
        self.assertFalse(validators.is_valid_domain("evil.com/../../etc"))

    def test_rejects_a_value_with_whitespace_or_shell_metacharacters(self):
        self.assertFalse(validators.is_valid_domain("evil.com; rm -rf /"))
        self.assertFalse(validators.is_valid_domain("evil.com`id`"))
        self.assertFalse(validators.is_valid_domain("evil.com $(id)"))

    def test_rejects_leading_or_trailing_hyphen_in_a_label(self):
        self.assertFalse(validators.is_valid_domain("-evil.com"))
        self.assertFalse(validators.is_valid_domain("evil-.com"))

    def test_accepts_hyphen_in_the_middle_of_a_label(self):
        self.assertTrue(validators.is_valid_domain("meu-dominio.com.br"))


class IsValidEmailTest(unittest.TestCase):
    def test_accepts_a_normal_email(self):
        self.assertTrue(validators.is_valid_email("suporte@phonevox.com.br"))

    def test_rejects_missing_at_sign(self):
        self.assertFalse(validators.is_valid_email("suporte.phonevox.com.br"))

    def test_rejects_missing_domain_dot(self):
        self.assertFalse(validators.is_valid_email("suporte@phonevox"))

    def test_rejects_empty_string(self):
        self.assertFalse(validators.is_valid_email(""))

    def test_rejects_whitespace_or_shell_metacharacters(self):
        self.assertFalse(validators.is_valid_email("a b@example.com"))
        self.assertFalse(validators.is_valid_email("a@example.com; rm -rf /"))


if __name__ == "__main__":
    unittest.main()
