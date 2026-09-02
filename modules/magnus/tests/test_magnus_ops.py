import datetime
import os
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import call, patch

import magnus_ops


class OutputFilenameTest(unittest.TestCase):
    def test_formats_date_as_dd_mm_yyyy_with_pxmagnus_prefix(self):
        name = magnus_ops.output_filename(today=datetime.date(2026, 9, 2))
        self.assertEqual(name, "backup-pxmagnus.02-09-2026.tgz")


class MysqlDefaultsFileTest(unittest.TestCase):
    # nunca senha em argv de subprocess (fica visível em `ps aux` pra qualquer
    # usuário local) -- credenciais sempre via --defaults-extra-file, 0600,
    # apagado ao sair do context manager.
    def test_writes_client_section_with_0600_perms_and_cleans_up(self):
        with magnus_ops._mysql_defaults_file("root", "s3nha") as path:
            self.assertTrue(os.path.isfile(path))
            content = Path(path).read_text()
            self.assertIn("[client]", content)
            self.assertIn("user=root", content)
            self.assertIn("password=s3nha", content)
            mode = os.stat(path).st_mode & 0o777
            self.assertEqual(mode, 0o600)
        self.assertFalse(os.path.exists(path))

    def test_cleans_up_even_when_the_block_raises(self):
        with self.assertRaises(ValueError):
            with magnus_ops._mysql_defaults_file("root", "s3nha") as path:
                raise ValueError("boom")
        self.assertFalse(os.path.exists(path))


class ExportBackupTest(unittest.TestCase):
    # export_backup só orquestra -- cada etapa (dump, cópias, tar) é testada
    # isolada abaixo. Mesmo padrão de pbackup_ops.fresh_install().
    @patch("magnus_ops._make_archive")
    @patch("magnus_ops._copy_dir")
    @patch("magnus_ops._dump_database")
    @patch("magnus_ops.os.path.isdir", return_value=True)
    def test_orchestrates_dump_copies_and_archive_in_order(self, mock_isdir, mock_dump, mock_copy, mock_archive):
        result_path, warnings = magnus_ops.export_backup(
            "root", "s3nha", output_path="/tmp/out.tgz",
            sounds_dir="/sounds", asterisk_dir="/ast",
        )
        self.assertEqual(result_path, "/tmp/out.tgz")
        self.assertEqual(warnings, [])

        dump_call = mock_dump.call_args
        self.assertEqual(dump_call.args[0], "root")
        self.assertEqual(dump_call.args[1], "s3nha")
        self.assertTrue(dump_call.args[2].endswith(os.path.join("tmp", "base.sql")))

        mock_copy.assert_any_call("/sounds", mock_copy.call_args_list[0].args[1])
        self.assertTrue(mock_copy.call_args_list[0].args[1].endswith(os.path.join("tmp", "audios-ura")))
        self.assertEqual(mock_copy.call_args_list[1].args[0], "/ast")
        self.assertTrue(mock_copy.call_args_list[1].args[1].endswith(os.path.join("etc", "asterisk")))

        mock_archive.assert_called_once()
        self.assertEqual(mock_archive.call_args.args[1], "/tmp/out.tgz")

    @patch("magnus_ops._make_archive")
    @patch("magnus_ops._copy_dir")
    @patch("magnus_ops._dump_database")
    @patch("magnus_ops.os.path.isdir", return_value=True)
    @patch("magnus_ops.output_filename", return_value="backup-pxmagnus.02-09-2026.tgz")
    def test_defaults_output_path_to_output_filename(self, mock_name, mock_isdir, mock_dump, mock_copy, mock_archive):
        result_path, warnings = magnus_ops.export_backup("root", "s3nha")
        self.assertEqual(result_path, "backup-pxmagnus.02-09-2026.tgz")

    @patch("magnus_ops._make_archive")
    @patch("magnus_ops._copy_dir")
    @patch("magnus_ops._dump_database")
    def test_skips_missing_sounds_dir_and_returns_a_warning(self, mock_dump, mock_copy, mock_archive):
        # áudios da URA são opcionais -- nem toda central tem gravação --
        # achado ao vivo: shutil.copytree crashava com FileNotFoundError.
        with patch("magnus_ops.os.path.isdir", side_effect=lambda p: p != "/sounds"):
            result_path, warnings = magnus_ops.export_backup(
                "root", "s3nha", output_path="/tmp/out.tgz",
                sounds_dir="/sounds", asterisk_dir="/ast",
            )
        self.assertEqual(result_path, "/tmp/out.tgz")
        self.assertEqual(len(warnings), 1)
        self.assertIn("/sounds", warnings[0])
        mock_copy.assert_called_once_with("/ast", mock_copy.call_args.args[1])


