import unittest
from unittest.mock import patch

from click.testing import CliRunner

from main import cli


def _invoke(args, is_root=True, **patches):
    defaults = {
        "main.os.geteuid": patch("main.os.geteuid", return_value=0 if is_root else 1000),
        "main.system_detect.detect_distro": patch("main.system_detect.detect_distro", return_value="debian"),
        "main.system_detect.apache_info": patch(
            "main.system_detect.apache_info",
            return_value={"service": "apache2", "conf_dir": "/etc/apache2/sites-available"},
        ),
        "main.packages.install": patch("main.packages.install"),
        "main.vhost.exists": patch("main.vhost.exists", return_value=False),
        "main.vhost.create": patch("main.vhost.create", return_value="/etc/apache2/sites-available/x.conf"),
        "main.vhost.remove": patch("main.vhost.remove"),
        "main.vhost.reload_apache": patch("main.vhost.reload_apache"),
        "main.firewall_guard.temporarily_open": patch("main.firewall_guard.temporarily_open"),
        "main.certbot_ops.has_certificate": patch("main.certbot_ops.has_certificate", return_value=False),
        "main.certbot_ops.issue": patch("main.certbot_ops.issue"),
        "main.certbot_ops.renew": patch("main.certbot_ops.renew"),
        "main.certbot_ops.remove": patch("main.certbot_ops.remove"),
        "main.certbot_ops.days_until_expiry": patch("main.certbot_ops.days_until_expiry", return_value=60),
        "main.certbot_ops.list_domains": patch("main.certbot_ops.list_domains", return_value=["example.com"]),
        "main.cron.ensure_scheduled": patch("main.cron.ensure_scheduled", return_value=True),
        "main.cron.remove_scheduled": patch("main.cron.remove_scheduled", return_value=True),
    }
    for name, override in patches.items():
        defaults[name] = override

    mocks = {}
    started = []
    try:
        for name, p in defaults.items():
            mocks[name] = p.start()
            started.append(p)
        result = CliRunner().invoke(cli.cli_group(), args)
    finally:
        for p in started:
            p.stop()
    return result, mocks


