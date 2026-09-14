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
CLEAN_SCAN = {"findings": [], "blobs_scanned": ["var.www.html.admin.tgz"]}


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
    def _invoke(self, args, interactive=False, checkbox_result=None, text_result="issabel-backup-x.tar",
                check_backup=False, checkbox_side_effect=None):
        checkbox_patch = (
            patch("main.ask_checkbox", side_effect=checkbox_side_effect) if checkbox_side_effect
            else patch("main.ask_checkbox", return_value=checkbox_result)
        )
        with patch("main._is_interactive", return_value=interactive), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.ask_text", return_value=text_result), \
             checkbox_patch as mock_checkbox, \
             patch("main.ask_confirm", return_value=check_backup), \
             patch("main.backup_ops.export_backup", return_value=("/tmp/x.tar", None)) as mock_export:
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export"] + args)
        return result, mock_checkbox, mock_export

    def test_interactive_prompts_filename_and_calls_export_with_the_chosen_components(self):
        result, mock_checkbox, mock_export = self._invoke(
            [], interactive=True, checkbox_result=["as_db", "mysql_db"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(mock_export.call_args.args, ("issabel-backup-x.tar", ["as_db", "mysql_db"]))

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
        self.assertEqual(mock_export.call_args.args[1], ["as_db"])

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

    def test_still_succeeds_and_warns_when_the_helper_returns_a_warning(self):
        # issabel-helper (igual a interface web nativa) retorna avisos sem
        # que o export como um todo tenha falhado -- não pode virar erro.
        with patch("main._is_interactive", return_value=False), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.export_backup", return_value=("/tmp/x.tar", "WARN: banco tal nao existe")):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("avisos", result.output)

    def test_default_answer_skips_checking_the_backup(self):
        with patch("main.security_scan.scan_backup") as mock_scan:
            result, _, _ = self._invoke([], interactive=True, checkbox_result=["as_db"], check_backup=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_scan.assert_not_called()

    def test_checking_a_clean_backup_shows_the_audit_and_offers_no_pruning(self):
        with patch("main.security_scan.scan_backup", return_value=CLEAN_SCAN):
            result, mock_checkbox, _ = self._invoke([], interactive=True, checkbox_result=["as_db"], check_backup=True)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("nenhum sinal de webshell", result.output)
        mock_checkbox.assert_called_once()  # só a escolha de componentes -- nenhum prompt de pruning

    def test_checking_offers_pruning_of_suspicious_files_checked_by_default(self):
        suspicious = {
            "findings": [main.security_scan.Finding("suspeito", "var.www.html.admin.tgz", "admin/shell.php", "ofuscacao")],
            "blobs_scanned": ["var.www.html.admin.tgz"],
        }
        with patch("main.security_scan.scan_backup", return_value=suspicious), \
             patch("main.security_scan.prune_backup", return_value=1) as mock_prune:
            result, mock_checkbox, _ = self._invoke(
                [], interactive=True, check_backup=True,
                checkbox_side_effect=[["as_db"], ["var.www.html.admin.tgz::admin/shell.php"]],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        prune_choices = mock_checkbox.call_args_list[1].args[1]
        self.assertEqual(len(prune_choices), 1)
        self.assertTrue(prune_choices[0].checked)
        mock_prune.assert_called_once()
        self.assertEqual(mock_prune.call_args.args[0], "/tmp/x.tar")
        self.assertIn("1 arquivo(s)", result.output)

    def test_dialplan_findings_are_never_offered_for_pruning(self):
        suspicious = {
            "findings": [main.security_scan.Finding(
                "suspeito", "etc.asterisk.tgz", "extensions.conf (linha 3)", "System(nc -e ...)",
            )],
            "blobs_scanned": ["etc.asterisk.tgz"],
        }
        with patch("main.security_scan.scan_backup", return_value=suspicious), \
             patch("main.security_scan.prune_backup") as mock_prune:
            # só 1 resposta na lista -- se o código pedir um checklist de
            # pruning pra um achado de dialplan, side_effect estoura.
            result, mock_checkbox, _ = self._invoke(
                [], interactive=True, check_backup=True, checkbox_side_effect=[["as_db"]],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_prune.assert_not_called()

    def test_unselecting_everything_skips_pruning(self):
        suspicious = {
            "findings": [main.security_scan.Finding("suspeito", "var.www.html.admin.tgz", "admin/shell.php", "ofuscacao")],
            "blobs_scanned": ["var.www.html.admin.tgz"],
        }
        with patch("main.security_scan.scan_backup", return_value=suspicious), \
             patch("main.security_scan.prune_backup") as mock_prune:
            result, _, _ = self._invoke(
                [], interactive=True, check_backup=True, checkbox_side_effect=[["as_db"], []],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_prune.assert_not_called()


class ImportCmdTest(unittest.TestCase):
    INSPECTED = {"components": ["as_db", "mysql_db"], "versions": {"issabel": "5.0.0"}}

    def _invoke(self, args, interactive=False, confirm=True, checkbox_result=None, text_result="/tmp/x.tar",
                installed_version="5.0.0", import_warning=None, ask_confirm_side_effect=None, scan_result=None):
        confirm_patch = (
            patch("main.ask_confirm", side_effect=ask_confirm_side_effect) if ask_confirm_side_effect
            else patch("main.ask_confirm", return_value=confirm)
        )
        with patch("main._is_interactive", return_value=interactive), \
             patch("main.ask_text", return_value=text_result), \
             confirm_patch, \
             patch("main.ask_checkbox", return_value=checkbox_result) as mock_checkbox, \
             patch("main.backup_ops.inspect_backup", return_value=self.INSPECTED), \
             patch("main.backup_ops.installed_issabel_version", return_value=installed_version), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.security_scan.scan_backup", return_value=scan_result or CLEAN_SCAN), \
             patch("main.backup_ops.import_backup", return_value=import_warning) as mock_import:
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

    def test_still_succeeds_and_warns_when_the_helper_returns_a_warning(self):
        result, _, _ = self._invoke(
            ["--file", "/tmp/x.tar", "--yes"], interactive=False, import_warning="WARN: banco tal nao existe",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("avisos", result.output)

    def test_trusting_the_backup_by_default_skips_the_security_scan(self):
        with patch("main.security_scan.scan_backup") as mock_scan:
            result, _, mock_import = self._invoke(
                [], interactive=True, confirm=True, checkbox_result=[main._TUDO],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_scan.assert_not_called()
        mock_import.assert_called_once()

    def test_distrust_runs_the_scan_and_proceeds_when_clean(self):
        result, _, mock_import = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], scan_result=CLEAN_SCAN,
            ask_confirm_side_effect=[False, True],  # não confio -> ... -> restaurar por cima? sim
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("nenhum sinal de webshell", result.output)
        mock_import.assert_called_once()

    def test_distrust_with_suspicious_findings_asks_to_proceed_and_stops_if_declined(self):
        suspicious = {
            "findings": [main.security_scan.Finding("suspeito", "var.www.html.admin.tgz", "shell.php", "ofuscacao")],
            "blobs_scanned": ["var.www.html.admin.tgz"],
        }
        result, _, mock_import = self._invoke(
            [], interactive=True, scan_result=suspicious,
            ask_confirm_side_effect=[False, False],  # não confio -> acha suspeito -> restaurar mesmo assim? nao
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_not_called()

    def test_confirming_despite_suspicious_findings_skips_the_generic_restore_confirm(self):
        suspicious = {
            "findings": [main.security_scan.Finding("suspeito", "var.www.html.admin.tgz", "shell.php", "ofuscacao")],
            "blobs_scanned": ["var.www.html.admin.tgz"],
        }
        # só 2 respostas na lista -- se o código pedir confirmação genérica
        # de novo depois da de segurança, side_effect estoura StopIteration.
        result, _, mock_import = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], scan_result=suspicious,
            ask_confirm_side_effect=[False, True],  # não confio -> restaurar mesmo assim? sim
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once()


class InspectCmdTest(unittest.TestCase):
    def _invoke(self, args, scan_result=None, manifest=None):
        with patch(
            "main.backup_ops.inspect_backup",
            return_value={
                "components": ["as_db"], "versions": {"issabel": "5.0.0"}, "manifest": manifest or {},
            },
        ), patch("main.security_scan.scan_backup", return_value=scan_result or CLEAN_SCAN):
            return CliRunner().invoke(cli.cli_group(), ["backups", "inspect"] + args)

    def test_prints_issabel_version_and_components_found(self):
        result = self._invoke(["/tmp/x.tar"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("5.0.0", result.output)
        self.assertIn("as_db", result.output)

    def test_prints_the_pvx_signature_when_present(self):
        result = self._invoke(
            ["/tmp/x.tar"], manifest={"gerado_por": "pvx issabel v0.1.4", "gerado_em": "2026-09-14T17:00:00"},
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("pvx issabel v0.1.4", result.output)

    def test_omits_the_signature_line_when_absent(self):
        result = self._invoke(["/tmp/x.tar"], manifest={})
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("Gerado por", result.output)

    def test_prints_a_clean_audit_verdict_when_nothing_suspicious(self):
        result = self._invoke(["/tmp/x.tar"], scan_result=CLEAN_SCAN)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("nenhum sinal de webshell", result.output)

    def test_prints_each_suspicious_finding_and_the_bad_verdict(self):
        scan_result = {
            "findings": [main.security_scan.Finding("suspeito", "var.www.html.admin.tgz", "shell.php", "ofuscacao")],
            "blobs_scanned": ["var.www.html.admin.tgz"],
        }
        result = self._invoke(["/tmp/x.tar"], scan_result=scan_result)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("shell.php", result.output)
        self.assertIn("achado(s) suspeito", result.output)

    def test_failure_becomes_a_clean_cli_error(self):
        with patch("main.backup_ops.inspect_backup", side_effect=backup_ops.IssabelBackupError("arquivo inválido")):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "inspect", "/tmp/x.tar"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("arquivo inválido", result.output)

    def test_scan_failure_becomes_a_clean_cli_error(self):
        with patch(
            "main.backup_ops.inspect_backup",
            return_value={"components": [], "versions": {}, "manifest": {}},
        ), patch("main.security_scan.scan_backup", side_effect=main.security_scan.SecurityScanError("corrompido")):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "inspect", "/tmp/x.tar"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("corrompido", result.output)

    def test_interactive_prompts_for_the_file_when_omitted(self):
        # achado ao vivo: argumento posicional obrigatório crasha com
        # "Missing parameter" quando vem do auto-menu (que roda o comando
        # sem args nenhum) -- precisa cair pro mesmo prompt de export/import.
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_text", return_value="/tmp/x.tar") as mock_text, \
             patch(
                 "main.backup_ops.inspect_backup",
                 return_value={"components": ["as_db"], "versions": {"issabel": "5.0.0"}, "manifest": {}},
             ) as mock_inspect, \
             patch("main.security_scan.scan_backup", return_value=CLEAN_SCAN), \
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
