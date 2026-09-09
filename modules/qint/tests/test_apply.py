import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import apply as apply_module


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.cache_root = Path(self._tmp.name) / "cache"
        self.dest_root = Path(self._tmp.name) / "dest"
        self.history_path = Path(self._tmp.name) / "history.log"

        self.base_dirs = {
            "agi": str(self.dest_root / "agi-bin"),
            "php": str(self.dest_root / "www"),
            "dialplan": str(self.dest_root / "etc-asterisk"),
            "moh": str(self.dest_root / "moh"),
            "audio": str(self.dest_root / "sounds"),
        }
        for d in self.base_dirs.values():
            Path(d).mkdir(parents=True)

        self.config = {
            "type": "ixcsoft",
            "sftp_user": "root", "sftp_host": "10.0.0.1", "sftp_port": 22,
            "sftp_versao": "1.0.0",
            "erp_url": "https://erp.example.com",
            "token": "tok",
            "asterisk_ip": "10.0.0.2",
            "fila_geral": "600", "fila_comercial": "601", "fila_suporte": "602", "fila_financeiro": "603",
            "id_timecondition_exitpoint": "10",
            "id_filial": "1",
            "id_departamento_geral": "1", "id_departamento_comercial": "2",
            "id_departamento_suporte": "3", "id_departamento_financeiro": "4",
            "id_assunto_geral": "1", "id_assunto_comercial": "2",
            "id_assunto_suporte": "3", "id_assunto_financeiro": "4",
        }

    def tearDown(self):
        self._tmp.cleanup()

    def _fake_fetch(self, sftp_info, remote_base, tipo, versao, cache_dir):
        # layout real do SFTP (achado ao vivo): agi/php/exten vivem sob "files/", "audio"
        # é "audios", e toda categoria tem mais um nível "<tipo>" antes do conteúdo.
        for remote_path in ("files/agi", "files/php", "files/exten", "moh", "audios"):
            (Path(cache_dir) / remote_path / tipo).mkdir(parents=True)
        (Path(cache_dir) / "files" / "php" / tipo / "config.php").write_text(
            "$server_local = '';\n$protocol_web = '';\n$servidor_web = '';\n"
            "$porta_web = '';\n$token = '';\n"
        )
        (Path(cache_dir) / "files" / "exten" / tipo / "phonevox-macros-atendimento.conf").write_text(
            "Set(dep_outros_assuntos=XXX)\nSet(dep_comercial=XXX)\nSet(dep_suporte=XXX)\n"
            "Set(dep_financeiro=XXX)\nGoto(timeconditions,TIMECONDITION_DESTINO,1)\n"
            "Set(FILIAL_ID=XXX)\nSet(ocorrencia_outros_assuntos=XXX)\nSet(ocorrencia_comercial=XXX)\n"
            "Set(ocorrencia_suporte=XXX)\nSet(ocorrencia_financeiro=XXX)\nSet(setor_outros_assuntos=XXX)\n"
            "Set(setor_comercial=XXX)\nSet(setor_suporte=XXX)\nSet(setor_financeiro=XXX)\n"
        )
        (Path(cache_dir) / "moh" / tipo / "sfx-teclado-digitando").mkdir(parents=True)

    @patch("deploy.subprocess.run")
    @patch("apply.reload_.reload_dialplan", return_value=True)
    @patch("apply.fetch.fetch")
    def test_full_apply_patches_deploys_wires_and_reloads(self, mock_fetch, mock_reload, mock_chown):
        mock_fetch.side_effect = self._fake_fetch

        result = apply_module.apply(
            self.config, "/sfiles/qint/integracoes", str(self.cache_root),
            self.base_dirs, str(self.history_path),
        )

        # destino usa o nome do tipo como subpasta (conferido contra o instalador bash
        # original), nunca um "qint" fixo.
        php_dest = Path(self.base_dirs["php"]) / "ixcsoft" / "config.php"
        content = php_dest.read_text()
        self.assertIn("erp.example.com", content)
        self.assertIn("10.0.0.2", content)

        macro_dest = Path(self.base_dirs["dialplan"]) / "ixcsoft" / "phonevox-macros-atendimento.conf"
        # achado ao vivo: "600" sozinho aqui passava tanto com o valor certo quanto
        # com o bug real (linha virando "exten => s,n,600" em vez de
        # "exten => s,n,Set(dep_outros_assuntos=600)") -- checa a expressão inteira.
        self.assertIn("Set(dep_outros_assuntos=600)", macro_dest.read_text())

        extensions = Path(self.base_dirs["dialplan"]) / "extensions_custom.conf"
        self.assertIn('#include "ixcsoft/phonevox.conf"', extensions.read_text())

        moh_conf = Path(self.base_dirs["dialplan"]) / "musiconhold_custom.conf"
        moh_conf_text = moh_conf.read_text()
        self.assertIn("[sfx-teclado-digitando]", moh_conf_text)
        expected_moh_dir = str(Path(self.base_dirs["moh"]) / "ixcsoft" / "sfx-teclado-digitando")
        self.assertIn(f"directory={expected_moh_dir}", moh_conf_text)

        mock_reload.assert_called_once()
        self.assertIn("apply ixcsoft 1.0.0", self.history_path.read_text())
        self.assertTrue(result["applied"])

    @patch("deploy.subprocess.run")
    @patch("apply.reload_.reload_dialplan", return_value=False)
    @patch("apply.fetch.fetch")
    def test_apply_reports_when_asterisk_reload_was_skipped(self, mock_fetch, mock_reload, mock_chown):
        mock_fetch.side_effect = self._fake_fetch

        result = apply_module.apply(
            self.config, "/sfiles/qint/integracoes", str(self.cache_root),
            self.base_dirs, str(self.history_path),
        )

        self.assertTrue(result["applied"])
        self.assertFalse(result["reloaded"])


if __name__ == "__main__":
    unittest.main()
