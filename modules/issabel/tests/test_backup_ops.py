import datetime
import io
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

    def test_calls_issabel_helper_with_an_absolute_path_split_into_tmpdir_and_bare_filename(self):
        # --backupfile do issabel-helper só aceita nome sem diretório --
        # --tmpdir vira o diretório de verdade que o usuário pediu.
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                path, warning = ops.export_backup(f"{tmp_dir}/x.tar", ["as_db", "as_config_files"])

        self.assertEqual(path, f"{tmp_dir}/x.tar")
        self.assertIsNone(warning)
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "issabel-helper")
        self.assertIn("--backup", args)
        self.assertIn("x.tar", args)
        self.assertIn("as_db,as_config_files", args)
        self.assertIn(tmp_dir, args)

    def test_a_bare_filename_lands_in_the_current_working_directory(self):
        # pedido explícito: exportar com só um nome de arquivo salva relativo
        # a onde o pvx foi chamado, não num diretório fixo do Issabel.
        with tempfile.TemporaryDirectory() as cwd:
            Path(cwd, "x.tar").write_text("fake")
            with patch("backup_ops.os.getcwd", return_value=cwd), \
                 patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                path, _ = ops.export_backup("x.tar", ["as_db"])

        self.assertEqual(path, f"{cwd}/x.tar")
        self.assertIn(cwd, mock_run.call_args.args[0])

    def test_raises_when_the_target_directory_does_not_exist(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("/nao/existe/x.tar", ["as_db"])
        self.assertIn("diretório", str(ctx.exception))

    def test_raises_when_issabel_helper_does_not_produce_the_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result()):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup(f"{tmp_dir}/x.tar", ["as_db"])
        self.assertIn("não foi gerado", str(ctx.exception))

    def test_raises_using_captured_output_when_the_file_is_missing_and_the_helper_failed(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="boom")):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"])
        self.assertIn("boom", str(ctx.exception))

    def test_falls_back_to_stdout_when_issabel_helper_writes_the_error_there(self):
        # achado ao vivo (autobackup): pbackup/issabel-helper às vezes erra sem
        # escrever nada em stderr -- sem o fallback pro stdout, o motivo real
        # do erro some sem deixar rastro nenhum.
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
             patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stdout="deu ruim")):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.export_backup("x.tar", ["as_db"])
        self.assertIn("deu ruim", str(ctx.exception))

    def test_writes_a_hidden_pvx_manifest_when_generated_by_is_given(self):
        # achado ao vivo: dá pra saber se um backup existente veio do pvx ou
        # de outra ferramenta (native/manual) só de olhar pra dentro dele.
        with tempfile.TemporaryDirectory() as tmp_dir:
            with tarfile.open(Path(tmp_dir, "x.tar"), "w"):
                pass  # tar vazio, mas válido -- issabel-helper é mockado abaixo
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()):
                path, _ = ops.export_backup(f"{tmp_dir}/x.tar", ["as_db"], generated_by="pvx issabel v0.1.4")
            with tarfile.open(path) as tar:
                manifest = tar.extractfile(ops.MANIFEST_MEMBER).read().decode()
        self.assertIn("gerado_por=pvx issabel v0.1.4", manifest)
        self.assertIn("gerado_em=", manifest)

    def test_skips_the_manifest_when_generated_by_is_not_given(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with tarfile.open(Path(tmp_dir, "x.tar"), "w"):
                pass
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()):
                path, _ = ops.export_backup(f"{tmp_dir}/x.tar", ["as_db"])
            with tarfile.open(path) as tar:
                self.assertNotIn(ops.MANIFEST_MEMBER, tar.getnames())

    def test_nonzero_exit_code_is_not_fatal_when_the_file_was_produced_anyway(self):
        # achado ao vivo: issabel-helper (igual a interface web nativa)
        # retorna código != 0 sempre que QUALQUER componente individual
        # falha (banco que não existe nessa central, etc.) mesmo com o
        # arquivo final gerado com sucesso -- exit code não é o sinal de
        # verdade, o arquivo no disco é.
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="WARN: ...")):
                path, warning = ops.export_backup(f"{tmp_dir}/x.tar", ["as_db"])
        self.assertEqual(path, f"{tmp_dir}/x.tar")
        self.assertEqual(warning, "WARN: ...")


class ImportBackupTest(unittest.TestCase):
    def test_raises_when_not_an_issabel_box(self):
        with patch("backup_ops.shutil.which", return_value=None):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.import_backup("x.tar", ["as_db"])
        self.assertIn("issabel-helper", str(ctx.exception))

    def test_raises_when_no_components_given(self):
        with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.import_backup("x.tar", [])
        self.assertIn("componente", str(ctx.exception))

    def test_raises_when_the_backup_file_is_not_found(self):
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"):
            with self.assertRaises(ops.IssabelBackupError) as ctx:
                ops.import_backup(f"{tmp_dir}/missing.tar", ["as_db"])
        self.assertIn("não encontrado", str(ctx.exception))

    def test_calls_issabel_helper_using_the_files_own_directory_as_tmpdir(self):
        # --restore do issabel-helper exige o arquivo já dentro de --tmpdir,
        # referenciado só pelo nome -- nada de copiar pra um lugar fixo.
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                ops.import_backup(f"{tmp_dir}/x.tar", ["as_db"])

        args = mock_run.call_args.args[0]
        self.assertIn("--restore", args)
        self.assertIn("x.tar", args)
        self.assertIn(tmp_dir, args)

    def test_a_bare_filename_is_resolved_against_the_current_working_directory(self):
        with tempfile.TemporaryDirectory() as cwd:
            Path(cwd, "x.tar").write_text("fake")
            with patch("backup_ops.os.getcwd", return_value=cwd), \
                 patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()) as mock_run:
                ops.import_backup("x.tar", ["as_db"])
        self.assertIn(cwd, mock_run.call_args.args[0])

    def test_nonzero_exit_code_is_not_fatal_and_is_returned_as_a_warning(self):
        # mesmo achado do export: o próprio --restore nativo (igual a
        # interface web) retorna código != 0 sempre que algum componente
        # individual falha, sem que a restauração como um todo tenha dado
        # errado -- não existe um "arquivo gerado" pra conferir aqui como no
        # export, então isso nunca é tratado como fatal.
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result(returncode=1, stderr="WARN: ...")):
                warning = ops.import_backup(f"{tmp_dir}/x.tar", ["as_db"])
        self.assertEqual(warning, "WARN: ...")

    def test_returns_no_warning_on_a_clean_exit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "x.tar").write_text("fake")
            with patch("backup_ops.shutil.which", return_value="/usr/bin/issabel-helper"), \
                 patch("backup_ops.subprocess.run", return_value=_run_result()):
                warning = ops.import_backup(f"{tmp_dir}/x.tar", ["as_db"])
        self.assertIsNone(warning)


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
        self.assertEqual(info["manifest"], {})

    def test_reads_the_pvx_manifest_when_present(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir, "x.tar"))
            self._build_fake_backup(path, ["as_db"])
            manifest = b"gerado_por=pvx issabel v0.1.4\ngerado_em=2026-09-14T17:00:00\n"
            with tarfile.open(path, "a") as tar:
                info = tarfile.TarInfo(ops.MANIFEST_MEMBER)
                info.size = len(manifest)
                tar.addfile(info, io.BytesIO(manifest))

            info = ops.inspect_backup(path)

        self.assertEqual(info["manifest"]["gerado_por"], "pvx issabel v0.1.4")
        self.assertEqual(info["manifest"]["gerado_em"], "2026-09-14T17:00:00")

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
