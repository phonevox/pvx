import datetime
import os
import subprocess

# arquivo local transitório -- nome fixo (sobrescrito a cada run, nunca
# acumula), sobrevive só entre a geração e o upload; limpo ao final se tudo
# der certo.
OUTPUT_PATH = "/tmp/backup-pxmagnus.tgz"


class MagnusUploadError(Exception):
    pass


def _run(args, error):
    # ponto único de subprocess -- falha vira MagnusUploadError com o
    # stderr, nunca um CalledProcessError cru estourando na tela.
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise MagnusUploadError(f"{error}{': ' + detail if detail else ''}")


def remote_name(today=None):
    # mesmo padrão do magnus_ops.output_filename() (dd-mm-yyyy) -- sem
    # isso, todo dia sobrescreve o backup do dia anterior no UOE em vez de
    # manter histórico.
    today = today or datetime.date.today()
    return f"backup-pxmagnus.{today:%d-%m-%Y}.tgz"


def export_and_upload(upload_url, token):
    # pvx magnus e pbackup são módulos/binários separados -- só dá pra
    # encadear via subprocess (nunca import direto entre módulos, cada um
    # é seu próprio .pyz isolado). Isso é exatamente o que a linha de cron
    # antiga fazia via shell (`&&`); só que aqui vira Python testável, sem
    # depender de escaping de `%`/data calculada em shell dentro do crontab.
    _run(["pvx", "magnus", "backup", "export", "-o", OUTPUT_PATH], "falha ao gerar o backup do magnus")

    _run(
        ["pbackup", "--files", f"{OUTPUT_PATH}:{remote_name()}", "--to", f"{upload_url}:/", "--token", token],
        "falha ao enviar o backup pro UOE",
    )

    # só limpa se os dois passos deram certo -- se algum falhou, a exceção
    # já propagou antes de chegar aqui, e o arquivo fica pra retry/debug.
    os.remove(OUTPUT_PATH)
