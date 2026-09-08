import unittest
from datetime import datetime, timezone
from subprocess import CompletedProcess
from unittest.mock import patch

import certbot_ops


class HasCertificateTest(unittest.TestCase):
    @patch("certbot_ops.os.path.exists", return_value=True)
    def test_true_when_fullchain_present(self, mock_exists):
        self.assertTrue(certbot_ops.has_certificate("example.com"))
        mock_exists.assert_called_once_with("/etc/letsencrypt/live/example.com/fullchain.pem")

    @patch("certbot_ops.os.path.exists", return_value=False)
    def test_false_when_absent(self, mock_exists):
        self.assertFalse(certbot_ops.has_certificate("example.com"))


class ListDomainsTest(unittest.TestCase):
    @patch("certbot_ops.os.path.isdir")
    @patch("certbot_ops.os.listdir")
    def test_lists_only_directories_and_skips_the_readme(self, mock_listdir, mock_isdir):
        mock_listdir.return_value = ["README", "example.com", "central.falevox.com.br"]
        mock_isdir.side_effect = lambda p: not p.endswith("README")
        self.assertEqual(
            certbot_ops.list_domains(),
            ["central.falevox.com.br", "example.com"],
        )

    @patch("certbot_ops.os.path.isdir", return_value=False)
    def test_empty_when_letsencrypt_dir_missing(self, mock_isdir):
        self.assertEqual(certbot_ops.list_domains(), [])


class DaysUntilExpiryTest(unittest.TestCase):
    @patch("certbot_ops.has_certificate", return_value=False)
    def test_none_when_no_certificate(self, mock_has_cert):
        self.assertIsNone(certbot_ops.days_until_expiry("example.com"))

    @patch("certbot_ops.subprocess.run")
    @patch("certbot_ops.has_certificate", return_value=True)
    def test_computes_days_remaining_from_openssl_output(self, mock_has_cert, mock_run):
        mock_run.return_value = CompletedProcess(
            args=[], returncode=0, stdout="notAfter=Nov 10 12:00:00 2026 GMT\n", stderr="",
        )
        now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(certbot_ops.days_until_expiry("example.com", now=now), 9)

    @patch("certbot_ops.subprocess.run")
    @patch("certbot_ops.has_certificate", return_value=True)
    def test_negative_when_already_expired(self, mock_has_cert, mock_run):
        mock_run.return_value = CompletedProcess(
            args=[], returncode=0, stdout="notAfter=Nov 10 12:00:00 2026 GMT\n", stderr="",
        )
        now = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(certbot_ops.days_until_expiry("example.com", now=now), -10)

    @patch("certbot_ops.subprocess.run")
    @patch("certbot_ops.has_certificate", return_value=True)
    def test_raises_when_openssl_fails(self, mock_has_cert, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with self.assertRaises(certbot_ops.CertbotError):
            certbot_ops.days_until_expiry("example.com")


class IssueTest(unittest.TestCase):
    @patch("certbot_ops.subprocess.run")
    def test_calls_certbot_with_domain_and_email(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        certbot_ops.issue("example.com", "suporte@phonevox.com.br")
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "certbot")
        self.assertIn("-d", args)
        self.assertIn("example.com", args)
        self.assertIn("--email", args)
        self.assertIn("suporte@phonevox.com.br", args)

    @patch("certbot_ops.subprocess.run")
    def test_raises_certbot_error_on_failure(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="", stderr="deu ruim")
        with self.assertRaises(certbot_ops.CertbotError):
            certbot_ops.issue("example.com", "suporte@phonevox.com.br")


class RenewTest(unittest.TestCase):
    @patch("certbot_ops.subprocess.run")
    def test_normal_renew_does_not_force(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        certbot_ops.renew("example.com")
        args = mock_run.call_args.args[0]
        self.assertIn("--cert-name", args)
        self.assertIn("example.com", args)
        self.assertNotIn("--force-renewal", args)

    @patch("certbot_ops.subprocess.run")
    def test_forced_renew_passes_force_renewal(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        certbot_ops.renew("example.com", force=True)
        args = mock_run.call_args.args[0]
        self.assertIn("--force-renewal", args)


class RemoveTest(unittest.TestCase):
    @patch("certbot_ops.subprocess.run")
    def test_calls_certbot_delete_non_interactive(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        certbot_ops.remove("example.com")
        args = mock_run.call_args.args[0]
        self.assertEqual(args[:2], ["certbot", "delete"])
        self.assertIn("--cert-name", args)
        self.assertIn("example.com", args)
        self.assertIn("--non-interactive", args)

    @patch("certbot_ops.subprocess.run")
    def test_raises_on_failure(self, mock_run):
        mock_run.return_value = CompletedProcess(args=[], returncode=1, stdout="", stderr="falhou")
        with self.assertRaises(certbot_ops.CertbotError):
            certbot_ops.remove("example.com")


if __name__ == "__main__":
    unittest.main()