class RunHelperTest(unittest.TestCase):
    # ponto único de execução de subprocess do módulo -- toda falha
    # previsível (senha errada, serviço fora do ar) vira MagnusError com o
    # stderr do comando, nunca um CalledProcessError cru estourando na tela.
    @patch("magnus_ops.subprocess.run")
    def test_returns_the_result_on_success(self, mock_run):
        mock_run.return_value.returncode = 0
        result = magnus_ops._run(["true"], "falha ao rodar true")
        self.assertIs(result, mock_run.return_value)

    @patch("magnus_ops.subprocess.run")
    def test_raises_magnus_error_with_stderr_detail_on_failure(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Access denied for user 'root'@'localhost'\n"
        with self.assertRaises(magnus_ops.MagnusError) as ctx:
            magnus_ops._run(["mysqldump"], "falha ao exportar o banco de dados")
        self.assertIn("falha ao exportar o banco de dados", str(ctx.exception))
        self.assertIn("Access denied", str(ctx.exception))

    @patch("magnus_ops.subprocess.run")
    def test_captures_stderr_by_default(self, mock_run):
        mock_run.return_value.returncode = 0
        magnus_ops._run(["true"], "falha")
        self.assertEqual(mock_run.call_args.kwargs.get("stderr"), magnus_ops.subprocess.PIPE)


class DumpDatabaseTest(unittest.TestCase):
    @patch("magnus_ops.subprocess.run")
    def test_runs_mysqldump_with_defaults_file_and_writes_stdout_to_dest(self, mock_run):
        mock_run.return_value.returncode = 0
        with TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "sub", "base.sql")
            magnus_ops._dump_database("root", "s3nha", dest)
            self.assertTrue(os.path.isdir(os.path.dirname(dest)))

        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "mysqldump")
        self.assertTrue(any(a.startswith("--defaults-extra-file=") for a in args))
        self.assertIn("mbilling", args)

    @patch("magnus_ops.subprocess.run")
    def test_raises_magnus_error_on_auth_failure_instead_of_crashing(self, mock_run):
        # achado ao vivo: senha errada crashava com CalledProcessError cru.
        mock_run.return_value.returncode = 2
        mock_run.return_value.stderr = "Access denied for user 'root'@'localhost' (using password: YES)"
        with TemporaryDirectory() as tmp:
            with self.assertRaises(magnus_ops.MagnusError) as ctx:
                magnus_ops._dump_database("root", "senha-errada", os.path.join(tmp, "base.sql"))
        self.assertIn("Access denied", str(ctx.exception))


class IsValidArchiveTest(unittest.TestCase):
    @patch("magnus_ops.subprocess.run")
    def test_true_when_tar_tzf_succeeds(self, mock_run):
        mock_run.return_value.returncode = 0
        self.assertTrue(magnus_ops.is_valid_archive("backup.tgz"))

    @patch("magnus_ops.subprocess.run")
    def test_false_when_tar_tzf_fails(self, mock_run):
        mock_run.return_value.returncode = 1
        self.assertFalse(magnus_ops.is_valid_archive("backup.tgz"))


