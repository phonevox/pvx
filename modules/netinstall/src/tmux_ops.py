import os
import shlex
import shutil
import sys

import os_ops

SESSION_NAME = "pvx-netinstall"


def is_active():
    return "TMUX" in os.environ


def ensure_installed():
    if shutil.which("tmux") is None:
        os_ops.run_cmd(["dnf", "install", "-y", "tmux"])


def relaunch_inside():
    # substitui o processo atual -- nunca retorna se der certo. A instalação de
    # verdade passa a rodar dentro da sessão tmux daqui pra frente, sobrevive a uma
    # queda de SSH (achado ao vivo: instalação de 20+min cortada no meio, sem
    # jeito de retomar/ver o que já tinha rodado -- reconecta e dá `tmux attach`).
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        # ensure_installed() deve ter rodado antes -- se mesmo assim não tem tmux
        # (ex.: dnf install falhou em silêncio, sem root), segue sem embrulhar.
        # O preflight normal, logo na sequência, reporta a causa real com clareza.
        return
    command = shlex.join(sys.argv)
    os.execvp(tmux_path, [tmux_path, "new-session", "-s", SESSION_NAME, command])
