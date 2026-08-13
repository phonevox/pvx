import unittest
from unittest.mock import patch

from pvx.interactive.inputs import ask_select


class AskSelectTest(unittest.TestCase):
    @patch("pvx.interactive.inputs.questionary.select")
    def test_delegates_to_questionary_select(self, mock_select):
        mock_select.return_value.ask.return_value = "escolhido"
        result = ask_select("pvx >", ["a", "b"])
        self.assertEqual(result, "escolhido")
        mock_select.assert_called_once()


if __name__ == "__main__":
    unittest.main()
