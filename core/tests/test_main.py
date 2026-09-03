import unittest
from unittest.mock import patch

import click

from pvx.__main__ import main


@patch("pvx.__main__.migration.migrate_legacy_modules")
class MainDispatchTest(unittest.TestCase):
    @patch("pvx.__main__.run_interactive")
    def test_no_args_enters_interactive_menu(self, mock_run_interactive, mock_migrate):
        main(argv=[])
        mock_run_interactive.assert_called_once()

    @patch("pvx.__main__.cli")
    def test_with_args_dispatches_to_cli(self, mock_cli, mock_migrate):
        main(argv=["--version"])
        mock_cli.main.assert_called_once_with(args=["--version"], prog_name="pvx")

    @patch("pvx.__main__.run_interactive", side_effect=KeyboardInterrupt)
    def test_ctrl_c_exits_cleanly_without_traceback(self, mock_run_interactive, mock_migrate):
        main(argv=[])  # não deve levantar

    @patch("pvx.__main__.run_interactive", side_effect=click.exceptions.Abort)
    def test_abort_from_deep_inside_the_menu_exits_cleanly_without_traceback(self, mock_run_interactive, mock_migrate):
        # ctrl-c num prompt (ask_password/ask_text) dentro de um comando de
        # módulo vira click.exceptions.Abort, não KeyboardInterrupt puro (ver
        # BaseCommand.main() do click) -- precisa do mesmo tratamento limpo.
        main(argv=[])  # não deve levantar

    @patch("pvx.__main__.widgets.crash")
    @patch("pvx.__main__.cli")
    def test_unhandled_exception_in_direct_cli_shows_crash_and_exits_nonzero(self, mock_cli, mock_crash, mock_migrate):
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
    def test_normal_system_exit_is_not_treated_as_a_crash(self, mock_cli, mock_crash, mock_migrate):
        mock_cli.main.side_effect = SystemExit(0)
        with self.assertRaises(SystemExit) as ctx:
            main(argv=["--version"])
        self.assertEqual(ctx.exception.code, 0)
        mock_crash.assert_not_called()


class MigrateLegacyStateTest(unittest.TestCase):
    # housekeeping best-effort -- nunca pode travar o uso normal do pvx.
    @patch("pvx.__main__.run_interactive")
    @patch("pvx.__main__.migration.migrate_legacy_modules")
    @patch("pvx.__main__.os.geteuid", return_value=0)
    def test_migrates_when_running_as_root(self, mock_geteuid, mock_migrate, mock_run_interactive):
        main(argv=[])
        mock_migrate.assert_called_once_with()

    @patch("pvx.__main__.run_interactive")
    @patch("pvx.__main__.migration.migrate_legacy_modules")
    @patch("pvx.__main__.os.geteuid", return_value=1000)
    def test_skips_migration_when_not_root(self, mock_geteuid, mock_migrate, mock_run_interactive):
        main(argv=[])
        mock_migrate.assert_not_called()

    @patch("pvx.__main__.run_interactive")
    @patch("pvx.__main__.migration.migrate_legacy_modules", side_effect=RuntimeError("disco cheio"))
    @patch("pvx.__main__.os.geteuid", return_value=0)
    def test_a_migration_failure_never_blocks_normal_usage(self, mock_geteuid, mock_migrate, mock_run_interactive):
        main(argv=[])  # não deve levantar
        mock_run_interactive.assert_called_once()

    @patch("pvx.__main__.cli")
    @patch("pvx.__main__.migration.migrate_legacy_modules")
    @patch("pvx.__main__.os.geteuid", return_value=0)
    def test_also_migrates_before_a_direct_cli_call(self, mock_geteuid, mock_migrate, mock_cli):
        main(argv=["--version"])
        mock_migrate.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
