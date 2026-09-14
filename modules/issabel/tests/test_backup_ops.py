import datetime
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import backup_ops as ops


def _run_result(returncode=0, stderr="", stdout=""):
    result = Mock()
    result.returncode = returncode
    result.stderr = stderr
    result.stdout = stdout
    return result


class AvailableComponentsTest(unittest.TestCase):
    def test_official_components_without_the_extras_marker(self):
        with patch("backup_ops.os.path.isfile", return_value=False):
            components = ops.available_components()
        self.assertIn("as_db", components)
        self.assertNotIn("int_ixcsoft", components)

    def test_appends_phonevox_extras_when_the_marker_file_exists(self):
        with patch("backup_ops.os.path.isfile", return_value=True):
            components = ops.available_components()
        self.assertIn("int_ixcsoft", components)
        self.assertIn("as_db", components)


class DefaultFilenameTest(unittest.TestCase):
    def test_formats_with_the_given_datetime(self):
        self.assertEqual(
            ops.default_filename(now=datetime.datetime(2026, 9, 14, 13, 5, 9)),
            "issabel-backup-20260914130509.tar",
        )


class ExportBackupTest(unittest.TestCase):
    def test_raises_when_not_an_issabel_box(self):
        with patch("backup_ops.shutil.which", return_value=None):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"])
        self.assertIn("issabel-helper", str(ctx.exception))

    def test_raises_when_no_components_given(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", [])
        self.assertIn("componente", str(ctx.exception))

    def test_calls_issabel_helper_with_the_given_components_and_returns_the_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                path = ops.export_backup("x.tar", ["as_db", "as_config_files"], backup_dir=tmp_dir)

        self.assertEqual(path, f"{tmp_dir}/x.tar")
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "issabel-helper")
        self.assertIn("--backup", args)
        self.assertIn("x.tar", args)
        self.assertIn("as_db,as_config_files", args)
        self.assertIn(tmp_dir, args)

    def test_raises_when_issabel_helper_does_not_produce_the_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result()):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"], backup_dir=tmp_dir)
        self.assertIn("não foi gerado", str(ctx.exception))

    def test_issabel_helper_failure_becomes_a_clean_error(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="boom")):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"])
        self.assertIn("boom", str(ctx.exception))

    def test_falls_back_to_stdout_when_issabel_helper_writes_the_error_there(self):
        # achado ao vivo (autobackup): pbackup/issabel-helper às vezes erra sem
        # escrever nada em stderr -- _run só olhava stderr, o motivo real do
        # erro sumia sem deixar rastro nenhum pro usuário nem pro log.
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stdout="deu ruim")):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"])
        self.assertIn("deu ruim", str(ctx.exception))


class InspectBackupTest(unittest.TestCase):
    def _build_fake_backup(self, path, components, issabel_version="5.0.0"):
        with tempfile.TemporaryDirectory() as work_dir:
            backup_dir = Path(work_dir, "backup")
            backup_dir.mkdir()
            options_xml = "<raiz>" + "".join(
                f'<options id="grp">{"".join(f"<option>{c}</option>" for c in components)}</options>'
            ) + "</raiz>"
            (backup_dir / "a_options.xml").write_text(options_xml)
            versions_xml = f'<versions><program id="issabel" ver="{issabel_version}" rel="1"/></versions>'
            (backup_dir / "versions.xml").write_text(versions_xml)
            with tarfile.open(path, "w") as tar:
                tar.add(backup_dir, arcname="backup")

    def test_reads_components_and_issabel_version_from_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            self._build_fake_backup(path, ["as_db", "mysql_db"], issabel_version="5.0.0")
            info = ops.inspect_backup(path)

        self.assertEqual(sorted(info["components"]), ["as_db", "mysql_db"])
        self.assertEqual(info["versions"]["issabel"], "5.0.0")

    def test_raises_a_clean_error_for_a_file_that_is_not_a_valid_backup(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "not-a-backup.tar"))
            Path(path).write_text("nem um tar de verdade")
            with self.assertRaises(ops.IssabelBackupError):
                ops.inspect_backup(path)


class InstalledIssabelVersionTest(unittest.TestCase):
    def test_returns_the_version_from_rpm(self):
        with patch("backup_ops.subprocess.run", return_value=_run_result(stdout="5.0.0")):
            self.assertEqual(ops.installed_issabel_version(), "5.0.0")

    def test_returns_none_when_rpm_query_fails(self):
        with patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1)):
            self.assertIsNone(ops.installed_issabel_version())


if __name__ == "__main__":
    unittest.main()
