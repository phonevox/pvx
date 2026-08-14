import os
import unittest
from tempfile import TemporaryDirectory

import questionary

from pvx.interactive.theme import (
    PRESETS,
    THEME,
    THEME_RULES,
    current_accent_color,
    current_style,
    current_theme_rules,
)


class ThemeTest(unittest.TestCase):
    def test_selected_item_style_is_blue(self):
        rules = dict(THEME_RULES)
        self.assertIn("0087ff", rules["pointer"])
        self.assertIn("0087ff", rules["highlighted"])

    def test_hint_separator_is_gray(self):
        rules = dict(THEME_RULES)
        self.assertIn("808080", rules["separator"])

    def test_answer_style_matches_accent_color(self):
        rules = dict(THEME_RULES)
        self.assertIn("0087ff", rules["answer"])

    def test_theme_is_questionary_style_instance(self):
        self.assertIsInstance(THEME, questionary.Style)


class CurrentStyleTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._old_home = os.environ.get("PVX_HOME")
        os.environ["PVX_HOME"] = self._tmp.name

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("PVX_HOME", None)
        else:
            os.environ["PVX_HOME"] = self._old_home
        self._tmp.cleanup()

    def test_defaults_to_azul_preset(self):
        self.assertEqual(current_theme_rules(), PRESETS["azul"])

    def test_reflects_configured_theme(self):
        from pvx import config

        config.set_theme_name("verde")
        self.assertEqual(current_theme_rules(), PRESETS["verde"])

    def test_current_style_is_questionary_style_instance(self):
        self.assertIsInstance(current_style(), questionary.Style)

    def test_current_accent_color_defaults_to_azul(self):
        self.assertEqual(current_accent_color(), "#0087ff")

    def test_current_accent_color_reflects_configured_theme(self):
        from pvx import config

        config.set_theme_name("verde")
        self.assertEqual(current_accent_color(), "#00af5f")


if __name__ == "__main__":
    unittest.main()
