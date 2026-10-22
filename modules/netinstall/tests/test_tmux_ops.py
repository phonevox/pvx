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
    #
    # relaunch_inside() recebe o argv já pronto (quem chama monta a partir dos
    # flags resolvidos pelo Click) em vez de ler sys.argv -- achado ao vivo: via
    # menu interativo, o processo pvx inteiro roda sem nenhum argumento (a
    # navegação acontece dentro do mesmo processo), então sys.argv[1:] vinha
    # vazio e reabria o menu raiz dentro do tmux em vez do comando escolhido.
    @patch("tmux_ops.pvx_config.pvx_bin_path", return_value="/usr/local/bin/pvx")
    @patch("tmux_ops.os.execvp")
    @patch("tmux_ops.shutil.which", return_value="/usr/bin/tmux")
    def test_execs_tmux_new_session_with_the_given_argv(self, mock_which, mock_execvp, mock_bin_path):
        tmux_ops.relaunch_inside(["netinstall", "issabel5", "--astver", "18"])
        args = mock_execvp.call_args.args
        self.assertEqual(args[0], "/usr/bin/tmux")
        self.assertEqual(args[1][:4], ["/usr/bin/tmux", "new-session", "-A", "-s"])
        self.assertEqual(args[1][-1], "/usr/local/bin/pvx netinstall issabel5 --astver 18")

    @patch("tmux_ops.pvx_config.pvx_bin_path", return_value="/usr/local/bin/pvx")
    @patch("tmux_ops.os.execvp")
    @patch("tmux_ops.shutil.which", return_value="/usr/bin/tmux")
    def test_uses_attach_or_create_so_a_leftover_session_does_not_crash(self, mock_which, mock_execvp, mock_bin_path):
        # achado ao vivo: reconectar depois de uma queda de SSH e rodar `issabel5` de
        # novo batia numa sessão "pvx-netinstall" órfã ainda viva -- `tmux new-session
        # -s` (sem -A) falha com "duplicate session" e mata o processo na hora, sem
        # nenhum traceback (os.execvp já trocou a imagem do processo Python pelo tmux,
        # não tem mais catch-global rodando ali). `-A` faz o tmux anexar na sessão
        # existente em vez de falhar -- é o "sobrevive a queda de SSH" completo.
        tmux_ops.relaunch_inside(["netinstall", "issabel5"])
        args = mock_execvp.call_args.args[1]
        self.assertIn("-A", args)

    @patch("tmux_ops.os.execvp")
    @patch("tmux_ops.shutil.which", return_value=None)
    def test_safe_no_op_when_tmux_still_unavailable(self, mock_which, mock_execvp):
        # ex.: ensure_installed() falhou em silêncio (sem root) -- segue sem tmux
        # em vez de estourar em os.execvp(None, ...); o preflight normal, logo na
        # sequência, é quem vai reportar a causa real (falta de root) com clareza.
        tmux_ops.relaunch_inside(["netinstall", "issabel5"])
        mock_execvp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
