import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import integrations


def _run_result(returncode=0, stdout="", stderr=""):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class IsModuleInstalledTest(unittest.TestCase):
    def test_false_when_manifest_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("integrations.pvx_config.modules_dir", return_value=Path(tmp)):
                self.assertFalse(integrations.is_module_installed("qint"))

    def test_true_when_manifest_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            module_dir = Path(tmp) / "qint"
            module_dir.mkdir()
            (module_dir / "manifest.json").write_text("{}")
            with patch("integrations.pvx_config.modules_dir", return_value=Path(tmp)):
                self.assertTrue(integrations.is_module_installed("qint"))


class EnsureModuleInstalledTest(unittest.TestCase):
    @patch("integrations.is_module_installed", return_value=True)
    @patch("integrations.subprocess.run")
    def test_skips_install_when_already_present(self, mock_run, mock_installed):
        self.assertTrue(integrations.ensure_module_installed("qint"))
        mock_run.assert_not_called()

    @patch("integrations.is_module_installed", return_value=False)
    @patch("integrations.subprocess.run")
    def test_installs_via_pvx_module_install_when_missing(self, mock_run, mock_installed):
        mock_run.return_value = _run_result(returncode=0)
        self.assertTrue(integrations.ensure_module_installed("qint", pvx_bin="pvx"))
        mock_run.assert_called_once_with(
            ["pvx", "module", "install", "qint", "--yes"], capture_output=True, text=True
        )

    @patch("integrations.is_module_installed", return_value=False)
    @patch("integrations.subprocess.run")
    def test_reports_failure_when_install_fails(self, mock_run, mock_installed):
        mock_run.return_value = _run_result(returncode=1, stderr="rede indisponível")
        self.assertFalse(integrations.ensure_module_installed("qint"))


class RunSshHardeningTest(unittest.TestCase):
    @patch("integrations.ensure_module_installed", return_value=False)
    def test_fails_fast_when_module_cannot_be_installed(self, mock_ensure):
        result = integrations.run_ssh_hardening({})
        self.assertFalse(result["ok"])

    @patch("integrations.subprocess.run")
    @patch("integrations.ensure_module_installed", return_value=True)
    def test_builds_full_apply_args_from_config(self, mock_ensure, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        config = {
            "lock_root": True, "root_password": "phonevox@@",
            "create_user": True, "username": "phonevox", "pubkey": "ssh-rsa AAAA... x",
            "allow_password": False,
            "change_port": True, "port": "21122",
        }
        result = integrations.run_ssh_hardening(config, pvx_bin="pvx")
        self.assertTrue(result["ok"])
        args = mock_run.call_args.args[0]
        self.assertEqual(args[:3], ["pvx", "ssh-hardening", "apply"])
        self.assertIn("--yes", args)
        self.assertIn("--lock-root", args)
        self.assertIn("phonevox@@", args)
        self.assertIn("--create-user", args)
        self.assertIn("--no-allow-password", args)
        self.assertIn("--change-port", args)
        self.assertIn("21122", args)

    @patch("integrations.subprocess.run")
    @patch("integrations.ensure_module_installed", return_value=True)
    def test_disabled_options_use_the_negative_flags(self, mock_ensure, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        config = {"lock_root": False, "create_user": False, "change_port": False}
        integrations.run_ssh_hardening(config)
        args = mock_run.call_args.args[0]
        self.assertIn("--no-lock-root", args)
        self.assertIn("--no-create-user", args)
        self.assertIn("--no-change-port", args)


class RunFirewallSyncTest(unittest.TestCase):
    @patch("integrations.ensure_module_installed", return_value=False)
    def test_fails_fast_when_module_cannot_be_installed(self, mock_ensure):
        result = integrations.run_firewall_sync()
        self.assertFalse(result["ok"])

    @patch("integrations.subprocess.run")
    @patch("integrations.ensure_module_installed", return_value=True)
    def test_syncs_forcefully_and_non_interactively(self, mock_ensure, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        result = integrations.run_firewall_sync(pvx_bin="pvx")
        self.assertTrue(result["ok"])
        mock_run.assert_called_once_with(
            ["pvx", "firewall", "sync", "--yes", "--force"], capture_output=True, text=True
        )


class RunQintTest(unittest.TestCase):
    @patch("integrations.ensure_module_installed", return_value=False)
    def test_fails_fast_when_module_cannot_be_installed(self, mock_ensure):
        result = integrations.run_qint({"tipo": "ixcsoft"})
        self.assertFalse(result["ok"])

    @patch("integrations.subprocess.run")
    @patch("integrations.ensure_module_installed", return_value=True)
    def test_prepares_then_applies(self, mock_ensure, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        config = {
            "tipo": "ixcsoft", "sftp": "root@10.0.0.1:2222", "url": "https://erp.example.com",
            "token": "abc123", "timecondition_out": "500",
        }
        result = integrations.run_qint(config, pvx_bin="pvx")
        self.assertTrue(result["ok"])
        self.assertEqual(mock_run.call_count, 2)

        prepare_args = mock_run.call_args_list[0].args[0]
        self.assertEqual(prepare_args[:3], ["pvx", "qint", "prepare"])
        self.assertIn("ixcsoft", prepare_args)
        self.assertIn("--sftp", prepare_args)
        self.assertIn("root@10.0.0.1:2222", prepare_args)
        self.assertIn("--timecondition-out", prepare_args)

        apply_args = mock_run.call_args_list[1].args[0]
        self.assertEqual(apply_args, ["pvx", "qint", "apply", "--yes"])

    @patch("integrations.subprocess.run")
    @patch("integrations.ensure_module_installed", return_value=True)
    def test_does_not_apply_when_prepare_fails(self, mock_ensure, mock_run):
        mock_run.return_value = _run_result(returncode=1, stderr="URL inválida")
        result = integrations.run_qint({"tipo": "ixcsoft", "url": "sem-protocolo"})
        self.assertFalse(result["ok"])
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
