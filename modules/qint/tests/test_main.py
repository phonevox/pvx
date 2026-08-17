import unittest
from unittest.mock import patch

from click.testing import CliRunner

from main import cli


def _invoke(args, is_root=True):
    with patch("main.os.geteuid", return_value=0 if is_root else 1000):
        return CliRunner().invoke(cli.cli_group(), args)


class PrepareRootCheckTest(unittest.TestCase):
    def test_refuses_to_run_without_root(self):
        result = _invoke(["prepare", "ixcsoft"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("root", result.output.lower())


class PrepareTypeTest(unittest.TestCase):
    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    def test_rejects_invalid_tipo(self, mock_load, mock_save):
        result = _invoke(["prepare", "algumacoisa"])
        self.assertNotEqual(result.exit_code, 0)
        mock_save.assert_not_called()

    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    def test_ixc_alias_resolves_to_ixcsoft(self, mock_load, mock_save):
        _invoke(["prepare", "ixc"])
        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["type"], "ixcsoft")


class PrepareFieldsTest(unittest.TestCase):
    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    def test_starting_fresh_saves_type_and_given_fields(self, mock_load, mock_save):
        _invoke(["prepare", "ixcsoft", "--sftp", "root@10.0.0.1:2222", "--url", "https://erp.example.com"])
        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["sftp_user"], "root")
        self.assertEqual(saved["sftp_host"], "10.0.0.1")
        self.assertEqual(saved["sftp_port"], 2222)
        self.assertEqual(saved["erp_url"], "https://erp.example.com")

    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value={"type": "ixcsoft", "erp_url": "https://old.example.com"})
    def test_omitted_flag_preserves_existing_staged_value(self, mock_load, mock_save):
        _invoke(["prepare", "ixcsoft", "--asterisk-ip", "10.0.0.9"])
        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["erp_url"], "https://old.example.com")
        self.assertEqual(saved["asterisk_ip"], "10.0.0.9")

    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value={"type": "sgp", "erp_url": "https://old.example.com"})
    def test_switching_type_discards_previous_staged_config(self, mock_load, mock_save):
        _invoke(["prepare", "ixcsoft", "--asterisk-ip", "10.0.0.9"])
        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["type"], "ixcsoft")
        self.assertNotIn("erp_url", saved)

    @patch("main.staged_config.save")
    @patch(
        "main.staged_config.load",
        return_value={"type": "ixcsoft", "fila_geral": "600", "fila_comercial": "601"},
    )
    def test_csv4_empty_segment_preserves_existing_value(self, mock_load, mock_save):
        _invoke(["prepare", "ixcsoft", "--filas", ",,602,603"])
        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["fila_geral"], "600")
        self.assertEqual(saved["fila_comercial"], "601")
        self.assertEqual(saved["fila_suporte"], "602")
        self.assertEqual(saved["fila_financeiro"], "603")

    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    def test_invalid_sftp_flag_raises_clean_error(self, mock_load, mock_save):
        result = _invoke(["prepare", "ixcsoft", "--sftp", "sem-arroba"])
        self.assertNotEqual(result.exit_code, 0)
        mock_save.assert_not_called()

    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    def test_invalid_url_flag_raises_clean_error(self, mock_load, mock_save):
        result = _invoke(["prepare", "ixcsoft", "--url", "erp.example.com/sem-protocolo"])
        self.assertNotEqual(result.exit_code, 0)
        mock_save.assert_not_called()


