import unittest

from template_patch import patch


class PatchTest(unittest.TestCase):
    def test_replaces_placeholder_when_present(self):
        result = patch("url={{URL}}\n", {"{{URL}}": "https://erp.example.com"})
        self.assertEqual(result, "url=https://erp.example.com\n")

    def test_replaces_multiple_placeholders_in_one_pass(self):
        result = patch(
            "url={{URL}}\ntoken={{TOKEN}}\n",
            {"{{URL}}": "https://erp.example.com", "{{TOKEN}}": "abc123"},
        )
        self.assertEqual(result, "url=https://erp.example.com\ntoken=abc123\n")

    def test_ignores_a_placeholder_absent_from_the_template(self):
        # achado ao vivo, conferido contra o instalador bash original: cada substituição
        # lá é um "sed -i 's|X|Y|'" -- se X não existe no arquivo, sed não erra, só não
        # muda nada. Templates reais legitimamente não têm todo placeholder previsto
        # (ex.: sgp não tem a variante sem sufixo de "ocorrencia_comercial").
        result = patch("token=fixo\n", {"{{TOKEN}}": "abc123"})
        self.assertEqual(result, "token=fixo\n")

    def test_applies_the_replacements_that_do_match_even_when_others_dont(self):
        result = patch(
            "url={{URL}}\ntoken=fixo\n",
            {"{{URL}}": "https://erp.example.com", "{{TOKEN}}": "abc123"},
        )
        self.assertEqual(result, "url=https://erp.example.com\ntoken=fixo\n")


if __name__ == "__main__":
    unittest.main()
