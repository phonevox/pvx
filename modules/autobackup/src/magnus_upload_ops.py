import datetime
import os
import subprocess

# arquivo local transitório -- nome fixo (sobrescrito a cada run, nunca
# acumula), sobrevive só entre a geração e o upload; limpo ao final se tudo
# der certo.
OUTPUT_PATH = "/tmp/backup-pxmagnus.tgz"
SPLIT_OUTPUT_DIR = "/tmp/pxmagnus-split"

# mesmas pastas que o issabel_upload_ops.py já usa pro config -- e as mesmas
# que o magnus.sh real (repo pbackup) usa pra recordings/soundfiles.
REMOTE_CONFIG_FOLDER = "/configuration"
REMOTE_RECORDINGS_FOLDER = "/recordings"
REMOTE_SOUNDFILES_FOLDER = "/soundfiles"

# nomes conferidos contra magnus_ops.py (módulo magnus) -- não dá pra importar
# direto (cada módulo é seu próprio .pyz isolado), só replicar o formato.
_CONFIG_PREFIX = "backup_voip_softswitch"
_RECORDINGS_PREFIX = "recordings"
_SOUNDFILES_PREFIX = "soundfiles"


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


def _split_filename(prefix, today=None):
    today = today or datetime.date.today()
    return f"{prefix}.{today:%d-%m-%Y}.tgz"


def _split_files():
    return [
        (os.path.join(SPLIT_OUTPUT_DIR, _split_filename(_CONFIG_PREFIX)), REMOTE_CONFIG_FOLDER),
        (os.path.join(SPLIT_OUTPUT_DIR, _split_filename(_RECORDINGS_PREFIX)), REMOTE_RECORDINGS_FOLDER),
        (os.path.join(SPLIT_OUTPUT_DIR, _split_filename(_SOUNDFILES_PREFIX)), REMOTE_SOUNDFILES_FOLDER),
    ]


def export_and_upload(upload_url, token, split=False):
    # pvx magnus e pbackup são módulos/binários separados -- só dá pra
    # encadear via subprocess (nunca import direto entre módulos, cada um
    # é seu próprio .pyz isolado). Isso é exatamente o que a linha de cron
    # antiga fazia via shell (`&&`); só que aqui vira Python testável, sem
    # depender de escaping de `%`/data calculada em shell dentro do crontab.
    if split:
        os.makedirs(SPLIT_OUTPUT_DIR, exist_ok=True)
        _run(
            ["pvx", "magnus", "backup", "export", "--configuration", "--recordings", "--soundfiles",
             "--output-dir", SPLIT_OUTPUT_DIR],
            "falha ao gerar o backup do magnus",
        )
        files = _split_files()
    else:
        _run(["pvx", "magnus", "backup", "export", "-o", OUTPUT_PATH], "falha ao gerar o backup do magnus")
        files = [(OUTPUT_PATH, remote_name())]

    files_arg = ",".join(f"{local}:{remote}" for local, remote in files)
    _run(
        ["pbackup", "--files", files_arg, "--to", f"{upload_url}:/", "--token", token],
        "falha ao enviar o backup pro UOE",
    )

    # só limpa se os dois passos deram certo -- se algum falhou, a exceção
    # já propagou antes de chegar aqui, e os arquivos ficam pra retry/debug.
    for local, _remote in files:
        os.remove(local)
