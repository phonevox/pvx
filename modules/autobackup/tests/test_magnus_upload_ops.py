import datetime
import unittest
from unittest.mock import Mock, patch

import magnus_upload_ops as ops


class RemoteNameTest(unittest.TestCase):
    def test_formats_with_the_given_date(self):
        self.assertEqual(
            ops.remote_name(today=datetime.date(2026, 9, 4)), "backup-pxmagnus.04-09-2026.tgz",
        )

    def test_defaults_to_today(self):
        with patch("magnus_upload_ops.datetime") as mock_dt:
            mock_dt.date.today.return_value = datetime.date(2026, 1, 5)
            self.assertEqual(ops.remote_name(), "backup-pxmagnus.05-01-2026.tgz")


class ExportAndUploadTest(unittest.TestCase):
    def _run_result(self, returncode=0, stderr=""):
        result = Mock()
        result.returncode = returncode
        result.stderr = stderr
        return result

    def test_exports_uploads_and_cleans_up_on_success(self):
        with patch("magnus_upload_ops.subprocess.run", return_value=self._run_result()) as mock_run, \
             patch("magnus_upload_ops.remote_name", return_value="backup-pxmagnus.04-09-2026.tgz"), \
             patch("magnus_upload_ops.os.remove") as mock_remove:
            ops.export_and_upload("http://uoe.example/v1/upload", "tok123")

        export_call, upload_call = mock_run.call_args_list
        self.assertEqual(export_call.args[0], ["pvx", "magnus", "backup", "export", "-o", ops.OUTPUT_PATH])
        self.assertEqual(upload_call.args[0], [
            "pbackup", "--files", f"{ops.OUTPUT_PATH}:backup-pxmagnus.04-09-2026.tgz",
            "--to", "http://uoe.example/v1/upload:/", "--token", "tok123",
        ])
        mock_remove.assert_called_once_with(ops.OUTPUT_PATH)

    def test_export_failure_raises_and_never_uploads_or_cleans_up(self):
        with patch(
            "magnus_upload_ops.subprocess.run", return_value=self._run_result(returncode=1, stderr="senha errada"),
        ) as mock_run, patch("magnus_upload_ops.os.remove") as mock_remove:
            with self.assertRaises(ops.MagnusUploadError) as ctx:
                ops.export_and_upload("http://uoe.example/v1/upload", "tok123")
        self.assertIn("senha errada", str(ctx.exception))
        mock_run.assert_called_once()
        mock_remove.assert_not_called()

    def test_upload_failure_raises_and_keeps_the_local_file(self):
        # falhou o upload -- mantém o arquivo local pra retry manual/debug,
        # não limpa às cegas.
        with patch("magnus_upload_ops.subprocess.run", side_effect=[
            self._run_result(returncode=0), self._run_result(returncode=1, stderr="401 unauthorized"),
        ]), patch("magnus_upload_ops.os.remove") as mock_remove:
            with self.assertRaises(ops.MagnusUploadError) as ctx:
                ops.export_and_upload("http://uoe.example/v1/upload", "tok123")
        self.assertIn("401 unauthorized", str(ctx.exception))
        mock_remove.assert_not_called()

    def test_split_exports_the_three_components_into_their_own_remote_folders(self):
        # pedido ao vivo: bkp splitado em config/gravações/sons, cada um na sua
        # pasta remota -- nomes/pastas conferidos contra o magnus.sh real e o
        # magnus_ops.py (módulo magnus, não dá pra importar direto daqui).
        with patch("magnus_upload_ops.subprocess.run", return_value=self._run_result()) as mock_run, \
             patch("magnus_upload_ops.datetime") as mock_dt, \
             patch("magnus_upload_ops.os.makedirs") as mock_makedirs, \
             patch("magnus_upload_ops.os.remove") as mock_remove:
            mock_dt.date.today.return_value = datetime.date(2026, 9, 4)
            ops.export_and_upload("http://uoe.example/v1/upload", "tok123", split=True)

        export_call, upload_call = mock_run.call_args_list
        self.assertEqual(export_call.args[0], [
            "pvx", "magnus", "backup", "export", "--configuration", "--recordings", "--soundfiles",
            "--output-dir", ops.SPLIT_OUTPUT_DIR,
        ])
        files_arg = upload_call.args[0][upload_call.args[0].index("--files") + 1]
        self.assertIn("backup_voip_softswitch.04-09-2026.tgz:/configuration", files_arg)
        self.assertIn("recordings.04-09-2026.tgz:/recordings", files_arg)
        self.assertIn("soundfiles.04-09-2026.tgz:/soundfiles", files_arg)
        self.assertEqual(mock_remove.call_count, 3)

    def test_split_export_failure_never_uploads_or_cleans_up(self):
        with patch(
            "magnus_upload_ops.subprocess.run", return_value=self._run_result(returncode=1, stderr="deu ruim"),
        ) as mock_run, patch("magnus_upload_ops.os.makedirs"), patch("magnus_upload_ops.os.remove") as mock_remove:
            with self.assertRaises(ops.MagnusUploadError):
                ops.export_and_upload("http://uoe.example/v1/upload", "tok123", split=True)
        mock_run.assert_called_once()
        mock_remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
