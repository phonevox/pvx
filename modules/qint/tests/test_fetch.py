import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fetch


class PrepareCacheDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_the_parent_but_not_the_final_directory_itself(self):
        # achado ao vivo: "sftp get -r remote local" nesta um nível a mais quando "local"
        # já existe (mesmo comportamento de cp -r) -- se prepare_cache_dir criasse o
        # diretório final, fetch() acabava gravando em cache_dir/<versao>/... em vez de
        # cache_dir/..., e apply() nunca achava cache_dir/php/config.php. Só o pai é
        # garantido; o sftp cria o final ao copiar.
        cache_dir = Path(fetch.prepare_cache_dir(self._tmp.name, "ixcsoft", "1.2.3"))
        self.assertTrue(cache_dir.parent.is_dir())
        self.assertFalse(cache_dir.exists())

    def test_deletes_stale_leftover_directory_when_already_present(self):
        cache_dir = Path(self._tmp.name) / "ixcsoft" / "1.2.3"
        cache_dir.mkdir(parents=True)
        stale_file = cache_dir / "leftover-from-a-previous-fetch"
        stale_file.write_text("lixo")

        fetch.prepare_cache_dir(self._tmp.name, "ixcsoft", "1.2.3")

        self.assertFalse(stale_file.exists())


class FetchTest(unittest.TestCase):
    @patch("fetch.subprocess.run")
    def test_invokes_sftp_with_user_host_and_port(self, mock_run):
        sftp_info = {"user": "root", "host": "10.0.0.1", "port": 2222}
        fetch.fetch(sftp_info, "/sfiles/qint/integracoes", "ixcsoft", "1.2.3", "/tmp/cache")

        args = mock_run.call_args.args[0]
        self.assertEqual(args[:2], ["sftp", "-P"])
        self.assertIn("2222", args)
        self.assertIn("root@10.0.0.1", args)

    @patch("fetch.subprocess.run")
    def test_auto_accepts_a_first_time_host_key(self, mock_run):
        # achado ao vivo: sftp em batch mode lê a senha de /dev/tty, mas a
        # confirmação de host key desconhecida (primeira conexão) tenta ler
        # de stdin -- que já está ocupado com os comandos do batch. Sem essa
        # flag, a primeira conexão a um host novo falha (exit 255) mesmo com
        # credenciais corretas, porque a resposta "yes" nunca chega.
        sftp_info = {"user": "root", "host": "10.0.0.1", "port": 22}
        fetch.fetch(sftp_info, "/sfiles/qint/integracoes", "ixcsoft", "1.2.3", "/tmp/cache")

        args = mock_run.call_args.args[0]
        self.assertIn("-o", args)
        self.assertIn("StrictHostKeyChecking=accept-new", args)

    @patch("fetch.subprocess.run")
    def test_batch_references_remote_path_and_local_cache_dir(self, mock_run):
        sftp_info = {"user": "root", "host": "10.0.0.1", "port": 22}
        fetch.fetch(sftp_info, "/sfiles/qint/integracoes", "ixcsoft", "1.2.3", "/tmp/cache")

        batch = mock_run.call_args.kwargs["input"]
        self.assertIn("/sfiles/qint/integracoes/ixcsoft/1.2.3", batch)
        self.assertIn("/tmp/cache", batch)


if __name__ == "__main__":
    unittest.main()
