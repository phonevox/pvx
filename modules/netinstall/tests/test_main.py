import re
import unittest
from unittest.mock import call, patch

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
    def _invoke(self, args, preflight_result=([], []), preflight_side_effect=None, step_side_effects=None):
        step_side_effects = step_side_effects or {}
        preflight_patch = (
            patch("main.preflight.check", side_effect=preflight_side_effect) if preflight_side_effect
            else patch("main.preflight.check", return_value=preflight_result)
        )
        with preflight_patch, \
             patch("main.preflight.version_major", return_value=9), \
             patch("main.install_steps.add_repos", side_effect=step_side_effects.get("add_repos")), \
             patch("main.install_steps.prepare_system", side_effect=step_side_effects.get("prepare_system")), \
             patch("main.install_steps.enable_php_remi", side_effect=step_side_effects.get("enable_php_remi")), \
             patch("main.install_steps.install_packages") as mock_install_packages, \
             patch("main.install_steps.post_install", side_effect=step_side_effects.get("post_install")), \
             patch("main.install_steps.install_db", side_effect=step_side_effects.get("install_db")), \
             patch("main.install_steps.install_control_panel"), \
             patch("main.install_steps.set_timezone"), \
             patch("main.install_steps.set_passwords", side_effect=step_side_effects.get("set_passwords")), \
             patch("main.credentials.save_credentials", return_value="/tmp/creds.txt") as mock_creds, \
             patch("main.os_ops.run_cmd") as mock_reboot, \
             patch("main.integrations.run_ssh_hardening", return_value={"ok": True}) as mock_ssh, \
             patch("main.integrations.run_firewall_sync", return_value={"ok": True}) as mock_fw, \
             patch("main.integrations.run_qint", return_value={"ok": True}) as mock_qint:
            result = CliRunner().invoke(cli.cli_group(), args)
            return result, {
                "reboot": mock_reboot, "ssh": mock_ssh, "firewall": mock_fw, "qint": mock_qint,
                "creds": mock_creds, "install_packages": mock_install_packages,
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


class PreflightReportTest(MainTestCase):
    def test_prints_a_check_result_line_per_preflight_check_as_it_resolves(self):
        def fake_check(min_version, force=False, report=None):
            report("root", "ok", None)
            report("SO", "ok", "Rocky/RHEL 9")
            report("rede", "pending", None)
            report("rede", "ok", None)
            report("RAM", "warn", "768 MB")
            report("instalação prévia", "error", "detectada")
            return [], []

        result, _ = self._invoke(BASE_ARGS, preflight_side_effect=fake_check)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("✓ root: ok", result.output)
        self.assertIn("✓ SO: ok (Rocky/RHEL 9)", result.output)
        self.assertIn("✓ rede: ok", result.output)
        self.assertIn("! RAM: atenção (768 MB)", result.output)
        self.assertIn("✗ instalação prévia: falha (detectada)", result.output)

    def test_check_without_detail_shows_only_the_status_word(self):
        def fake_check(min_version, force=False, report=None):
            report("root", "ok", None)
            return [], []

        result, _ = self._invoke(BASE_ARGS, preflight_side_effect=fake_check)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("✓ root: ok", result.output)

    def test_network_pending_phase_opens_its_own_spinner(self):
        def fake_check(min_version, force=False, report=None):
            report("rede", "pending", None)
            report("rede", "ok", None)
            return [], []

        with patch("main.widgets.step") as mock_step:
            result, _ = self._invoke(BASE_ARGS, preflight_side_effect=fake_check)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(call("Verificando rede..."), mock_step.call_args_list)


class AddpkgsDefaultsTest(MainTestCase):
    def test_never_asks_and_uses_the_default_packages(self):
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_checkbox", return_value=[]) as mock_checkbox, \
             patch("main.ask_select", return_value="Usar padrões da Phonevox (recomendado)"):
            result, mocks = self._invoke(
                ["issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
                 "--tweaks", "ssh-hardening"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        mock_checkbox.assert_not_called()
        packages = mocks["install_packages"].call_args.args[1]
        self.assertIn("issabel-license", packages)
        self.assertIn("issabel-packetbl", packages)
        self.assertNotIn("wanpipe", packages)

    def test_flag_still_overrides_the_default(self):
        args = ["issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
                "--tweaks", "firewall", "--addpkgs", "wanpipe"]
        result, mocks = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        packages = mocks["install_packages"].call_args.args[1]
        self.assertIn("wanpipe-utils", packages)
        self.assertNotIn("issabel-license", packages)


class HappyPathTest(MainTestCase):
    def test_skip_clean_flag_forwards_to_install_packages(self):
        result, mocks = self._invoke(BASE_ARGS + ["--skip-clean"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(mocks["install_packages"].call_args.kwargs["skip_clean"])

    def test_skip_clean_defaults_to_false(self):
        result, mocks = self._invoke(BASE_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse(mocks["install_packages"].call_args.kwargs["skip_clean"])

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


class StepAnnouncementTest(MainTestCase):
    # cada etapa deve anunciar sucesso ao terminar -- ver widgets.step()/_run_step().
    # duração fica só no timer ao vivo do spinner (widgets.step), não repete no texto
    # de sucesso -- linha do spinner some ao terminar (transient=True), então o que
    # resta na tela é só a sequência de "✓ sucesso!".
    DONE_MESSAGES = (
        "Repositórios adicionados.",
        "Sistema preparado.",
        "Repo Remi + PHP habilitados.",
        "Pacotes instalados.",
        "Pós-instalação concluída.",
        "Schema do banco instalado.",
        "Senhas de acesso definidas.",
    )

    def test_announces_success_for_every_base_step(self):
        result, _ = self._invoke(BASE_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        for done_message in self.DONE_MESSAGES:
            self.assertIn(
                f"✓ sucesso! {done_message}", result.output,
                f"faltou anúncio de sucesso para: {done_message}",
            )

    def test_success_text_has_no_duration_suffix(self):
        result, _ = self._invoke(BASE_ARGS)
        self.assertNotRegex(result.output, r"\(\d+\.\ds\)")

    def test_announces_tweak_results_too(self):
        args = ["issabel5", "--astver", "18", "--yes", "--sql-password", "a", "--web-password", "b",
                "--tweaks", "ssh-hardening"]
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_checkbox", return_value=[]), \
             patch("main.ask_select", return_value="Usar padrões da Phonevox (recomendado)"):
            result, _ = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("✓ sucesso! ssh-hardening aplicado.", result.output)


class AsteriskVersionPromptTest(MainTestCase):
    def test_defaults_to_18_when_asked_interactively(self):
        args = ["issabel5", "--yes", "--sql-password", "a", "--web-password", "b", "--tweaks", "firewall"]
        with patch("main._is_interactive", return_value=True), \
             patch("main.ask_checkbox", return_value=[]), \
             patch("main.ask_select", return_value="18") as mock_select:
            result, _ = self._invoke(args)
        self.assertEqual(result.exit_code, 0, result.output)
        mock_select.assert_called_once_with("Versão do Asterisk:", ["16", "18"], default="18")


class CoffeeBreakTest(MainTestCase):
    def test_warns_before_the_slowest_step_and_prints_coffee_art(self):
        result, _ = self._invoke(BASE_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("pega um café", result.output.lower())
        cafe_index = result.output.lower().index("pega um café")
        packages_index = result.output.index("Pacotes instalados.")
        self.assertLess(cafe_index, packages_index)


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


class LoggingTest(MainTestCase):
    # achado ao vivo: netinstall falhou numa instalação real e não sobrou log nenhum
    # acionável pra diagnosticar depois -- cada passo agora registra início/sucesso/falha
    # no logger do próprio módulo (self.get_logger()), não só no terminal.
    @patch("main.NetinstallModule.get_logger")
    def test_logs_info_for_every_successful_step(self, mock_get_logger):
        result, _ = self._invoke(BASE_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        logger = mock_get_logger.return_value
        self.assertTrue(logger.info.called)
        self.assertFalse(logger.error.called)

    @patch("main.NetinstallModule.get_logger")
    def test_logs_error_when_a_step_fails(self, mock_get_logger):
        logger = mock_get_logger.return_value
        result, _ = self._invoke(
            BASE_ARGS, step_side_effects={"post_install": RuntimeError("falha real do passo")},
        )
        self.assertNotEqual(result.exit_code, 0)
        logger.error.assert_called_once()
        self.assertIn("falha real do passo", logger.error.call_args.args[0])

    @patch("main.NetinstallModule.get_logger")
    def test_logs_tweak_results(self, mock_get_logger):
        logger = mock_get_logger.return_value
        result, _ = self._invoke(BASE_ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        info_messages = " ".join(c.args[0] for c in logger.info.call_args_list)
        self.assertIn("firewall", info_messages)


if __name__ == "__main__":
    unittest.main()
