import unittest
from unittest.mock import patch

from pvx.__main__ import main


class MainDispatchTest(unittest.TestCase):
    @patch("pvx.__main__.run_interactive")
    def test_no_args_enters_interactive_menu(self, mock_run_interactive):
        main(argv=[])
        mock_run_interactive.assert_called_once()

    @patch("pvx.__main__.cli")
    def test_with_args_dispatches_to_cli(self, mock_cli):
        main(argv=["--version"])
        mock_cli.main.assert_called_once_with(args=["--version"], prog_name="pvx")


if __name__ == "__main__":
    unittest.main()
