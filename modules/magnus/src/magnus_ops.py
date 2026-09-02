import contextlib
import datetime
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

DEFAULT_SOUNDS_DIR = "/usr/local/src/magnus/sounds"
DEFAULT_ASTERISK_DIR = "/etc/asterisk"
MBILLING_WEB_DIR = "/var/www/html/mbilling"
UPDATE_SCRIPT = MBILLING_WEB_DIR + "/protected/commands/update.sh"
RES_CONFIG_MYSQL = "/etc/asterisk/res_config_mysql.conf"
INSTALLER_URL = "https://raw.githubusercontent.com/magnussolution/magnusbilling7/source/script/install.sh"


class MagnusError(Exception):
    pass


def output_filename(today=None):
    today = today or datetime.date.today()
    return f"backup-pxmagnus.{today:%d-%m-%Y}.tgz"


def _run(args, error, **kwargs):
    # ponto único pra todo subprocess do módulo que pode falhar por motivo
    # previsível (senha errada, serviço fora do ar, permissão) -- sem isso,
    # cada chamador vira um CalledProcessError cru estourando na tela (achado
    # ao vivo: mysqldump com senha errada crashava com traceback).
    kwargs.setdefault("stderr", subprocess.PIPE)
    kwargs.setdefault("text", True)
    result = subprocess.run(args, **kwargs)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise MagnusError(f"{error}{': ' + detail if detail else ''}")
    return result


@contextlib.contextmanager
def _mysql_defaults_file(db_user, db_password):
    # nunca senha em argv de subprocess (fica visível em `ps aux` pra
    # qualquer usuário local, diferente do bash original que fazia
    # `-p"$SENHA"` direto) -- credenciais sempre via --defaults-extra-file,
    # 0600, apagado ao sair do context manager.
    fd, path = tempfile.mkstemp(prefix="pvx-magnus-", suffix=".cnf")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"[client]\nuser={db_user}\npassword={db_password}\n")
        yield path
    finally:
        os.remove(path)


