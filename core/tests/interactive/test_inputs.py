import unittest
from unittest.mock import patch

from pvx.interactive import inputs
from pvx.interactive.inputs import ask_checkbox, ask_confirm, ask_password, ask_select, ask_text


class AskSelectTest(unittest.TestCase):
    # ask_select() não passa mais por questionary.select() -- usa um
    # controle próprio (_ScrollableList + _run_scrollable, ver
    # test_scrollable_list.py) pra ter viewport limitado com scroll, que o
    # questionary não suporta. Aqui só testa a integração: escolhas certas
    # chegam no _ScrollableList, resultado e resumo saem certos.
    @patch("pvx.interactive.inputs._run_scrollable", return_value="a")
    def test_delegates_to_run_scrollable(self, mock_run):
        result = ask_select("pvx >", ["a", "b"])
        self.assertEqual(result, "a")
        mock_run.assert_called_once()

    @patch("pvx.interactive.inputs._run_scrollable", return_value="a")
    def test_builds_a_single_select_state_with_the_given_choices(self, mock_run):
        ask_select("pvx >", ["a", "b"], default="b")
        state = mock_run.call_args.args[1]
        self.assertFalse(state.multi)
        self.assertEqual([c.value for c in state.choices], ["a", "b"])
        self.assertEqual(state.pointed_at, 1)

    @patch("pvx.interactive.inputs._run_scrollable", return_value="a")
    def test_passes_the_nav_hint_text(self, mock_run):
        ask_select("pvx >", ["a", "b"])
        self.assertEqual(mock_run.call_args.args[2], inputs.NAV_HINT_TEXT)

    @patch("pvx.interactive.inputs._run_scrollable", return_value="a")
    def test_defaults_to_the_windowed_viewport(self, mock_run):
        ask_select("pvx >", ["a", "b"])
        state = mock_run.call_args.args[1]
        self.assertEqual(state.window_size, inputs._ScrollableList.WINDOW_SIZE)

    @patch("pvx.interactive.inputs._run_scrollable", return_value="a")
    def test_window_size_none_shows_the_full_classic_list(self, mock_run):
        # menu raiz pediu de volta a lista clássica sem scroll -- window_size
        # é o jeito de qualquer chamador optar por isso.
        ask_select("pvx >", ["a", "b"], window_size=None)
        state = mock_run.call_args.args[1]
        self.assertIsNone(state.window_size)

    @patch("pvx.interactive.inputs.widgets.select_answer")
    @patch("pvx.interactive.inputs._run_scrollable", return_value="b")
    def test_prints_the_chosen_title_as_the_answer(self, mock_run, mock_answer):
        # _run_scrollable devolve state.result() no fim -- o pointed_at do
        # state já reflete a escolha real nesse ponto (default="b" simula
        # isso sem precisar rodar o Application de verdade).
        ask_select("pvx >", ["a", "b"], default="b")
        mock_answer.assert_called_once_with("pvx >", "b")

    @patch("pvx.interactive.inputs.widgets.select_answer")
    @patch("pvx.interactive.inputs._run_scrollable", return_value=None)
    def test_does_not_print_an_answer_when_the_user_backs_out(self, mock_run, mock_answer):
        result = ask_select("pvx >", ["a", "b"])
        self.assertIsNone(result)
        mock_answer.assert_not_called()


class AskCheckboxTest(unittest.TestCase):
    @patch("pvx.interactive.inputs._run_scrollable", return_value=["a"])
    def test_delegates_to_run_scrollable(self, mock_run):
        result = ask_checkbox("Selecione:", ["a", "b", "c"])
        self.assertEqual(result, ["a"])
        mock_run.assert_called_once()

    @patch("pvx.interactive.inputs._run_scrollable", return_value=[])
    def test_builds_a_multi_select_state_with_defaults_pre_checked(self, mock_run):
        ask_checkbox("Selecione:", ["a", "b"], defaults=["a"])
        state = mock_run.call_args.args[1]
        self.assertTrue(state.multi)
        self.assertEqual(state.selected, {"a"})

    @patch("pvx.interactive.inputs._run_scrollable", return_value=[])
    def test_passes_the_checkbox_nav_hint_text(self, mock_run):
        ask_checkbox("Selecione:", ["a"])
        self.assertEqual(mock_run.call_args.args[2], inputs.CHECKBOX_NAV_HINT_TEXT)

    @patch("pvx.interactive.inputs.widgets.checkbox_answer")
    @patch("pvx.interactive.inputs._run_scrollable", return_value=["a", "b"])
    def test_prints_selected_values_instead_of_a_count(self, mock_run, mock_answer):
        ask_checkbox("Selecione:", ["a", "b", "c"])
        mock_answer.assert_called_once_with("Selecione:", ["a", "b"])

    @patch("pvx.interactive.inputs.widgets.checkbox_answer")
    @patch("pvx.interactive.inputs._run_scrollable", return_value=None)
    def test_does_not_print_answer_when_user_goes_back(self, mock_run, mock_answer):
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


class AskPasswordTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.password")
    def test_delegates_to_questionary_password(self, mock_password):
        mock_password.return_value.unsafe_ask.return_value = "hunter2"
        result = ask_password("Senha:")
        self.assertEqual(result, "hunter2")
        mock_password.assert_called_once()

    @patch("pvx.interactive.inputs.theme.current_style")
    @patch("pvx.interactive.inputs.questionary.password")
    def test_uses_current_theme(self, mock_password, mock_current_style):
        mock_password.return_value.unsafe_ask.return_value = "hunter2"
        ask_password("Senha:")
        self.assertIs(mock_password.call_args.kwargs["style"], mock_current_style.return_value)


if __name__ == "__main__":
    unittest.main()
