import unittest

import questionary

from pvx.interactive.inputs import _ScrollableList


def _choices(n):
    return [f"item{i}" for i in range(n)]


class InitialPointerTest(unittest.TestCase):
    def test_starts_at_the_first_item_by_default(self):
        state = _ScrollableList(_choices(3))
        self.assertEqual(state.pointed_at, 0)

    def test_starts_at_the_default_value_when_given(self):
        state = _ScrollableList(_choices(5), default="item3")
        self.assertEqual(state.pointed_at, 3)

    def test_skips_separators_when_picking_the_first_item(self):
        choices = [questionary.Separator("---"), "a", "b"]
        state = _ScrollableList(choices)
        self.assertEqual(state.pointed_at, 1)

    def test_empty_choices_does_not_crash(self):
        state = _ScrollableList([])
        self.assertEqual(state.pointed_at, 0)
        self.assertEqual(state.result(), None)


class NavigationTest(unittest.TestCase):
    def test_move_down_advances_one_item(self):
        state = _ScrollableList(_choices(3))
        state.move_down()
        self.assertEqual(state.pointed_at, 1)

    def test_move_up_wraps_to_the_last_item(self):
        state = _ScrollableList(_choices(3))
        state.move_up()
        self.assertEqual(state.pointed_at, 2)

    def test_move_down_wraps_to_the_first_item(self):
        state = _ScrollableList(_choices(3))
        state.pointed_at = 2
        state.move_down()
        self.assertEqual(state.pointed_at, 0)

    def test_navigation_skips_separators(self):
        choices = ["a", questionary.Separator("---"), "b"]
        state = _ScrollableList(choices)
        state.move_down()
        self.assertEqual(state.pointed_at, 2)

    def test_navigation_is_a_no_op_with_no_selectable_items(self):
        state = _ScrollableList([questionary.Separator("---")])
        state.move_down()
        state.move_up()
        # não deve levantar


class VisibleWindowTest(unittest.TestCase):
    def test_shows_everything_when_fewer_than_window_size(self):
        state = _ScrollableList(_choices(3))
        self.assertEqual(state.visible_range(), (0, 3))

    def test_caps_at_window_size_when_pointer_at_start(self):
        state = _ScrollableList(_choices(12))
        self.assertEqual(state.visible_range(), (0, 5))

    def test_window_slides_down_to_keep_pointer_visible(self):
        state = _ScrollableList(_choices(12))
        for _ in range(6):
            state.move_down()
        self.assertEqual(state.pointed_at, 6)
        start, end = state.visible_range()
        self.assertTrue(start <= 6 < end)
        self.assertEqual(end - start, 5)

    def test_window_slides_back_up_when_returning(self):
        state = _ScrollableList(_choices(12))
        for _ in range(8):
            state.move_down()
        for _ in range(8):
            state.move_up()
        self.assertEqual(state.pointed_at, 0)
        self.assertEqual(state.visible_range(), (0, 5))

    def test_window_never_exceeds_the_end_of_the_list(self):
        state = _ScrollableList(_choices(7))
        for _ in range(6):
            state.move_down()
        start, end = state.visible_range()
        self.assertEqual(end, 7)
        self.assertEqual(end - start, 5)

    def test_empty_choices_has_an_empty_window(self):
        state = _ScrollableList([])
        self.assertEqual(state.visible_range(), (0, 0))

    def test_window_size_none_shows_everything_no_scrolling(self):
        # menu raiz: lista clássica, sem limite -- só as listas grandes
        # (módulos instalados, etc.) usam o viewport de 5.
        state = _ScrollableList(_choices(12), window_size=None)
        self.assertEqual(state.visible_range(), (0, 12))
        for _ in range(11):
            state.move_down()
        self.assertEqual(state.visible_range(), (0, 12))

    def test_window_size_none_never_shows_scroll_indicators(self):
        state = _ScrollableList(_choices(12), window_size=None)
        lines = state.render_lines()
        self.assertEqual(len(lines), 12)
        joined = "".join(t for line in lines for _, t in line)
        self.assertNotIn("acima", joined)
        self.assertNotIn("abaixo", joined)


