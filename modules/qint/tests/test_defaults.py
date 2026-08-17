import unittest

import defaults

_COMPLETE_IXCSOFT = {
    "type": "ixcsoft",
    "sftp_user": "x",
    "sftp_host": "y",
    "erp_url": "https://erp.example.com",
    "token": "abc",
    "id_timecondition_exitpoint": "10",
    "fila_geral": "1",
    "fila_comercial": "2",
    "fila_suporte": "3",
    "fila_financeiro": "4",
    "asterisk_ip": "10.0.0.1",
    "id_departamento_geral": "1",
    "id_departamento_comercial": "2",
    "id_departamento_suporte": "3",
    "id_departamento_financeiro": "4",
    "id_assunto_geral": "1",
    "id_assunto_comercial": "2",
    "id_assunto_suporte": "3",
    "id_assunto_financeiro": "4",
}

_COMPLETE_SGP = {
    "type": "sgp",
    "sftp_user": "x",
    "sftp_host": "y",
    "erp_url": "https://erp.example.com",
    "token": "abc",
    "id_timecondition_exitpoint": "10",
    "fila_geral": "1",
    "fila_comercial": "2",
    "fila_suporte": "3",
    "fila_financeiro": "4",
    "asterisk_ip": "10.0.0.1",
    "id_setor_geral": "1",
    "id_setor_comercial": "2",
    "id_setor_suporte": "3",
    "id_setor_financeiro": "4",
    "id_ocorrencia_geral": "1",
    "id_ocorrencia_comercial": "2",
    "id_ocorrencia_suporte": "3",
    "id_ocorrencia_financeiro": "4",
    "id_motivo_os_geral": "1",
    "id_motivo_os_comercial": "2",
    "id_motivo_os_suporte": "3",
    "id_motivo_os_financeiro": "4",
}


class ApplyDefaultsTest(unittest.TestCase):
    def test_fills_common_and_type_defaults(self):
        merged = defaults.apply_defaults({"type": "ixcsoft"})
        self.assertEqual(merged["sftp_port"], 22)
        self.assertEqual(merged["sftp_remote_path"], "/sfiles/qint/integracoes")
        self.assertEqual(merged["sftp_versao"], "recent")
        self.assertEqual(merged["id_filial"], "1")

    def test_sgp_gets_its_own_default(self):
        merged = defaults.apply_defaults({"type": "sgp"})
        self.assertEqual(merged["app"], "app")

    def test_explicit_value_is_never_overwritten_by_default(self):
        merged = defaults.apply_defaults({"type": "ixcsoft", "sftp_versao": "1.2.3", "id_filial": "9"})
        self.assertEqual(merged["sftp_versao"], "1.2.3")
        self.assertEqual(merged["id_filial"], "9")


class MissingFieldsTest(unittest.TestCase):
    def test_everything_missing_on_a_freshly_typed_config(self):
        missing = defaults.missing_fields({"type": "ixcsoft"})
        for field in (
            "sftp_user", "sftp_host", "erp_url", "token", "id_timecondition_exitpoint",
            "fila_geral", "fila_comercial", "fila_suporte", "fila_financeiro", "asterisk_ip",
            "id_departamento_geral", "id_assunto_geral",
        ):
            self.assertIn(field, missing)

    def test_fields_with_defaults_are_never_reported_missing(self):
        missing = defaults.missing_fields({"type": "ixcsoft"})
        self.assertNotIn("sftp_port", missing)
        self.assertNotIn("sftp_remote_path", missing)
        self.assertNotIn("sftp_versao", missing)
        self.assertNotIn("id_filial", missing)

    def test_nothing_missing_when_ixcsoft_config_is_complete(self):
        self.assertEqual(defaults.missing_fields(_COMPLETE_IXCSOFT), [])

    def test_nothing_missing_when_sgp_config_is_complete(self):
        self.assertEqual(defaults.missing_fields(_COMPLETE_SGP), [])

    def test_sgp_does_not_require_ixcsoft_only_fields(self):
        missing = defaults.missing_fields(_COMPLETE_SGP)
        self.assertNotIn("id_departamento_geral", missing)
        self.assertNotIn("id_assunto_geral", missing)

    def test_ixcsoft_does_not_require_sgp_only_fields(self):
        missing = defaults.missing_fields(_COMPLETE_IXCSOFT)
        self.assertNotIn("id_setor_geral", missing)
        self.assertNotIn("id_ocorrencia_geral", missing)
        self.assertNotIn("id_motivo_os_geral", missing)


if __name__ == "__main__":
    unittest.main()
