import unittest
from unittest.mock import patch

from click.testing import CliRunner

from main import cli


def _invoke(args, is_root=True, is_tty=False):
    with patch("main.os.geteuid", return_value=0 if is_root else 1000), patch(
        "main._is_interactive", return_value=is_tty
    ):
        return CliRunner().invoke(cli.cli_group(), args)


class RootCheckTest(unittest.TestCase):
    def test_refuses_to_run_without_root(self):
        result = _invoke(["apply", "--quick", "--yes"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("root", result.output.lower())


class UnattendedSafetyGateTest(unittest.TestCase):
    @patch("main.apply_module.apply")
    def test_no_tty_and_no_flags_does_nothing(self, mock_apply):
        result = _invoke(["apply"], is_tty=False)
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_apply.assert_not_called()

    @patch("main.apply_module.apply")
    def test_flags_without_yes_and_without_tty_does_nothing(self, mock_apply):
        result = _invoke(["apply", "--lock-root"], is_tty=False)
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_apply.assert_not_called()

    @patch("main.apply_module.apply")
    def test_quick_and_yes_works_without_a_tty(self, mock_apply):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}

        result = _invoke(["apply", "--quick", "--yes"], is_tty=False)

        self.assertEqual(result.exit_code, 0, msg=result.output)
        plan = mock_apply.call_args.args[0]
        self.assertTrue(plan["lock_root"])
        self.assertTrue(plan["create_user"])
        self.assertTrue(plan["change_port"])

    @patch("main.apply_module.apply")
    def test_explicit_flags_pin_the_plan_without_a_tty(self, mock_apply):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}

        result = _invoke(
            ["apply", "--lock-root", "--no-create-user", "--no-change-port", "--yes"], is_tty=False
        )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        plan = mock_apply.call_args.args[0]
        self.assertTrue(plan["lock_root"])
        self.assertFalse(plan["create_user"])
        self.assertFalse(plan["change_port"])


class WizardModeQuestionTest(unittest.TestCase):
    @patch("main.apply_module.apply")
    @patch("main.ask_text")
    @patch("main.ask_confirm")
    @patch("main.ask_select", return_value="Usar os padrões da Phonevox (recomendado)")
    def test_choosing_defaults_skips_every_per_item_question(
        self, mock_select, mock_confirm, mock_text, mock_apply
    ):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}

        result = _invoke(["apply", "--yes"], is_tty=True)

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_confirm.assert_not_called()
        mock_text.assert_not_called()
        plan = mock_apply.call_args.args[0]
        self.assertTrue(plan["lock_root"])
        self.assertTrue(plan["create_user"])
        self.assertTrue(plan["change_port"])


class WizardCustomizeModeTest(unittest.TestCase):
    @patch("main.apply_module.apply")
    @patch("main.ask_text")
    @patch("main.ask_confirm")
    @patch("main.ask_select", return_value="Customizar cada opção")
    def test_asks_each_toggle_and_follow_up_values_in_order(
        self, mock_select, mock_confirm, mock_text, mock_apply
    ):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}
        # ordem: lock_root?, create_user?, change_port?, confirmação final
        mock_confirm.side_effect = [True, False, True, True]
        # ordem: senha do root, porta nova (create_user=False pula username/chave)
        mock_text.side_effect = ["custom-root-pass", "2222"]

        result = _invoke(["apply"], is_tty=True)

        self.assertEqual(result.exit_code, 0, msg=result.output)
        plan = mock_apply.call_args.args[0]
        self.assertTrue(plan["lock_root"])
        self.assertEqual(plan["root_password"], "custom-root-pass")
        self.assertFalse(plan["create_user"])
        self.assertTrue(plan["change_port"])
        self.assertEqual(plan["port"], "2222")

    @patch("main.apply_module.apply")
    @patch("main.ask_text")
    @patch("main.ask_confirm", return_value=True)
    @patch("main.ask_select")
    def test_flags_pin_every_item_and_skip_all_follow_up_questions(
        self, mock_select, mock_confirm, mock_text, mock_apply
    ):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}

        result = _invoke(
            ["apply", "--lock-root", "--root-password", "fixedpass", "--no-create-user", "--no-change-port"],
            is_tty=True,
        )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        # bug reportado ao vivo: com todas as flags relevantes já dadas (é assim que o
        # netinstall invoca isso como subprocesso, herdando um tty real), a pergunta
        # padrões/customizar não deve nem aparecer -- travava esperando resposta que
        # nunca vinha, já que quem chamou não é um humano no terminal.
        mock_select.assert_not_called()
        mock_text.assert_not_called()
        mock_confirm.assert_called_once()  # só a confirmação final
        plan = mock_apply.call_args.args[0]
        self.assertEqual(plan["root_password"], "fixedpass")

    @patch("main.apply_module.apply")
    @patch("main.ask_select")
    def test_all_flags_given_never_asks_the_quick_vs_customize_question_even_with_a_tty(
        self, mock_select, mock_apply
    ):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}

        result = _invoke(
            [
                "apply", "--yes", "--lock-root", "--root-password", "x", "--create-user",
                "--username", "phonevox", "--public-key", "ssh-rsa AAAA...", "--no-allow-password",
                "--change-port", "--port", "21122",
            ],
            is_tty=True,
        )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_select.assert_not_called()


