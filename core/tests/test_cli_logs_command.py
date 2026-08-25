import unittest
from unittest.mock import patch

from click.testing import CliRunner

from pvx.cli import build_cli


class LogsCommandTest(unittest.TestCase):
    @patch("pvx.cli.viewer.read_combined_logs", return_value="conteúdo")
    def test_defaults_to_tail_50_no_follow(self, mock_read):
        result = CliRunner().invoke(build_cli(), ["logs", "netinstall"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_read.assert_called_once_with(["netinstall"], lines=50)
        self.assertIn("conteúdo", result.output)

    @patch("pvx.cli.viewer.read_combined_logs", return_value="")
    def test_tail_option_overrides_default(self, mock_read):
        CliRunner().invoke(build_cli(), ["logs", "netinstall", "--tail", "10"])
        mock_read.assert_called_once_with(["netinstall"], lines=10)

    @patch("pvx.cli.viewer.list_log_names", return_value=["core", "netinstall"])
    @patch("pvx.cli.viewer.read_combined_logs", return_value="")
    def test_all_flag_combines_every_log(self, mock_read, mock_list):
        result = CliRunner().invoke(build_cli(), ["logs", "--all"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_read.assert_called_once_with(["core", "netinstall"], lines=50)

    def test_requires_name_or_all(self):
        result = CliRunner().invoke(build_cli(), ["logs"])
        self.assertNotEqual(result.exit_code, 0)

    @patch("pvx.cli.time.sleep", side_effect=KeyboardInterrupt)
    @patch("pvx.cli.viewer.LogFollower")
    @patch("pvx.cli.viewer.read_combined_logs", return_value="")
    def test_follow_polls_until_interrupted(self, mock_read, mock_follower_cls, mock_sleep):
        # -f nunca deve crashar com traceback feio no Ctrl+C -- mesmo padrão de "back sem
        # crash" já usado no menu interativo, aplicado aqui pro terminal puro.
        follower = mock_follower_cls.return_value
        follower.poll.return_value = ["linha nova"]
        result = CliRunner().invoke(build_cli(), ["logs", "netinstall", "-f"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("linha nova", result.output)

    @patch("pvx.cli.viewer.read_combined_logs", return_value="")
    def test_follow_off_by_default(self, mock_read):
        result = CliRunner().invoke(build_cli(), ["logs", "netinstall"])
        self.assertEqual(result.exit_code, 0, msg=result.output)


if __name__ == "__main__":
    unittest.main()
