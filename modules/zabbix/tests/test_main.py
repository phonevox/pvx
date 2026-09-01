import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from click.testing import CliRunner

from main import cli

BASE_INSTALL_ARGS = [
    "install", "--server", "zabbix.local", "--yes",
]


class MainTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._state_dir = Path(self._tmp.name)
        self._state_patch = patch("main._state_dir", return_value=self._state_dir)
        self._state_patch.start()

    def tearDown(self):
        self._state_patch.stop()
        self._tmp.cleanup()

    def _invoke(self, args, is_tty=False, is_root=True, os_release=None, asterisk_version=None,
                repo_ok=True, agent_ok=True, start_ok=True):
        os_release = os_release or {"ID": "rocky", "VERSION_ID": "8.10"}
        with patch("main.os.geteuid", return_value=0 if is_root else 1000), \
             patch("main._is_interactive", return_value=is_tty), \
             patch("main.system_info.read_os_release", return_value=os_release), \
             patch("main.system_info.detect_provider", return_value="local"), \
             patch("main.system_info.detect_hostname", return_value="detected-host"), \
             patch("main.system_info.asterisk_version", return_value=asterisk_version), \
             patch("main.install_steps.install_repo", return_value=repo_ok) as mock_repo, \
             patch("main.install_steps.install_agent", return_value=agent_ok) as mock_agent, \
             patch("main.install_steps.enable_and_start", return_value=start_ok) as mock_start, \
             patch("main.config.set_params") as mock_set_params, \
             patch("main.config.ensure_include") as mock_ensure_include:
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, {
                "repo": mock_repo, "agent": mock_agent, "start": mock_start,
                "set_params": mock_set_params, "ensure_include": mock_ensure_include,
            }


