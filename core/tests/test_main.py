import unittest
from unittest.mock import patch

from pvx.__main__ import main


class MainDispatchTest(unittest.TestCase):
    @patch("pvx.__main__.run_interactive")
    def test_no_args_enters_interactive_menu(self, mock_run_interactive):
        main(argv=[])
        mock_run_interactive.assert_called_once()

    @patch("pvx.__main__.cli")
    def test_with_args_dispatches_to_cli(self, mock_cli):
        main(argv=["--version"])
        mock_cli.main.assert_called_once_with(args=["--version"], prog_name="pvx")

    @patch("pvx.__main__.run_interactive", side_effect=KeyboardInterrupt)
    def test_ctrl_c_exits_cleanly_without_traceback(self, mock_run_interactive):
        main(argv=[])  # não deve levantar

    @patch("pvx.__main__.widgets.crash")
    @patch("pvx.__main__.cli")
    def test_unhandled_exception_in_direct_cli_shows_crash_and_exits_nonzero(self, mock_cli, mock_crash):
        # a mesma classe de bug do menu interativo, mas aqui: chamada direta
        # (`pvx <modulo> <comando>` sem terminal) tampouco tinha nenhum catch --
        # qualquer exceção não-ClickException de um módulo saía como traceback
        # cru, sem cor, indistinguível do resto da saída.
        mock_cli.main.side_effect = RuntimeError("algo quebrou de verdade")
        with self.assertRaises(SystemExit) as ctx:
            main(argv=["algum-modulo", "comando"])
        self.assertNotEqual(ctx.exception.code, 0)
        mock_crash.assert_called_once()
        self.assertIn("algo quebrou de verdade", mock_crash.call_args.args[0])

    @patch("pvx.__main__.widgets.crash")
    @patch("pvx.__main__.cli")
    def test_normal_system_exit_is_not_treated_as_a_crash(self, mock_cli, mock_crash):
        mock_cli.main.side_effect = SystemExit(0)
        with self.assertRaises(SystemExit) as ctx:
            main(argv=["--version"])
        self.assertEqual(ctx.exception.code, 0)
        mock_crash.assert_not_called()


if __name__ == "__main__":
    unittest.main()
