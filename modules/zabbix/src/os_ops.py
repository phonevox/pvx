import subprocess


def run_cmd(args, logger=None, action=None, verify_cmd=None):
    # subprocess.run() levanta FileNotFoundError se o binário não existe -- diferente de
    # "rodou e falhou" (returncode != 0), já coberto abaixo. Sem capturar isso o processo
    # crasha com traceback cru em vez de reportar falha limpa.
    #
    # achado ao vivo: uma falha aqui virava só um bool -- o motivo real
    # (stderr do yum, comando ausente) nunca ia pra lugar nenhum, nem pro
    # `pvx logs`. Chamador que passa logger/action fica com o motivo
    # registrado, mesmo mostrando uma mensagem limpa e genérica pro usuário.
    label = action or " ".join(args)
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError as e:
        if logger:
            logger.error(f"{label}: {e}")
        return False
    if result.returncode == 0:
        return True
    # achado ao vivo: "yum install -y <rpm já instalado>" costuma sair com
    # código != 0 ("Nothing to do") mesmo o pacote já estando no estado
    # certo -- em vez de confiar no texto do erro (frágil, muda com
    # locale/versão do yum), confirma via um comando de verdade (`rpm -q`):
    # se o alvo já está instalado, o objetivo foi atingido de qualquer jeito.
    if verify_cmd and subprocess.run(verify_cmd, capture_output=True, text=True).returncode == 0:
        return True
    if logger:
        logger.error(f"{label}: {result.stderr.strip()}")
    return False
