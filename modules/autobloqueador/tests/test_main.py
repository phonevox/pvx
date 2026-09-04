import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

import autobloqueador_ops as ops
from main import _read_password_file, cli

_KEY_FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False)
_KEY_FILE.write("crypted-key-de-teste")
_KEY_FILE.close()
CRYPTED_KEY_FILE = _KEY_FILE.name

BASE_CONFIG = {"url_base": "https://x.com", "type": "pabx", "code": "cliente-1", "crypted_key": "chave-secreta"}


class ReadPasswordFileTest(unittest.TestCase):
    def test_reads_and_strips_the_file_content(self):
        self.assertEqual(_read_password_file(CRYPTED_KEY_FILE), "crypted-key-de-teste")

    def test_none_when_no_path_given(self):
        self.assertIsNone(_read_password_file(None))


class InstallCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False, configs_exist=False, existing_config=None, start_timer_error=None):
        with patch("main.os.geteuid", return_value=0), \
             patch("main._is_interactive", return_value=is_tty), \
             patch("main.autobloqueador_ops.configs_exist", return_value=configs_exist), \
             patch("main.autobloqueador_ops.load_config", return_value=existing_config or BASE_CONFIG), \
             patch("main.autobloqueador_ops.save_config") as mock_save, \
             patch("main.autobloqueador_ops.install_timer") as mock_install_timer, \
             patch("main.autobloqueador_ops.start_timer", side_effect=start_timer_error) as mock_start_timer, \
             patch("main.autobloqueador_ops.check_and_apply", return_value={
                 "http_code": 200, "last_status": 200, "action": None, "warning": None,
             }), \
             patch("main.autobloqueador_ops.lock"), \
             patch("main.AutobloqueadorModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, {
                "save_config": mock_save, "install_timer": mock_install_timer, "start_timer": mock_start_timer,
            }

    def test_reuses_existing_config_without_asking_anything(self):
        result, mocks = self._invoke(["install"], configs_exist=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["save_config"].assert_not_called()
        mocks["install_timer"].assert_called_once()

    def test_defaults_url_base_when_not_given(self):
        # endpoint real, quase nunca muda -- auto-preenchido, nunca pergunta.
        result, mocks = self._invoke([
            "install", "--type", "pabx", "--code", "c1", "--crypted-key-file", CRYPTED_KEY_FILE,
        ])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["save_config"].assert_called_once_with(
            "https://auto-blocker.falevox.com.br", "pabx", "c1", "crypted-key-de-teste",
        )

    def test_headless_requires_crypted_key_file(self):
        result, mocks = self._invoke([
            "install", "--url-base", "x.com", "--type", "pabx", "--code", "c1",
        ])
        self.assertNotEqual(result.exit_code, 0)
        mocks["save_config"].assert_not_called()

    def test_explicit_empty_url_base_is_a_clean_error_not_a_crash(self):
        result, mocks = self._invoke([
            "install", "--url-base", "  ", "--type", "pabx", "--code", "c1",
            "--crypted-key-file", CRYPTED_KEY_FILE,
        ])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        mocks["save_config"].assert_not_called()

    def test_headless_rejects_invalid_type(self):
        result, mocks = self._invoke([
            "install", "--url-base", "x.com", "--type", "invalido", "--code", "c1",
            "--crypted-key-file", CRYPTED_KEY_FILE,
        ])
        self.assertNotEqual(result.exit_code, 0)
        mocks["save_config"].assert_not_called()

    def test_headless_happy_path_saves_config_and_installs_timer(self):
        result, mocks = self._invoke([
            "install", "--url-base", "x.com", "--type", "pabx", "--code", "c1",
            "--crypted-key-file", CRYPTED_KEY_FILE,
        ])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["save_config"].assert_called_once_with("https://x.com", "pabx", "c1", "crypted-key-de-teste")
        mocks["install_timer"].assert_called_once()

    def test_install_starts_the_timer_automatically(self):
        # pedido ao vivo: técnico não devia precisar rodar `pvx autobloqueador
        # start` manualmente depois do install.
        result, mocks = self._invoke([
            "install", "--url-base", "x.com", "--type", "pabx", "--code", "c1",
            "--crypted-key-file", CRYPTED_KEY_FILE,
        ])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["start_timer"].assert_called_once()

    def test_start_failure_after_a_successful_install_is_not_blamed_on_install(self):
        # achado na revisão: install_timer() pode ter funcionado direitinho
        # (units gravadas) e só o start_timer() falhar (ex.: hiccup do
        # systemd/dbus) -- a mensagem não pode dizer "falha ao instalar",
        # senão o técnico tenta reinstalar em vez de só rodar `start` de novo.
        result, mocks = self._invoke(
            ["install", "--url-base", "x.com", "--type", "pabx", "--code", "c1",
             "--crypted-key-file", CRYPTED_KEY_FILE],
            start_timer_error=ops.AutobloqueadorError("dbus indisponível"),
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("falha ao instalar", result.output.lower())
        self.assertIn("falha ao iniciar", result.output.lower())
        mocks["install_timer"].assert_called_once()

    def test_interactive_prompts_for_missing_fields_and_the_pasted_key(self):
        with patch("main.ask_text", return_value="c1"), \
             patch("main.ask_select", return_value="PABX (Asterisk)"), \
             patch("main.ask_password", return_value="chave-colada"):
            result, mocks = self._invoke(["install"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["save_config"].assert_called_once_with(
            "https://auto-blocker.falevox.com.br", "pabx", "c1", "chave-colada",
        )

    def test_code_prompt_for_pabx_asks_about_contract_id(self):
        with patch("main.ask_text", return_value="c1") as mock_text, \
             patch("main.ask_select", return_value="PABX (Asterisk)"), \
             patch("main.ask_password", return_value="chave"):
            self._invoke(["install"], is_tty=True)
        prompt = mock_text.call_args.args[0]
        self.assertIn("ID do contrato a ser monitorado", prompt)

    def test_code_prompt_for_opa_asks_about_opasuite_key(self):
        with patch("main.ask_text", return_value="c1") as mock_text, \
             patch("main.ask_select", return_value="OPA (PM2)"), \
             patch("main.ask_password", return_value="chave"):
            self._invoke(["install"], is_tty=True)
        prompt = mock_text.call_args.args[0]
        self.assertIn("Chave do Opa!Suite a ser monitorado", prompt)

    def test_escaping_the_key_paste_prompt_aborts_cleanly(self):
        with patch("main.ask_text", return_value="c1"), \
             patch("main.ask_select", return_value="PABX (Asterisk)"), \
             patch("main.ask_password", return_value=None):
            result, mocks = self._invoke(["install"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["save_config"].assert_not_called()
        mocks["install_timer"].assert_not_called()

    def test_requires_root(self):
        with patch("main.os.geteuid", return_value=1000):
            result = CliRunner().invoke(cli.cli_group(), ["install"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("root", result.output.lower())

    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause):
        result, _ = self._invoke(["install"], is_tty=True, configs_exist=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause):
        result, _ = self._invoke([
            "install", "--url-base", "x.com", "--type", "pabx", "--code", "c1",
            "--crypted-key-file", CRYPTED_KEY_FILE,
        ])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_not_called()


class ReconfigCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False, existing=BASE_CONFIG):
        with patch("main.os.geteuid", return_value=0), \
             patch("main._is_interactive", return_value=is_tty), \
             patch("main.autobloqueador_ops.load_config", return_value=existing), \
             patch("main.autobloqueador_ops.save_config") as mock_save, \
             patch("main.autobloqueador_ops.check_and_apply", return_value={
                 "http_code": 200, "last_status": 200, "action": None, "warning": None,
             }), \
             patch("main.autobloqueador_ops.lock"), \
             patch("main.AutobloqueadorModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, mock_save

    def test_requires_an_existing_install(self):
        result, mock_save = self._invoke(
            ["reconfig", "--type", "pabx", "--code", "c1", "--crypted-key-file", CRYPTED_KEY_FILE],
            existing=None,
        )
        self.assertNotEqual(result.exit_code, 0)
        mock_save.assert_not_called()

    def test_reuses_the_saved_url_base(self):
        result, mock_save = self._invoke([
            "reconfig", "--type", "opa", "--code", "c2", "--crypted-key-file", CRYPTED_KEY_FILE,
        ])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_save.assert_called_once_with("https://x.com", "opa", "c2", "crypted-key-de-teste")


class RunCommandTest(unittest.TestCase):
    def _invoke(self, args, config=BASE_CONFIG, check_result=None):
        check_result = check_result or {"http_code": 200, "last_status": 200, "action": None, "warning": None}
        with patch("main.os.geteuid", return_value=0), \
             patch("main.autobloqueador_ops.load_config", return_value=config), \
             patch("main.autobloqueador_ops.lock"), \
             patch("main.autobloqueador_ops.check_and_apply", return_value=check_result) as mock_check, \
             patch("main.autobloqueador_ops.log"), \
             patch("main.AutobloqueadorModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, mock_check

    def test_requires_existing_config(self):
        result, mock_check = self._invoke(["run"], config=None)
        self.assertNotEqual(result.exit_code, 0)
        mock_check.assert_not_called()

    def test_calls_check_and_apply_with_saved_credentials(self):
        result, mock_check = self._invoke(["run"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_check.assert_called_once_with("https://x.com", "pabx", "chave-secreta", dry_run=False)

    def test_dry_run_flag_is_forwarded(self):
        result, mock_check = self._invoke(["run", "--dry-run"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_check.assert_called_once_with("https://x.com", "pabx", "chave-secreta", dry_run=True)

    def test_autobloqueador_error_becomes_a_clean_click_exception(self):
        with patch("main.os.geteuid", return_value=0), \
             patch("main.autobloqueador_ops.load_config", return_value=BASE_CONFIG), \
             patch("main.autobloqueador_ops.lock", side_effect=ops.AutobloqueadorError("timeout esperando lock")), \
             patch("main.autobloqueador_ops.log"), \
             patch("main.AutobloqueadorModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), ["run"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("timeout", result.output.lower())


class StatusCommandTest(unittest.TestCase):
    def test_reports_not_configured(self):
        with patch("main.autobloqueador_ops.load_config", return_value=None):
            result = CliRunner().invoke(cli.cli_group(), ["status"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("não configurado", result.output.lower())

    def test_shows_config_and_never_the_full_key(self):
        long_key = "a" * 100
        with patch("main.autobloqueador_ops.load_config", return_value={**BASE_CONFIG, "crypted_key": long_key}), \
             patch("main.autobloqueador_ops.last_response", return_value=None), \
             patch("main.autobloqueador_ops.timer_status", return_value=None):
            result = CliRunner().invoke(cli.cli_group(), ["status"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("cliente-1", result.output)
        self.assertNotIn(long_key, result.output)


class LogsCommandTest(unittest.TestCase):
    def test_shows_the_tail_of_the_log(self):
        with patch("main.autobloqueador_ops.tail_log", return_value="linha1\nlinha2\n") as mock_tail:
            result = CliRunner().invoke(cli.cli_group(), ["logs"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("linha1", result.output)
        mock_tail.assert_called_once_with(lines=100)

    def test_lines_option_is_forwarded(self):
        with patch("main.autobloqueador_ops.tail_log", return_value="") as mock_tail:
            CliRunner().invoke(cli.cli_group(), ["logs", "--lines", "20"])
        mock_tail.assert_called_once_with(lines=20)


class StartStopCommandTest(unittest.TestCase):
    def test_start_calls_start_timer(self):
        with patch("main.os.geteuid", return_value=0), \
             patch("main.autobloqueador_ops.start_timer") as mock_start, \
             patch("main.AutobloqueadorModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), ["start"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_start.assert_called_once_with()

    def test_stop_calls_stop_timer(self):
        with patch("main.os.geteuid", return_value=0), \
             patch("main.autobloqueador_ops.stop_timer") as mock_stop, \
             patch("main.AutobloqueadorModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), ["stop"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_stop.assert_called_once_with()


class RemoveCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False, configs_exist=True):
        with patch("main.os.geteuid", return_value=0), \
             patch("main._is_interactive", return_value=is_tty), \
             patch("main.autobloqueador_ops.remove_timer") as mock_remove_timer, \
             patch("main.autobloqueador_ops.configs_exist", return_value=configs_exist), \
             patch("main.autobloqueador_ops.remove_config") as mock_remove_config, \
             patch("main.AutobloqueadorModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, {"remove_timer": mock_remove_timer, "remove_config": mock_remove_config}

    def test_always_removes_the_timer(self):
        result, mocks = self._invoke(["remove"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["remove_timer"].assert_called_once_with()

    def test_keeps_config_by_default_headless(self):
        result, mocks = self._invoke(["remove"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["remove_config"].assert_not_called()

    def test_delete_config_flag_removes_it_headless(self):
        result, mocks = self._invoke(["remove", "--delete-config"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["remove_config"].assert_called_once_with()

    def test_interactive_asks_before_deleting_config(self):
        with patch("main.ask_confirm", return_value=True) as mock_confirm:
            result, mocks = self._invoke(["remove"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["remove_config"].assert_called_once_with()
        mock_confirm.assert_called_once()

    def test_declining_the_interactive_confirmation_keeps_config(self):
        with patch("main.ask_confirm", return_value=False):
            result, mocks = self._invoke(["remove"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["remove_config"].assert_not_called()

    def test_never_asks_when_there_is_no_config_to_delete(self):
        with patch("main.ask_confirm") as mock_confirm:
            result, mocks = self._invoke(["remove"], is_tty=True, configs_exist=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_confirm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
