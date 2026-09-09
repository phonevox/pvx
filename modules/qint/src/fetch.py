import shutil
import subprocess
from pathlib import Path


def prepare_cache_dir(cache_root, tipo, versao):
    cache_dir = Path(cache_root) / tipo / versao
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    # não cria cache_dir em si, só o pai -- "sftp get -r remote local" se comporta como
    # cp -r: se "local" já existe, o conteúdo remoto entra ANINHADO um nível a mais dentro
    # dele (cache_dir/<versao>/...) em vez de direto em cache_dir/... . achado ao vivo:
    # isso fazia apply() procurar cache_dir/php/config.php e nunca achar (Errno 2), porque
    # o conteúdo real tinha ido parar em cache_dir/<versao>/php/config.php.
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    return str(cache_dir)


def fetch(sftp_info, remote_base, tipo, versao, cache_dir):
    remote_path = f"{remote_base}/{tipo}/{versao}"
    batch = f"get -r {remote_path} {cache_dir}\n"

    # sftp/ssh leem a senha direto de /dev/tty quando disponível, não de
    # stdin -- login continua interativo mesmo com os comandos do batch
    # sendo passados via stdin. Nunca scripta/guarda a senha.
    #
    # achado ao vivo: a confirmação de host key NUNCA vista antes ("Are you
    # sure you want to continue connecting?") tenta ler a resposta de stdin,
    # não de /dev/tty -- e stdin já está ocupado com os comandos do batch.
    # Na primeira conexão a um host novo isso falha (exit 255) mesmo com
    # credenciais corretas, porque o "yes" nunca chega. accept-new resolve
    # isso sem abrir mão de checar a chave em conexões seguintes (host
    # trocado de chave depois de já confiável continua barrado).
    subprocess.run(
        [
            "sftp", "-P", str(sftp_info["port"]), "-o", "StrictHostKeyChecking=accept-new",
            f"{sftp_info['user']}@{sftp_info['host']}",
        ],
        input=batch,
        text=True,
        check=True,
    )
