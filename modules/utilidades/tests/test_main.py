import unittest
from unittest.mock import patch

from click.testing import CliRunner

import audit_ops
from main import cli


def _invoke(args, is_tty=False):
    with patch("main._is_interactive", return_value=is_tty):
        return CliRunner().invoke(cli.cli_group(), args)


class ChecklistPhonevoxCommandTest(unittest.TestCase):
    @patch("main.issabel_detect.is_issabel", return_value=False)
    def test_refuses_outside_issabel(self, mock_is_issabel):
        result = _invoke(["checks-phonevox"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("issabel", result.output.lower())

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_shows_a_title_header(self, mock_is_issabel, mock_run_all):
        result = _invoke(["checks-phonevox"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("pvx > utilidades > checks-phonevox", result.output)

    @patch(
        "main.checklist_phonevox.run_all",
        return_value=[
            {
                "rule": "SSL", "description": "dias até o certificado mais próximo expirar",
                "value": "central.example.com expira em 60 dia(s)", "level": "ok",
            },
            {
                "rule": "Autobackup", "description": "backup automático agendado (cron)",
                "value": "não configurado", "level": "warn",
            },
        ],
    )
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_shows_a_table_with_a_row_per_item(self, mock_is_issabel, mock_run_all):
        with patch("main.widgets.table") as mock_table, patch("main.widgets.status_cell", side_effect=lambda lvl: lvl):
            _invoke(["checks-phonevox"])

        mock_table.assert_called_once()
        columns, rows = mock_table.call_args.args
        self.assertEqual(columns, ["Regra", "Descrição", "Valor", "Resumo"])
        self.assertEqual(rows, [
            ["SSL", "dias até o certificado mais próximo expirar", "central.example.com expira em 60 dia(s)", "ok"],
            ["Autobackup", "backup automático agendado (cron)", "não configurado", "warn"],
        ])

    @patch(
        "main.checklist_phonevox.run_all",
        return_value=[
            {"rule": "Zabbix", "description": "agent Zabbix configurado", "value": "hostname=vps-x", "level": "ok"},
            {
                "rule": "Zabbix (script de auditoria)", "description": "script de auditoria adicionado ao Zabbix",
                "value": "não adicionado", "level": "warn",
            },
        ],
    )
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_adjacent_items_of_the_same_section_repeat_the_section_name(self, mock_is_issabel, mock_run_all):
        with patch("main.widgets.table") as mock_table, patch("main.widgets.status_cell", side_effect=lambda lvl: lvl):
            _invoke(["checks-phonevox"])

        _, rows = mock_table.call_args.args
        self.assertEqual([row[0] for row in rows], ["Zabbix", "Zabbix (script de auditoria)"])

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause, mock_is_issabel, mock_run_all):
        _invoke(["checks-phonevox"], is_tty=True)
        mock_pause.assert_called_once_with()

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause, mock_is_issabel, mock_run_all):
        _invoke(["checks-phonevox"], is_tty=False)
        mock_pause.assert_not_called()


class InstallSngrepCommandTest(unittest.TestCase):
    @patch("main.sngrep_ops.is_installed", return_value=True)
    def test_skips_when_already_installed(self, mock_is_installed):
        with patch("main.widgets.message") as mock_message:
            result = _invoke(["install-sngrep"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_message.assert_called_once()
        self.assertIn("já está instalado", mock_message.call_args.args[0])

    @patch("main.sngrep_ops.install")
    @patch("main.sngrep_ops.detect_distro", return_value="rhel")
    @patch("main.sngrep_ops.is_installed", return_value=False)
    def test_installs_when_missing(self, mock_is_installed, mock_detect_distro, mock_install):
        with patch("main.widgets.success") as mock_success:
            result = _invoke(["install-sngrep"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_install.assert_called_once_with("rhel")
        mock_success.assert_called_once()

    @patch("main.sngrep_ops.detect_distro", return_value="rhel")
    @patch("main.sngrep_ops.is_installed", return_value=False)
    def test_logs_success_with_module_logger(self, mock_is_installed, mock_detect_distro):
        with patch("main.sngrep_ops.install"), patch("main.UtilidadesModule.get_logger") as mock_get_logger:
            _invoke(["install-sngrep"])
        mock_get_logger.return_value.info.assert_called_once()

    @patch("main.sngrep_ops.detect_distro", return_value=None)
    @patch("main.sngrep_ops.is_installed", return_value=False)
    def test_fails_for_unsupported_distro(self, mock_is_installed, mock_detect_distro):
        with patch("main.UtilidadesModule.get_logger") as mock_get_logger:
            result = _invoke(["install-sngrep"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        mock_get_logger.return_value.error.assert_called_once()

    @patch("main.sngrep_ops.detect_distro", return_value="rhel")
    @patch("main.sngrep_ops.is_installed", return_value=False)
    def test_fails_when_install_raises(self, mock_is_installed, mock_detect_distro):
        import sngrep_ops

        with patch("main.sngrep_ops.install", side_effect=sngrep_ops.SngrepError("deu ruim")), \
                patch("main.UtilidadesModule.get_logger") as mock_get_logger:
            result = _invoke(["install-sngrep"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        mock_get_logger.return_value.error.assert_called_once()

    @patch("main.sngrep_ops.is_installed", return_value=True)
    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause, mock_is_installed):
        _invoke(["install-sngrep"], is_tty=True)
        mock_pause.assert_called_once_with()

    @patch("main.sngrep_ops.is_installed", return_value=True)
    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause, mock_is_installed):
        _invoke(["install-sngrep"], is_tty=False)
        mock_pause.assert_not_called()

    def test_building_the_cli_group_alone_does_not_touch_the_logger(self):
        with patch("main.UtilidadesModule.get_logger") as mock_get_logger:
            cli.cli_group()
        mock_get_logger.assert_not_called()


def _invoke_audit(is_tty=False, is_root=True, **extra_patches):
    patches = {
        "main.os.geteuid": patch("main.os.geteuid", return_value=0 if is_root else 1000),
        "main.audit_ops.deploy": patch("main.audit_ops.deploy", return_value="/fake/audit.sh"),
        "main.subprocess.run": patch("main.subprocess.run"),
        "main.UtilidadesModule.get_logger": patch("main.UtilidadesModule.get_logger"),
    }
    patches.update(extra_patches)
    with patch("main._is_interactive", return_value=is_tty), \
            patches["main.os.geteuid"], \
            patches["main.audit_ops.deploy"] as mock_deploy, \
            patches["main.subprocess.run"] as mock_run, \
            patches["main.UtilidadesModule.get_logger"] as mock_get_logger:
        mock_run.return_value.returncode = 0
        result = CliRunner().invoke(cli.cli_group(), ["audit"])
    return result, mock_deploy, mock_run, mock_get_logger


class AuditCommandTest(unittest.TestCase):
    def test_refuses_without_root(self):
        result, *_ = _invoke_audit(is_root=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("root", result.output.lower())

    def test_deploys_the_script_and_runs_it_with_text_flag(self):
        result, mock_deploy, mock_run, _ = _invoke_audit()
        self.assertEqual(result.exit_code, 0, result.output)
        mock_deploy.assert_called_once_with(audit_ops.default_dest_dir())
        mock_run.assert_called_once_with(["/fake/audit.sh", "--text"])

    def test_logs_a_summary_with_the_module_logger(self):
        _, _, _, mock_get_logger = _invoke_audit()
        mock_get_logger.return_value.info.assert_called_once()

    def test_exit_code_mirrors_the_script_exit_code(self):
        with patch("main._is_interactive", return_value=False), \
                patch("main.os.geteuid", return_value=0), \
                patch("main.audit_ops.deploy", return_value="/fake/audit.sh"), \
                patch("main.subprocess.run") as mock_run, \
                patch("main.UtilidadesModule.get_logger"):
            mock_run.return_value.returncode = 1
            result = CliRunner().invoke(cli.cli_group(), ["audit"])
        self.assertEqual(result.exit_code, 1)

    def test_pauses_when_interactive(self):
        with patch("main.widgets.pause") as mock_pause:
            _invoke_audit(is_tty=True)
        mock_pause.assert_called_once_with()

    def test_does_not_pause_when_not_interactive(self):
        with patch("main.widgets.pause") as mock_pause:
            _invoke_audit(is_tty=False)
        mock_pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
