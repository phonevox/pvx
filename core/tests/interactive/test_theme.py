import os
import unittest
from tempfile import TemporaryDirectory

import questionary

from pvx.interactive.theme import (
    ACCENT_COLORS,
    BORDERS,
    LINE_FORMATS,
    PRESETS,
    SYMBOL_SETS,
    THEME,
    THEME_RULES,
    current_accent_color,
    current_border_char,
    current_line_format,
    current_style,
    current_symbols,
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

    def test_selected_checkbox_item_has_no_background_reverse(self):
        # prompt_toolkit.styles.defaults.PROMPT_TOOLKIT_STYLE tem ("selected", "reverse")
        # numa camada abaixo do style do questionary -- merge de style é por atributo, não
        # substituição total, então só *não definir* "reverse" aqui não cancela o que essa
        # camada de baixo já setou. Precisa de "noreverse" explícito. Achado ao vivo: item
        # marcado saía com o fundo inteiro invertido, sem querer.
        rules = dict(THEME_RULES)
        self.assertIn("0087ff", rules["selected"])
        self.assertIn("noreverse", rules["selected"])

    def test_theme_is_questionary_style_instance(self):
        self.assertIsInstance(THEME, questionary.Style)

    def test_more_preset_colors_available(self):
        self.assertEqual(ACCENT_COLORS["vermelho"], "#ff5555")
        self.assertEqual(ACCENT_COLORS["amarelo"], "#ffd700")
        self.assertEqual(ACCENT_COLORS["ciano"], "#00d7ff")
        self.assertEqual(ACCENT_COLORS["rosa"], "#ff5fd7")
        self.assertIn("vermelho", PRESETS)
        self.assertIn("amarelo", PRESETS)
        self.assertIn("ciano", PRESETS)
        self.assertIn("rosa", PRESETS)


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

    def test_current_symbols_defaults_to_ascii(self):
        self.assertEqual(current_symbols(), SYMBOL_SETS["ascii"])

    def test_current_symbols_reflects_configured_set(self):
        from pvx import config

        config.set_symbol_set_name("ascii")
        self.assertEqual(current_symbols(), SYMBOL_SETS["ascii"])

    def test_current_border_char_defaults_to_duplo(self):
        self.assertEqual(current_border_char(), "═")

    def test_current_border_char_reflects_configured_border(self):
        from pvx import config

        config.set_border_name("simples")
        self.assertEqual(current_border_char(), "─")

    def test_current_line_format_defaults_to_modern_full_color(self):
        self.assertEqual(current_line_format(), "modern-full-color")

    def test_current_line_format_reflects_configured_format(self):
        from pvx import config

        config.set_line_format_name("minimal")
        self.assertEqual(current_line_format(), "minimal")

    def test_current_line_format_falls_back_to_modern_full_color_on_unknown_value(self):
        from pvx import config

        config.set_line_format_name("isso-nao-existe")
        self.assertEqual(current_line_format(), "modern-full-color")


class SymbolAndFormatPresetsTest(unittest.TestCase):
    def test_more_symbol_sets_available(self):
        self.assertIn("padrão", SYMBOL_SETS)
        self.assertIn("ascii", SYMBOL_SETS)
        self.assertIn("geométrico", SYMBOL_SETS)

    def test_more_borders_available(self):
        self.assertEqual(BORDERS["duplo"], "═")
        self.assertEqual(BORDERS["simples"], "─")
        self.assertEqual(BORDERS["grosso"], "━")

    def test_all_line_formats_available(self):
        self.assertEqual(
            LINE_FORMATS,
            (
                "verbose", "verbose-v2", "verbose-v2-full-color",
                "minimal", "ultra-minimal",
                "modern", "modern-colored-brackets", "modern-full-color",
            ),
        )


if __name__ == "__main__":
    unittest.main()
