import os
import shlex
import shutil

from pvx import config as pvx_config

import os_ops

SESSION_NAME = "pvx-netinstall"


def is_active():
    return "TMUX" in os.environ


def ensure_installed():
    if shutil.which("tmux") is None:
        os_ops.run_cmd(["dnf", "install", "-y", "tmux"])


def relaunch_inside(argv):
    # substitui o processo atual -- nunca retorna se der certo. A instalação de
    # verdade passa a rodar dentro da sessão tmux daqui pra frente, sobrevive a uma
    # queda de SSH (achado ao vivo: instalação de 20+min cortada no meio, sem
    # jeito de retomar/ver o que já tinha rodado -- reconecta e dá `tmux attach`).
    #
    # argv vem pronto de quem chama (montado a partir dos flags já resolvidos
    # pelo Click), não de sys.argv -- achado ao vivo: via menu interativo o
    # processo pvx inteiro roda sem nenhum argumento (a navegação acontece
    # dentro do mesmo processo), sys.argv[1:] vinha vazio e reabria o menu raiz
    # dentro do tmux em vez do comando escolhido.
    tmux_path = shutil.which("tmux")
    if tmux_path is None:
        # ensure_installed() deve ter rodado antes -- se mesmo assim não tem tmux
        # (ex.: dnf install falhou em silêncio, sem root), segue sem embrulhar.
        # O preflight normal, logo na sequência, reporta a causa real com clareza.
        return
    # usa o binário `pvx` de verdade (config.pvx_bin_path()), nunca sys.argv[0]:
    # esse é o caminho do .pyz (é assim que o wrapper `pvx` invoca o python --
    # `exec python3.11 /usr/local/lib/pvx/core.pyz "$@"`), não é executável
    # sozinho pelo shell (achado ao vivo: fazia o comando dentro do tmux morrer
    # na hora, "permission denied", sem traceback nenhum -- o processo Python já
    # tinha sido substituído pelo tmux nesse ponto).
    command = shlex.join([str(pvx_config.pvx_bin_path())] + argv)
    # -A: anexa numa sessão SESSION_NAME já existente em vez de falhar com
    # "duplicate session" -- achado ao vivo, uma sessão órfã de instalação
    # anterior (queda de SSH) fazia o `new-session` sem -A matar o processo na
    # hora (os.execvp já trocou a imagem, não sobra catch-global pra pegar).
    os.execvp(tmux_path, [tmux_path, "new-session", "-A", "-s", SESSION_NAME, command])
