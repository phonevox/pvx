import unittest
from unittest.mock import MagicMock

from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.keys import Keys

from pvx.interactive.inputs import _cancel_on_escape


class CancelOnEscapeTest(unittest.TestCase):
    def _assert_escape_triggers_keyboard_interrupt(self, question):
        merged = question.application.key_bindings
        bindings_for_escape = merged.get_bindings_for_keys((Keys.Escape,))
        self.assertEqual(len(bindings_for_escape), 1)

        event = MagicMock()
        bindings_for_escape[0].handler(event)
        event.app.exit.assert_called_once_with(exception=KeyboardInterrupt, style="class:aborting")

    def test_registers_escape_binding_on_plain_key_bindings(self):
        question = MagicMock()
        question.application.key_bindings = KeyBindings()

        _cancel_on_escape(question)

        self._assert_escape_triggers_keyboard_interrupt(question)

    def test_registers_escape_binding_on_already_merged_key_bindings(self):
        question = MagicMock()
        question.application.key_bindings = merge_key_bindings([KeyBindings()])

        _cancel_on_escape(question)

        self._assert_escape_triggers_keyboard_interrupt(question)


if __name__ == "__main__":
    unittest.main()