class FinalConfirmationTest(unittest.TestCase):
    @patch("main.widgets.pause")
    @patch("main.widgets.message")
    @patch("main.apply_module.apply")
    @patch("main.ask_confirm", return_value=False)
    @patch("main.ask_select", return_value="Usar os padrões da Phonevox (recomendado)")
    def test_declining_final_confirmation_pauses_with_no_changes_message(
        self, mock_select, mock_confirm, mock_apply, mock_message, mock_pause
    ):
        result = _invoke(["apply"], is_tty=True)

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_apply.assert_not_called()
        mock_message.assert_called_once_with("nada foi alterado.")
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    @patch("main.widgets.message")
    @patch("main.apply_module.apply")
    @patch("main.ask_confirm")
    @patch("main.ask_select", return_value="Usar os padrões da Phonevox (recomendado)")
    def test_yes_flag_skips_final_confirmation_even_with_a_tty(
        self, mock_select, mock_confirm, mock_apply, mock_message, mock_pause
    ):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}

        result = _invoke(["apply", "--yes"], is_tty=True)

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_confirm.assert_not_called()
        mock_apply.assert_called_once()
        mock_pause.assert_called_once_with()


class ApplyOutcomeTest(unittest.TestCase):
    @patch("main.widgets.pause")
    @patch("main.widgets.message")
    @patch("main.apply_module.apply")
    def test_success_pauses_with_restart_reminder_when_interactive(
        self, mock_apply, mock_message, mock_pause
    ):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}

        result = _invoke(["apply", "--quick", "--yes"], is_tty=True)

        self.assertEqual(result.exit_code, 0, msg=result.output)
        shown = mock_message.call_args.args[0]
        self.assertIn("aplicado", shown)
        self.assertIn("reinicie", shown.lower())
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    @patch("main.widgets.message")
    @patch("main.apply_module.apply")
    def test_invalid_resulting_config_shows_rollback_message_and_pauses(
        self, mock_apply, mock_message, mock_pause
    ):
        mock_apply.return_value = {"applied": True, "config_valid": False, "record_path": "/x"}

        result = _invoke(["apply", "--quick", "--yes"], is_tty=True)

        self.assertEqual(result.exit_code, 0, msg=result.output)
        shown = mock_message.call_args.args[0]
        self.assertIn("revertido", shown.lower())
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    @patch("main.click.echo")
    @patch("main.apply_module.apply")
    def test_does_not_pause_when_run_without_a_tty(self, mock_apply, mock_echo, mock_pause):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}

        result = _invoke(["apply", "--quick", "--yes"], is_tty=False)

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_pause.assert_not_called()
        self.assertTrue(any("aplicado" in str(c) for c in mock_echo.call_args_list))


class InvalidValueTest(unittest.TestCase):
    @patch("main.apply_module.apply")
    def test_invalid_username_raises_a_clean_error_no_traceback(self, mock_apply):
        result = _invoke(
            ["apply", "--create-user", "--username", "Invalid User", "--yes"], is_tty=False
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("inválido", result.output)
        mock_apply.assert_not_called()


class LoggingTest(unittest.TestCase):
    @patch("main.SSHHardeningModule.get_logger")
    @patch("main.apply_module.apply")
    def test_logs_outcome_on_success(self, mock_apply, mock_get_logger):
        mock_apply.return_value = {"applied": True, "config_valid": True, "record_path": "/x"}
        _invoke(["apply", "--quick", "--yes"], is_tty=False)
        logger = mock_get_logger.return_value
        logger.info.assert_called_once()
        self.assertIn("aplicado", logger.info.call_args.args[0].lower())

    @patch("main.SSHHardeningModule.get_logger")
    @patch("main.apply_module.apply")
    def test_logs_error_on_invalid_plan(self, mock_apply, mock_get_logger):
        result = _invoke(
            ["apply", "--create-user", "--username", "Invalid User", "--yes"], is_tty=False
        )
        self.assertNotEqual(result.exit_code, 0)
        mock_get_logger.return_value.error.assert_called_once()
        mock_apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