class ToggleAndResultTest(unittest.TestCase):
    def test_single_select_result_is_the_pointed_value(self):
        state = _ScrollableList(_choices(3))
        state.move_down()
        self.assertEqual(state.result(), "item1")

    def test_toggle_is_a_no_op_in_single_select_mode(self):
        state = _ScrollableList(_choices(3))
        state.toggle()
        self.assertEqual(state.result(), "item0")

    def test_toggle_adds_and_removes_from_the_multi_result(self):
        state = _ScrollableList(_choices(3), multi=True)
        state.toggle()
        self.assertEqual(state.result(), ["item0"])
        state.toggle()
        self.assertEqual(state.result(), [])

    def test_multi_select_starts_with_pre_checked_defaults(self):
        wrapped = [questionary.Choice(c, checked=(c == "item1")) for c in _choices(3)]
        state = _ScrollableList(wrapped, multi=True)
        self.assertEqual(state.result(), ["item1"])

    def test_multi_result_preserves_choice_order_not_toggle_order(self):
        state = _ScrollableList(_choices(3), multi=True)
        state.pointed_at = 2
        state.toggle()
        state.pointed_at = 0
        state.toggle()
        self.assertEqual(state.result(), ["item0", "item2"])


class RenderLinesTest(unittest.TestCase):
    def test_shows_description_only_on_the_current_line(self):
        wrapped = [
            questionary.Choice("a", description="descrição a"),
            questionary.Choice("b", description="descrição b"),
        ]
        state = _ScrollableList(wrapped)
        state.pointed_at = 1
        lines = state.render_lines()
        self.assertNotIn("descrição a", "".join(t for _, t in lines[0]))
        self.assertIn("descrição b", "".join(t for _, t in lines[1]))

    def test_no_description_shown_when_choice_has_none(self):
        state = _ScrollableList(_choices(2))
        lines = state.render_lines()
        self.assertNotIn("—", "".join(t for line in lines for _, t in line))

    def test_separator_renders_without_pointer_or_checkbox_glyph(self):
        state = _ScrollableList([questionary.Separator("=== grupo ==="), "a"])
        lines = state.render_lines()
        text = "".join(t for _, t in lines[0])
        self.assertIn("=== grupo ===", text)
        self.assertNotIn("»", text)

    def test_shows_up_indicator_only_when_scrolled_past_the_top(self):
        state = _ScrollableList(_choices(12))
        lines = state.render_lines()
        self.assertNotIn("acima", lines[0][0][1])

        for _ in range(6):
            state.move_down()
        lines = state.render_lines()
        self.assertIn("acima", lines[0][0][1])

    def test_shows_down_indicator_with_remaining_count(self):
        state = _ScrollableList(_choices(12))
        lines = state.render_lines()
        self.assertIn("7 abaixo", lines[-1][0][1])

    def test_show_scroll_count_false_keeps_only_the_arrow(self):
        # flag única (versão 1: só a seta / versão 2: "mais N acima/abaixo")
        # -- atributo de classe, mesmo padrão do WINDOW_SIZE.
        state = _ScrollableList(_choices(12))
        state.SHOW_SCROLL_COUNT = False
        for _ in range(6):
            state.move_down()
        lines = state.render_lines()
        self.assertEqual(lines[0][0][1].strip(), "↑")
        self.assertEqual(lines[-1][0][1].strip(), "↓")

    def test_show_scroll_count_true_is_the_default(self):
        self.assertTrue(_ScrollableList.SHOW_SCROLL_COUNT)

    def test_checkbox_glyphs_reflect_selection(self):
        state = _ScrollableList(_choices(2), multi=True)
        state.toggle()
        lines = state.render_lines()
        self.assertIn("●", "".join(t for _, t in lines[0]))
        self.assertIn("○", "".join(t for _, t in lines[1]))

    def test_tokens_joins_lines_with_newlines_and_no_trailing_newline(self):
        state = _ScrollableList(_choices(2))
        tokens = state.tokens()
        text = "".join(t for _, t in tokens)
        self.assertEqual(text.count("\n"), 1)
        self.assertFalse(text.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
