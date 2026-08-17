import unittest
from unittest.mock import patch

from click.testing import CliRunner

from main import cli

BASE_ARGS = [
    "issabel5", "--astver", "18", "--yes",
    "--sql-password", "sqlpw", "--web-password", "webpw",
    "--tweaks", "firewall",  # só firewall -- evita disparar ssh-hardening/qint nos testes genéricos
]


def _patched(**overrides):
    patches = {
        "main.preflight.check": (["errors"] if overrides.pop("preflight_fails", False) else ([], [])),
    }
    return patches


class MainTestCase(unittest.TestCase):
    def _invoke(self, args, preflight_result=([], [])):
        with patch("main.preflight.check", return_value=preflight_result), \
             patch("main.preflight.version_major", return_value=9), \
             patch("main.install_steps.add_repos"), \
             patch("main.install_steps.prepare_system"), \
             patch("main.install_steps.enable_php_remi"), \
             patch("main.install_steps.install_packages"), \
             patch("main.install_steps.post_install"), \
             patch("main.install_steps.install_db"), \
             patch("main.install_steps.install_control_panel"), \
             patch("main.install_steps.set_timezone"), \
             patch("main.install_steps.set_passwords"), \
             patch("main.credentials.save_credentials", return_value="/tmp/creds.txt") as mock_creds, \
             patch("main.os_ops.run_cmd") as mock_reboot, \
             patch("main.integrations.run_ssh_hardening", return_value={"ok": True}) as mock_ssh, \
             patch("main.integrations.run_firewall_sync", return_value={"ok": True}) as mock_fw, \
             patch("main.integrations.run_qint", return_value={"ok": True}) as mock_qint:
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, {
                "reboot": mock_reboot, "ssh": mock_ssh, "firewall": mock_fw, "qint": mock_qint,
                "creds": mock_creds,
            }


class PreflightTest(MainTestCase):
    def test_aborts_with_preflight_errors(self):
        result, _ = self._invoke(BASE_ARGS, preflight_result=(["não é RHEL-like"], []))
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("RHEL", result.output)

    def test_prints_warnings_but_proceeds(self):
        result, mocks = self._invoke(BASE_ARGS, preflight_result=([], ["RAM baixa"]))
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("RAM baixa", result.output)


