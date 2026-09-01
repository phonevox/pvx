import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

import pbackup_ops
import uoe_client
from main import _read_password_file, _resolve_script, cli

# conteúdo nunca é checado de verdade (uoe_client.login/register são mockados em
# todo teste) -- só precisa ser um arquivo real e legível pro _read_password_file.
_PW_FILE = tempfile.NamedTemporaryFile(mode="w", suffix=".pw", delete=False)
_PW_FILE.write("rootpw")
_PW_FILE.close()
PASSWORD_FILE = _PW_FILE.name

def _without_flag(args, flag):
    # remove só o par <flag> <valor>, não qualquer outro uso do mesmo valor
    # (ex.: PASSWORD_FILE reaparece em --admin-password-file também).
    result = list(args)
    if flag in result:
        i = result.index(flag)
        del result[i : i + 2]
    return result


BASE_SETUP_ARGS = [
    "setup",
    "--root-path", "clientes/1-2-empresa",
    "--username", "empresa",
    "--password-file", PASSWORD_FILE,
    "--admin-password-file", PASSWORD_FILE,
    "--script", "issabel",
    "--issabel-config-only",
    "--cron-minute", "25",
    "--cron-hour", "2",
]


class ReadPasswordFileTest(unittest.TestCase):
    def test_reads_and_strips_the_file_content(self):
        self.assertEqual(_read_password_file(PASSWORD_FILE), "rootpw")

    def test_none_when_no_path_given(self):
        self.assertIsNone(_read_password_file(None))


class ResolveScriptTest(unittest.TestCase):
    # pedido ao vivo: rótulos "IssabelPBX"/"MagnusBilling"/"Definir script..."
    # (não mais "Issabel (config + gravações)"/"Comando customizado"), e
    # escolher IssabelPBX abre um submenu -- só config (padrão) ou +gravações.
    def test_headless_with_issabel_flag_defaults_to_config_only(self):
        script, custom, recordings = _resolve_script("issabel", None, None, interactive=False)
        self.assertEqual(script, "issabel")
        self.assertFalse(recordings)

    def test_headless_respects_explicit_recordings_flag(self):
        script, custom, recordings = _resolve_script("issabel", None, True, interactive=False)
        self.assertTrue(recordings)

    def test_magnus_never_asks_the_issabel_submenu(self):
        with patch("main.ask_select") as mock_select:
            script, custom, recordings = _resolve_script("magnus", None, None, interactive=True)
        self.assertEqual(script, "magnus")
        self.assertIsNone(recordings)
        mock_select.assert_not_called()

    def test_interactive_offers_the_new_top_level_labels(self):
        with patch("main.ask_select", return_value=None) as mock_select:
            _resolve_script(None, None, None, interactive=True)
        choices = mock_select.call_args.args[1]
        self.assertEqual(choices, ["IssabelPBX", "MagnusBilling", "Definir script..."])

    def test_choosing_issabel_opens_the_config_vs_recordings_submenu(self):
        with patch(
            "main.ask_select",
            side_effect=["IssabelPBX", "Somente configurações (padrão)"],
        ) as mock_select:
            script, custom, recordings = _resolve_script(None, None, None, interactive=True)
        self.assertEqual(script, "issabel")
        self.assertFalse(recordings)
        submenu_choices = mock_select.call_args_list[1].args[1]
        self.assertEqual(submenu_choices, ["Somente configurações (padrão)", "Configurações e gravações"])

    def test_choosing_recordings_in_the_submenu(self):
        with patch(
            "main.ask_select",
            side_effect=["IssabelPBX", "Configurações e gravações"],
        ):
            script, custom, recordings = _resolve_script(None, None, None, interactive=True)
        self.assertTrue(recordings)

    def test_escaping_the_issabel_submenu_aborts_cleanly(self):
        with patch("main.ask_select", side_effect=["IssabelPBX", None]):
            script, custom, recordings = _resolve_script(None, None, None, interactive=True)
        self.assertIsNone(script)


