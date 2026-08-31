import subprocess


def run_cmd(args):
    # subprocess.run() levanta FileNotFoundError se o binário não existe -- diferente de
    # "rodou e falhou" (returncode != 0), já coberto abaixo. Sem capturar isso o processo
    # crasha com traceback cru em vez de reportar falha limpa.
    try:
        return subprocess.run(args, capture_output=True, text=True).returncode == 0
    except FileNotFoundError:
        return False
