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


class PkgInstallTest(unittest.TestCase):
    @patch("os_ops.run_cmd", return_value=True)
    def test_batch_install_succeeds_in_one_call(self, mock_run_cmd):
        failed = os_ops.pkg_install(["a", "b", "c"])
        self.assertEqual(failed, [])
        mock_run_cmd.assert_called_once_with(["dnf", "install", "-y", "a", "b", "c"])

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