class SetupCommandTest(unittest.TestCase):
    def _invoke(self, args, is_tty=False, pbackup_root="/root/pbackup", pbackup_version=(1, 3, 1),
                register_error=None, login_side_effect=None):
        with patch("main._is_interactive", return_value=is_tty), \
             patch("main.pbackup_ops.find_install", return_value=pbackup_root), \
             patch("main.pbackup_ops.installed_version", return_value=pbackup_version), \
             patch(
                 "main.pbackup_ops.is_supported",
                 return_value=pbackup_version is not None and pbackup_version >= pbackup_ops.MIN_VERSION,
             ), \
             patch("main.pbackup_ops.fresh_install", return_value="/opt/pbackup") as mock_fresh, \
             patch("main.pbackup_ops.update_in_place") as mock_update, \
             patch("main.crontab.read_crontab", return_value=[]), \
             patch("main.crontab.find_legacy_candidates", return_value=[]), \
             patch("main.crontab.write_crontab") as mock_write_crontab, \
             patch("main.uoe_client.login", side_effect=login_side_effect or (lambda u, p: f"token-{u}")), \
             patch("main.uoe_client.register", side_effect=register_error), \
             patch("main.state.save") as mock_state_save, \
             patch("main.UOEModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, {
                "fresh_install": mock_fresh, "update_in_place": mock_update,
                "write_crontab": mock_write_crontab, "state_save": mock_state_save,
            }

    def test_happy_path_writes_the_managed_cron_entry_and_state(self):
        result, mocks = self._invoke(BASE_SETUP_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["fresh_install"].assert_not_called()
        mocks["update_in_place"].assert_not_called()

        cron_lines = mocks["write_crontab"].call_args.args[0]
        self.assertIn("# gerenciado pelo pvx uoe", cron_lines[-2])
        self.assertIn("25 2 * * *", cron_lines[-1])
        self.assertIn("issabel.sh", cron_lines[-1])
        self.assertIn("token-empresa", cron_lines[-1])

        saved = mocks["state_save"].call_args.args[1]
        self.assertEqual(saved["username"], "empresa")
        self.assertEqual(saved["token"], "token-empresa")
        self.assertEqual(saved["script"], "issabel")

    def test_installs_pbackup_when_missing(self):
        result, mocks = self._invoke(BASE_SETUP_ARGS, pbackup_root=None, pbackup_version=None)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["fresh_install"].assert_called_once()
        mocks["update_in_place"].assert_not_called()

    def test_updates_pbackup_when_below_minimum_version(self):
        result, mocks = self._invoke(BASE_SETUP_ARGS, pbackup_version=(1, 0, 0))
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["update_in_place"].assert_called_once_with("/root/pbackup")
        mocks["fresh_install"].assert_not_called()

    def test_register_failure_is_fatal_by_default(self):
        result, _ = self._invoke(
            BASE_SETUP_ARGS, register_error=uoe_client.UOEError(500, "Internal Server Error"),
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)

    def test_register_failure_offers_a_skip_to_login_when_interactive(self):
        with patch("main.ask_confirm", return_value=True):
            result, mocks = self._invoke(
                BASE_SETUP_ARGS, is_tty=True,
                register_error=uoe_client.UOEError(500, "Internal Server Error"),
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["state_save"].assert_called_once()

    def test_skip_register_flag_never_calls_register(self):
        with patch("main.uoe_client.register") as mock_register:
            result, _ = self._invoke(BASE_SETUP_ARGS + ["--skip-register"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_register.assert_not_called()

    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause):
        result, _ = self._invoke(BASE_SETUP_ARGS, is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause):
        result, _ = self._invoke(BASE_SETUP_ARGS, is_tty=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_not_called()

    def test_requires_root_path_pieces_or_flag_when_headless(self):
        result, _ = self._invoke(["setup", "--username", "empresa", "--admin-password-file", PASSWORD_FILE])
        self.assertNotEqual(result.exit_code, 0)

    def test_requires_password_file_when_headless(self):
        # nunca deriva/hardcoda a senha do cliente -- headless precisa do arquivo.
        args = _without_flag(BASE_SETUP_ARGS, "--password-file")
        result, mocks = self._invoke(args)
        self.assertNotEqual(result.exit_code, 0)
        mocks["state_save"].assert_not_called()

    def test_interactive_prompts_for_the_password_with_no_default(self):
        with patch("main.ask_password", side_effect=["senha-digitada-pelo-tecnico"]) as mock_password:
            args = _without_flag(BASE_SETUP_ARGS, "--password-file")
            result, mocks = self._invoke(args, is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        prompt = mock_password.call_args_list[0].args[0]
        self.assertIn("empresa", prompt)

    def test_root_password_prompt_is_unmistakable(self):
        with patch("main.ask_password", return_value="senha-digitada") as mock_password:
            args = _without_flag(BASE_SETUP_ARGS, "--admin-password-file")
            self._invoke(args, is_tty=True)
        prompt = mock_password.call_args_list[-1].args[0]
        self.assertIn("ROOT", prompt)
        self.assertIn("NÃO é a senha do cliente", prompt)


class RelonginCommandTest(unittest.TestCase):
    SAVED = {
        "username": "empresa", "token": "old-token", "root_path": "clientes/1-2-empresa",
        "script": "issabel", "custom_command": None, "pbackup_root": "/root/pbackup",
        "cron_minute": "25", "cron_hour": "2",
    }

    _UNSET = object()

    def _invoke(self, args, is_tty=False, saved=_UNSET):
        if saved is self._UNSET:
            saved = self.SAVED
        with patch("main._is_interactive", return_value=is_tty), \
             patch("main.state.load", return_value=saved), \
             patch("main.state.save") as mock_save, \
             patch("main.crontab.read_crontab", return_value=[]), \
             patch("main.crontab.write_crontab") as mock_write, \
             patch("main.uoe_client.login", return_value="new-token"), \
             patch("main.UOEModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, {"save": mock_save, "write_crontab": mock_write}

    def test_requires_existing_setup(self):
        result, _ = self._invoke(["relogin", "--password-file", PASSWORD_FILE], saved=None)
        self.assertNotEqual(result.exit_code, 0)

    def test_updates_token_in_state_and_cron(self):
        result, mocks = self._invoke(["relogin", "--password-file", PASSWORD_FILE])
        self.assertEqual(result.exit_code, 0, result.output)
        saved_arg = mocks["save"].call_args.args[1]
        self.assertEqual(saved_arg["token"], "new-token")
        cron_lines = mocks["write_crontab"].call_args.args[0]
        self.assertIn("new-token", cron_lines[-1])

    @patch("main.ask_password", return_value=None)
    def test_escaping_the_password_prompt_aborts_cleanly(self, mock_password):
        result, mocks = self._invoke(["relogin"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["save"].assert_not_called()

    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause):
        result, _ = self._invoke(["relogin", "--password-file", PASSWORD_FILE], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()


class RemoveCommandTest(unittest.TestCase):
    MANAGED_LINE = "25 2 * * * bash issabel.sh --token abcdefgh1234"

    def _invoke(self, args, is_tty=False, saved=None, managed=None):
        with patch("main._is_interactive", return_value=is_tty), \
             patch("main.state.load", return_value=saved), \
             patch("main.state.remove") as mock_remove_state, \
             patch("main.crontab.read_crontab", return_value=["x", managed] if managed else []), \
             patch(
                 "main.crontab.find_managed_entry",
                 return_value=(1, managed) if managed else None,
             ), \
             patch("main.crontab.remove_managed_entry", return_value=([], True)) as mock_remove_entry, \
             patch("main.crontab.write_crontab") as mock_write, \
             patch("main.uoe_client.delete_user") as mock_delete_user, \
             patch("main.uoe_client.login", return_value="admintoken"), \
             patch("main.UOEModule.get_logger"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, {
                "remove_state": mock_remove_state, "remove_entry": mock_remove_entry,
                "write_crontab": mock_write, "delete_user": mock_delete_user,
            }

    def test_reports_nothing_to_remove(self):
        result, mocks = self._invoke(["remove", "--yes"], saved=None, managed=None)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["remove_state"].assert_not_called()

    def test_yes_flag_skips_confirmation_and_removes(self):
        result, mocks = self._invoke(["remove", "--yes"], saved={"username": "empresa"}, managed=self.MANAGED_LINE)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["remove_entry"].assert_called_once()
        mocks["remove_state"].assert_called_once()
        mocks["delete_user"].assert_not_called()

    def test_declining_confirmation_removes_nothing(self):
        with patch("main.ask_confirm", return_value=False):
            result, mocks = self._invoke(
                ["remove"], is_tty=True, saved={"username": "empresa"}, managed=self.MANAGED_LINE,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["remove_state"].assert_not_called()

    def test_never_shows_the_full_token_when_confirming(self):
        result, mocks = self._invoke(["remove", "--yes"], saved={"username": "empresa"}, managed=self.MANAGED_LINE)
        self.assertNotIn("abcdefgh1234", result.output)

    def test_can_also_delete_the_remote_user_when_asked_interactively(self):
        with patch("main.ask_confirm", side_effect=[True, True]):
            result, mocks = self._invoke(
                ["remove", "--admin-password-file", PASSWORD_FILE],
                is_tty=True, saved={"username": "empresa"}, managed=self.MANAGED_LINE,
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["delete_user"].assert_called_once_with("admintoken", "empresa")

    def test_yes_alone_never_implies_deleting_the_remote_user(self):
        result, mocks = self._invoke(["remove", "--yes"], saved={"username": "empresa"}, managed=self.MANAGED_LINE)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["delete_user"].assert_not_called()

    def test_delete_remote_user_flag_works_headless(self):
        result, mocks = self._invoke(
            ["remove", "--yes", "--delete-remote-user", "--admin-password-file", PASSWORD_FILE],
            saved={"username": "empresa"}, managed=self.MANAGED_LINE,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["delete_user"].assert_called_once_with("admintoken", "empresa")

    @patch("main.widgets.pause")
    def test_pauses_when_interactive_even_with_nothing_to_remove(self, mock_pause):
        # o wrapper do comando pausa em qualquer retorno sem exceção -- inclusive
        # o caminho "nada a remover", igual o padrão já usado em netinstall/qint.
        result, _ = self._invoke(["remove", "--yes"], is_tty=True, saved=None, managed=None)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()


class CheckCommandTest(unittest.TestCase):
    def _invoke(self, is_tty=False, saved=None, managed=None):
        with patch("main._is_interactive", return_value=is_tty), \
             patch("main.state.load", return_value=saved), \
             patch("main.crontab.read_crontab", return_value=[]), \
             patch("main.crontab.find_managed_entry", return_value=managed):
            return CliRunner().invoke(cli.cli_group(), ["check"])

    def test_reports_not_configured_when_no_state(self):
        result = self._invoke(saved=None)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("não configurado", result.output.lower())

    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause):
        self._invoke(is_tty=True, saved=None)
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause):
        self._invoke(is_tty=False, saved=None)
        mock_pause.assert_not_called()

    def test_shows_state_and_redacts_the_token_in_the_cron_line(self):
        saved = {
            "username": "empresa", "root_path": "clientes/1-2-empresa", "script": "issabel",
            "cron_minute": "25", "cron_hour": "2",
        }
        result = self._invoke(saved=saved, managed=(1, "25 2 * * * bash issabel.sh --token abcdefgh1234"))
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("empresa", result.output)
        self.assertIn("clientes/1-2-empresa", result.output)
        self.assertNotIn("abcdefgh1234", result.output)

    def test_warns_when_managed_entry_is_missing_despite_saved_state(self):
        saved = {"username": "empresa", "root_path": "x", "script": "issabel", "cron_minute": "0", "cron_hour": "2"}
        result = self._invoke(saved=saved, managed=None)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("não encontrada", result.output.lower())


if __name__ == "__main__":
    unittest.main()