class RootGateTest(unittest.TestCase):
    def test_setup_requires_root(self):
        result, _ = _invoke(["setup", "example.com"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("root", result.output.lower())

    def test_check_requires_root(self):
        result, _ = _invoke(["check"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)

    def test_renew_requires_root(self):
        result, _ = _invoke(["renew", "example.com"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)

    def test_reissue_requires_root(self):
        result, _ = _invoke(["reissue", "example.com"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)

    def test_remove_requires_root(self):
        result, _ = _invoke(["remove", "example.com", "--yes"], is_root=False)
        self.assertNotEqual(result.exit_code, 0)


class SetupCommandTest(unittest.TestCase):
    def test_rejects_an_invalid_domain(self):
        result, _ = _invoke(["setup", "../../etc/passwd"])
        self.assertNotEqual(result.exit_code, 0)

    def test_rejects_an_invalid_email(self):
        result, _ = _invoke(["setup", "example.com", "--email", "not-an-email"])
        self.assertNotEqual(result.exit_code, 0)

    def test_unsupported_distro_raises(self):
        result, _ = _invoke(
            ["setup", "example.com"],
            **{"main.system_detect.detect_distro": patch("main.system_detect.detect_distro", return_value=None)},
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_happy_path_issues_a_new_certificate_and_schedules_cron(self):
        result, mocks = _invoke(["setup", "example.com"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.packages.install"].assert_called_once_with("debian")
        mocks["main.vhost.create"].assert_called_once()
        mocks["main.certbot_ops.issue"].assert_called_once_with("example.com", "suporte@phonevox.com.br")
        mocks["main.cron.ensure_scheduled"].assert_called_once_with("apache2")

    def test_skips_vhost_creation_when_it_already_exists(self):
        result, mocks = _invoke(
            ["setup", "example.com"],
            **{"main.vhost.exists": patch("main.vhost.exists", return_value=True)},
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.vhost.create"].assert_not_called()

    def test_renews_instead_of_issuing_when_a_certificate_already_exists(self):
        result, mocks = _invoke(
            ["setup", "example.com"],
            **{"main.certbot_ops.has_certificate": patch("main.certbot_ops.has_certificate", return_value=True)},
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.certbot_ops.issue"].assert_not_called()
        mocks["main.certbot_ops.renew"].assert_called_once()

    def test_forces_renewal_when_close_to_expiry(self):
        result, mocks = _invoke(
            ["setup", "example.com"],
            **{
                "main.certbot_ops.has_certificate": patch("main.certbot_ops.has_certificate", return_value=True),
                "main.certbot_ops.days_until_expiry": patch("main.certbot_ops.days_until_expiry", return_value=5),
            },
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(mocks["main.certbot_ops.renew"].call_args.kwargs.get("force"))

    def test_custom_email_flag_is_used(self):
        result, mocks = _invoke(["setup", "example.com", "--email", "time@phonevox.com.br"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.certbot_ops.issue"].assert_called_once_with("example.com", "time@phonevox.com.br")

    def test_certbot_failure_is_reported_as_a_click_exception(self):
        import certbot_ops as certbot_ops_module

        result, _ = _invoke(
            ["setup", "example.com"],
            **{
                "main.certbot_ops.issue": patch(
                    "main.certbot_ops.issue", side_effect=certbot_ops_module.CertbotError("deu ruim"),
                ),
            },
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("deu ruim", result.output)


class CheckCommandTest(unittest.TestCase):
    def test_shows_days_left_for_a_single_domain(self):
        result, _ = _invoke(["check", "example.com"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("60", result.output)

    def test_lists_every_managed_domain_when_none_given(self):
        result, mocks = _invoke(
            ["check"],
            **{
                "main.certbot_ops.list_domains": patch(
                    "main.certbot_ops.list_domains", return_value=["a.com", "b.com"],
                ),
            },
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("a.com", result.output)
        self.assertIn("b.com", result.output)

    def test_message_when_nothing_is_managed_yet(self):
        result, _ = _invoke(
            ["check"], **{"main.certbot_ops.list_domains": patch("main.certbot_ops.list_domains", return_value=[])},
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("nenhum", result.output.lower())

    def test_shows_expired_wording_for_negative_days(self):
        result, _ = _invoke(
            ["check", "example.com"],
            **{"main.certbot_ops.days_until_expiry": patch("main.certbot_ops.days_until_expiry", return_value=-3)},
        )
        self.assertIn("expirado", result.output.lower())

    def _level_for(self, days_until_expiry):
        with patch("main.widgets.check_result") as mock_check_result:
            _invoke(
                ["check", "example.com"],
                **{
                    "main.certbot_ops.days_until_expiry": patch(
                        "main.certbot_ops.days_until_expiry", return_value=days_until_expiry,
                    ),
                },
            )
        return mock_check_result.call_args.args[1]

    def test_plenty_of_time_left_is_a_success(self):
        self.assertEqual(self._level_for(60), "ok")

    def test_close_to_the_renew_threshold_is_a_warning(self):
        self.assertEqual(self._level_for(15), "warn")

    def test_expired_is_an_error_not_just_a_warning(self):
        self.assertEqual(self._level_for(-3), "error")

    def test_no_certificate_issued_yet_is_a_warning_not_an_error(self):
        self.assertEqual(self._level_for(None), "warn")

    def test_nothing_managed_yet_is_a_warning(self):
        with patch("main.widgets.check_result") as mock_check_result:
            _invoke(
                ["check"],
                **{"main.certbot_ops.list_domains": patch("main.certbot_ops.list_domains", return_value=[])},
            )
        mock_check_result.assert_called_once()
        self.assertEqual(mock_check_result.call_args.args[1], "warn")


class RenewCommandTest(unittest.TestCase):
    def test_normal_renew_does_not_force(self):
        result, mocks = _invoke(["renew", "example.com"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.certbot_ops.renew"].assert_called_once_with("example.com", force=False)

    def test_reissue_forces(self):
        result, mocks = _invoke(["reissue", "example.com"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.certbot_ops.renew"].assert_called_once_with("example.com", force=True)

    def test_rejects_a_domain_with_no_managed_certificate(self):
        result, _ = _invoke(
            ["renew", "unknown.com"],
            **{"main.certbot_ops.list_domains": patch("main.certbot_ops.list_domains", return_value=["example.com"])},
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_reloads_apache_after_renewing(self):
        result, mocks = _invoke(["renew", "example.com"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.vhost.reload_apache"].assert_called_once_with("apache2")


class RemoveCommandTest(unittest.TestCase):
    def test_cancels_without_yes_when_confirm_declines(self):
        result, mocks = _invoke(["remove", "example.com"], **{"main.ask_confirm": patch("main.ask_confirm", return_value=False)})
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.certbot_ops.remove"].assert_not_called()

    def test_yes_flag_skips_confirmation(self):
        result, mocks = _invoke(["remove", "example.com", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.certbot_ops.remove"].assert_called_once_with("example.com")
        mocks["main.vhost.remove"].assert_called_once_with("/etc/apache2/sites-available", "example.com", "debian")

    def test_removes_the_cron_schedule_when_it_was_the_last_domain(self):
        # list_domains() é chamado 2x: valida o domínio antes de remover, confere se
        # sobrou algo depois -- a remoção de verdade que muda o resultado da 2a chamada.
        result, mocks = _invoke(
            ["remove", "example.com", "--yes"],
            **{
                "main.certbot_ops.list_domains": patch(
                    "main.certbot_ops.list_domains", side_effect=[["example.com"], []],
                ),
            },
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.cron.remove_scheduled"].assert_called_once()

    def test_keeps_the_cron_schedule_when_other_domains_remain(self):
        result, mocks = _invoke(
            ["remove", "example.com", "--yes"],
            **{
                "main.certbot_ops.list_domains": patch(
                    "main.certbot_ops.list_domains", side_effect=[["example.com", "other.com"], ["other.com"]],
                ),
            },
        )
        self.assertEqual(result.exit_code, 0, result.output)
        mocks["main.cron.remove_scheduled"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
