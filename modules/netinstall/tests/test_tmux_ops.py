import unittest
from unittest.mock import patch

import tmux_ops


class IsActiveTest(unittest.TestCase):
    @patch.dict("tmux_ops.os.environ", {"TMUX": "/tmp/tmux-0/default,1234,0"})
    def test_true_when_tmux_env_var_present(self):
        self.assertTrue(tmux_ops.is_active())

    @patch.dict("tmux_ops.os.environ", {}, clear=True)
    def test_false_when_absent(self):
        self.assertFalse(tmux_ops.is_active())


class EnsureInstalledTest(unittest.TestCase):
    @patch("tmux_ops.os_ops.run_cmd")
    @patch("tmux_ops.shutil.which", return_value="/usr/bin/tmux")
    def test_does_not_install_when_already_present(self, mock_which, mock_run_cmd):
        tmux_ops.ensure_installed()
        mock_run_cmd.assert_not_called()

    @patch("tmux_ops.os_ops.run_cmd")
    @patch("tmux_ops.shutil.which", return_value=None)
    def test_installs_via_dnf_when_absent(self, mock_which, mock_run_cmd):
        tmux_ops.ensure_installed()
        mock_run_cmd.assert_called_once_with(["dnf", "install", "-y", "tmux"])


class RelaunchInsideTest(unittest.TestCase):
    # achado ao vivo: instalação de 20+min cortada no meio por queda de SSH, sem
    # jeito de retomar/ver o que já tinha rodado -- relançar dentro de uma sessão
    # tmux sobrevive a isso (reconecta e dá `tmux attach`).
    @patch("tmux_ops.os.execvp")
    @patch("tmux_ops.shutil.which", return_value="/usr/bin/tmux")
    def test_execs_tmux_new_session_with_the_original_command_line(self, mock_which, mock_execvp):
        with patch("tmux_ops.sys.argv", ["/usr/local/bin/pvx", "netinstall", "issabel5", "--astver", "18"]):
            tmux_ops.relaunch_inside()
        args = mock_execvp.call_args.args
        self.assertEqual(args[0], "/usr/bin/tmux")
        self.assertEqual(args[1][:3], ["/usr/bin/tmux", "new-session", "-s"])
        self.assertIn("pvx netinstall issabel5 --astver 18", args[1][-1])

    @patch("tmux_ops.os.execvp")
    @patch("tmux_ops.shutil.which", return_value=None)
    def test_safe_no_op_when_tmux_still_unavailable(self, mock_which, mock_execvp):
        # ex.: ensure_installed() falhou em silêncio (sem root) -- segue sem tmux
        # em vez de estourar em os.execvp(None, ...); o preflight normal, logo na
        # sequência, é quem vai reportar a causa real (falta de root) com clareza.
        tmux_ops.relaunch_inside()
        mock_execvp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
