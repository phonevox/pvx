import unittest
from unittest.mock import patch

from click.testing import CliRunner

from src.main import cli as dummy_module


class DummyModuleTest(unittest.TestCase):
    def test_cli_group_has_hello_command(self):
        result = CliRunner().invoke(dummy_module.cli_group(), ["hello"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello", result.output.lower())

    @patch("src.main.DummyModule.get_logger")
    def test_hello_logs_invocation(self, mock_get_logger):
        CliRunner().invoke(dummy_module.cli_group(), ["hello"])
        mock_get_logger.return_value.info.assert_called_once()

    @patch("src.main.DummyModule.get_logger")
    def test_building_the_cli_group_alone_does_not_touch_the_logger(self, mock_get_logger):
        dummy_module.cli_group()
        mock_get_logger.assert_not_called()


class HelloPausesWhenInteractiveTest(unittest.TestCase):
    # achado ao vivo: hello nunca pausava -- no menu, o "hello from dummy"
    # some antes do usuário conseguir ler.
    @patch("src.main.widgets.pause")
    @patch("src.main._is_interactive", return_value=True)
    def test_pauses_when_interactive(self, mock_interactive, mock_pause):
        CliRunner().invoke(dummy_module.cli_group(), ["hello"])
        mock_pause.assert_called_once_with()

    @patch("src.main.widgets.pause")
    @patch("src.main._is_interactive", return_value=False)
    def test_does_not_pause_when_not_interactive(self, mock_interactive, mock_pause):
        CliRunner().invoke(dummy_module.cli_group(), ["hello"])
        mock_pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
