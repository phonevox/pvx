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

    def test_creates_the_directory_when_absent(self):
        cache_dir = fetch.prepare_cache_dir(self._tmp.name, "ixcsoft", "1.2.3")
        self.assertTrue(Path(cache_dir).is_dir())

    def test_deletes_and_recreates_when_already_present(self):
        cache_dir = Path(fetch.prepare_cache_dir(self._tmp.name, "ixcsoft", "1.2.3"))
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
    def test_batch_references_remote_path_and_local_cache_dir(self, mock_run):
        sftp_info = {"user": "root", "host": "10.0.0.1", "port": 22}
        fetch.fetch(sftp_info, "/sfiles/qint/integracoes", "ixcsoft", "1.2.3", "/tmp/cache")

        batch = mock_run.call_args.kwargs["input"]
        self.assertIn("/sfiles/qint/integracoes/ixcsoft/1.2.3", batch)
        self.assertIn("/tmp/cache", batch)


if __name__ == "__main__":
    unittest.main()
