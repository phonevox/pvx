import unittest
from unittest.mock import MagicMock

from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.keys import Keys

from pvx.interactive.inputs import _BACK, _ask


class AskTest(unittest.TestCase):
    def _question_with(self, unsafe_ask_return):
        question = MagicMock()
        question.application.key_bindings = KeyBindings()
        question.unsafe_ask.return_value = unsafe_ask_return
        return question

    def test_returns_the_underlying_answer_unchanged(self):
        question = self._question_with("escolhido")
        self.assertEqual(_ask(question), "escolhido")

    def test_back_sentinel_becomes_none(self):
        question = self._question_with(_BACK)
        self.assertIsNone(_ask(question))

    def test_registers_escape_binding_that_exits_with_back_sentinel(self):
        question = self._question_with("qualquer coisa")
        _ask(question, include_q=False)

        bindings = question.application.key_bindings.get_bindings_for_keys((Keys.Escape,))
        self.assertEqual(len(bindings), 1)

        event = MagicMock()
        bindings[0].handler(event)
        event.app.exit.assert_called_once_with(result=_BACK)

    def test_registers_q_binding_only_when_include_q_is_true(self):
        question = self._question_with("x")
        _ask(question, include_q=True)
        self.assertEqual(len(question.application.key_bindings.get_bindings_for_keys(("q",))), 1)

    def test_does_not_register_q_binding_by_default(self):
        question = self._question_with("x")
        _ask(question, include_q=False)
        self.assertEqual(len(question.application.key_bindings.get_bindings_for_keys(("q",))), 0)

    def test_works_when_original_bindings_are_already_merged(self):
        question = MagicMock()
        question.application.key_bindings = merge_key_bindings([KeyBindings()])
        question.unsafe_ask.return_value = "x"

        _ask(question)

        bindings = question.application.key_bindings.get_bindings_for_keys((Keys.Escape,))
        self.assertEqual(len(bindings), 1)

    def test_ctrl_c_is_not_caught_here_propagates_to_caller(self):
        question = MagicMock()
        question.application.key_bindings = KeyBindings()
        question.unsafe_ask.side_effect = KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            _ask(question)


if __name__ == "__main__":
    unittest.main()
