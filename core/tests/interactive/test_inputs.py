import unittest
from unittest.mock import patch

from pvx.interactive.inputs import ask_confirm, ask_select, ask_text


class AskSelectTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.select")
    def test_delegates_to_questionary_select(self, mock_select):
        mock_select.return_value.ask.return_value = "escolhido"
        result = ask_select("pvx >", ["a", "b"])
        self.assertEqual(result, "escolhido")
        mock_select.assert_called_once()


class AskConfirmTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.confirm")
    def test_delegates_to_questionary_confirm(self, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        result = ask_confirm("Remover?")
        self.assertTrue(result)
        mock_confirm.assert_called_once()


class AskTextTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.text")
    def test_delegates_to_questionary_text(self, mock_text):
        mock_text.return_value.ask.return_value = "valor digitado"
        result = ask_text("Nome:")
        self.assertEqual(result, "valor digitado")
        mock_text.assert_called_once()


if __name__ == "__main__":
    unittest.main()