class StatusTest(unittest.TestCase):
    @patch("main.staged_config.load", return_value=None)
    def test_shows_message_when_nothing_staged(self, mock_load):
        result = _invoke(["status"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("prepare", result.output.lower())

    @patch(
        "main.staged_config.load",
        return_value={"type": "ixcsoft", "token": "supersecreto", "asterisk_ip": "10.0.0.1"},
    )
    def test_shows_staged_fields_and_masks_token(self, mock_load):
        result = _invoke(["status"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("ixcsoft", result.output)
        self.assertIn("10.0.0.1", result.output)
        self.assertNotIn("supersecreto", result.output)


def _invoke_interactive(args, is_root=True):
    with patch("main.os.geteuid", return_value=0 if is_root else 1000), patch(
        "main._is_interactive", return_value=True
    ):
        return CliRunner().invoke(cli.cli_group(), args)


class SetupRequiresTtyTest(unittest.TestCase):
    def test_refuses_without_a_tty(self):
        with patch("main.os.geteuid", return_value=0), patch("main._is_interactive", return_value=False):
            result = CliRunner().invoke(cli.cli_group(), ["setup"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("prepare", result.output.lower())


class SetupTypeQuestionTest(unittest.TestCase):
    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    @patch("main.reachability.is_reachable", return_value=True)
    @patch("main.ask_confirm", return_value=True)
    @patch("main.ask_text")
    @patch("main.ask_select", return_value="IXCSoft")
    def test_asks_type_when_not_given_as_argument(
        self, mock_select, mock_text, mock_confirm, mock_reachable, mock_load, mock_save
    ):
        mock_text.side_effect = ["root@10.0.0.1"] + ["https://x.example.com"] * 30
        _invoke_interactive(["setup"])
        mock_select.assert_called_once()
        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["type"], "ixcsoft")

    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    @patch("main.reachability.is_reachable", return_value=True)
    @patch("main.ask_confirm", return_value=True)
    @patch("main.ask_text")
    @patch("main.ask_select")
    def test_skips_type_question_when_given_as_argument(
        self, mock_select, mock_text, mock_confirm, mock_reachable, mock_load, mock_save
    ):
        mock_text.side_effect = ["root@10.0.0.1"] + ["https://x.example.com"] * 30
        _invoke_interactive(["setup", "ixcsoft"])
        mock_select.assert_not_called()


class SetupSftpReachabilityTest(unittest.TestCase):
    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    @patch("main.ask_confirm", return_value=True)
    @patch("main.ask_text")
    @patch("main.reachability.is_reachable")
    def test_unreachable_host_reprompts_but_resubmitting_same_value_proceeds(
        self, mock_reachable, mock_text, mock_confirm, mock_load, mock_save
    ):
        mock_reachable.return_value = False
        mock_text.side_effect = ["root@10.0.0.1", "root@10.0.0.1"] + ["https://x.example.com"] * 30

        _invoke_interactive(["setup", "ixcsoft"])

        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["sftp_host"], "10.0.0.1")
        self.assertEqual(mock_reachable.call_count, 2)


class SetupUrlValidationTest(unittest.TestCase):
    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    @patch("main.reachability.is_reachable", return_value=True)
    @patch("main.ask_confirm", return_value=True)
    @patch("main.ask_text")
    def test_reprompts_until_a_valid_url_is_given(self, mock_text, mock_confirm, mock_reachable, mock_load, mock_save):
        mock_text.side_effect = (
            ["root@10.0.0.1"]  # sftp
            + ["600", "601", "602", "603"]  # filas
            + ["10"]  # timecondition
            + ["10.0.0.2"]  # asterisk ip
            + ["sem-protocolo", "https://erp.example.com"]  # url (1a inválida)
            + ["https://x.example.com"] * 20
        )
        _invoke_interactive(["setup", "ixcsoft"])
        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["erp_url"], "https://erp.example.com")


class SetupTokenTest(unittest.TestCase):
    @patch("main.staged_config.save")
    @patch(
        "main.staged_config.load",
        return_value={"type": "ixcsoft", "token": "token-antigo"},
    )
    @patch("main.reachability.is_reachable", return_value=True)
    @patch("main.ask_confirm", return_value=True)
    @patch("main.ask_text")
    def test_empty_token_answer_keeps_existing_value(self, mock_text, mock_confirm, mock_reachable, mock_load, mock_save):
        mock_text.side_effect = (
            ["root@10.0.0.1"] + ["600", "601", "602", "603"] + ["10"] + ["10.0.0.2"]
            + ["https://erp.example.com"] + [""] + ["https://x.example.com"] * 20
        )
        _invoke_interactive(["setup", "ixcsoft"])
        saved = mock_save.call_args.args[1]
        self.assertEqual(saved["token"], "token-antigo")


class SetupSummaryConfirmationTest(unittest.TestCase):
    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    @patch("main.reachability.is_reachable", return_value=True)
    @patch("main.ask_confirm", return_value=False)
    @patch("main.ask_text")
    def test_declining_summary_discards_without_saving(self, mock_text, mock_confirm, mock_reachable, mock_load, mock_save):
        mock_text.side_effect = ["root@10.0.0.1"] + ["https://x.example.com"] * 30
        _invoke_interactive(["setup", "ixcsoft"])
        mock_save.assert_not_called()

    @patch("main.staged_config.save")
    @patch("main.staged_config.load", return_value=None)
    @patch("main.reachability.is_reachable", return_value=True)
    @patch("main.ask_confirm", return_value=True)
    @patch("main.ask_text")
    def test_full_ixcsoft_run_ends_up_complete(self, mock_text, mock_confirm, mock_reachable, mock_load, mock_save):
        mock_text.side_effect = (
            ["root@10.0.0.1"]  # sftp
            + ["600", "601", "602", "603"]  # filas
            + ["10"]  # timecondition
            + ["10.0.0.2"]  # asterisk ip
            + ["https://erp.example.com"]  # url
            + ["tok"]  # token
            + ["1"]  # filial
            + ["10", "20", "30", "40"]  # departamentos
            + ["11", "21", "31", "41"]  # assuntos
        )
        _invoke_interactive(["setup", "ixcsoft"])

        saved = mock_save.call_args.args[1]
        from defaults import missing_fields

        self.assertEqual(missing_fields(saved), [])
        self.assertEqual(saved["id_departamento_comercial"], "20")
        self.assertEqual(saved["id_assunto_financeiro"], "41")


_COMPLETE_STAGED = {
    "type": "ixcsoft",
    "sftp_user": "root", "sftp_host": "10.0.0.1", "sftp_port": 22,
    "sftp_remote_path": "/sfiles/qint/integracoes", "sftp_versao": "recent",
    "erp_url": "https://erp.example.com", "token": "tok",
    "id_timecondition_exitpoint": "10",
    "fila_geral": "600", "fila_comercial": "601", "fila_suporte": "602", "fila_financeiro": "603",
    "asterisk_ip": "10.0.0.2",
    "id_filial": "1",
    "id_departamento_geral": "1", "id_departamento_comercial": "2",
    "id_departamento_suporte": "3", "id_departamento_financeiro": "4",
    "id_assunto_geral": "1", "id_assunto_comercial": "2",
    "id_assunto_suporte": "3", "id_assunto_financeiro": "4",
}


class ApplyCommandTest(unittest.TestCase):
    def test_requires_root(self):
        result = _invoke(["apply"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("root", result.output.lower())

    @patch("main.staged_config.load", return_value=None)
    def test_requires_a_staged_config(self, mock_load):
        result = _invoke(["apply"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("prepare", result.output.lower())

    @patch("main.staged_config.load", return_value={"type": "ixcsoft"})
    def test_refuses_when_required_fields_are_missing(self, mock_load):
        result = _invoke(["apply"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("sftp_user", result.output)

    @patch("main.apply_module.apply")
    @patch("main.ask_confirm", return_value=False)
    @patch("main.staged_config.load", return_value=_COMPLETE_STAGED)
    def test_declining_confirmation_does_not_apply(self, mock_load, mock_confirm, mock_apply):
        result = _invoke(["apply"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_apply.assert_not_called()

    @patch("main.apply_module.apply")
    @patch("main.deploy.compute_conflicts", return_value=["php"])
    @patch("main.ask_confirm", side_effect=[True, False])  # confirma aplicar, recusa sobrescrever php
    @patch("main.staged_config.load", return_value=_COMPLETE_STAGED)
    def test_declining_a_directory_overwrite_aborts_the_whole_apply(
        self, mock_load, mock_confirm, mock_conflicts, mock_apply
    ):
        result = _invoke(["apply"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_apply.assert_not_called()

    @patch("main.apply_module.apply")
    @patch("main.deploy.compute_conflicts", return_value=[])
    @patch("main.ask_confirm", return_value=True)
    @patch("main.staged_config.load", return_value=_COMPLETE_STAGED)
    def test_confirmed_apply_calls_apply_module_and_prints_manual_reminders(
        self, mock_load, mock_confirm, mock_conflicts, mock_apply
    ):
        mock_apply.return_value = {"applied": True, "reloaded": True}

        result = _invoke(["apply"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_apply.assert_called_once()
        applied_config = mock_apply.call_args.args[0]
        self.assertEqual(applied_config["type"], "ixcsoft")
        self.assertIn("inicio-ixcsoft", result.output)
        self.assertIn("Time Condition", result.output)

    @patch("main.apply_module.apply")
    @patch("main.deploy.compute_conflicts", return_value=[])
    @patch("main.staged_config.load", return_value=_COMPLETE_STAGED)
    def test_yes_flag_skips_confirmation(self, mock_load, mock_conflicts, mock_apply):
        mock_apply.return_value = {"applied": True, "reloaded": True}
        result = _invoke(["apply", "--yes"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_apply.assert_called_once()

    @patch("main.apply_module.apply")
    @patch("main.deploy.compute_conflicts", return_value=[])
    @patch("main.ask_confirm", return_value=True)
    @patch("main.staged_config.load", return_value=_COMPLETE_STAGED)
    def test_reports_when_dialplan_reload_was_skipped(self, mock_load, mock_confirm, mock_conflicts, mock_apply):
        mock_apply.return_value = {"applied": True, "reloaded": False}
        result = _invoke(["apply"])
        self.assertIn("reload", result.output.lower())


if __name__ == "__main__":
    unittest.main()
