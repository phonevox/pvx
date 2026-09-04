import unittest

import backup_scripts


class BuildCommandTest(unittest.TestCase):
    def test_issabel_command_defaults_to_config_only(self):
        # pedido ao vivo: centraliza a orquestração no pvx em vez de depender
        # do scripts/issabel.sh do pbackup -- a geração em si continua sendo
        # trabalho do issabel-helper (issabel_upload_ops.py só orquestra).
        result = backup_scripts.build_command("issabel", token="eyJhbGc")
        self.assertEqual(
            result,
            "pvx autobackup issabel-upload "
            "--upload-url http://uoe.interno.falevox.com.br/v1/upload --token eyJhbGc",
        )

    def test_issabel_command_with_recordings(self):
        result = backup_scripts.build_command("issabel", token="eyJhbGc", issabel_recordings=True)
        self.assertEqual(
            result,
            "pvx autobackup issabel-upload "
            "--upload-url http://uoe.interno.falevox.com.br/v1/upload --token eyJhbGc --recordings",
        )

    def test_magnus_command(self):
        result = backup_scripts.build_command("magnus", token="eyJhbGc", pbackup_root="/opt/pbackup")
        self.assertEqual(
            result,
            "bash /opt/pbackup/scripts/magnus.sh -t http://uoe.interno.falevox.com.br/v1/upload:/ --token eyJhbGc",
        )

    def test_magnus_pvx_command(self):
        # alternativa que não depende do magnus.sh do pbackup (nem do cron.php
        # do próprio MagnusBilling) -- pvx magnus só gera o backup, upload é
        # sempre responsabilidade do pbackup (mesma separação dos outros scripts).
        # pedido ao vivo: nada de shell chain complexo (data calculada em shell,
        # && encadeado) direto no crontab -- isso vira um comando próprio do
        # módulo (`magnus-upload`), testável, que faz a orquestração em Python.
        result = backup_scripts.build_command("magnus-pvx", token="eyJhbGc")
        self.assertEqual(
            result,
            "pvx autobackup magnus-upload "
            "--upload-url http://uoe.interno.falevox.com.br/v1/upload --token eyJhbGc",
        )

    def test_custom_command_substitutes_the_placeholder(self):
        result = backup_scripts.build_command(
            "custom", token="eyJhbGc", custom_template="/opt/meuscript.sh --upload --token {TOKEN} --verbose",
        )
        self.assertEqual(result, "/opt/meuscript.sh --upload --token eyJhbGc --verbose")

    def test_custom_without_placeholder_raises(self):
        # Q5 do design: {TOKEN} é obrigatório -- sem ele o relogin não teria como
        # saber onde trocar o token depois.
        with self.assertRaises(ValueError):
            backup_scripts.build_command("custom", token="eyJhbGc", custom_template="/opt/meuscript.sh --upload")

    def test_unknown_script_raises(self):
        with self.assertRaises(ValueError):
            backup_scripts.build_command("unknown", token="eyJhbGc")


if __name__ == "__main__":
    unittest.main()
