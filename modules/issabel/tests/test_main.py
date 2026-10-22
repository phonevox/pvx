import json
import os
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

import click
from click.testing import CliRunner

import backup_ops
import health_checks
import main
import trust_ops
from main import _version_mismatch_warning, cli

FAKE_COMPONENTS = {
    "as_db": "Asterisk: banco de dados",
    "mysql_db": "MySQL: banco de dados geral",
    "as_monitor": "Asterisk: gravações (monitor)",
    "menus_permissions": "Menus e permissões",
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


class IssabelVersionTest(unittest.TestCase):
    def test_prefers_the_hyphenated_product_package(self):
        # achado ao vivo (2026-10): uma central real com histórico de
        # upgrade tinha "issabelpbx" (sem hífen) = 2.11.0 -- um framework
        # interno, não o produto -- e "issabel-pbx" (com hífen) = 4.0.0, a
        # versão de produto de verdade. Sem priorizar o nome com hífen, a
        # migração 4->5 nunca detectava a diferença de versão e restaurava
        # um backup do Issabel 4 como se fosse a mesma versão da central 5.
        versions = {"issabelpbx": "2.11.0", "issabel-pbx": "4.0.0"}
        self.assertEqual(main._issabel_version(versions), "4.0.0")

    def test_falls_back_to_issabelpbx_when_the_hyphenated_package_is_absent(self):
        self.assertEqual(main._issabel_version({"issabelpbx": "5.0.0"}), "5.0.0")

    def test_falls_back_to_the_meta_package(self):
        self.assertEqual(main._issabel_version({"issabel": "5.0.0"}), "5.0.0")

    def test_none_when_nothing_matches(self):
        self.assertIsNone(main._issabel_version({}))


class ExportCmdTest(unittest.TestCase):
    def _invoke(self, args, interactive=False, checkbox_result=None, text_result="issabel-backup-x.tar",
                check_backup=False, checkbox_side_effect=None, autodetected=None):
        checkbox_patch = (
            patch("main.ask_checkbox", side_effect=checkbox_side_effect) if checkbox_side_effect
            else patch("main.ask_checkbox", return_value=checkbox_result)
        )
        with patch("main._is_interactive", return_value=interactive), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.autodetect_components", return_value=autodetected or []), \
             patch("main.ask_text", return_value=text_result), \
             checkbox_patch as mock_checkbox, \
             patch("main.ask_confirm", return_value=check_backup), \
             patch("main.trust_ops.merged_trusted_items", return_value={}), \
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

    def test_warns_when_the_chosen_filename_does_not_match_issabels_native_pattern(self):
        result, _, _ = self._invoke(
            [], interactive=True, checkbox_result=["as_db"], text_result="meu-backup-custom.tar",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("só vai funcionar aqui no pvx", result.output)

    def test_no_warning_when_the_filename_matches_the_native_pattern(self):
        result, _, _ = self._invoke(
            [], interactive=True, checkbox_result=["as_db"],
            text_result="issabelbackup-20260924162220-px.tar",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("só vai funcionar aqui no pvx", result.output)

    def test_warns_on_a_non_native_filename_passed_via_flag_too(self):
        with patch("main._is_interactive", return_value=False), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.autodetect_components", return_value=[]), \
             patch("main.backup_ops.export_backup", return_value=("/tmp/x.tar", None)):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export", "--filename", "custom.tar"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("só vai funcionar aqui no pvx", result.output)

    def test_interactive_checklist_offers_autodetected_extras_marked_as_such(self):
        _, mock_checkbox, _ = self._invoke(
            [], interactive=True, checkbox_result=["as_db"], autodetected=["int_sgp"],
        )
        choices = {c.value: c.description for c in mock_checkbox.call_args.args[1]}
        self.assertIn("int_sgp", choices)
        self.assertTrue(choices["int_sgp"].endswith("(autodetectado)"))

    def test_autodetected_extra_already_native_is_not_offered_twice(self):
        # marker presente -> int_sgp já vem de available_components(); não
        # precisa (e não deve) ganhar o sufixo "(autodetectado)" nesse caso.
        with_extras = {**FAKE_COMPONENTS, "int_sgp": "Phonevox: integração SGP"}
        with patch("main._is_interactive", return_value=True), \
             patch("main.backup_ops.available_components", return_value=with_extras), \
             patch("main.backup_ops.autodetect_components", return_value=["int_sgp"]), \
             patch("main.ask_checkbox", return_value=["int_sgp"]) as mock_checkbox, \
             patch("main.ask_text", return_value="issabel-backup-x.tar"), \
             patch("main.ask_confirm", return_value=False), \
             patch("main.backup_ops.export_backup", return_value=("/tmp/x.tar", None)):
            CliRunner().invoke(cli.cli_group(), ["backups", "export"])
        choices = {c.value: c.description for c in mock_checkbox.call_args.args[1]}
        self.assertEqual(choices["int_sgp"], "Phonevox: integração SGP")

    def test_selecting_only_an_autodetected_extra_skips_the_helper_and_builds_a_manual_shell(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.autodetect_components", return_value=["int_sgp"]), \
             patch("main.ask_checkbox", return_value=["int_sgp"]), \
             patch("main.ask_text", return_value="issabel-backup-x.tar"), \
             patch("main.ask_confirm", return_value=False), \
             patch("main.backup_ops.export_backup") as mock_export, \
             patch("main.backup_ops.create_manual_backup_shell", return_value="/tmp/x.tar") as mock_shell, \
             patch("main.backup_ops.export_manual_component") as mock_manual:
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_export.assert_not_called()
        mock_shell.assert_called_once_with("issabel-backup-x.tar", ["int_sgp"], generated_by=f"pvx issabel v{cli.version}")
        mock_manual.assert_called_once_with("/tmp/x.tar", "int_sgp")

    def test_selecting_helper_and_autodetected_components_together_runs_both_and_records_them(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.autodetect_components", return_value=["int_sgp"]), \
             patch("main.ask_checkbox", return_value=["as_db", "int_sgp"]), \
             patch("main.ask_text", return_value="issabel-backup-x.tar"), \
             patch("main.ask_confirm", return_value=False), \
             patch("main.backup_ops.export_backup", return_value=("/tmp/x.tar", None)) as mock_export, \
             patch("main.backup_ops.inspect_backup", return_value={"components": ["as_db"]}), \
             patch("main.backup_ops.record_components") as mock_record, \
             patch("main.backup_ops.write_manifest") as mock_manifest, \
             patch("main.backup_ops.export_manual_component") as mock_manual:
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_export.assert_called_once_with(
            "issabel-backup-x.tar", ["as_db"], generated_by=f"pvx issabel v{cli.version}",
        )
        mock_record.assert_called_once_with("/tmp/x.tar", ["as_db", "int_sgp"])
        mock_manifest.assert_called_once_with(
            "/tmp/x.tar", f"pvx issabel v{cli.version}", manual_components=["int_sgp"],
        )
        mock_manual.assert_called_once_with("/tmp/x.tar", "int_sgp")

    def test_records_the_actually_exported_components_not_the_requested_ones(self):
        # export_backup pode ter derrubado sozinho um componente que essa
        # central não implementa (ver backup_ops.ExportBackupTest) -- o
        # a_options.xml regravado tem que refletir a verdade do arquivo, não
        # o que foi pedido no checklist.
        with patch("main._is_interactive", return_value=True), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.autodetect_components", return_value=["int_sgp"]), \
             patch("main.ask_checkbox", return_value=["as_db", "mysql_db", "int_sgp"]), \
             patch("main.ask_text", return_value="issabel-backup-x.tar"), \
             patch("main.ask_confirm", return_value=False), \
             patch("main.backup_ops.export_backup", return_value=("/tmp/x.tar", "mysql_db não suportado.")), \
             patch("main.backup_ops.inspect_backup", return_value={"components": ["as_db"]}), \
             patch("main.backup_ops.record_components") as mock_record, \
             patch("main.backup_ops.write_manifest"), \
             patch("main.backup_ops.export_manual_component"):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_record.assert_called_once_with("/tmp/x.tar", ["as_db", "int_sgp"])

    def test_non_interactive_explicit_components_flag_accepts_an_autodetected_extra(self):
        with patch("main._is_interactive", return_value=False), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.backup_ops.autodetect_components", return_value=["int_sgp"]), \
             patch("main.backup_ops.create_manual_backup_shell", return_value="/tmp/x.tar") as mock_shell, \
             patch("main.backup_ops.export_manual_component") as mock_manual:
            result = CliRunner().invoke(cli.cli_group(), ["backups", "export", "--components", "int_sgp"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_shell.assert_called_once()
        mock_manual.assert_called_once_with("/tmp/x.tar", "int_sgp")

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
                installed_version="5.0.0", import_warning=None, ask_confirm_side_effect=None, scan_result=None,
                ask_select_result=None, checkbox_side_effect=None, inspected=None, manual_restored=None):
        confirm_patch = (
            patch("main.ask_confirm", side_effect=ask_confirm_side_effect) if ask_confirm_side_effect
            else patch("main.ask_confirm", return_value=confirm)
        )
        checkbox_patch = (
            patch("main.ask_checkbox", side_effect=checkbox_side_effect) if checkbox_side_effect
            else patch("main.ask_checkbox", return_value=checkbox_result)
        )
        with patch("main._is_interactive", return_value=interactive), \
             patch("main.ask_text", return_value=text_result), \
             confirm_patch, \
             checkbox_patch as mock_checkbox, \
             patch("main.ask_select", return_value=ask_select_result) as mock_select, \
             patch("main.backup_ops.inspect_backup", return_value=inspected or self.INSPECTED), \
             patch("main.backup_ops.installed_issabel_version", return_value=installed_version), \
             patch("main.backup_ops.available_components", return_value=FAKE_COMPONENTS), \
             patch("main.security_scan.scan_backup", return_value=scan_result or CLEAN_SCAN), \
             patch("main.trust_ops.merged_trusted_items", return_value={}), \
             patch("main.backup_ops.restore_manual_component", return_value=manual_restored or []) as mock_manual, \
             patch("main.backup_ops.run_native_migration", return_value=None) as mock_migrate, \
             patch("main.backup_ops.restart_asterisk", return_value=None) as mock_restart, \
             patch("main.backup_ops.import_backup", return_value=import_warning) as mock_import:
            result = CliRunner().invoke(cli.cli_group(), ["backups", "import"] + args)
        return result, mock_checkbox, mock_import, mock_select, mock_manual, mock_migrate, mock_restart

    def test_interactive_checklist_defaults_to_tudo_checked_and_rest_unchecked(self):
        _, mock_checkbox, _, _, _, _, _ = self._invoke([], interactive=True, checkbox_result=[main._TUDO])
        choices = {c.value: c.checked for c in mock_checkbox.call_args.args[1]}
        self.assertTrue(choices[main._TUDO])
        self.assertFalse(choices["as_db"])
        self.assertFalse(choices["mysql_db"])

    def test_interactive_default_choice_is_all_components_from_the_backup(self):
        result, _, mock_import, _, _, _, _ = self._invoke([], interactive=True, checkbox_result=[main._TUDO])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db", "mysql_db"])

    def test_interactive_can_narrow_to_specific_components(self):
        result, _, mock_import, _, _, _, _ = self._invoke([], interactive=True, checkbox_result=["as_db"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db"])

    def test_restarts_asterisk_after_a_successful_restore(self):
        # achado ao vivo (2026-10): restore sem reiniciar o Asterisk depois
        # pode deixar uma conexão presa no astdb.sqlite3 antigo (db.c
        # ast_db_put: SQL logic error) mesmo com o arquivo já correto.
        _, _, _, _, _, _, mock_restart = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO],
        )
        mock_restart.assert_called_once()

    def test_interactive_declining_the_confirm_never_imports(self):
        result, _, mock_import, _, _, _, _ = self._invoke([], interactive=True, confirm=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_not_called()

    def test_interactive_warns_on_issabel_version_mismatch(self):
        result, _, _, _, _, _, _ = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], installed_version="4.0.0",
        )
        self.assertIn("4", result.output)
        self.assertIn("5", result.output)

    def test_non_interactive_requires_yes_to_skip_confirmation(self):
        result, _, mock_import, _, _, _, _ = self._invoke(["--file", "/tmp/x.tar"], interactive=False)
        self.assertNotEqual(result.exit_code, 0)
        mock_import.assert_not_called()

    def test_non_interactive_with_yes_defaults_to_all_components_from_the_backup(self):
        result, _, mock_import, _, _, _, _ = self._invoke(["--file", "/tmp/x.tar", "--yes"], interactive=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db", "mysql_db"])

    def test_non_interactive_honors_explicit_components_flag(self):
        result, _, mock_import, _, _, _, _ = self._invoke(
            ["--file", "/tmp/x.tar", "--yes", "--components", "as_db"], interactive=False,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db"])

    def test_version_mismatch_uses_native_migration_instead_of_the_helper(self):
        # versão diferente: usa o migrador nativo (issabel-helper migration),
        # mesma coisa que o botão "Migrate from Issabel 4" da web roda --
        # ele cuida de menu.db, senha de admin e upgrade dos módulos PBX
        # sozinho, sem precisar de seleção de componentes.
        inspected = {"components": ["as_db", "menus_permissions"], "versions": {"issabel": "4.0.0"}}
        result, _, mock_import, _, _, mock_migrate, _ = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], inspected=inspected, installed_version="5.0.0",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_not_called()
        mock_migrate.assert_called_once_with("/tmp/x.tar")

    def test_same_version_uses_the_helper_normally(self):
        inspected = {"components": ["as_db", "menus_permissions"], "versions": {"issabel": "5.0.0"}}
        result, _, mock_import, _, _, mock_migrate, _ = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], inspected=inspected, installed_version="5.0.0",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db", "menus_permissions"])
        mock_migrate.assert_not_called()

    def test_extras_unsupported_locally_go_to_manual_restore_instead_of_the_helper(self):
        # destino sem a backupengine customizada (int_sgp fora de
        # FAKE_COMPONENTS) -- não pode mandar pro issabel-helper (ele dá
        # error_exit fatal em componente desconhecido, abortando o restore
        # inteiro), então o pvx restaura esse na mão.
        inspected = {"components": ["as_db", "int_sgp"], "versions": {"issabel": "5.0.0"}}
        result, _, mock_import, _, mock_manual, _, _ = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], inspected=inspected,
            manual_restored=["/etc/asterisk/sgp"],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once_with("/tmp/x.tar", ["as_db"])
        mock_manual.assert_called_once_with("/tmp/x.tar", "int_sgp")
        self.assertIn("int_sgp", result.output)

    def test_interactive_checklist_describes_a_phonevox_extra_even_without_local_support(self):
        inspected = {"components": ["as_db", "int_sgp"], "versions": {"issabel": "5.0.0"}}
        _, mock_checkbox, _, _, _, _, _ = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], inspected=inspected,
        )
        choices = {c.value: c for c in mock_checkbox.call_args.args[1]}
        self.assertEqual(choices["int_sgp"].description, "Phonevox: integração SGP")

    def test_component_unknown_to_both_helper_and_manual_restore_is_rejected(self):
        result, _, mock_import, _, mock_manual, _, _ = self._invoke(
            ["--file", "/tmp/x.tar", "--yes", "--components", "nao_existe"], interactive=False,
        )
        self.assertNotEqual(result.exit_code, 0)
        mock_import.assert_not_called()
        mock_manual.assert_not_called()

    def test_still_succeeds_and_warns_when_the_helper_returns_a_warning(self):
        result, _, _, _, _, _, _ = self._invoke(
            ["--file", "/tmp/x.tar", "--yes"], interactive=False, import_warning="WARN: banco tal nao existe",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("avisos", result.output)

    def test_trusting_the_backup_by_default_skips_the_security_scan(self):
        with patch("main.security_scan.scan_backup") as mock_scan:
            result, _, mock_import, _, _, _, _ = self._invoke(
                [], interactive=True, confirm=True, checkbox_result=[main._TUDO],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_scan.assert_not_called()
        mock_import.assert_called_once()

    def test_distrust_runs_the_scan_and_proceeds_when_clean(self):
        result, _, mock_import, _, _, _, _ = self._invoke(
            [], interactive=True, checkbox_result=[main._TUDO], scan_result=CLEAN_SCAN,
            ask_confirm_side_effect=[False, True],  # não confio -> ... -> restaurar por cima? sim
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("nenhum sinal de webshell", result.output)
        mock_import.assert_called_once()

    SUSPICIOUS_SCAN = {
        "findings": [main.security_scan.Finding("suspeito", "var.www.html.admin.tgz", "admin/shell.php", "ofuscacao")],
        "blobs_scanned": ["var.www.html.admin.tgz"],
    }

    def test_distrust_with_suspicious_findings_shows_the_menu_and_aborts_by_default(self):
        # só 1 resposta de confirm na lista -- se o código pedir mais
        # alguma confirmação depois do menu de achados, estoura.
        result, _, mock_import, mock_select, _, _, _ = self._invoke(
            [], interactive=True, scan_result=self.SUSPICIOUS_SCAN,
            ask_confirm_side_effect=[False], ask_select_result=main._ABORTAR,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(mock_select.call_args.args[1], main._SUSPICIOUS_CHOICES)
        mock_import.assert_not_called()

    def test_escaping_the_menu_also_aborts(self):
        result, _, mock_import, _, _, _, _ = self._invoke(
            [], interactive=True, scan_result=self.SUSPICIOUS_SCAN,
            ask_confirm_side_effect=[False], ask_select_result=None,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_not_called()

    def test_proceeding_anyway_skips_the_generic_restore_confirm_and_never_prunes(self):
        with patch("main.security_scan.prune_backup") as mock_prune:
            result, _, mock_import, _, _, _, _ = self._invoke(
                [], interactive=True, checkbox_result=[main._TUDO], scan_result=self.SUSPICIOUS_SCAN,
                ask_confirm_side_effect=[False], ask_select_result=main._PROSSEGUIR,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_import.assert_called_once()
        mock_prune.assert_not_called()

    def test_proceeding_and_removing_prunes_every_suspicious_file_without_asking_which(self):
        with patch("main.security_scan.prune_backup", return_value=1) as mock_prune:
            result, _, mock_import, mock_checkbox, _, _, _ = self._invoke(
                [], interactive=True, checkbox_result=[main._TUDO], scan_result=self.SUSPICIOUS_SCAN,
                ask_confirm_side_effect=[False], ask_select_result=main._PROSSEGUIR_REMOVENDO,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_prune.assert_called_once()
        self.assertEqual(mock_prune.call_args.args[0], "/tmp/x.tar")
        self.assertEqual(len(mock_prune.call_args.args[1]), 1)
        mock_import.assert_called_once()
        self.assertIn("1 arquivo(s)", result.output)

    def test_proceeding_and_selecting_offers_a_cherrypick_checklist(self):
        with patch("main.security_scan.prune_backup", return_value=1) as mock_prune:
            result, mock_checkbox, mock_import, _, _, _, _ = self._invoke(
                [], scan_result=self.SUSPICIOUS_SCAN, ask_select_result=main._PROSSEGUIR_SELECIONANDO,
                ask_confirm_side_effect=[False],
                checkbox_side_effect=[["var.www.html.admin.tgz::admin/shell.php"], [main._TUDO]],
                interactive=True,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        prune_choices = mock_checkbox.call_args_list[0].args[1]
        self.assertEqual(len(prune_choices), 1)
        self.assertTrue(prune_choices[0].checked)
        mock_prune.assert_called_once()
        mock_import.assert_called_once()


class InspectCmdTest(unittest.TestCase):
    def _invoke(self, args, scan_result=None, manifest=None):
        with patch(
            "main.backup_ops.inspect_backup",
            return_value={
                "components": ["as_db"], "versions": {"issabel": "5.0.0"}, "manifest": manifest or {},
            },
        ), patch("main.security_scan.scan_backup", return_value=scan_result or CLEAN_SCAN), \
           patch("main.trust_ops.merged_trusted_items", return_value={}):
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
             patch("main.trust_ops.merged_trusted_items", return_value={}), \
             patch("main.widgets.pause"):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "inspect"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_text.assert_called_once()
        mock_inspect.assert_called_once_with("/tmp/x.tar")

    def test_non_interactive_without_a_file_raises_a_clean_error(self):
        with patch("main._is_interactive", return_value=False):
            result = CliRunner().invoke(cli.cli_group(), ["backups", "inspect"])
        self.assertNotEqual(result.exit_code, 0)


class TestsCmdTest(unittest.TestCase):
    def test_runs_everything_by_default_and_prints_pass(self):
        with patch("main.health_checks.run_checks", return_value=[
            health_checks.CheckResult("astdb_write", True),
            health_checks.CheckResult("odbc", True),
        ]) as mock_run:
            result = CliRunner().invoke(cli.cli_group(), ["tests"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_run.assert_called_once_with(())
        self.assertIn("PASS astdb_write", result.output)
        self.assertIn("PASS odbc", result.output)

    def test_colors_pass_green_and_fail_red_on_a_real_terminal(self):
        # só colore quando tem terminal de verdade (color=True força isso no
        # teste) -- pipe/cron/grep continua recebendo "PASS"/"FAIL" crus,
        # sem escape code, porque o click já faz esse strip sozinho fora de
        # um tty real.
        with patch("main.health_checks.run_checks", return_value=[
            health_checks.CheckResult("astdb_write", True),
            health_checks.CheckResult("odbc", False, "boom"),
        ]):
            result = CliRunner().invoke(cli.cli_group(), ["tests"], color=True)
        self.assertIn(f"{click.style('PASS', fg='green')} astdb_write", result.output)
        self.assertIn(f"{click.style('FAIL', fg='red')} odbc boom", result.output)

    def test_prints_fail_with_the_detail_and_exits_nonzero(self):
        with patch("main.health_checks.run_checks", return_value=[
            health_checks.CheckResult("odbc", False, "DSN(s) desconectado(s): asteriskcdrdb"),
        ]):
            result = CliRunner().invoke(cli.cli_group(), ["tests"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("FAIL odbc DSN(s) desconectado(s): asteriskcdrdb", result.output)

    def test_zero_exit_code_when_everything_passes(self):
        with patch("main.health_checks.run_checks", return_value=[health_checks.CheckResult("odbc", True)]):
            result = CliRunner().invoke(cli.cli_group(), ["tests"])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_narrows_to_the_requested_checks(self):
        with patch("main.health_checks.run_checks", return_value=[health_checks.CheckResult("odbc", True)]) as mock_run:
            CliRunner().invoke(cli.cli_group(), ["tests", "--check", "odbc"])
        mock_run.assert_called_once_with(("odbc",))

    def test_rejects_an_unknown_check_name(self):
        result = CliRunner().invoke(cli.cli_group(), ["tests", "--check", "nao_existe"])
        self.assertNotEqual(result.exit_code, 0)


FAKE_REPORT = {
    "os": "Rocky 8", "pbx": "Issabel 5",
    "notes": [],
    "findings": [
        {"sev": "CRIT", "class": "webshell", "msg": "arquivo suspeito: /var/www/html/admin/modules/x/foo.php"},
        {"sev": "MED", "class": "persist", "msg": "cron novo sem dono de pacote: /etc/cron.d/x"},
    ],
}


class AuditRunCmdTest(unittest.TestCase):
    def _invoke(self, args=None, interactive=False, is_root=True, report=None, returncode=0, trusted=None):
        args = args or ["audit", "run"]
        proc = Mock(returncode=returncode, stdout=json.dumps(report if report is not None else FAKE_REPORT), stderr="")
        with patch("main._is_interactive", return_value=interactive), \
             patch("main.os.geteuid", return_value=0 if is_root else 1000), \
             patch("main.audit_ops.deploy", return_value="/opt/pvx/modules/issabel/scripts/audit.sh"), \
             patch("main.subprocess.run", return_value=proc) as mock_run, \
             patch("main.trust_ops.merged_trusted_items", return_value=trusted or {}) as mock_trusted, \
             patch("main.widgets.pause") as mock_pause:
            result = CliRunner().invoke(cli.cli_group(), args)
        return result, mock_run, mock_trusted, mock_pause

    def test_requires_root(self):
        result, mock_run, _, _ = self._invoke(is_root=False)
        self.assertNotEqual(result.exit_code, 0)
        mock_run.assert_not_called()

    def test_prints_every_finding_including_trusted_ones(self):
        # achado confiado NUNCA some -- só fica marcado, pedido explícito.
        trusted = {"/var/www/html/admin/modules/x/foo.php": {"sha256": "whatever", "origem": "remoto"}}
        with patch("trust_ops.annotate_findings", return_value=[
            (FAKE_REPORT["findings"][0], ("/var/www/html/admin/modules/x/foo.php", "remoto")),
            (FAKE_REPORT["findings"][1], None),
        ]):
            result, _, _, _ = self._invoke(trusted=trusted)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("cron novo sem dono de pacote", result.output)
        self.assertIn("webshell", result.output)

    def test_marks_a_trusted_finding_with_an_explanatory_arrow_line(self):
        with patch("trust_ops.annotate_findings", return_value=[
            (FAKE_REPORT["findings"][0], ("/var/www/html/admin/modules/x/foo.php", "remoto")),
            (FAKE_REPORT["findings"][1], None),
        ]):
            result, _, _, _ = self._invoke()
        self.assertIn("↳ confiado", result.output)
        self.assertIn("/var/www/html/admin/modules/x/foo.php", result.output)

    def test_distinguishes_network_trust_from_local_pending_trust_in_the_arrow_note(self):
        with patch("trust_ops.annotate_findings", return_value=[
            (FAKE_REPORT["findings"][0], ("/var/www/html/admin/modules/x/foo.php", "remoto")),
            (FAKE_REPORT["findings"][1], ("/etc/cron.d/x", "local")),
        ]):
            result, _, _, _ = self._invoke()
        self.assertIn("confiado (rede)", result.output)
        self.assertIn("confiado (local, não publicado)", result.output)

    def test_exits_1_when_the_script_itself_reports_compromised(self):
        result, _, _, _ = self._invoke(returncode=1)
        self.assertEqual(result.exit_code, 1)

    def test_clean_error_when_the_script_does_not_output_valid_json(self):
        proc = Mock(returncode=3, stdout="not json", stderr="boom")
        with patch("main._is_interactive", return_value=False), \
             patch("main.os.geteuid", return_value=0), \
             patch("main.audit_ops.deploy", return_value="/x/audit.sh"), \
             patch("main.subprocess.run", return_value=proc):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "run"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("boom", result.output)

    def test_passes_the_url_through_to_trust_lookup(self):
        _, _, mock_trusted, _ = self._invoke(args=["audit", "run", "--url", "http://trust.example"])
        mock_trusted.assert_called_once_with("http://trust.example")

    def test_uses_the_default_url_when_none_is_given(self):
        _, _, mock_trusted, _ = self._invoke()
        mock_trusted.assert_called_once_with(trust_ops.DEFAULT_URL)

    def test_shows_status_score_and_duration(self):
        report = dict(FAKE_REPORT, level="suspect", score=35, duration_s=7, version="1.4.0")
        result, _, _, _ = self._invoke(report=report)
        self.assertIn("suspect", result.output)
        self.assertIn("35/100", result.output)
        self.assertIn("duração: 7s", result.output)
        self.assertIn("1.4.0", result.output)

    def test_shows_degraded_warning_and_reason(self):
        report = dict(FAKE_REPORT, degraded=1, reason="rodando sem root")
        result, _, _, _ = self._invoke(report=report)
        self.assertIn("cobertura reduzida", result.output)
        self.assertIn("rodando sem root", result.output)


class AuditTrustCmdTest(unittest.TestCase):
    def test_trust_stages_every_file_given(self):
        with patch("main._is_interactive", return_value=False), \
             patch("main.trust_ops.stage", return_value="a" * 64) as mock_stage:
            result = CliRunner().invoke(cli.cli_group(), ["audit", "trust", "/a.php", "/b.php"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_stage.assert_any_call("/a.php", "trust")
        mock_stage.assert_any_call("/b.php", "trust")

    def test_untrust_stages_with_the_untrust_action(self):
        with patch("main._is_interactive", return_value=False), \
             patch("main.trust_ops.stage", return_value="a" * 64) as mock_stage:
            result = CliRunner().invoke(cli.cli_group(), ["audit", "untrust", "/a.php"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_stage.assert_called_once_with("/a.php", "untrust")

    def test_explains_itself_in_interactive_mode(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.trust_ops.stage", return_value="a" * 64), \
             patch("main.widgets.pause"):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "trust", "/a.php"])
        self.assertIn("Calcula o sha256", result.output)

    def test_non_interactive_requires_at_least_one_file(self):
        with patch("main._is_interactive", return_value=False):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "trust"])
        self.assertNotEqual(result.exit_code, 0)

    def test_interactive_prompts_when_no_files_are_given(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_text", return_value="/a.php, /b.php /c.php") as mock_ask, \
             patch("main.trust_ops.stage", return_value="a" * 64) as mock_stage, \
             patch("main.widgets.pause"):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "trust"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_ask.assert_called_once()
        mock_stage.assert_any_call("/a.php", "trust")
        mock_stage.assert_any_call("/b.php", "trust")
        mock_stage.assert_any_call("/c.php", "trust")

    def test_interactive_untrust_also_prompts_when_no_files_are_given(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_text", return_value="/a.php,/b.php"), \
             patch("main.trust_ops.stage", return_value="a" * 64) as mock_stage, \
             patch("main.widgets.pause"):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "untrust"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_stage.assert_any_call("/a.php", "untrust")
        mock_stage.assert_any_call("/b.php", "untrust")

    def test_interactive_cancel_on_file_prompt_aborts_without_staging_anything(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_text", return_value=None), \
             patch("main.trust_ops.stage") as mock_stage:
            result = CliRunner().invoke(cli.cli_group(), ["audit", "trust"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_stage.assert_not_called()

    def test_explicit_files_skip_the_prompt_even_when_interactive(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_text") as mock_ask, \
             patch("main.trust_ops.stage", return_value="a" * 64), \
             patch("main.widgets.pause"):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "trust", "/a.php"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_ask.assert_not_called()


class AuditPublishTrustCmdTest(unittest.TestCase):
    def _invoke(self, args=None, interactive=False, pending=None, password_input=None, url="http://trust.example"):
        args = args or ["audit", "publish-trust"]
        if url:
            args = args + ["--url", url]
        with patch("main._is_interactive", return_value=interactive), \
             patch("main.trust_ops.load_pending", return_value=pending if pending is not None else [{"x": 1}]), \
             patch("main.ask_password", return_value=password_input), \
             patch("main.trust_ops.publish", return_value={"ok": True, "aplicados": 1, "total": 1}) as mock_publish, \
             patch("main.widgets.pause") as mock_pause:
            result = CliRunner().invoke(cli.cli_group(), args)
        return result, mock_publish, mock_pause

    def test_does_nothing_when_there_is_no_pending_trust(self):
        result, mock_publish, _ = self._invoke(pending=[])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_publish.assert_not_called()

    def test_non_interactive_requires_a_password_file(self):
        result, mock_publish, _ = self._invoke(interactive=False)
        self.assertNotEqual(result.exit_code, 0)
        mock_publish.assert_not_called()

    def test_interactive_asks_for_the_password_and_publishes(self):
        result, mock_publish, _ = self._invoke(interactive=True, password_input="hunter2")
        self.assertEqual(result.exit_code, 0, result.output)
        mock_publish.assert_called_once_with("hunter2", url="http://trust.example", gerado_por=socket.gethostname())

    def test_uses_the_default_url_when_none_is_given(self):
        result, mock_publish, _ = self._invoke(interactive=True, password_input="hunter2", url=None)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_publish.assert_called_once_with(
            "hunter2", url=trust_ops.DEFAULT_URL, gerado_por=socket.gethostname(),
        )

    def test_interactive_cancel_on_password_prompt_aborts(self):
        result, mock_publish, _ = self._invoke(interactive=True, password_input=None)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_publish.assert_not_called()

    def test_uses_a_password_file_non_interactively(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("hunter2\n")
            password_file = f.name
        try:
            with patch("main._is_interactive", return_value=False), \
                 patch("main.trust_ops.load_pending", return_value=[{"x": 1}]), \
                 patch("main.trust_ops.publish", return_value={"ok": True, "aplicados": 1, "total": 1}) as mock_publish:
                result = CliRunner().invoke(cli.cli_group(), [
                    "audit", "publish-trust", "--url", "http://trust.example",
                    "--password-file", password_file,
                ])
            self.assertEqual(result.exit_code, 0, result.output)
            mock_publish.assert_called_once_with(
                "hunter2", url="http://trust.example", gerado_por=socket.gethostname(),
            )
        finally:
            os.remove(password_file)

    def test_clean_error_on_publish_failure(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.trust_ops.load_pending", return_value=[{"x": 1}]), \
             patch("main.ask_password", return_value="hunter2"), \
             patch("main.trust_ops.publish", side_effect=trust_ops.TrustError("servidor respondeu 401: nope")):
            result = CliRunner().invoke(cli.cli_group(), [
                "audit", "publish-trust", "--url", "http://trust.example",
            ])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("401", result.output)


class AuditCheckTrustCmdTest(unittest.TestCase):
    def test_reports_remote_and_local_counts(self):
        with patch("main.trust_ops.fetch_remote_trust", return_value=[{"a": 1}, {"a": 2}, {"a": 3}]) as mock_fetch, \
             patch("main.trust_ops.load_pending", return_value=[{"b": 1}]):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "check-trust", "--url", "http://trust.example"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_fetch.assert_called_once_with("http://trust.example")
        self.assertIn("3", result.output)
        self.assertIn("1", result.output)

    def test_uses_the_env_var_when_no_url_flag_is_given(self):
        with patch.dict(os.environ, {"PVX_AUDIT_TRUST_URL": "http://from-env.example"}), \
             patch("main.trust_ops.fetch_remote_trust", return_value=[]) as mock_fetch, \
             patch("main.trust_ops.load_pending", return_value=[]):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "check-trust"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_fetch.assert_called_once_with("http://from-env.example")

    def test_uses_the_default_url_when_nothing_else_is_configured(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("main.trust_ops.fetch_remote_trust", return_value=[]) as mock_fetch, \
             patch("main.trust_ops.load_pending", return_value=[{"b": 1}]):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "check-trust"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_fetch.assert_called_once_with(trust_ops.DEFAULT_URL)
        self.assertIn("1", result.output)

    def test_clear_wipes_everything_locally_without_touching_whats_published(self):
        with patch("main._is_interactive", return_value=False), \
             patch("main.trust_ops.remove_pending", return_value=2) as mock_remove, \
             patch("main.trust_ops.fetch_remote_trust", return_value=[]), \
             patch("main.trust_ops.load_pending", return_value=[]):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "check-trust", "--clear"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_remove.assert_called_once_with(None)
        self.assertIn("2 item(ns) removido(s)", result.output)

    def test_clear_with_files_only_removes_those(self):
        with patch("main._is_interactive", return_value=False), \
             patch("main.trust_ops.remove_pending", return_value=1) as mock_remove, \
             patch("main.trust_ops.fetch_remote_trust", return_value=[]), \
             patch("main.trust_ops.load_pending", return_value=[]):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "check-trust", "--clear", "/a.php"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_remove.assert_called_once_with(("/a.php",))

    def test_clear_asks_for_confirmation_interactively(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_confirm", return_value=False) as mock_confirm, \
             patch("main.trust_ops.remove_pending") as mock_remove, \
             patch("main.widgets.pause"):
            result = CliRunner().invoke(cli.cli_group(), ["audit", "check-trust", "--clear"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_confirm.assert_called_once()
        mock_remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