class HappyPathTest(MainTestCase):
    def test_runs_base_install_sequence(self):
        result, mocks = self._invoke(BASE_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["firewall"].assert_called_once()
        mocks["ssh"].assert_not_called()
        mocks["qint"].assert_not_called()

    def test_reboots_by_default(self):
        result, mocks = self._invoke(BASE_ARGS)
        mocks["reboot"].assert_called_once_with(["reboot"])

    def test_no_reboot_flag_skips_reboot(self):
        result, mocks = self._invoke(BASE_ARGS + ["--no-reboot"])
        mocks["reboot"].assert_not_called()
        self.assertIn("no-reboot", result.output.replace("--", ""))

    def test_requires_astver_without_tty(self):
        args = [a for a in BASE_ARGS if a not in ("--astver", "18")]
        result, _ = self._invoke(args)
        self.assertNotEqual(result.exit_code, 0)

    def test_generates_random_passwords_without_tty_instead_of_blocking(self):
        # bash original nunca trava esperando senha -- sem flag e sem TTY, gera aleatória
        # (fica recuperável depois via credentials.save_credentials). Corrigido: antes
        # disso, faltar --sql-password/--web-password sem terminal dava erro.
        args = ["issabel5", "--astver", "18", "--yes", "--tweaks", "firewall"]
        result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        sql_pw, web_pw = mocks["creds"].call_args.args[2], mocks["creds"].call_args.args[3]
        self.assertEqual(len(sql_pw), 24)
        self.assertEqual(len(web_pw), 24)
        self.assertNotEqual(sql_pw, web_pw)


class SshHardeningTweakTest(MainTestCase):
    def test_runs_ssh_hardening_with_resolved_defaults(self):
        args = ["issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
                "--tweaks", "ssh-hardening"]
        result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["ssh"].assert_called_once()
        config = mocks["ssh"].call_args.args[0]
        self.assertTrue(config["lock_root"])
        self.assertEqual(config["username"], "phonevox")
        self.assertEqual(config["port"], "21122")

    def test_flags_override_defaults(self):
        args = [
            "issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
            "--tweaks", "ssh-hardening", "--tweak-ssh-username", "custom", "--tweak-ssh-port", "2222",
        ]
        result, mocks = self._invoke(args)
        config = mocks["ssh"].call_args.args[0]
        self.assertEqual(config["username"], "custom")
        self.assertEqual(config["port"], "2222")


class QintTweakTest(MainTestCase):
    def test_errors_without_tipo(self):
        args = ["issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
                "--tweaks", "qint"]
        result, mocks = self._invoke(args)
        self.assertNotEqual(result.exit_code, 0)
        mocks["qint"].assert_not_called()

    def test_runs_qint_with_provided_fields(self):
        args = [
            "issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
            "--tweaks", "qint", "--qint-tipo", "ixcsoft", "--qint-sftp", "root@10.0.0.1:2222",
            "--qint-url", "https://erp.example.com",
        ]
        result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        config = mocks["qint"].call_args.args[0]
        self.assertEqual(config["tipo"], "ixcsoft")
        self.assertEqual(config["sftp"], "root@10.0.0.1:2222")


class InteractivePasswordTest(MainTestCase):
    def test_empty_enter_generates_random_password(self):
        args = ["issabel5", "--astver", "18", "--yes", "--tweaks", "firewall"]
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_checkbox", return_value=[]), \
             patch("main.ask_text", return_value=""):
            result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        sql_pw, web_pw = mocks["creds"].call_args.args[2], mocks["creds"].call_args.args[3]
        self.assertEqual(len(sql_pw), 24)
        self.assertNotEqual(sql_pw, web_pw)

    def test_esc_on_password_prompt_aborts(self):
        args = ["issabel5", "--astver", "18", "--yes", "--tweaks", "firewall"]
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_checkbox", return_value=[]), \
             patch("main.ask_text", return_value=None):
            result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["firewall"].assert_not_called()


class SshHardeningQuickShortcutTest(MainTestCase):
    def test_quick_choice_uses_defaults_without_asking_anything_else(self):
        args = ["issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
                "--tweaks", "ssh-hardening"]
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_checkbox", return_value=[]), \
             patch("main.ask_select", return_value="Usar padrões da Phonevox (recomendado)") as mock_select:
            result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_select.assert_called_once()  # só a pergunta quick-vs-customize, mais nenhuma
        config = mocks["ssh"].call_args.args[0]
        self.assertEqual(config["username"], "phonevox")
        self.assertEqual(config["port"], "21122")

    def test_customize_choice_falls_through_to_per_field_questions(self):
        args = ["issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
                "--tweaks", "ssh-hardening"]
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_checkbox", return_value=[]), \
             patch("main.ask_select", return_value="Personalizar cada opção") as mock_select, \
             patch("main.ask_confirm", return_value=True) as mock_confirm:
            result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        # 1 pergunta quick-vs-customize + 3 confirmações (lock_root/create_user/change_port).
        self.assertEqual(mock_select.call_count, 1)
        self.assertEqual(mock_confirm.call_count, 3)
        mocks["ssh"].assert_called_once()

    def test_flag_given_skips_the_quick_vs_customize_question(self):
        args = [
            "issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
            "--tweaks", "ssh-hardening", "--tweak-ssh-username", "custom",
        ]
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_checkbox", return_value=[]), \
             patch("main.ask_select") as mock_select, patch("main.ask_confirm", return_value=True):
            result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_select.assert_not_called()  # uma flag ssh já dada pula a pergunta quick-vs-customize
        config = mocks["ssh"].call_args.args[0]
        self.assertEqual(config["username"], "custom")


class ConfirmationTest(MainTestCase):
    def test_cancels_without_yes_when_confirm_declines(self):
        args = ["issabel5", "--astver", "18", "--sql-password", "a", "--web-password", "b",
                "--tweaks", "firewall"]
        with patch("main.ask_confirm", return_value=False):
            result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("cancelada", result.output.lower())
        mocks["firewall"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