class RootCheckTest(MainTestCase):
    def test_refuses_without_root(self):
        result, _ = self._invoke(BASE_INSTALL_ARGS, is_root=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("root", result.output.lower())


class InstallHappyPathTest(MainTestCase):
    def test_installs_agent2_by_default(self):
        result, mocks = self._invoke(BASE_INSTALL_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["agent"].assert_called_once_with("zabbix-agent2")

    def test_selects_classic_agent_via_flag(self):
        result, mocks = self._invoke(BASE_INSTALL_ARGS + ["--agent-version", "agent"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["agent"].assert_called_once_with("zabbix-agent")

    def test_server_active_defaults_to_server_when_not_given(self):
        result, mocks = self._invoke(BASE_INSTALL_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        values = mocks["set_params"].call_args.args[1]
        self.assertEqual(values["Server"], "zabbix.local")
        self.assertEqual(values["ServerActive"], "zabbix.local")

    def test_hostname_defaults_to_detected_value(self):
        result, mocks = self._invoke(BASE_INSTALL_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(mocks["set_params"].call_args.args[1]["Hostname"], "detected-host")

    def test_metadata_includes_asterisk_version_when_present(self):
        result, mocks = self._invoke(BASE_INSTALL_ARGS, asterisk_version="18")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("av:18", mocks["set_params"].call_args.args[1]["HostMetadata"])

    def test_metadata_omits_asterisk_when_absent(self):
        result, mocks = self._invoke(BASE_INSTALL_ARGS, asterisk_version=None)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("av:", mocks["set_params"].call_args.args[1]["HostMetadata"])

    def test_test_flag_adds_test_true_to_metadata(self):
        result, mocks = self._invoke(BASE_INSTALL_ARGS + ["--test"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("test:true", mocks["set_params"].call_args.args[1]["HostMetadata"])

    def test_persists_chosen_agent_variant_for_later_script_commands(self):
        result, _ = self._invoke(BASE_INSTALL_ARGS + ["--agent-version", "agent"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual((self._state_dir / "agent_variant.txt").read_text().strip(), "agent")

    def test_requires_server_without_tty_and_without_flag(self):
        result, _ = self._invoke(["install", "--yes"], is_tty=False)
        self.assertNotEqual(result.exit_code, 0)

    def test_metadata_flag_overrides_auto_value_in_headless_mode(self):
        result, mocks = self._invoke(BASE_INSTALL_ARGS + ["--metadata", "l:custom literal:value"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(mocks["set_params"].call_args.args[1]["HostMetadata"], "l:custom literal:value")


class InstallDeclineConfirmationTest(MainTestCase):
    # achado ao vivo: decliner o "Prosseguir?" só ecoava "Operação cancelada." e voltava
    # pro menu direto -- sem pause(), a tela limpa antes do usuário conseguir ler.
    @patch("main.widgets.pause")
    @patch("main.widgets.message")
    @patch("main.ask_confirm", return_value=False)
    @patch("main.ask_text", side_effect=["vps-x", "zabbix.local", "l:ovh os:linux osn:rocky-8.10"])
    @patch("main.ask_select", side_effect=["ovh", "Agent 2 (recomendado)"])
    def test_shows_message_and_pauses_when_interactive(
        self, mock_select, mock_text, mock_confirm, mock_message, mock_pause
    ):
        result, mocks = self._invoke(["install", "--server", "zabbix.local"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_message.assert_called_once_with("nada foi alterado.")
        mock_pause.assert_called_once_with()
        mocks["repo"].assert_not_called()

    @patch("main.widgets.pause")
    @patch("main.widgets.message")
    @patch("main.ask_confirm", return_value=False)
    def test_does_not_pause_when_not_interactive(self, mock_confirm, mock_message, mock_pause):
        result, mocks = self._invoke(["install", "--server", "zabbix.local"], is_tty=False)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_not_called()


class InteractiveMetadataPromptTest(MainTestCase):
    def test_metadata_prompt_defaults_to_auto_value_and_user_edit_wins(self):
        # não deve mais existir um prompt separado de "metadata extra" -- o usuário edita
        # o valor auto-calculado inteiro ali mesmo (geralmente só aperta Enter).
        with patch("main.ask_select", side_effect=["ovh", "Agent 2 (recomendado)"]), \
             patch("main.ask_text", side_effect=[
                 "vps-x", "zabbix.local", "zabbix.local", "l:ovh os:linux osn:rocky-8.10 custom:value",
             ]) as mock_text, \
             patch("main.ask_confirm", side_effect=[False, True]):
            result, mocks = self._invoke(["install"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)

        metadata_call = mock_text.call_args_list[-1]
        self.assertEqual(metadata_call.kwargs["default"], "l:ovh os:linux osn:rocky-8.10")
        self.assertEqual(
            mocks["set_params"].call_args.args[1]["HostMetadata"],
            "l:ovh os:linux osn:rocky-8.10 custom:value",
        )


class AutoDetectFeedbackTest(MainTestCase):
    # achado ao vivo: detect_provider() bate na rede (ipinfo.io) e demora --
    # sem spinner, o menu parecia travado até as opções aparecerem.
    @patch("main.widgets.success")
    @patch("main.widgets.spinner")
    def test_provider_detection_uses_a_spinner_and_reports_the_result(self, mock_spinner, mock_success):
        with patch("main.ask_select", side_effect=["local", "Agent 2 (recomendado)"]), \
             patch("main.ask_text", side_effect=["detected-host", "zabbix.local", "zabbix.local", ""]), \
             patch("main.ask_confirm", side_effect=[False, True]):
            result, _ = self._invoke(["install"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_spinner.assert_any_call("Detectando provider...")
        self.assertTrue(any("local" in str(c) for c in mock_success.call_args_list))

    @patch("main.widgets.success")
    @patch("main.widgets.spinner")
    def test_hostname_detection_uses_a_spinner_and_reports_the_result(self, mock_spinner, mock_success):
        with patch("main.ask_select", side_effect=["local", "Agent 2 (recomendado)"]), \
             patch("main.ask_text", side_effect=["detected-host", "zabbix.local", "zabbix.local", ""]), \
             patch("main.ask_confirm", side_effect=[False, True]):
            result, _ = self._invoke(["install"], is_tty=True)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_spinner.assert_any_call("Detectando hostname...")
        self.assertTrue(any("detected-host" in str(c) for c in mock_success.call_args_list))

    @patch("main.widgets.success")
    @patch("main.widgets.spinner")
    def test_no_detection_feedback_when_provider_given_via_flag(self, mock_spinner, mock_success):
        with patch("main.ask_select", return_value="Agent 2 (recomendado)"), \
             patch("main.ask_text", side_effect=["zabbix.local", "zabbix.local", ""]), \
             patch("main.ask_confirm", side_effect=[False, True]):
            result, _ = self._invoke(
                BASE_INSTALL_ARGS + ["--provider", "aws", "--hostname", "x"], is_tty=True
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse(any(c == (("Detectando provider...",), {}) for c in mock_spinner.call_args_list))
        self.assertFalse(any(c == (("Detectando hostname...",), {}) for c in mock_spinner.call_args_list))


class InstallFailureTest(MainTestCase):
    def test_raises_when_repo_install_fails(self):
        result, _ = self._invoke(BASE_INSTALL_ARGS, repo_ok=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertNotIn("Traceback", result.output)

    def test_raises_when_agent_install_fails(self):
        result, _ = self._invoke(BASE_INSTALL_ARGS, agent_ok=False)
        self.assertNotEqual(result.exit_code, 0)

    def test_raises_when_service_start_fails(self):
        result, _ = self._invoke(BASE_INSTALL_ARGS, start_ok=False)
        self.assertNotEqual(result.exit_code, 0)

    @patch("main.ZabbixModule.get_logger")
    def test_logs_error_on_failure(self, mock_get_logger):
        result, _ = self._invoke(BASE_INSTALL_ARGS, repo_ok=False)
        self.assertNotEqual(result.exit_code, 0)
        mock_get_logger.return_value.error.assert_called_once()

    @patch("main.ZabbixModule.get_logger")
    def test_logs_success(self, mock_get_logger):
        result, _ = self._invoke(BASE_INSTALL_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_get_logger.return_value.info.assert_called()


class ScriptAddCommandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._state_dir = Path(self._tmp.name)
        (self._state_dir / "agent_variant.txt").write_text("agent2")
        self._state_patch = patch("main._state_dir", return_value=self._state_dir)
        self._state_patch.start()
        self._scripts_dir = Path(self._tmp.name) / "pvx-scripts.d"
        self._scripts_patch = patch("main.defaults.PVX_SCRIPTS_DIR", str(self._scripts_dir))
        self._scripts_patch.start()

    def tearDown(self):
        self._scripts_patch.stop()
        self._state_patch.stop()
        self._tmp.cleanup()

    def _invoke(self, args):
        with patch("main.sudoers.write_rules") as mock_sudoers, patch("main._write_confd_file"):
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, mock_sudoers

    def test_adds_a_known_script_deploys_it_and_persists_it(self):
        result, _ = self._invoke(["script", "add", "audit"])
        self.assertEqual(result.exit_code, 0, result.output)

        deployed = self._scripts_dir / "audit.sh"
        self.assertTrue(deployed.exists())
        self.assertIn("#!/bin/bash", deployed.read_text())

        import scripts as scripts_module
        entries = scripts_module.list_all(str(self._state_dir / "scripts.json"))
        self.assertEqual(entries["audit"]["command"], f"{deployed} --zabbix")

    def test_known_script_needing_root_calls_sudoers_write_rules(self):
        result, mock_sudoers = self._invoke(["script", "add", "audit"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_sudoers.assert_called_once()
        self.assertIn(str(self._scripts_dir / "audit.sh"), mock_sudoers.call_args.args[2][0])

    def test_rejects_duplicate_key(self):
        self._invoke(["script", "add", "audit"])
        result, _ = self._invoke(["script", "add", "audit"])
        self.assertNotEqual(result.exit_code, 0)

    def test_rejects_key_outside_the_catalog(self):
        result, _ = self._invoke(["script", "add", "nao-existe"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("audit", result.output)

    def test_requires_key_without_tty(self):
        result, _ = self._invoke(["script", "add"])
        self.assertNotEqual(result.exit_code, 0)

    def test_asks_from_the_catalog_when_interactive(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_select", return_value="audit -- auditoria de comprometimento "
                                                     "(mineração, persistência, webshell, abuso de PBX...)") as mock_select:
            result, _ = self._invoke(["script", "add"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_select.assert_called_once()

    def test_fails_clearly_when_agent_was_never_installed(self):
        (self._state_dir / "agent_variant.txt").unlink()
        result, _ = self._invoke(["script", "add", "audit"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("install", result.output.lower())


class ScriptRemoveCommandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._state_dir = Path(self._tmp.name)
        (self._state_dir / "agent_variant.txt").write_text("agent2")
        self._state_patch = patch("main._state_dir", return_value=self._state_dir)
        self._state_patch.start()
        self._scripts_dir = Path(self._tmp.name) / "pvx-scripts.d"
        self._scripts_patch = patch("main.defaults.PVX_SCRIPTS_DIR", str(self._scripts_dir))
        self._scripts_patch.start()

    def tearDown(self):
        self._scripts_patch.stop()
        self._state_patch.stop()
        self._tmp.cleanup()

    def _invoke(self, args):
        with patch("main.sudoers.write_rules"), patch("main._write_confd_file"):
            return CliRunner().invoke(cli.cli_group(), args)

    def test_removes_an_existing_script_and_its_deployed_file(self):
        self._invoke(["script", "add", "audit"])
        deployed = self._scripts_dir / "audit.sh"
        self.assertTrue(deployed.exists())

        result = self._invoke(["script", "remove", "audit"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse(deployed.exists())

        import scripts as scripts_module
        entries = scripts_module.list_all(str(self._state_dir / "scripts.json"))
        self.assertNotIn("audit", entries)

    def test_raises_when_key_does_not_exist(self):
        result = self._invoke(["script", "remove", "does-not-exist"])
        self.assertNotEqual(result.exit_code, 0)

    @patch("main.widgets.pause")
    @patch("main._is_interactive", return_value=True)
    def test_pauses_when_no_scripts_registered_and_interactive(self, mock_interactive, mock_pause):
        # mesmo bug do check_cmd: "return" logo depois do echo informativo nunca
        # chegava no pause() do fim da função.
        with patch("main.sudoers.write_rules"), patch("main._write_confd_file"):
            result = CliRunner().invoke(cli.cli_group(), ["script", "remove"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()


class ScriptListCommandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._state_dir = Path(self._tmp.name)
        self._state_patch = patch("main._state_dir", return_value=self._state_dir)
        self._state_patch.start()

    def tearDown(self):
        self._state_patch.stop()
        self._tmp.cleanup()

    def test_shows_message_when_empty(self):
        result = CliRunner().invoke(cli.cli_group(), ["script", "list"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("nenhum", result.output.lower())

    def test_lists_added_scripts(self):
        import scripts as scripts_module
        scripts_module.add(str(self._state_dir / "scripts.json"), "cpu.custom", "/opt/scripts/cpu.sh")
        result = CliRunner().invoke(cli.cli_group(), ["script", "list"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("cpu.custom", result.output)
        self.assertIn("/opt/scripts/cpu.sh", result.output)


class CheckCommandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._state_dir = Path(self._tmp.name)
        self._state_patch = patch("main._state_dir", return_value=self._state_dir)
        self._state_patch.start()

    def tearDown(self):
        self._state_patch.stop()
        self._tmp.cleanup()

    def test_reports_not_configured_when_never_installed(self):
        result = CliRunner().invoke(cli.cli_group(), ["check"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("não configurado", result.output.lower())

    @patch("main.widgets.pause")
    @patch("main._is_interactive", return_value=True)
    def test_pauses_when_not_configured_and_interactive(self, mock_interactive, mock_pause):
        # achado ao vivo: o "return" antecipado desse caminho nunca chegava no pause() do
        # fim da função -- tela do menu voltava vazia antes do usuário conseguir ler.
        result = CliRunner().invoke(cli.cli_group(), ["check"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_called_once_with()

    @patch("main.widgets.pause")
    @patch("main._is_interactive", return_value=False)
    def test_does_not_pause_when_not_configured_and_not_interactive(self, mock_interactive, mock_pause):
        result = CliRunner().invoke(cli.cli_group(), ["check"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_pause.assert_not_called()

    def _invoke_configured(self, params=None, status=None, entries=None):
        (self._state_dir / "agent_variant.txt").write_text("agent2")
        params = params if params is not None else {"Server": "zabbix.local"}
        status = status if status is not None else {"active": "active", "enabled": "enabled"}
        entries = entries if entries is not None else {}
        with patch("main.config.read_params", return_value=params), \
             patch("main.install_steps.service_status", return_value=status), \
             patch("main.scripts.list_all", return_value=entries):
            return CliRunner().invoke(cli.cli_group(), ["check"])

    def test_shows_config_summary(self):
        result = self._invoke_configured(params={
            "Server": "zabbix.falevox.com.br", "ServerActive": "zabbix.falevox.com.br",
            "Hostname": "vps-x", "HostMetadata": "l:ovh os:linux osn:rocky-8.10",
        })
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("zabbix.falevox.com.br", result.output)
        self.assertIn("vps-x", result.output)
        self.assertIn("l:ovh os:linux osn:rocky-8.10", result.output)

    def test_reports_agent_active_and_enabled(self):
        result = self._invoke_configured(status={"active": "active", "enabled": "enabled"})
        self.assertIn("ativo", result.output.lower())

    def test_reports_agent_inactive_and_disabled(self):
        result = self._invoke_configured(status={"active": "inactive", "enabled": "disabled"})
        self.assertIn("inativo", result.output.lower())

    def test_shows_no_scripts_message_when_empty(self):
        result = self._invoke_configured(entries={})
        self.assertIn("nenhum", result.output.lower())

    def test_lists_custom_scripts(self):
        result = self._invoke_configured(entries={"cpu.custom": {"command": "/opt/cpu.sh", "needs_root": False}})
        self.assertIn("cpu.custom", result.output)
        self.assertIn("/opt/cpu.sh", result.output)


if __name__ == "__main__":
    unittest.main()
