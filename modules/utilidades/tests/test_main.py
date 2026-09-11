import unittest
from unittest.mock import patch

from click.testing import CliRunner

from main import cli


def _invoke(args, is_tty=False):
    with patch("main._is_interactive", return_value=is_tty):
        return CliRunner().invoke(cli.cli_group(), args)


class ChecklistPhonevoxCommandTest(unittest.TestCase):
    @patch("main.issabel_detect.is_issabel", return_value=False)
    def test_refuses_outside_issabel(self, mock_is_issabel):
        result = _invoke(["checks-phonevox"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("issabel", result.output.lower())

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_shows_a_title_header(self, mock_is_issabel, mock_run_all):
        result = _invoke(["checks-phonevox"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("pvx > utilidades > checks-phonevox", result.output)

    @patch(
        "main.checklist_phonevox.run_all",
        return_value=[
            {"section": "SSL", "level": "ok", "text": "central.example.com expira em 60 dia(s)"},
            {"section": "Autobackup", "level": "warn", "text": "não configurado"},
        ],
    )
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_shows_a_table_with_a_row_per_item(self, mock_is_issabel, mock_run_all):
        with patch("main.widgets.table") as mock_table, patch("main.widgets.status_cell", side_effect=lambda lvl: lvl):
            _invoke(["checks-phonevox"])

        mock_table.assert_called_once()
        columns, rows = mock_table.call_args.args
        self.assertEqual(columns, ["Seção", "Detalhe", "Status"])
        self.assertEqual(rows, [
            ["SSL", "central.example.com expira em 60 dia(s)", "ok"],
            ["Autobackup", "não configurado", "warn"],
        ])

    @patch(
        "main.checklist_phonevox.run_all",
        return_value=[
            {"section": "Zabbix", "level": "ok", "text": "hostname=vps-x"},
            {"section": "Zabbix", "level": "warn", "text": "script de auditoria não adicionado"},
        ],
    )
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_adjacent_items_of_the_same_section_repeat_the_section_name(self, mock_is_issabel, mock_run_all):
        with patch("main.widgets.table") as mock_table, patch("main.widgets.status_cell", side_effect=lambda lvl: lvl):
            _invoke(["checks-phonevox"])

        _, rows = mock_table.call_args.args
        self.assertEqual([row[0] for row in rows], ["Zabbix", "Zabbix"])

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause, mock_is_issabel, mock_run_all):
        _invoke(["checks-phonevox"], is_tty=True)
        mock_pause.assert_called_once_with()

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause, mock_is_issabel, mock_run_all):
        _invoke(["checks-phonevox"], is_tty=False)
        mock_pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
