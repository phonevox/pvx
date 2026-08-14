import unittest
from unittest.mock import patch

import questionary

from pvx.interactive.inputs import ask_confirm, ask_select, ask_text


class AskSelectTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.select")
    def test_delegates_to_questionary_select(self, mock_select):
        mock_select.return_value.ask.return_value = "escolhido"
        result = ask_select("pvx >", ["a", "b"])
        self.assertEqual(result, "escolhido")
        mock_select.assert_called_once()

    @patch("pvx.interactive.inputs.questionary.select")
    def test_suppresses_default_instruction_and_appends_hint_separator(self, mock_select):
        mock_select.return_value.ask.return_value = "a"
        ask_select("pvx >", ["a", "b"])

        _, kwargs = mock_select.call_args
        self.assertEqual(kwargs["instruction"], "")

        choices = kwargs["choices"]
        self.assertEqual(choices[:2], ["a", "b"])
        self.assertIsInstance(choices[-1], questionary.Separator)

    @patch("pvx.interactive.inputs.theme.current_style")
    @patch("pvx.interactive.inputs.questionary.select")
    def test_uses_current_theme(self, mock_select, mock_current_style):
        mock_select.return_value.ask.return_value = "a"
        ask_select("pvx >", ["a", "b"])
        self.assertIs(mock_select.call_args.kwargs["style"], mock_current_style.return_value)


class AskConfirmTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.confirm")
    def test_delegates_to_questionary_confirm(self, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        result = ask_confirm("Remover?")
        self.assertTrue(result)
        mock_confirm.assert_called_once()

    @patch("pvx.interactive.inputs.theme.current_style")
    @patch("pvx.interactive.inputs.questionary.confirm")
    def test_uses_current_theme(self, mock_confirm, mock_current_style):
        mock_confirm.return_value.ask.return_value = True
        ask_confirm("Remover?")
        self.assertIs(mock_confirm.call_args.kwargs["style"], mock_current_style.return_value)


class AskTextTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.text")
    def test_delegates_to_questionary_text(self, mock_text):
        mock_text.return_value.ask.return_value = "valor digitado"
        result = ask_text("Nome:")
        self.assertEqual(result, "valor digitado")
        mock_text.assert_called_once()

    @patch("pvx.interactive.inputs.theme.current_style")
    @patch("pvx.interactive.inputs.questionary.text")
    def test_uses_current_theme(self, mock_text, mock_current_style):
        mock_text.return_value.ask.return_value = "valor digitado"
        ask_text("Nome:")
        self.assertIs(mock_text.call_args.kwargs["style"], mock_current_style.return_value)


if __name__ == "__main__":
    unittest.main()
