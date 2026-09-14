import unittest
from unittest.mock import patch

from click.testing import CliRunner

import backup_ops
import main
from main import _version_mismatch_warning, cli

FAKE_COMPONENTS = {
    "as_db": "Asterisk: banco de dados",
    "mysql_db": "MySQL: banco de dados geral",
    "as_monitor": "Asterisk: gravações (monitor)",
}


class VersionMismatchWarningTest(unittest.TestCase):
    def test_none_when_versions_match(self):
        self.assertIsNone(_version_mismatch_warning("5.0.0", "5.0.0"))

    def test_none_when_either_version_is_unknown(self):
        self.assertIsNone(_version_mismatch_warning(None, "5.0.0"))
        self.assertIsNone(_version_mismatch_warning("5.0.0", None))

    def test_warns_on_major_version_mismatch(self):
        message = _version_mismatch_warning("4.0.0", "5.0.0")
        self.assertIn("4", message)
        self.assertIn("5", message)


class ExportCmdTest(unittest.TestCase):
    def _invoke(self, args, interactive=False, checkbox_result=None, text_result="issabel-backup-x.tar"):
        with patch("main._is_interactive", return_value=interactive), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.ask_text", return_value=text_result), \
             patch("main.ask_checkbox", return_value=checkbox_result) as mock_checkbox, \
             patch("main.backup_ops.export_backup", return_value="/tmp/x.tar") as mock_export:
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export"] + args)
        return result, mock_checkbox, mock_export

    def test_interactive_prompts_filename_and_calls_export_with_the_chosen_components(self):
        result, mock_checkbox, mock_export = self._invoke(
            [], interactive=True, checkbox_result=["as_db", "mysql_db"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_export.assert_called_once_with("issabel-backup-x.tar", ["as_db", "mysql_db"])

    def test_interactive_checklist_shows_bare_key_with_description_in_the_hover_field(self):
        # pedido explícito: descrição vai no `description` (hover), não
        # embutida na label visível do item.
        _, mock_checkbox, _ = self._invoke([], interactive=True, checkbox_result=["as_db"])
        choices = {c.value: c for c in mock_checkbox.call_args.args[1]}
        self.assertEqual(choices["as_db"].title, "as_db")
        self.assertEqual(choices["as_db"].description, FAKE_COMPONENTS["as_db"])

    def test_interactive_unchecks_heavy_components_by_default(self):
        _, mock_checkbox, _ = self._invoke([], interactive=True, checkbox_result=["as_db"])
        choices = {c.value: c.checked for c in mock_checkbox.call_args.args[1]}
        self.assertTrue(choices["as_db"])
        self.assertTrue(choices["mysql_db"])
        self.assertFalse(choices["as_monitor"])

    def test_interactive_cancel_on_checklist_aborts_without_exporting(self):
        result, _, mock_export = self._invoke([], interactive=True, checkbox_result=None)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_export.assert_not_called()

    def test_non_interactive_defaults_to_all_components_without_prompting(self):
        result, mock_checkbox, mock_export = self._invoke([], interactive=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_checkbox.assert_not_called()
        mock_export.assert_called_once()
        self.assertEqual(sorted(mock_export.call_args.args[1]), sorted(FAKE_COMPONENTS))

    def test_non_interactive_honors_explicit_components_flag(self):
        result, _, mock_export = self._invoke(["--components", "as_db"], interactive=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_export.assert_called_once_with(mock_export.call_args.args[0], ["as_db"])

    def test_rejects_unknown_component(self):
        result, _, mock_export = self._invoke(["--components", "nao_existe"], interactive=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("nao_existe", result.output)
        mock_export.assert_not_called()

    def test_export_failure_becomes_a_clean_cli_error(self):
        with patch("main._is_interactive", return_value=False), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.export_backup", side_effect=backup_ops.IssabelBackupError("deu ruim")):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("deu ruim", result.output)


class ImportCmdTest(unittest.TestCase):
    INSPECTED = {"components": ["as_db", "mysql_db"], "versions": {"issabel": "5.0.0"}}

    def _invoke(self, args, interactive=False, confirm=True, checkbox_result=None, text_result="/tmp/x.tar",
                installed_version="5.0.0"):
        with patch("main._is_interactive", return_value=interactive), \
             patch("main.ask_text", return_value=text_result), \
             patch("main.ask_confirm", return_value=confirm), \
             patch("main.ask_checkbox", return_value=checkbox_result) as mock_checkbox, \
             patch("main.backup_ops.inspect_backup", return_value=self.INSPECTED), \
             patch("main.backup_ops.installed_issabel_version", return_value=installed_version), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.import_backup") as mock_import:
            result = CliRunner().invoke(cli.cli_group(), ["backups", "import"] + args)
        return result, mock_checkbox, mock_import

    def test_interactive_checklist_defaults_to_tudo_checked_and_rest_unchecked(self):
        _, mock_checkbox, _ = self._invoke([], interactive=True, checkbox_result=[main._TUDO])
        choices = {c.value: c.checked for c in mock_checkbox.call_args.args[1]}
        self.assertTrue(choices[main._TUDO])
        self.assertFalse(choices["as_db"])
        self.assertFalse(choices["mysql_db"])

    def test_interactive_default_choice_is_all_components_from_the_backup(self):
        result, _, mock_import = self._invoke([], interactive=True, checkbox_result=[main._TUDO])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db", "mysql_db"])

    def test_interactive_can_narrow_to_specific_components(self):
        result, _, mock_import = self._invoke([], interactive=True, checkbox_result=["as_db"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db"])

    def test_interactive_declining_the_confirm_never_imports(self):
        result, _, mock_import = self._invoke([], interactive=True, confirm=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_not_called()

    def test_interactive_warns_on_issabel_version_mismatch(self):
        result, _, _ = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], installed_version="4.0.0",
        )
        self.assertIn("4", result.output)
        self.assertIn("5", result.output)

    def test_non_interactive_requires_yes_to_skip_confirmation(self):
        result, _, mock_import = self._invoke(["--file", "/tmp/x.tar"], interactive=False)
        self.assertNotEqual(result.exit_code, 0)
        mock_import.assert_not_called()

    def test_non_interactive_with_yes_defaults_to_all_components_from_the_backup(self):
        result, _, mock_import = self._invoke(["--file", "/tmp/x.tar", "--yes"], interactive=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db", "mysql_db"])

    def test_non_interactive_honors_explicit_components_flag(self):
        result, _, mock_import = self._invoke(
            ["--file", "/tmp/x.tar", "--yes", "--components", "as_db"], interactive=False,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db"])


class InspectCmdTest(unittest.TestCase):
    def test_prints_issabel_version_and_components_found(self):
        with patch(
            "main.backup_ops.inspect_backup",
            return_value={"components": ["as_db"], "versions": {"issabel": "5.0.0"}},
        ):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "inspect", "/tmp/x.tar"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("5.0.0", result.output)
        self.assertIn("as_db", result.output)

    def test_failure_becomes_a_clean_cli_error(self):
        with patch("main.backup_ops.inspect_backup", side_effect=backup_ops.IssabelBackupError("arquivo inválido")):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "inspect", "/tmp/x.tar"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("arquivo inválido", result.output)

    def test_interactive_prompts_for_the_file_when_omitted(self):
        # achado ao vivo: argumento posicional obrigatório crasha com
        # "Missing parameter" quando vem do auto-menu (que roda o comando
        # sem args nenhum) -- precisa cair pro mesmo prompt de export/import.
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_text", return_value="/tmp/x.tar") as mock_text, \
             patch(
                 "main.backup_ops.inspect_backup",
                 return_value={"components": ["as_db"], "versions": {"issabel": "5.0.0"}},
             ) as mock_inspect, \
             patch("main.widgets.pause"):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "inspect"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_text.assert_called_once()
        mock_inspect.assert_called_once_with("/tmp/x.tar")

    def test_non_interactive_without_a_file_raises_a_clean_error(self):
        with patch("main._is_interactive", return_value=False):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "inspect"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
