import unittest

import metadata


class BuildTest(unittest.TestCase):
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

    def test_appends_extra_freeform_metadata_last(self):
        result = metadata.build(provider="local", os_label="rocky-8.10", extra="custom:value")
        self.assertTrue(result.endswith("custom:value"))

    def test_raises_when_metadata_exceeds_255_chars(self):
        # o script bash original tinha essa checagem quebrada (exit dentro de um
        # subshell só mata o subshell, nunca o script real) -- metadata truncado
        # ia pro Zabbix sem avisar ninguém. Aqui precisa levantar de verdade.
        with self.assertRaises(metadata.MetadataTooLongError):
            metadata.build(provider="local", os_label="rocky-8.10", extra="x" * 300)


if __name__ == "__main__":
    unittest.main()
