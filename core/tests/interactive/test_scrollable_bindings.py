import unittest
from unittest.mock import MagicMock

from prompt_toolkit.keys import Keys

from pvx.interactive.inputs import _ScrollableList, _build_bindings


class BuildBindingsTest(unittest.TestCase):
    def _handler_for(self, bindings, key):
        found = bindings.get_bindings_for_keys((key,))
        self.assertEqual(len(found), 1, f"esperava 1 binding pra {key}, achou {len(found)}")
        return found[0].handler

    def test_down_moves_the_pointer_forward(self):
        state = _ScrollableList(["a", "b"])
        handler = self._handler_for(_build_bindings(state), Keys.Down)
        handler(MagicMock())
        self.assertEqual(state.pointed_at, 1)

    def test_up_moves_the_pointer_back(self):
        state = _ScrollableList(["a", "b"])
        handler = self._handler_for(_build_bindings(state), Keys.Up)
        handler(MagicMock())
        self.assertEqual(state.pointed_at, 1)  # wrap

    def test_enter_exits_with_the_current_result(self):
        state = _ScrollableList(["a", "b"], default="b")
        handler = self._handler_for(_build_bindings(state), Keys.ControlM)
        event = MagicMock()
        handler(event)
        event.app.exit.assert_called_once_with(result="b")

    def test_escape_exits_with_none(self):
        state = _ScrollableList(["a", "b"])
        handler = self._handler_for(_build_bindings(state), Keys.Escape)
        event = MagicMock()
        handler(event)
        event.app.exit.assert_called_once_with(result=None)

    def test_q_exits_with_none_when_enabled(self):
        state = _ScrollableList(["a", "b"])
        bindings = _build_bindings(state, qmark_binding_for_back=True)
        handler = self._handler_for(bindings, "q")
        event = MagicMock()
        handler(event)
        event.app.exit.assert_called_once_with(result=None)

    def test_q_binding_is_absent_when_disabled(self):
        # checkbox nunca usa "q" pra voltar -- letras ficam livres se algum
        # dia usar busca por digitação.
        state = _ScrollableList(["a", "b"], multi=True)
        bindings = _build_bindings(state, qmark_binding_for_back=False)
        self.assertEqual(bindings.get_bindings_for_keys(("q",)), [])

    def test_ctrl_c_exits_with_keyboard_interrupt_not_swallowed(self):
        state = _ScrollableList(["a", "b"])
        handler = self._handler_for(_build_bindings(state), Keys.ControlC)
        event = MagicMock()
        handler(event)
        self.assertEqual(event.app.exit.call_args.kwargs["exception"], KeyboardInterrupt)

    def test_space_toggles_only_in_multi_mode(self):
        state = _ScrollableList(["a", "b"], multi=True)
        handler = self._handler_for(_build_bindings(state), " ")
        handler(MagicMock())
        self.assertEqual(state.result(), ["a"])

    def test_space_is_not_bound_in_single_select_mode(self):
        state = _ScrollableList(["a", "b"])
        bindings = _build_bindings(state)
        self.assertEqual(bindings.get_bindings_for_keys((" ",)), [])


if __name__ == "__main__":
    unittest.main()