def _copy_dir(src, dst):
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _dump_database(db_user, db_password, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with _mysql_defaults_file(db_user, db_password) as defaults_file, open(dest_path, "wb") as f:
        _run(
            ["mysqldump", f"--defaults-extra-file={defaults_file}", "mbilling"],
            "falha ao exportar o banco de dados", stdout=f,
        )


def _make_archive(src_dir, output_path):
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(src_dir, arcname=".")


def export_backup(db_user, db_password, output_path=None,
                   sounds_dir=DEFAULT_SOUNDS_DIR, asterisk_dir=DEFAULT_ASTERISK_DIR):
    # áudios da URA são opcionais -- nem toda central tem gravação --
    # ausência vira aviso, não motivo pra abortar o backup inteiro.
    output_path = output_path or output_filename()
    warnings = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        _dump_database(db_user, db_password, os.path.join(tmp_dir, "tmp", "base.sql"))
        if os.path.isdir(sounds_dir):
            _copy_dir(sounds_dir, os.path.join(tmp_dir, "tmp", "audios-ura"))
        else:
            warnings.append(f"diretório de áudios da URA não encontrado em '{sounds_dir}' -- pulado.")
        _copy_dir(asterisk_dir, os.path.join(tmp_dir, "etc", "asterisk"))
        _make_archive(tmp_dir, output_path)
    return output_path, warnings


def is_valid_archive(path):
    return subprocess.run(["tar", "-tzf", path], capture_output=True).returncode == 0


def extract_archive(path, dest_dir):
    # arquivo de backup pode vir de qualquer lugar (`backup import <arquivo>`)
    # -- nunca confia cegamente no conteúdo de um tar de terceiro.
    with tarfile.open(path) as tar:
        dest_real = os.path.realpath(dest_dir)
        for member in tar.getmembers():
            member_path = os.path.realpath(os.path.join(dest_dir, member.name))
            if member_path != dest_real and not member_path.startswith(dest_real + os.sep):
                raise ValueError(f"entrada suspeita no arquivo de backup: '{member.name}'.")
        tar.extractall(dest_dir)


def _asterisk_active():
    if subprocess.run(["systemctl", "is-active", "--quiet", "asterisk"]).returncode == 0:
        return True
    return subprocess.run(["/etc/init.d/asterisk", "status"], capture_output=True).returncode == 0


def validate_extracted(extracted_dir):
    errors = []

    db_dump = os.path.join(extracted_dir, "tmp", "base.sql")
    if not os.path.isfile(db_dump):
        errors.append(f"dump do banco de dados não encontrado em '{db_dump}'.")

    ast_dir = os.path.join(extracted_dir, "etc", "asterisk")
    if not os.path.isdir(ast_dir):
        errors.append(f"diretório com configurações do Asterisk não encontrado em '{ast_dir}'.")

    # áudios da URA são opcionais no backup (ver export_backup) -- nunca
    # bloqueia a importação sozinho.

    if not os.access(UPDATE_SCRIPT, os.X_OK):
        errors.append(f"script de atualização '{UPDATE_SCRIPT}' não encontrado ou não executável.")

    if not _asterisk_active():
        errors.append("serviço 'asterisk' não está ativo.")

    return errors


def _restore_database(defaults_file, dump_path):
    with open(dump_path, "rb") as f:
        _run(
            ["mysql", f"--defaults-extra-file={defaults_file}", "mbilling",
             "--init-command=SET FOREIGN_KEY_CHECKS=0; SET UNIQUE_CHECKS=0; SET AUTOCOMMIT=0;"],
            "falha ao restaurar o banco de dados", stdin=f,
        )


def _run_update_script():
    # update.sh imprime o próprio banner ASCII -- suprime o stdout (stderr
    # continua capturado por _run, pra aparecer na mensagem se falhar).
    _run(["bash", UPDATE_SCRIPT], "falha ao rodar o update.sh do MagnusBilling", stdout=subprocess.DEVNULL)


def _restart_asterisk():
    _run(["systemctl", "restart", "asterisk"], "falha ao reiniciar o asterisk")


def _fix_web_permissions():
    _run(["chmod", "-R", "755", MBILLING_WEB_DIR], f"falha ao ajustar permissões de {MBILLING_WEB_DIR}")


def _read_mbilling_user_dbpass():
    content = open(RES_CONFIG_MYSQL).read()
    in_general = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_general = stripped == "[general]"
            continue
        if in_general and stripped.startswith("dbpass"):
            return stripped.split("=", 1)[1].strip()
    return None


def _reset_mbilling_user_password(defaults_file, dbpass):
    _run(
        ["mysql", f"--defaults-extra-file={defaults_file}", "mbilling", "-e",
         f"ALTER USER 'mbillingUser'@'localhost' IDENTIFIED BY '{dbpass}'; FLUSH PRIVILEGES;"],
        "falha ao atualizar a senha do usuário mbillingUser",
    )


def restore(extracted_dir, db_user, db_password):
    with _mysql_defaults_file(db_user, db_password) as defaults_file:
        _restore_database(defaults_file, os.path.join(extracted_dir, "tmp", "base.sql"))
        _copy_dir(os.path.join(extracted_dir, "etc", "asterisk"), DEFAULT_ASTERISK_DIR)
        ura_dir = os.path.join(extracted_dir, "tmp", "audios-ura")
        if os.path.isdir(ura_dir):
            _copy_dir(ura_dir, DEFAULT_SOUNDS_DIR)
        _run_update_script()
        _restart_asterisk()
        _fix_web_permissions()
        # sed no original não garante um match -- só reseta a senha do
        # mbillingUser se de fato achou o dbpass no res_config_mysql.conf.
        dbpass = _read_mbilling_user_dbpass()
        if dbpass:
            _reset_mbilling_user_password(defaults_file, dbpass)


def is_already_installed():
    return os.path.isdir(MBILLING_WEB_DIR)


def _download(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def run_installer():
    # handoff completo pro instalador oficial (interativo, pede confirmação
    # própria) -- sem check=True: um exit != 0 aqui é decisão de quem
    # respondeu os prompts do instalador, não uma falha do pvx pra reportar.
    with tempfile.TemporaryDirectory() as tmp_dir:
        installer_path = os.path.join(tmp_dir, "install.sh")
        data = _download(INSTALLER_URL)
        with open(installer_path, "wb") as f:
            f.write(data)
        os.chmod(installer_path, os.stat(installer_path).st_mode | 0o111)
        subprocess.run(["bash", installer_path], cwd=tmp_dir)
