import unittest
from unittest.mock import MagicMock, patch

import os_ops


def _run_result(returncode=0):
    return MagicMock(returncode=returncode)


class RunCmdTest(unittest.TestCase):
    @patch("os_ops.subprocess.run")
    def test_delegates_to_subprocess_run(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        result = os_ops.run_cmd(["dnf", "install", "-y", "zabbix-agent2"])
        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["dnf", "install", "-y", "zabbix-agent2"], capture_output=True, text=True
        )

    @patch("os_ops.subprocess.run")
    def test_false_on_nonzero_exit(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertFalse(os_ops.run_cmd(["false"]))

    @patch("os_ops.subprocess.run", side_effect=FileNotFoundError())
    def test_false_when_the_executable_does_not_exist(self, mock_run):
        self.assertFalse(os_ops.run_cmd(["does-not-exist"]))

    @patch("os_ops.subprocess.run")
    def test_logs_the_real_stderr_on_failure_when_a_logger_is_given(self, mock_run):
        # achado ao vivo: falha de comando (ex.: yum sem repositório
        # alcançável) só virava "falha ao instalar X" genérico pro usuário --
        # o stderr de verdade nunca ia pra lugar nenhum, nem pro `pvx logs`.
        mock_run.return_value = MagicMock(returncode=1, stderr="repo não encontrado\n")
        logger = MagicMock()
        result = os_ops.run_cmd(["yum", "install", "-y", "pacote"], logger=logger, action="instalar pacote")
        self.assertFalse(result)
        logger.error.assert_called_once_with("instalar pacote: repo não encontrado")

    @patch("os_ops.subprocess.run")
    def test_does_not_log_on_success_even_with_a_logger(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        logger = MagicMock()
        self.assertTrue(os_ops.run_cmd(["yum", "install", "-y", "pacote"], logger=logger))
        logger.error.assert_not_called()

    @patch("os_ops.subprocess.run", side_effect=FileNotFoundError("[Errno 2] No such file or directory: 'yum'"))
    def test_logs_missing_executable_too(self, mock_run):
        logger = MagicMock()
        result = os_ops.run_cmd(["yum", "install", "-y", "pacote"], logger=logger, action="instalar pacote")
        self.assertFalse(result)
        logger.error.assert_called_once()
        self.assertIn("instalar pacote", logger.error.call_args.args[0])

    @patch("os_ops.subprocess.run")
    def test_verify_cmd_treats_an_already_satisfied_target_as_success(self, mock_run):
        # achado ao vivo: "yum install -y <rpm já instalado>" costuma sair
        # com código != 0 ("Nothing to do") mesmo o pacote já estando no
        # estado certo -- confia num comando de verdade (`rpm -q`), não no
        # texto do erro (muda com locale/versão do yum).
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="Error: Nothing to do\n"),
            MagicMock(returncode=0),
        ]
        logger = MagicMock()
        result = os_ops.run_cmd(
            ["yum", "install", "-y", "pacote"], logger=logger, verify_cmd=["rpm", "-q", "pacote"],
        )
        self.assertTrue(result)
        logger.error.assert_not_called()
        mock_run.assert_any_call(["rpm", "-q", "pacote"], capture_output=True, text=True)

    @patch("os_ops.subprocess.run")
    def test_verify_cmd_does_not_mask_a_genuine_failure(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="Error: repo indisponível\n"),
            MagicMock(returncode=1),
        ]
        result = os_ops.run_cmd(
            ["yum", "install", "-y", "pacote"], verify_cmd=["rpm", "-q", "pacote"],
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
