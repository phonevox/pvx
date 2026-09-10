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
        result = _invoke(["checklist", "phonevox"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("issabel", result.output.lower())

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_shows_a_title_header(self, mock_is_issabel, mock_run_all):
        result = _invoke(["checklist", "phonevox"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("pvx > utilidades > checklist phonevox", result.output)

    @patch(
        "main.checklist_phonevox.run_all",
        return_value=[
            {"section": "SSL", "level": "ok", "text": "central.example.com expira em 60 dia(s)"},
            {"section": "Autobackup", "level": "warn", "text": "não configurado"},
        ],
    )
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_shows_a_section_and_a_check_result_line_per_item(self, mock_is_issabel, mock_run_all):
        with patch("main.widgets.section") as mock_section, patch("main.widgets.check_result") as mock_check_result:
            _invoke(["checklist", "phonevox"])

        self.assertEqual([c.args[0] for c in mock_section.call_args_list], ["SSL", "Autobackup"])
        self.assertEqual(mock_check_result.call_count, 2)
        first_text, first_level = mock_check_result.call_args_list[0].args
        self.assertIn("60 dia(s)", first_text)
        self.assertEqual(first_level, "ok")
        second_text, second_level = mock_check_result.call_args_list[1].args
        self.assertIn("não configurado", second_text)
        self.assertEqual(second_level, "warn")

    @patch(
        "main.checklist_phonevox.run_all",
        return_value=[
            {"section": "Zabbix", "level": "ok", "text": "hostname=vps-x"},
            {"section": "Zabbix", "level": "warn", "text": "script de auditoria não adicionado"},
        ],
    )
    @patch("main.issabel_detect.is_issabel", return_value=True)
    def test_adjacent_items_of_the_same_section_share_a_single_header(self, mock_is_issabel, mock_run_all):
        with patch("main.widgets.section") as mock_section, patch("main.widgets.check_result") as mock_check_result:
            _invoke(["checklist", "phonevox"])

        mock_section.assert_called_once_with("Zabbix")
        self.assertEqual(mock_check_result.call_count, 2)

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    @patch("main.widgets.pause")
    def test_pauses_when_interactive(self, mock_pause, mock_is_issabel, mock_run_all):
        _invoke(["checklist", "phonevox"], is_tty=True)
        mock_pause.assert_called_once_with()

    @patch("main.checklist_phonevox.run_all", return_value=[])
    @patch("main.issabel_detect.is_issabel", return_value=True)
    @patch("main.widgets.pause")
    def test_does_not_pause_when_not_interactive(self, mock_pause, mock_is_issabel, mock_run_all):
        _invoke(["checklist", "phonevox"], is_tty=False)
        mock_pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
