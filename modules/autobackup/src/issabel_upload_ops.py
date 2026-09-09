import datetime
import os
import subprocess
import tarfile
import tempfile

# porta pro Python da orquestração de scripts/issabel.sh do pbackup --
# centralizado aqui pra não depender de acompanhar mudanças em outro repo.
# A geração em si continua sendo trabalho do próprio issabel-helper (não dá
# nem faz sentido reimplementar isso -- é ferramenta oficial do Issabel).
BACKUP_DIR = "/var/www/backup"
MONITOR_DIR = "/var/spool/asterisk/monitor"
REMOTE_CONFIG_FOLDER = "/configuration"
REMOTE_RECORDINGS_FOLDER = "/recordings"

# mesma lista de componentes do issabel.sh original.
_COMPONENTS = (
    "as_db,as_config_files,as_sounds,as_mohmp3,as_dahdi,fx_db,fx_pdf,ep_db,"
    "ep_config_files,callcenter_db,asternic_db,FOP2_settings_db,sugar_db,"
    "vtiger_db,a2billing_db,mysql_db,menus_permissions,calendar_db,address_db,"
    "conference_db,eop_db"
)
_EXTRA_COMPONENTS = "int_ixcsoft,int_sgp,int_receitanet,int_altarede"
_EXTRAS_MARKER = "/usr/share/issabel/privileged/pvx-backupengine-extras"

# janela de gravações do issabel.sh original -- últimos 3 dias.
_RECORDINGS_DAYS = (1, 2, 3)


class IssabelUploadError(Exception):
    pass


def _run(args, error):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise IssabelUploadError(f"{error}{': ' + detail if detail else ''}")


def backup_filename(now=None):
    now = now or datetime.datetime.now()
    return f"issabelbackup-{now:%Y%m%d%H%M%S}-06.tar"


def _components():
    components = _COMPONENTS
    if os.path.isfile(_EXTRAS_MARKER):
        components += f",{_EXTRA_COMPONENTS}"
    return components


def generate_config_backup():
    if not os.path.isfile("/usr/bin/issabel-helper"):
        raise IssabelUploadError("não parece ser uma central Issabel (/usr/bin/issabel-helper ausente)")

    filename = backup_filename()
    _run(
        ["issabel-helper", "backupengine", "--backup", "--backupfile", filename,
         "--tmpdir", BACKUP_DIR, "--components", _components()],
        "falha ao gerar o backup de configuração via issabel-helper",
    )

    path = os.path.join(BACKUP_DIR, filename)
    if not os.path.isfile(path):
        raise IssabelUploadError("issabel-helper rodou mas o arquivo de backup não foi gerado")
    return path


def archive_recent_recordings(tmp_dir):
    archives = []
    for days_ago in _RECORDINGS_DAYS:
        day = datetime.date.today() - datetime.timedelta(days=days_ago)
        local_dir = os.path.join(MONITOR_DIR, f"{day:%Y}", f"{day:%m}", f"{day:%d}")
        if not os.path.isdir(local_dir):
            continue

        archive_path = os.path.join(tmp_dir, f"recordings-{days_ago}d.tar.gz")
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(local_dir, arcname=os.path.basename(local_dir))

        remote = f"{REMOTE_RECORDINGS_FOLDER}/{day:%Y}/{day:%m}/{day:%d}"
        archives.append((archive_path, remote))
    return archives


def export_and_upload(upload_url, token, configuration=True, recordings=False):
    if not configuration and not recordings:
        raise IssabelUploadError("nada pra fazer -- configuration e recordings desligados.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        files = archive_recent_recordings(tmp_dir) if recordings else []

        config_path = None
        if configuration:
            config_path = generate_config_backup()
            files.append((config_path, REMOTE_CONFIG_FOLDER))

        files_arg = ",".join(f"{local}:{remote}" for local, remote in files)
        _run(
            ["pbackup", "--files", files_arg, "--to", f"{upload_url}:/", "--token", token],
            "falha ao enviar o backup pro UOE",
        )

        # só limpa o backup de configuração se o upload deu certo -- as
        # gravações em tmp_dir já somem sozinhas ao sair do `with` (igual o
        # TMP_DIR do issabel.sh original, sempre limpo no fim).
        if config_path and os.path.isfile(config_path):
            os.remove(config_path)
