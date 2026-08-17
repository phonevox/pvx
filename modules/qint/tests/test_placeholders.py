import unittest

import placeholders

_BASE_CONFIG = {
    "asterisk_ip": "10.0.0.1",
    "erp_url": "https://erp.example.com:8080",
    "token": "abc123",
    "app": "app",
    "fila_geral": "600",
    "fila_comercial": "601",
    "fila_suporte": "602",
    "fila_financeiro": "603",
    "id_timecondition_exitpoint": "10",
    "id_filial": "1",
    "id_departamento_geral": "1",
    "id_departamento_comercial": "2",
    "id_departamento_suporte": "3",
    "id_departamento_financeiro": "4",
    "id_assunto_geral": "1",
    "id_assunto_comercial": "2",
    "id_assunto_suporte": "3",
    "id_assunto_financeiro": "4",
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


class BuildPhpReplacementsTest(unittest.TestCase):
    def test_maps_asterisk_ip_and_token_directly(self):
        result = placeholders.build_php_replacements({**_BASE_CONFIG, "type": "ixcsoft"})
        self.assertEqual(result["$server_local = ''"], "10.0.0.1")
        self.assertEqual(result["$token = ''"], "abc123")

    def test_derives_scheme_host_and_port_from_erp_url(self):
        result = placeholders.build_php_replacements({**_BASE_CONFIG, "type": "ixcsoft"})
        self.assertEqual(result["$protocol_web = ''"], "https")
        self.assertEqual(result["$servidor_web = ''"], "erp.example.com")
        self.assertEqual(result["$porta_web = ''"], "8080")

    def test_erp_url_without_explicit_port_yields_empty_port(self):
        config = {**_BASE_CONFIG, "type": "ixcsoft", "erp_url": "https://erp.example.com"}
        result = placeholders.build_php_replacements(config)
        self.assertEqual(result["$porta_web = ''"], "")

    def test_ixcsoft_does_not_include_app_placeholder(self):
        result = placeholders.build_php_replacements({**_BASE_CONFIG, "type": "ixcsoft"})
        self.assertNotIn("$app = ''", result)

    def test_sgp_includes_app_placeholder(self):
        result = placeholders.build_php_replacements({**_BASE_CONFIG, "type": "sgp", "app": "meuapp"})
        self.assertEqual(result["$app = ''"], "meuapp")


class BuildMacroReplacementsTest(unittest.TestCase):
    def test_maps_common_queue_and_timecondition_placeholders(self):
        result = placeholders.build_macro_replacements({**_BASE_CONFIG, "type": "ixcsoft"})
        self.assertEqual(result["Set(dep_outros_assuntos=XXX)"], "600")
        self.assertEqual(result["Set(dep_comercial=XXX)"], "601")
        self.assertEqual(result["Goto(timeconditions,TIMECONDITION_DESTINO,1)"], "10")

    def test_ixcsoft_maps_filial_departamento_and_assunto(self):
        config = {
            **_BASE_CONFIG, "type": "ixcsoft", "id_filial": "1",
            "id_departamento_geral": "10", "id_assunto_comercial": "20",
        }
        result = placeholders.build_macro_replacements(config)
        self.assertEqual(result["Set(FILIAL_ID=XXX)"], "1")
        self.assertEqual(result["Set(setor_outros_assuntos=XXX)"], "10")
        self.assertEqual(result["Set(ocorrencia_comercial=XXX)"], "20")

    def test_sgp_maps_multiple_placeholders_to_the_same_config_key(self):
        config = {**_BASE_CONFIG, "type": "sgp", "id_ocorrencia_comercial": "42"}
        result = placeholders.build_macro_replacements(config)
        self.assertEqual(result["Set(ocorrencia_comercial=XXX)"], "42")
        self.assertEqual(result["Set(ocorrencia_comercial_adesao=XXX)"], "42")
        self.assertEqual(result["Set(ocorrencia_comercial_cancelamento=XXX)"], "42")

    def test_sgp_does_not_include_ixcsoft_only_placeholders(self):
        result = placeholders.build_macro_replacements({**_BASE_CONFIG, "type": "sgp"})
        self.assertNotIn("Set(FILIAL_ID=XXX)", result)


if __name__ == "__main__":
    unittest.main()