class ExtractArchiveTest(unittest.TestCase):
    def _make_tgz(self, tmp, files):
        archive_path = os.path.join(tmp, "backup.tgz")
        src_dir = os.path.join(tmp, "src")
        os.makedirs(src_dir)
        for rel, content in files.items():
            full = os.path.join(src_dir, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            Path(full).write_text(content)
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(src_dir, arcname=".")
        return archive_path

    def test_extracts_into_dest_dir(self):
        with TemporaryDirectory() as tmp:
            archive = self._make_tgz(tmp, {"tmp/base.sql": "dump"})
            dest = os.path.join(tmp, "dest")
            magnus_ops.extract_archive(archive, dest)
            self.assertEqual(Path(dest, "tmp", "base.sql").read_text(), "dump")

    def test_rejects_path_traversal_entries(self):
        # arquivo de backup pode vir de qualquer lugar (--import <arquivo>) --
        # nunca confia cegamente no conteúdo de um tar de terceiro.
        with TemporaryDirectory() as tmp:
            archive_path = os.path.join(tmp, "evil.tgz")
            with tarfile.open(archive_path, "w:gz") as tar:
                info = tarfile.TarInfo(name="../../etc/passwd")
                info.size = 0
                tar.addfile(info)
            dest = os.path.join(tmp, "dest")
            with self.assertRaises(ValueError):
                magnus_ops.extract_archive(archive_path, dest)


class ValidateExtractedTest(unittest.TestCase):
    def _make_valid_tree(self, tmp):
        os.makedirs(os.path.join(tmp, "tmp", "audios-ura"))
        os.makedirs(os.path.join(tmp, "etc", "asterisk"))
        Path(tmp, "tmp", "base.sql").write_text("dump")
        return tmp

    @patch("magnus_ops._asterisk_active", return_value=True)
    @patch("magnus_ops.os.access", return_value=True)
    def test_no_errors_when_everything_present_and_asterisk_active(self, mock_access, mock_active):
        with TemporaryDirectory() as tmp:
            self._make_valid_tree(tmp)
            self.assertEqual(magnus_ops.validate_extracted(tmp), [])

    @patch("magnus_ops._asterisk_active", return_value=True)
    @patch("magnus_ops.os.access", return_value=True)
    def test_reports_missing_db_dump(self, mock_access, mock_active):
        with TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "tmp", "audios-ura"))
            os.makedirs(os.path.join(tmp, "etc", "asterisk"))
            errors = magnus_ops.validate_extracted(tmp)
            self.assertTrue(any("base.sql" in e for e in errors))

    @patch("magnus_ops._asterisk_active", return_value=True)
    @patch("magnus_ops.os.access", return_value=False)
    def test_reports_missing_update_script(self, mock_access, mock_active):
        with TemporaryDirectory() as tmp:
            self._make_valid_tree(tmp)
            errors = magnus_ops.validate_extracted(tmp)
            self.assertTrue(any("update.sh" in e for e in errors))

    @patch("magnus_ops._asterisk_active", return_value=False)
    @patch("magnus_ops.os.access", return_value=True)
    def test_reports_asterisk_not_active(self, mock_access, mock_active):
        with TemporaryDirectory() as tmp:
            self._make_valid_tree(tmp)
            errors = magnus_ops.validate_extracted(tmp)
            self.assertTrue(any("asterisk" in e.lower() for e in errors))

    @patch("magnus_ops._asterisk_active", return_value=True)
    @patch("magnus_ops.os.access", return_value=True)
    def test_no_errors_when_audios_ura_dir_is_absent(self, mock_access, mock_active):
        # opcional -- nem toda central tem gravação de URA (ver export_backup).
        with TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "etc", "asterisk"))
            Path(tmp, "tmp", "base.sql").parent.mkdir(parents=True)
            Path(tmp, "tmp", "base.sql").write_text("dump")
            self.assertEqual(magnus_ops.validate_extracted(tmp), [])


class AsteriskActiveTest(unittest.TestCase):
    @patch("magnus_ops.subprocess.run")
    def test_true_via_systemd(self, mock_run):
        mock_run.return_value.returncode = 0
        self.assertTrue(magnus_ops._asterisk_active())
        mock_run.assert_called_once()

    @patch("magnus_ops.subprocess.run")
    def test_falls_back_to_init_d_when_systemd_reports_inactive(self, mock_run):
        mock_run.side_effect = [
            unittest.mock.Mock(returncode=3),
            unittest.mock.Mock(returncode=0),
        ]
        self.assertTrue(magnus_ops._asterisk_active())
        self.assertEqual(mock_run.call_count, 2)

    @patch("magnus_ops.subprocess.run")
    def test_false_when_neither_reports_active(self, mock_run):
        mock_run.return_value.returncode = 1
        self.assertFalse(magnus_ops._asterisk_active())


