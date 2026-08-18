import unittest
from unittest.mock import MagicMock, patch

import os_ops


def _run_result(returncode=0):
    return MagicMock(returncode=returncode)


class MemTotalKbTest(unittest.TestCase):
    def test_sums_mem_total_and_swap_total(self, tmp_path=None):
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".meminfo") as f:
            f.write("MemTotal:       1000000 kB\nSwapTotal:        500000 kB\nOther: 1\n")
            path = f.name
        self.assertEqual(os_ops.mem_total_kb(path), 1500000)

    def test_returns_zero_when_file_missing(self):
        self.assertEqual(os_ops.mem_total_kb("/nonexistent/meminfo"), 0)


class RunCmdTest(unittest.TestCase):
    @patch("os_ops.subprocess.run")
    def test_delegates_to_subprocess_run(self, mock_run):
        mock_run.return_value = _run_result(returncode=0)
        result = os_ops.run_cmd(["dnf", "install", "-y", "vim"])
        self.assertTrue(result)
        mock_run.assert_called_once_with(["dnf", "install", "-y", "vim"], capture_output=True, text=True)

    @patch("os_ops.subprocess.run")
    def test_false_on_nonzero_exit(self, mock_run):
        mock_run.return_value = _run_result(returncode=1)
        self.assertFalse(os_ops.run_cmd(["false"]))

    @patch("os_ops.subprocess.run", side_effect=FileNotFoundError())
    def test_false_when_the_executable_does_not_exist(self, mock_run):
        # o bash original (`&> /dev/null`, sem checar $?) trata "command not found" como
        # falha muda -- nunca derruba o script. subprocess.run() levanta FileNotFoundError
        # nesse caso (diferente de "rodou e retornou erro", já tratado acima); sem capturar
        # isso aqui, um binário ainda não existente nessa etapa do fluxo (ex.: amportal
        # antes do issabel-firstboot rodar) crasha o processo inteiro em vez de só falhar.
        self.assertFalse(os_ops.run_cmd(["/usr/sbin/amportal", "chown"]))


def _fake_stdout(text):
    # simula leitura char a char de um pipe real -- termina com "" (EOF), igual
    # file.read(1) de verdade.
    return list(text) + [""]


class RunCmdStreamingTest(unittest.TestCase):
    # on_line dado -- transmite linha por linha (docker-build-style) em vez de esperar
    # o processo inteiro terminar pra devolver tudo de uma vez (subprocess.run padrão).
    @patch("os_ops.subprocess.Popen")
    def test_feeds_each_stdout_line_to_the_callback(self, mock_popen):
        proc = mock_popen.return_value
        proc.stdout.read.side_effect = _fake_stdout("linha 1\nlinha 2\n")
        proc.wait.return_value = None
        proc.returncode = 0
        lines = []
        result = os_ops.run_cmd(["dnf", "install", "-y", "vim"], on_line=lines.append)
        self.assertTrue(result)
        self.assertEqual(lines, ["linha 1", "linha 2"])
        mock_popen.assert_called_once_with(
            ["dnf", "install", "-y", "vim"], stdout=os_ops.subprocess.PIPE,
            stderr=os_ops.subprocess.STDOUT, text=True, bufsize=1,
        )

    @patch("os_ops.subprocess.Popen")
    def test_treats_a_bare_carriage_return_as_a_line_break_too(self, mock_popen):
        # dnf atualiza a MESMA linha de progresso via "\r" (sem "\n") -- sem tratar
        # isso também como quebra, o update só aparece quando o "\n" de verdade vem
        # (ex.: só quando aquele download termina), escondendo o progresso ao vivo.
        proc = mock_popen.return_value
        proc.stdout.read.side_effect = _fake_stdout("10%\r50%\r100%\ndone\n")
        proc.returncode = 0
        lines = []
        os_ops.run_cmd(["dnf", "install", "-y", "vim"], on_line=lines.append)
        self.assertEqual(lines, ["10%", "50%", "100%", "done"])

    @patch("os_ops.subprocess.Popen")
    def test_false_on_nonzero_exit(self, mock_popen):
        proc = mock_popen.return_value
        proc.stdout.read.side_effect = _fake_stdout("")
        proc.returncode = 1
        self.assertFalse(os_ops.run_cmd(["false"], on_line=lambda line: None))

    @patch("os_ops.subprocess.Popen", side_effect=FileNotFoundError())
    def test_false_when_the_executable_does_not_exist(self, mock_popen):
        self.assertFalse(os_ops.run_cmd(["/nonexistent"], on_line=lambda line: None))


class PkgInstallTest(unittest.TestCase):
    @patch("os_ops.run_cmd", return_value=True)
    def test_batch_install_succeeds_in_one_call(self, mock_run_cmd):
        failed = os_ops.pkg_install(["a", "b", "c"])
        self.assertEqual(failed, [])
        mock_run_cmd.assert_called_once_with(["dnf", "install", "-y", "a", "b", "c"], on_line=None)

    @patch("os_ops.run_cmd", return_value=True)
    def test_forwards_on_line_to_run_cmd(self, mock_run_cmd):
        on_line = lambda line: None
        os_ops.pkg_install(["a"], on_line=on_line)
        mock_run_cmd.assert_called_once_with(["dnf", "install", "-y", "a"], on_line=on_line)

    @patch("os_ops.run_cmd")
    def test_falls_back_to_per_package_on_batch_failure(self, mock_run_cmd):
        # 1a chamada (lote) falha; depois uma por pacote -- só "b" falha.
        mock_run_cmd.side_effect = [False, True, False, True]
        failed = os_ops.pkg_install(["a", "b", "c"])
        self.assertEqual(failed, ["b"])
        self.assertEqual(mock_run_cmd.call_count, 4)

    def test_empty_list_is_a_no_op(self):
        self.assertEqual(os_ops.pkg_install([]), [])


class GenPasswordTest(unittest.TestCase):
    def test_generates_24_char_alphanumeric_password_by_default(self):
        password = os_ops.gen_password()
        self.assertEqual(len(password), 24)
        self.assertTrue(password.isalnum())

    def test_never_repeats_between_calls(self):
        # senha aleatória por instalação -- nunca um default fixo/compartilhado (ao
        # contrário do resto dos defaults deste módulo, que são intencionalmente fixos).
        self.assertNotEqual(os_ops.gen_password(), os_ops.gen_password())


if __name__ == "__main__":
    unittest.main()
