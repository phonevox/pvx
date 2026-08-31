import unittest

import metadata


class BuildTest(unittest.TestCase):
    # build() só monta a parte auto-detectada -- o usuário edita o resultado inteiro
    # depois (ver main.py: ask_text com default=build(...), geralmente só aperta Enter).
    # Não tem mais "extra" separado aqui -- validate() cobre o texto final, seja ele
    # editado ou não.
    def test_includes_base_fields(self):
        result = metadata.build(provider="ovh", os_label="rocky-8.10")
        self.assertEqual(result, "l:ovh os:linux osn:rocky-8.10")

    def test_includes_asterisk_version_when_given(self):
        result = metadata.build(provider="local", os_label="rocky-8.10", asterisk_version="18")
        self.assertIn("av:18", result)

    def test_omits_asterisk_when_not_given(self):
        result = metadata.build(provider="local", os_label="rocky-8.10")
        self.assertNotIn("av:", result)

    def test_includes_test_flag_when_true(self):
        result = metadata.build(provider="local", os_label="rocky-8.10", test=True)
        self.assertIn("test:true", result)

    def test_omits_test_flag_when_false(self):
        result = metadata.build(provider="local", os_label="rocky-8.10", test=False)
        self.assertNotIn("test:", result)


class ValidateTest(unittest.TestCase):
    def test_accepts_value_within_limit(self):
        metadata.validate("l:ovh os:linux osn:rocky-8.10")  # não deve levantar

    def test_raises_when_metadata_exceeds_255_chars(self):
        # o script bash original tinha essa checagem quebrada (exit dentro de um
        # subshell só mata o subshell, nunca o script real) -- metadata truncado
        # ia pro Zabbix sem avisar ninguém. Aqui precisa levantar de verdade.
        with self.assertRaises(metadata.MetadataTooLongError):
            metadata.validate("x" * 300)


if __name__ == "__main__":
    unittest.main()