class RunUpdateScriptTest(unittest.TestCase):
    @patch("magnus_ops.subprocess.run")
    def test_suppresses_the_banner_the_official_script_prints(self, mock_run):
        # update.sh do MagnusBilling imprime o próprio banner ASCII no
        # stdout -- polui a tela por baixo do spinner de restore(). Achado
        # ao vivo (diferente do install: ali é handoff total, banner é
        # esperado; aqui é só mais uma etapa interna nossa).
        mock_run.return_value.returncode = 0
        magnus_ops._run_update_script()
        self.assertEqual(mock_run.call_args.kwargs.get("stdout"), magnus_ops.subprocess.DEVNULL)


class ReadMbillingUserDbpassTest(unittest.TestCase):
    CONF = """\
[general]
dbhost=localhost
dbpass=  s3gredo
[other]
dbpass=not-this-one
"""

    def test_extracts_dbpass_from_general_section_only(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "res_config_mysql.conf")
            Path(path).write_text(self.CONF)
            with patch("magnus_ops.RES_CONFIG_MYSQL", path):
                self.assertEqual(magnus_ops._read_mbilling_user_dbpass(), "s3gredo")

    def test_none_when_dbpass_is_absent(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "res_config_mysql.conf")
            Path(path).write_text("[general]\ndbhost=localhost\n")
            with patch("magnus_ops.RES_CONFIG_MYSQL", path):
                self.assertIsNone(magnus_ops._read_mbilling_user_dbpass())


