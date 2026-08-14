import unittest
from unittest.mock import patch

from pvx.interactive.widgets import clear


class ClearTest(unittest.TestCase):
    @patch("pvx.interactive.widgets.click.clear")
    def test_delegates_to_click_clear(self, mock_clear):
        clear()
        mock_clear.assert_called_once()


if __name__ == "__main__":
    unittest.main()
