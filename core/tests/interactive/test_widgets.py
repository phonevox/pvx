import unittest
from unittest.mock import patch

from pvx.interactive.widgets import clear, spinner


class ClearTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.click.clear")
    def test_delegates_to_click_clear(self, mock_clear):
        clear()
        mock_clear.assert_called_once()


class SpinnerTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.theme.current_accent_color", return_value="#0087ff")
    @patch("pvx.interactive.widgets.Console")
    def test_spinner_uses_theme_accent_color_text_stays_normal(self, mock_console_cls, mock_accent):
        spinner("Instalando módulo...")
        mock_console_cls.return_value.status.assert_called_once_with(
            "Instalando módulo...", spinner_style="#0087ff"
        )


if __name__ == "__main__":
    unittest.main()
