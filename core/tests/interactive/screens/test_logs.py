import unittest
from unittest.mock import patch

from pvx.interactive.screens.logs import LogsScreen


class LogsScreenTest(unittest.TestCase):
    @patch("pvx.interactive.screens.logs.ask_select", return_value=None)
    @patch("pvx.interactive.screens.logs.discover_installed_modules", return_value={"dummy": object()})
    def test_offers_core_and_tudo_alongside_installed_modules(self, mock_discover, mock_ask_select):
        LogsScreen().render()
        choices = mock_ask_select.call_args.args[1]
        self.assertIn("core", choices)
        self.assertIn("dummy", choices)
        self.assertTrue(any("tudo" in c for c in choices))

    @patch("pvx.interactive.screens.logs.time.sleep", side_effect=KeyboardInterrupt)
    @patch("pvx.interactive.screens.logs.viewer.LogFollower")
    @patch("pvx.interactive.screens.logs.viewer.read_combined_logs", return_value="conteúdo do log")
    @patch("pvx.interactive.screens.logs.ask_select", return_value="dummy")
    @patch("pvx.interactive.screens.logs.discover_installed_modules", return_value={"dummy": object()})
    def test_selecting_a_module_tails_100_then_follows_until_ctrl_c(
        self, mock_discover, mock_ask_select, mock_read, mock_follower_cls, mock_sleep
    ):
        # menu interativo = auto-follow com tail 100 (diferente do default da CLI, que é
        # tail 50 sem follow) -- ctrl-c durante o follow volta pro menu, nunca crasha.
        mock_follower_cls.return_value.poll.return_value = []
        result = LogsScreen().render()
        self.assertEqual(result, "BACK")
        mock_read.assert_called_once_with(["dummy"], lines=100)
        mock_follower_cls.assert_called_once_with(["dummy"])

    @patch("pvx.interactive.screens.logs.ask_select", return_value=None)
    @patch("pvx.interactive.screens.logs.discover_installed_modules", return_value={"dummy": object()})
    def test_none_selection_returns_back(self, mock_discover, mock_ask_select):
        self.assertEqual(LogsScreen().render(), "BACK")

    @patch("pvx.interactive.screens.logs.viewer.read_combined_logs")
    @patch("pvx.interactive.screens.logs.ask_select", return_value="voltar")
    @patch("pvx.interactive.screens.logs.discover_installed_modules", return_value={"dummy": object()})
    def test_selecting_voltar_returns_back_without_reading_log(
        self, mock_discover, mock_ask_select, mock_read
    ):
        self.assertEqual(LogsScreen().render(), "BACK")
        mock_read.assert_not_called()

    @patch("pvx.interactive.screens.logs.time.sleep", side_effect=KeyboardInterrupt)
    @patch("pvx.interactive.screens.logs.viewer.LogFollower")
    @patch("pvx.interactive.screens.logs.viewer.read_combined_logs", return_value="")
    @patch("pvx.interactive.screens.logs.viewer.list_log_names", return_value=["core", "dummy"])
    @patch("pvx.interactive.screens.logs.discover_installed_modules", return_value={"dummy": object()})
    def test_tudo_option_combines_core_and_every_module(
        self, mock_discover, mock_list, mock_read, mock_follower_cls, mock_sleep
    ):
        mock_follower_cls.return_value.poll.return_value = []
        with patch("pvx.interactive.screens.logs.ask_select") as mock_ask_select:
            choices = None

            def fake_ask_select(_msg, options):
                nonlocal choices
                choices = options
                return next(c for c in options if "tudo" in c)

            mock_ask_select.side_effect = fake_ask_select
            result = LogsScreen().render()

        self.assertEqual(result, "BACK")
        mock_read.assert_called_once_with(["core", "dummy"], lines=100)


if __name__ == "__main__":
    unittest.main()
