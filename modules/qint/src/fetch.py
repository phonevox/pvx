import shutil
import subprocess
from pathlib import Path


def prepare_cache_dir(cache_root, tipo, versao):
    cache_dir = Path(cache_root) / tipo / versao
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True)
    return str(cache_dir)


def fetch(sftp_info, remote_base, tipo, versao, cache_dir):
    remote_path = f"{remote_base}/{tipo}/{versao}"
    batch = f"get -r {remote_path} {cache_dir}\n"

    # sftp/ssh leem a senha direto de /dev/tty quando disponível, não de
    # stdin -- login continua interativo mesmo com os comandos do batch
    # sendo passados via stdin. Nunca scripta/guarda a senha.
    subprocess.run(
        ["sftp", "-P", str(sftp_info["port"]), f"{sftp_info['user']}@{sftp_info['host']}"],
        input=batch,
        text=True,
        check=True,
    )
