import unittest
from unittest.mock import patch

import questionary

from pvx.interactive import inputs
from pvx.interactive.inputs import ask_checkbox, ask_confirm, ask_select, ask_text


class AskSelectTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.select")
    def test_delegates_to_questionary_select(self, mock_select):
        mock_select.return_value.unsafe_ask.return_value = "escolhido"
        result = ask_select("pvx >", ["a", "b"])
        self.assertEqual(result, "escolhido")
        mock_select.assert_called_once()

    @patch("pvx.interactive.inputs.questionary.select")
    def test_suppresses_default_instruction_and_appends_hint_separator(self, mock_select):
        mock_select.return_value.unsafe_ask.return_value = "a"
        ask_select("pvx >", ["a", "b"])

        _, kwargs = mock_select.call_args
        self.assertEqual(kwargs["instruction"], "")

        choices = kwargs["choices"]
        self.assertEqual(choices[:2], ["a", "b"])
        self.assertIsInstance(choices[-1], questionary.Separator)

    @patch("pvx.interactive.inputs.theme.current_style")
    @patch("pvx.interactive.inputs.questionary.select")
    def test_uses_current_theme(self, mock_select, mock_current_style):
        mock_select.return_value.unsafe_ask.return_value = "a"
        ask_select("pvx >", ["a", "b"])
        self.assertIs(mock_select.call_args.kwargs["style"], mock_current_style.return_value)


class AskCheckboxTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.checkbox")
    def test_delegates_to_questionary_checkbox(self, mock_checkbox):
        mock_checkbox.return_value.unsafe_ask.return_value = ["a", "b"]
        result = ask_checkbox("Selecione:", ["a", "b", "c"])
        self.assertEqual(result, ["a", "b"])
        mock_checkbox.assert_called_once()

    @patch("pvx.interactive.inputs.questionary.checkbox")
    def test_marks_defaults_as_pre_checked(self, mock_checkbox):
        mock_checkbox.return_value.unsafe_ask.return_value = ["a"]
        ask_checkbox("Selecione:", ["a", "b"], defaults=["a"])
        passed_choices = mock_checkbox.call_args.kwargs["choices"]
        checked_values = [c.value for c in passed_choices if c.checked]
        self.assertEqual(checked_values, ["a"])

    @patch("pvx.interactive.inputs.theme.current_style")
    @patch("pvx.interactive.inputs.questionary.checkbox")
    def test_uses_current_theme(self, mock_checkbox, mock_current_style):
        mock_checkbox.return_value.unsafe_ask.return_value = []
        ask_checkbox("Selecione:", ["a"])
        self.assertIs(mock_checkbox.call_args.kwargs["style"], mock_current_style.return_value)

    @patch("pvx.interactive.inputs.questionary.checkbox")
    def test_appends_hint_separator_explaining_the_navigation(self, mock_checkbox):
        # usuário leigo reclamou de não entender a navegação (breadcrumb sozinho não
        # deixava claro) -- mesmo padrão de ask_select(), adaptado pro que existe aqui
        # (espaço marca; sem "q" -- questionary não trata isso na checkbox).
        mock_checkbox.return_value.unsafe_ask.return_value = []
        ask_checkbox("Selecione:", ["a", "b"])
        choices = mock_checkbox.call_args.kwargs["choices"]
        self.assertIsInstance(choices[-1], questionary.Separator)

    @patch("pvx.interactive.inputs.questionary.checkbox")
    def test_erases_default_done_line_so_it_can_print_its_own(self, mock_checkbox):
        # questionary não tem parâmetro pra customizar o "done (N selections)" --
        # erase_when_done repassa pro prompt_toolkit.Application e apaga a linha de
        # resposta padrão inteira ao sair, sobrando só a nossa (widgets.checkbox_answer).
        mock_checkbox.return_value.unsafe_ask.return_value = []
        ask_checkbox("Selecione:", ["a", "b"])
        self.assertTrue(mock_checkbox.call_args.kwargs["erase_when_done"])

    @patch("pvx.interactive.inputs.widgets.checkbox_answer")
    @patch("pvx.interactive.inputs.questionary.checkbox")
    def test_prints_selected_values_instead_of_a_count(self, mock_checkbox, mock_answer):
        mock_checkbox.return_value.unsafe_ask.return_value = ["a", "b"]
        ask_checkbox("Selecione:", ["a", "b", "c"])
        mock_answer.assert_called_once_with("Selecione:", ["a", "b"])

    @patch("pvx.interactive.inputs.widgets.checkbox_answer")
    @patch("pvx.interactive.inputs.questionary.checkbox")
    def test_does_not_print_answer_when_user_goes_back(self, mock_checkbox, mock_answer):
        mock_checkbox.return_value.unsafe_ask.return_value = inputs._BACK
        result = ask_checkbox("Selecione:", ["a", "b"])
        self.assertIsNone(result)
        mock_answer.assert_not_called()


class AskConfirmTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.confirm")
    def test_delegates_to_questionary_confirm(self, mock_confirm):
        mock_confirm.return_value.unsafe_ask.return_value = True
        result = ask_confirm("Remover?")
        self.assertTrue(result)
        mock_confirm.assert_called_once()

    @patch("pvx.interactive.inputs.theme.current_style")
    @patch("pvx.interactive.inputs.questionary.confirm")
    def test_uses_current_theme(self, mock_confirm, mock_current_style):
        mock_confirm.return_value.unsafe_ask.return_value = True
        ask_confirm("Remover?")
        self.assertIs(mock_confirm.call_args.kwargs["style"], mock_current_style.return_value)


class AskTextTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.text")
    def test_delegates_to_questionary_text(self, mock_text):
        mock_text.return_value.unsafe_ask.return_value = "valor digitado"
        result = ask_text("Nome:")
        self.assertEqual(result, "valor digitado")
        mock_text.assert_called_once()

    @patch("pvx.interactive.inputs.theme.current_style")
    @patch("pvx.interactive.inputs.questionary.text")
    def test_uses_current_theme(self, mock_text, mock_current_style):
        mock_text.return_value.unsafe_ask.return_value = "valor digitado"
        ask_text("Nome:")
        self.assertIs(mock_text.call_args.kwargs["style"], mock_current_style.return_value)


if __name__ == "__main__":
    unittest.main()
