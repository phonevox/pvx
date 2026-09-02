import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

import magnus_ops
from main import _read_password_file, cli

_PW_FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".pw", delete=False)
_PW_FILE.write("s3nha")
_PW_FILE.close()
PASSWORD_FILE = _PW_FILE.name


class ReadPasswordFileTest(unittest.TestCase):
    def test_reads_and_strips_the_file_content(self):
        self.assertEqual(_read_password_file(PASSWORD_FILE), "s3nha")

    def test_none_when_no_path_given(self):
        self.assertIsNone(_read_password_file(None))


class BackupExportCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False):
        with patch("main._is_interactive", return_value=is_tty), \
             patch(
                 "main.magnus_ops.export_backup",
                 return_value=("/tmp/backup-pxmagnus.02-09-2026.tgz", []),
             ) as mock_export, \
             patch("main.MagnusModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, mock_export

    def test_headless_requires_db_user(self):
        result, mock_export = self._invoke(["backup", "export", "--db-password-file", PASSWORD_FILE])
        self.assertNotEqual(result.exit_code, 0)
        mock_export.assert_not_called()

    def test_headless_requires_db_password_file(self):
        result, mock_export = self._invoke(["backup", "export", "--db-user", "root"])
        self.assertNotEqual(result.exit_code, 0)
        mock_export.assert_not_called()

    def test_happy_path_calls_export_backup(self):
        result, mock_export = self._invoke([
            "backup", "export", "--db-user", "root", "--db-password-file", PASSWORD_FILE, "-o", "/tmp/out.tgz",
        ])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_export.assert_called_once_with("root", "s3nha", output_path="/tmp/out.tgz")

    def test_reports_warnings_from_export_backup_eg_missing_sounds_dir(self):
        with patch(
            "main.magnus_ops.export_backup",
            return_value=("/tmp/out.tgz", ["diretório de áudios da URA não encontrado em '/x' -- pulado."]),
        ), patch("main.MagnusModule.get_logger"), patch("main._is_interactive", return_value=False):
            result = CliRunner().invoke(cli.cli_group(), [
                "backup", "export", "--db-user", "root", "--db-password-file", PASSWORD_FILE,
            ])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("áudios da URA", result.output)

    def test_interactive_prompts_for_missing_credentials(self):
        with patch("main.ask_text", return_value="root"), patch("main.ask_password", return_value="s3nha"):
            result, mock_export = self._invoke(["backup", "export"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_export.assert_called_once_with("root", "s3nha", output_path=None)

    def test_escaping_the_db_user_prompt_aborts_cleanly(self):
        with patch("main.ask_text", return_value=None):
            result, mock_export = self._invoke(["backup", "export"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_export.assert_not_called()

    def test_magnus_error_becomes_a_clean_click_exception_not_a_traceback(self):
        # achado ao vivo: senha errada no mysqldump crashava com traceback.
        with patch("main._is_interactive", return_value=False), \
             patch(
                 "main.magnus_ops.export_backup",
                 side_effect=magnus_ops.MagnusError("Access denied for user 'root'@'localhost'"),
             ), \
             patch("main.MagnusModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), [
                "backup", "export", "--db-user", "root", "--db-password-file", PASSWORD_FILE,
            ])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("Access denied", result.output)

    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause):
        with patch("main.ask_text", return_value="root"), patch("main.ask_password", return_value="s3nha"):
            result, _ = self._invoke(["backup", "export"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause):
        result, _ = self._invoke(["backup", "export", "--db-user", "root", "--db-password-file", PASSWORD_FILE])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_not_called()


class BackupImportCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False, valid_archive=True, validation_errors=None):
        with patch("main._is_interactive", return_value=is_tty), \
             patch("main.magnus_ops.is_valid_archive", return_value=valid_archive), \
             patch("main.magnus_ops.extract_archive"), \
             patch("main.magnus_ops.validate_extracted", return_value=validation_errors or []), \
             patch("main.magnus_ops.restore") as mock_restore, \
             patch("main.MagnusModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, mock_restore

    def test_headless_requires_backup_file(self):
        result, mock_restore = self._invoke(
            ["backup", "import", "--yes", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
        )
        self.assertNotEqual(result.exit_code, 0)
        mock_restore.assert_not_called()

    def test_interactive_prompts_for_the_backup_file_path(self):
        # achado ao vivo: no menu interativo o auto-menu chama o comando sem
        # argumento nenhum -- um @click.argument obrigatório nunca chega a
        # perguntar nada, só falha com "missing argument" antes de qualquer
        # prompt.
        with patch("main.ask_text", return_value="/root/backup-pxmagnus.02-09-2026.tgz"), \
             patch("main.ask_confirm", return_value=True):
            result, mock_restore = self._invoke(
                ["backup", "import", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
                is_tty=True,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_restore.assert_called_once()

    def test_escaping_the_backup_file_prompt_aborts_cleanly(self):
        with patch("main.ask_text", return_value=None):
            result, mock_restore = self._invoke(
                ["backup", "import", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
                is_tty=True,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_restore.assert_not_called()

    def test_rejects_an_invalid_archive_before_anything_else(self):
        result, mock_restore = self._invoke(
            ["backup", "import", "backup.tgz", "--yes", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
            valid_archive=False,
        )
        self.assertNotEqual(result.exit_code, 0)
        mock_restore.assert_not_called()

    def test_reports_validation_errors_and_never_restores(self):
        result, mock_restore = self._invoke(
            ["backup", "import", "backup.tgz", "--yes", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
            validation_errors=["serviço 'asterisk' não está ativo."],
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("asterisk", result.output.lower())
        mock_restore.assert_not_called()

    def test_headless_requires_yes(self):
        result, mock_restore = self._invoke(
            ["backup", "import", "backup.tgz", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
        )
        self.assertNotEqual(result.exit_code, 0)
        mock_restore.assert_not_called()

    def test_magnus_error_becomes_a_clean_click_exception_not_a_traceback(self):
        with patch("main._is_interactive", return_value=False), \
             patch("main.magnus_ops.is_valid_archive", return_value=True), \
             patch("main.magnus_ops.extract_archive"), \
             patch("main.magnus_ops.validate_extracted", return_value=[]), \
             patch(
                 "main.magnus_ops.restore",
                 side_effect=magnus_ops.MagnusError("serviço 'asterisk' não está ativo"),
             ), \
             patch("main.MagnusModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), [
                "backup", "import", "backup.tgz", "--yes", "--db-user", "root", "--db-password-file", PASSWORD_FILE,
            ])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("asterisk", result.output.lower())

    def test_yes_flag_skips_confirmation_and_restores(self):
        result, mock_restore = self._invoke(
            ["backup", "import", "backup.tgz", "--yes", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_restore.assert_called_once()
        self.assertEqual(mock_restore.call_args.args[1:], ("root", "s3nha"))

    def test_declining_confirmation_restores_nothing(self):
        with patch("main.ask_confirm", return_value=False):
            result, mock_restore = self._invoke(
                ["backup", "import", "backup.tgz", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
                is_tty=True,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_restore.assert_not_called()

    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause):
        with patch("main.ask_confirm", return_value=True):
            result, _ = self._invoke(
                ["backup", "import", "backup.tgz", "--db-user", "root", "--db-password-file", PASSWORD_FILE],
                is_tty=True,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()


class InstallCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False, already_installed=False):
        with patch("main._is_interactive", return_value=is_tty), \
             patch("main.magnus_ops.is_already_installed", return_value=already_installed), \
             patch("main.magnus_ops.run_installer") as mock_run, \
             patch("main.MagnusModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, mock_run

    def test_headless_requires_yes(self):
        result, mock_run = self._invoke(["install"])
        self.assertNotEqual(result.exit_code, 0)
        mock_run.assert_not_called()

    def test_yes_flag_skips_confirmation_and_installs(self):
        result, mock_run = self._invoke(["install", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_run.assert_called_once_with()

    def test_declining_confirmation_installs_nothing(self):
        with patch("main.ask_confirm", return_value=False):
            result, mock_run = self._invoke(["install"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_run.assert_not_called()

    def test_confirmation_warns_this_is_the_official_third_party_installer(self):
        with patch("main.ask_confirm", return_value=True) as mock_confirm:
            self._invoke(["install"], is_tty=True)
        prompt = mock_confirm.call_args.args[0]
        self.assertIn("OFICIAL", prompt)

    def test_confirmation_warns_when_already_installed(self):
        with patch("main.ask_confirm", return_value=True) as mock_confirm:
            self._invoke(["install"], is_tty=True, already_installed=True)
        prompt = mock_confirm.call_args.args[0]
        self.assertIn("já", prompt.lower())

    def test_help_text_mentions_this_is_a_third_party_installer(self):
        result = CliRunner().invoke(cli.cli_group(), ["install", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("OFICIAL", result.output)

    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause):
        with patch("main.ask_confirm", return_value=True):
            result, _ = self._invoke(["install"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause):
        result, _ = self._invoke(["install", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
