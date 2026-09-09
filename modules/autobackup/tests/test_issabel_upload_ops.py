import datetime
import unittest
from unittest.mock import Mock, patch

import issabel_upload_ops as ops


def _run_result(returncode=0, stderr=""):
    result = Mock()
    result.returncode = returncode
    result.stderr = stderr
    return result


class BackupFilenameTest(unittest.TestCase):
    def test_formats_with_the_given_datetime(self):
        self.assertEqual(
            ops.backup_filename(now=datetime.datetime(2026, 9, 4, 13, 5, 9)),
            "issabelbackup-20260904130509-06.tar",
        )


class ComponentsTest(unittest.TestCase):
    def test_base_components_without_the_extras_marker(self):
        with patch("issabel_upload_ops.os.path.isfile", return_value=False):
            components = ops._components()
        self.assertIn("as_db", components)
        self.assertNotIn("int_ixcsoft", components)

    def test_appends_extras_when_the_marker_file_exists(self):
        with patch("issabel_upload_ops.os.path.isfile", return_value=True):
            components = ops._components()
        self.assertIn("int_ixcsoft", components)
        self.assertIn("int_sgp", components)


class GenerateConfigBackupTest(unittest.TestCase):
    def test_raises_when_not_an_issabel_box(self):
        with patch("issabel_upload_ops.os.path.isfile", return_value=False):
            with self.assertRaises(ops.IssabelUploadError) as ctx:
                ops.generate_config_backup()
        self.assertIn("issabel-helper", str(ctx.exception))

    def test_calls_issabel_helper_and_returns_the_generated_path(self):
        def fake_isfile(path):
            return path == "/usr/bin/issabel-helper" or path.startswith(ops.BACKUP_DIR)

        with patch("issabel_upload_ops.os.path.isfile", side_effect=fake_isfile), \
             patch("issabel_upload_ops.backup_filename", return_value="issabelbackup-x-06.tar"), \
             patch("issabel_upload_ops.subprocess.run", return_value=_run_result()) as mock_run:
            path = ops.generate_config_backup()

        self.assertEqual(path, f"{ops.BACKUP_DIR}/issabelbackup-x-06.tar")
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "issabel-helper")
        self.assertIn("--backupfile", args)
        self.assertIn("issabelbackup-x-06.tar", args)
        self.assertIn("--tmpdir", args)
        self.assertIn(ops.BACKUP_DIR, args)

    def test_raises_when_issabel_helper_does_not_produce_the_file(self):
        def fake_isfile(path):
            return path == "/usr/bin/issabel-helper"  # nunca o arquivo de backup

        with patch("issabel_upload_ops.os.path.isfile", side_effect=fake_isfile), \
             patch("issabel_upload_ops.subprocess.run", return_value=_run_result()):
            with self.assertRaises(ops.IssabelUploadError) as ctx:
                ops.generate_config_backup()
        self.assertIn("não foi gerado", str(ctx.exception))

    def test_issabel_helper_failure_becomes_a_clean_error(self):
        with patch("issabel_upload_ops.os.path.isfile", return_value=True), \
             patch("issabel_upload_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="boom")):
            with self.assertRaises(ops.IssabelUploadError) as ctx:
                ops.generate_config_backup()
        self.assertIn("boom", str(ctx.exception))


class ArchiveRecentRecordingsTest(unittest.TestCase):
    def test_archives_only_the_days_that_exist_on_disk(self):
        today = datetime.date(2026, 9, 4)
        existing = {
            "/var/spool/asterisk/monitor/2026/09/03",  # ontem -- existe
        }
        with patch("issabel_upload_ops.datetime") as mock_dt, \
             patch("issabel_upload_ops.os.path.isdir", side_effect=lambda p: p in existing), \
             patch("issabel_upload_ops.tarfile.open") as mock_tar_open:
            mock_dt.date.today.return_value = today
            mock_dt.timedelta = datetime.timedelta
            archives = ops.archive_recent_recordings("/tmp/xyz")

        self.assertEqual(len(archives), 1)
        local, remote = archives[0]
        self.assertEqual(local, "/tmp/xyz/recordings-1d.tar.gz")
        self.assertEqual(remote, "/recordings/2026/09/03")
        mock_tar_open.assert_called_once_with(local, "w:gz")

    def test_empty_when_no_recent_recordings_exist(self):
        with patch("issabel_upload_ops.os.path.isdir", return_value=False), \
             patch("issabel_upload_ops.tarfile.open") as mock_tar_open:
            archives = ops.archive_recent_recordings("/tmp/xyz")
        self.assertEqual(archives, [])
        mock_tar_open.assert_not_called()


class ExportAndUploadTest(unittest.TestCase):
    def test_requires_at_least_one_of_configuration_or_recordings(self):
        with self.assertRaises(ops.IssabelUploadError):
            ops.export_and_upload("http://uoe.example/v1/upload", "tok", configuration=False, recordings=False)

    def test_configuration_only_uploads_and_cleans_up_on_success(self):
        with patch("issabel_upload_ops.generate_config_backup", return_value="/var/www/backup/x.tar") as mock_gen, \
             patch("issabel_upload_ops.archive_recent_recordings") as mock_rec, \
             patch("issabel_upload_ops.subprocess.run", return_value=_run_result()) as mock_run, \
             patch("issabel_upload_ops.os.path.isfile", return_value=True), \
             patch("issabel_upload_ops.os.remove") as mock_remove:
            ops.export_and_upload("http://uoe.example/v1/upload", "tok123", configuration=True, recordings=False)

        mock_gen.assert_called_once()
        mock_rec.assert_not_called()
        upload_call = mock_run.call_args
        self.assertEqual(upload_call.args[0][0], "pbackup")
        files_index = upload_call.args[0].index("--files") + 1
        self.assertEqual(upload_call.args[0][files_index], "/var/www/backup/x.tar:/configuration")
        self.assertIn("--to", upload_call.args[0])
        self.assertEqual(upload_call.args[0][upload_call.args[0].index("--to") + 1], "http://uoe.example/v1/upload:/")
        mock_remove.assert_called_once_with("/var/www/backup/x.tar")

    def test_recordings_only_never_touches_issabel_helper(self):
        with patch("issabel_upload_ops.generate_config_backup") as mock_gen, \
             patch("issabel_upload_ops.archive_recent_recordings", return_value=[("/tmp/x/r1.tar.gz", "/recordings/2026/09/03")]), \
             patch("issabel_upload_ops.subprocess.run", return_value=_run_result()) as mock_run:
            ops.export_and_upload("http://uoe.example/v1/upload", "tok123", configuration=False, recordings=True)

        mock_gen.assert_not_called()
        files_index = mock_run.call_args.args[0].index("--files") + 1
        self.assertEqual(mock_run.call_args.args[0][files_index], "/tmp/x/r1.tar.gz:/recordings/2026/09/03")

    def test_combines_configuration_and_recordings_in_one_upload_call(self):
        with patch("issabel_upload_ops.generate_config_backup", return_value="/var/www/backup/x.tar"), \
             patch(
                 "issabel_upload_ops.archive_recent_recordings",
                 return_value=[("/tmp/x/r1.tar.gz", "/recordings/2026/09/03")],
             ), \
             patch("issabel_upload_ops.subprocess.run", return_value=_run_result()) as mock_run, \
             patch("issabel_upload_ops.os.path.isfile", return_value=True), \
             patch("issabel_upload_ops.os.remove"):
            ops.export_and_upload("http://uoe.example/v1/upload", "tok123", configuration=True, recordings=True)

        self.assertEqual(mock_run.call_count, 1)
        files_index = mock_run.call_args.args[0].index("--files") + 1
        files_arg = mock_run.call_args.args[0][files_index]
        self.assertIn("/tmp/x/r1.tar.gz:/recordings/2026/09/03", files_arg)
        self.assertIn("/var/www/backup/x.tar:/configuration", files_arg)

    def test_upload_failure_raises_and_keeps_the_config_file(self):
        with patch("issabel_upload_ops.generate_config_backup", return_value="/var/www/backup/x.tar"), \
             patch("issabel_upload_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="401")), \
             patch("issabel_upload_ops.os.remove") as mock_remove:
            with self.assertRaises(ops.IssabelUploadError) as ctx:
                ops.export_and_upload("http://uoe.example/v1/upload", "tok123", configuration=True, recordings=False)
        self.assertIn("401", str(ctx.exception))
        mock_remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