class RestoreTest(unittest.TestCase):
    # restore() só orquestra -- cada etapa é testada isolada. Foco aqui:
    # ordem das chamadas e que update.sh roda EXATAMENTE UMA VEZ (era
    # chamado 2x no bash original -- confirmado como bug, corrigido no port).
    @patch("magnus_ops._reset_mbilling_user_password")
    @patch("magnus_ops._read_mbilling_user_dbpass", return_value="s3gredo")
    @patch("magnus_ops._fix_web_permissions")
    @patch("magnus_ops._restart_asterisk")
    @patch("magnus_ops._run_update_script")
    @patch("magnus_ops._copy_dir")
    @patch("magnus_ops._restore_database")
    @patch("magnus_ops._mysql_defaults_file")
    @patch("magnus_ops.os.path.isdir", return_value=True)
    def test_runs_all_steps_in_order_with_update_script_once(
        self, mock_isdir, mock_defaults, mock_restore_db, mock_copy, mock_update,
        mock_restart, mock_perms, mock_read_pass, mock_reset_pass,
    ):
        mock_defaults.return_value.__enter__.return_value = "/tmp/defaults.cnf"
        manager = unittest.mock.Mock()
        manager.attach_mock(mock_restore_db, "restore_db")
        manager.attach_mock(mock_copy, "copy_dir")
        manager.attach_mock(mock_update, "run_update")
        manager.attach_mock(mock_restart, "restart")
        manager.attach_mock(mock_perms, "fix_perms")
        manager.attach_mock(mock_reset_pass, "reset_pass")

        magnus_ops.restore("/tmp/extracted", "root", "s3nha")

        mock_update.assert_called_once_with()
        self.assertEqual(
            [c[0] for c in manager.mock_calls],
            ["restore_db", "copy_dir", "copy_dir", "run_update", "restart", "fix_perms", "reset_pass"],
        )
        mock_reset_pass.assert_called_once_with("/tmp/defaults.cnf", "s3gredo")

    @patch("magnus_ops._reset_mbilling_user_password")
    @patch("magnus_ops._read_mbilling_user_dbpass", return_value=None)
    @patch("magnus_ops._fix_web_permissions")
    @patch("magnus_ops._restart_asterisk")
    @patch("magnus_ops._run_update_script")
    @patch("magnus_ops._copy_dir")
    @patch("magnus_ops._restore_database")
    @patch("magnus_ops._mysql_defaults_file")
    def test_skips_password_reset_when_dbpass_cannot_be_read(
        self, mock_defaults, mock_restore_db, mock_copy, mock_update,
        mock_restart, mock_perms, mock_read_pass, mock_reset_pass,
    ):
        mock_defaults.return_value.__enter__.return_value = "/tmp/defaults.cnf"
        magnus_ops.restore("/tmp/extracted", "root", "s3nha")
        mock_reset_pass.assert_not_called()

    @patch("magnus_ops._restore_database", side_effect=magnus_ops.MagnusError("falha ao restaurar o banco"))
    @patch("magnus_ops._mysql_defaults_file")
    def test_propagates_magnus_error_from_a_failing_step(self, mock_defaults, mock_restore_db):
        # restore() nunca engole um MagnusError -- quem chama (main.py) que
        # decide como reportar (ClickException, sem traceback).
        mock_defaults.return_value.__enter__.return_value = "/tmp/defaults.cnf"
        with self.assertRaises(magnus_ops.MagnusError):
            magnus_ops.restore("/tmp/extracted", "root", "s3nha")

    @patch("magnus_ops._reset_mbilling_user_password")
    @patch("magnus_ops._read_mbilling_user_dbpass", return_value=None)
    @patch("magnus_ops._fix_web_permissions")
    @patch("magnus_ops._restart_asterisk")
    @patch("magnus_ops._run_update_script")
    @patch("magnus_ops._copy_dir")
    @patch("magnus_ops._restore_database")
    @patch("magnus_ops._mysql_defaults_file")
    def test_skips_copying_sounds_when_audios_ura_dir_is_absent(
        self, mock_defaults, mock_restore_db, mock_copy, mock_update,
        mock_restart, mock_perms, mock_read_pass, mock_reset_pass,
    ):
        # opcional no backup (ver export_backup) -- ausente no extraído não
        # pode crashar o restore com FileNotFoundError.
        mock_defaults.return_value.__enter__.return_value = "/tmp/defaults.cnf"
        with TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "etc", "asterisk"))
            magnus_ops.restore(tmp, "root", "s3nha")
        mock_copy.assert_called_once_with(os.path.join(tmp, "etc", "asterisk"), magnus_ops.DEFAULT_ASTERISK_DIR)


class IsAlreadyInstalledTest(unittest.TestCase):
    def test_true_when_web_dir_exists(self):
        with TemporaryDirectory() as tmp:
            with patch("magnus_ops.MBILLING_WEB_DIR", tmp):
                self.assertTrue(magnus_ops.is_already_installed())

    def test_false_when_web_dir_is_absent(self):
        with patch("magnus_ops.MBILLING_WEB_DIR", "/does/not/exist"):
            self.assertFalse(magnus_ops.is_already_installed())


class RunInstallerTest(unittest.TestCase):
    @patch("magnus_ops.subprocess.run")
    @patch("magnus_ops._download", return_value=b"#!/bin/bash\necho hi\n")
    def test_downloads_the_official_installer_and_runs_it(self, mock_download, mock_run):
        magnus_ops.run_installer()
        mock_download.assert_called_once_with(magnus_ops.INSTALLER_URL)
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0][0], "bash")
        self.assertTrue(args[0][1].endswith("install.sh"))

    @patch("magnus_ops.subprocess.run")
    @patch("magnus_ops._download", return_value=b"#!/bin/bash\nexit 1\n")
    def test_never_raises_on_a_non_zero_exit(self, mock_download, mock_run):
        # instalador oficial é interativo e pode ser recusado pelo próprio
        # usuário ("Type I UNDERSTAND...") -- exit != 0 não é erro nosso pra
        # reportar, é decisão de quem respondeu o prompt. A partir do
        # handoff, o resultado não é mais responsabilidade do pvx.
        mock_run.return_value.returncode = 1
        magnus_ops.run_installer()  # não deve levantar


if __name__ == "__main__":
    unittest.main()
