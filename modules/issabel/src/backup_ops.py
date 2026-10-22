import datetime
import io
import os
import re
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

HELPER = "issabel-helper"
# assinatura opcional embutida no próprio backup -- membro extra que o
# issabel-helper/backupengine nativo ignora de boa (não faz parte do
# a_options.xml), então não quebra `--restore` nativo nem retrocompat.
MANIFEST_MEMBER = "backup/PVX_MANIFEST.txt"

# lista oficial de componentes do backupengine do Issabel (a mesma tela de
# Backup/Restore da interface web) -- mesmo arquivo/estrutura em Issabel 4 e
# 5, então não precisa de tabela separada por versão.
COMPONENTS = {
    "as_db": "Asterisk: banco de dados",
    "as_config_files": "Asterisk: arquivos de configuração",
    "as_monitor": "Asterisk: gravações (monitor)",
    "as_voicemail": "Asterisk: correio de voz",
    "as_sounds": "Asterisk: sons",
    "as_mohmp3": "Asterisk: música de espera (MOH)",
    "as_dahdi": "Asterisk: configuração DAHDI",
    "fx_db": "Fax: banco de dados",
    "fx_pdf": "Fax: PDFs",
    "em_db": "Email: banco de dados",
    "em_mailbox": "Email: caixas de email",
    "ep_db": "Endpoint: banco de dados",
    "ep_config_files": "Endpoint: arquivos de configuração",
    "callcenter_db": "Call Center CE: banco de dados",
    "asternic_db": "Asternic: estatísticas do call center",
    "FOP2_settings_db": "FOP2: configurações de usuário",
    "sugar_db": "SugarCRM: banco de dados",
    "vtiger_db": "VtigerCRM: banco de dados",
    "a2billing_db": "A2Billing: banco de dados",
    "mysql_db": "MySQL: banco de dados geral",
    "menus_permissions": "Menus e permissões",
    "fop_config": "FOP: arquivos de configuração (Flash Operator Panel)",
    "calendar_db": "Agenda: banco de dados",
    "address_db": "Catálogo de endereços: banco de dados",
    "conference_db": "Conferência: banco de dados",
    "eop_db": "EOP: banco de dados",
}
# só existem em centrais com o backupengine já parcheado pela Phonevox
# (mesmo marker que o autobackup já usa) -- issabel-helper rejeita
# qualquer componente que não conheça, então nunca oferece isso à toa.
EXTRA_COMPONENTS = {
    "int_ixcsoft": "Phonevox: integração IXC",
    "int_sgp": "Phonevox: integração SGP",
    "int_receitanet": "Phonevox: integração ReceitaNet",
    "int_altarede": "Phonevox: integração AltaRede",
}
_EXTRAS_MARKER = "/usr/share/issabel/privileged/pvx-backupengine-extras"

# mesmos diretórios que a backupengine customizada (Backup::addCategory) faz
# backup/restore -- todos cópia crua de diretório, dono asterisk:asterisk,
# sem banco. Quando o destino não tem a engine customizada (marker ausente)
# mas o backup tem esses componentes, import_backup restaura na mão em vez
# de mandar pro issabel-helper (que dá error_exit fatal em componente
# desconhecido -- ver phonevox/issabel-backupengine).
# primeiro item de cada lista é o diretório IDENTIFICADOR único da
# integração (autodetect_components() confia nisso) -- os demais são
# auxiliares (sons, agi-bin, web) e podem colidir entre integrações (ex.:
# /var/lib/asterisk/sounds/ura-inteligente aparece tanto em int_sgp quanto
# em int_receitanet), então nunca servem sozinhos pra identificar qual é.
MANUAL_COMPONENTS = {
    "int_sgp": [
        "/etc/asterisk/sgp",
        "/var/lib/asterisk/agi-bin/sgp",
        "/var/lib/asterisk/sounds/sgp",
        "/var/lib/asterisk/sounds/ura-inteligente",
        "/var/www/html/sgp",
    ],
    "int_ixcsoft": [
        "/etc/asterisk/ixcsoft",
        "/var/lib/asterisk/agi-bin/ixcsoft",
        "/var/lib/asterisk/sounds/ixcsoft",
        "/var/lib/asterisk/moh/ixcsoft",
        "/var/www/html/ixcsoft",
    ],
    "int_receitanet": [
        "/etc/asterisk/receitanet",
        "/var/lib/asterisk/agi-bin/receitanet",
        "/var/lib/asterisk/sounds/ura-inteligente",
        "/var/www/html/receitanet",
    ],
    "int_altarede": [
        "/etc/asterisk/vox-ura",
        "/var/lib/asterisk/agi-bin/vox-ura",
        "/var/lib/asterisk/sounds/vox-ura",
    ],
}
_TAR_SUPPORTS_FILTER = "filter" in tarfile.TarFile.extractall.__code__.co_varnames


class IssabelBackupError(Exception):
    pass


def _run(args):
    # achado ao vivo: issabel-helper (igual a interface web nativa do
    # Issabel) retorna código != 0 sempre que QUALQUER componente individual
    # falha (banco que não existe nessa central, arquivo ausente, etc.),
    # mesmo quando o resultado final (arquivo de backup, restauração)
    # funcionou -- exit code aqui é só informativo, nunca o sinal de
    # verdade. Quem chama decide o que fazer com o resultado.
    return subprocess.run(args, capture_output=True, text=True)


def _warning_text(result):
    if result.returncode == 0:
        return None
    # achado no autobackup: issabel-helper/pbackup às vezes erram sem
    # escrever nada em stderr -- sem o fallback pro stdout, o motivo real
    # do erro some sem deixar rastro nenhum.
    return (result.stderr or result.stdout or "").strip() or None


# achado ao vivo (Issabel 5 real sem Call Center CE/Asternic/FOP2
# instalados): ao contrário de um componente que falha sozinho sem quebrar o
# backup como um todo, um componente que o issabel-helper dessa central
# específica simplesmente não implementa faz ele recusar o --components
# inteiro (nenhum arquivo sai). COMPONENTS é uma lista fixa do que o Issabel
# oficial *pode* ter -- não do que ESSA central tem instalado -- então
# qualquer um desses módulos opcionais (SugarCRM, VtigerCRM, A2Billing,
# FOP2, Call Center CE, Asternic) pode faltar em qualquer box real.
_UNIMPLEMENTED_RE = re.compile(r"unimplemented components:\s*([\w,]+)", re.IGNORECASE)


def available_components():
    components = dict(COMPONENTS)
    if os.path.isfile(_EXTRAS_MARKER):
        components.update(EXTRA_COMPONENTS)
    return components


# central sem o backupengine parcheado (marker ausente) não tem os extras em
# available_components(), mas pode ter os diretórios mesmo assim (integração
# instalada por fora do engine) -- mesma lista de diretórios que
# restore_manual_component já usa pra restaurar esses componentes na mão.
def autodetect_components(root="/"):
    return [
        key for key, dirs in MANUAL_COMPONENTS.items()
        if os.path.isdir(os.path.join(root, dirs[0].lstrip("/")))
    ]


def backupfile_for_dir(path):
    # mesma convenção de nome do backupengine customizado (Backup::addDirectory
    # sem $backupfile explícito): ltrim("/") do parentdir + "." + dirname,
    # com "/" -> "." -- usado pra achar o .tgz certo dentro do backup na hora
    # de restaurar um componente extra na mão (ver import_backup).
    parent, name = path.rsplit("/", 1)
    return f"{parent.lstrip('/')}.{name}".replace("/", ".") + ".tgz"


# regex que `modules/backup_restore/index.php` (System module do Issabel)
# exige pra listar/restaurar/baixar um backup na interface web nativa --
# confirmado lendo o fonte público (IssabelFoundation/system). Um nome fora
# desse padrão só funciona pelo próprio pvx (import/inspect), nunca aparece
# nem é aceito na tela "Sistema > Backup and Restore".
NATIVE_FILENAME_RE = re.compile(r"^(issabel|cloud)backup-\d{14}-\w{2}\.tar$")


def matches_native_naming(filename):
    return bool(NATIVE_FILENAME_RE.match(os.path.basename(filename)))


# bate exatamente com NATIVE_FILENAME_RE -- os 2 chars finais não têm
# significado nativo (lá são só session id do PHP); "px" (Phonevox) é a
# assinatura do pvx nesse espaço.
def default_filename(now=None):
    now = now or datetime.datetime.now()
    return f"issabelbackup-{now:%Y%m%d%H%M%S}-px.tar"


def _split_path(filename_or_path):
    # issabel-helper só aceita --backupfile como nome sem diretório --
    # --tmpdir carrega o diretório de verdade. Um nome sem "/" (ex.: só
    # "x.tar") é relativo a onde o pvx foi chamado, não a um lugar fixo.
    directory, filename = os.path.split(filename_or_path)
    directory = os.path.abspath(directory) if directory else os.getcwd()
    return directory, filename


# "componentes_manuais" distingue, pra quem inspecionar o backup depois, um
# componente que veio do backupengine de verdade de um que foi empacotado cru
# por fora dele (tar direto de diretório, sem a validação/tratamento que o
# engine faria) -- afeta o quanto dá pra confiar nele numa restauração.
def write_manifest(path, generated_by, manual_components=None):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    lines = [f"gerado_por={generated_by}", f"gerado_em={now}"]
    if manual_components:
        lines.append(f"componentes_manuais={','.join(manual_components)}")
    content = ("\n".join(lines) + "\n").encode()
    with tarfile.open(path, "a") as tar:
        info = tarfile.TarInfo(MANIFEST_MEMBER)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))


def export_backup(filename_or_path, components, generated_by=None):
    if not shutil.which(HELPER):
        raise IssabelBackupError("não parece ser uma central Issabel (issabel-helper ausente)")
    if not components:
        raise IssabelBackupError("nenhum componente selecionado.")

    directory, filename = _split_path(filename_or_path)
    if not os.path.isdir(directory):
        raise IssabelBackupError(f"diretório não existe: {directory}")

    path = os.path.join(directory, filename)
    remaining = list(components)
    dropped = []
    while True:
        result = _run([
            HELPER, "backupengine", "--backup", "--backupfile", filename,
            "--tmpdir", directory, "--components", ",".join(remaining),
        ])
        if os.path.isfile(path):
            break
        detail = _warning_text(result)
        match = detail and _UNIMPLEMENTED_RE.search(detail)
        unimplemented = [c for c in match.group(1).split(",") if c in remaining] if match else []
        if not unimplemented:
            msg = "issabel-helper rodou mas o arquivo de backup não foi gerado."
            raise IssabelBackupError(f"{msg} {detail}" if detail else msg)
        dropped.extend(unimplemented)
        remaining = [c for c in remaining if c not in unimplemented]
        if not remaining:
            raise IssabelBackupError(
                "nenhum dos componentes selecionados é suportado por este issabel-helper "
                f"(não implementado(s): {', '.join(dropped)})."
            )

    if generated_by:
        write_manifest(path, generated_by)
    warning = _warning_text(result)
    if dropped:
        note = (
            f"componente(s) não suportado(s) nesta central, removido(s) automaticamente do "
            f"backup: {', '.join(dropped)}."
        )
        warning = f"{note} {warning}" if warning else note
    return path, warning


def _write_options_xml(backup_path, components, mode):
    options = "".join(f"<option>{escape(c)}</option>" for c in components)
    content = f'<raiz><options id="pvx">{options}</options></raiz>'.encode()
    with tarfile.open(backup_path, mode) as tar:
        info = tarfile.TarInfo("backup/a_options.xml")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))


def _write_versions_xml(backup_path, issabel_version):
    program = f'<program id="issabelpbx" ver="{issabel_version}" rel="1"/>' if issabel_version else ""
    content = f"<versions>{program}</versions>".encode()
    with tarfile.open(backup_path, "w") as tar:
        info = tarfile.TarInfo("backup/versions.xml")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))


# tarfile.getmember()/extractfile() resolve um nome duplicado pro ÚLTIMO
# membro com esse nome no arquivo -- então gravar de novo o a_options.xml
# (append) substitui a leitura de inspect_backup() sem precisar reescrever o
# tar inteiro. Usado tanto pro shell manual quanto pra registrar, depois de
# um export normal, os componentes autodetectados que foram anexados por
# fora do issabel-helper.
def record_components(backup_path, components):
    _write_options_xml(backup_path, components, mode="a")


# usado quando NENHUM componente vai pro issabel-helper (só autodetectados) --
# gera um backup válido do zero (mesmos dois manifestos que inspect_backup()
# exige) pra export_manual_component ter em cima do que anexar os .tgz.
def create_manual_backup_shell(filename_or_path, components, generated_by=None):
    directory, filename = _split_path(filename_or_path)
    if not os.path.isdir(directory):
        raise IssabelBackupError(f"diretório não existe: {directory}")

    path = os.path.join(directory, filename)
    _write_versions_xml(path, installed_issabel_version())
    record_components(path, components)
    if generated_by:
        write_manifest(path, generated_by, manual_components=components)
    return path


# contraparte do restore_manual_component -- mesma convenção de nome
# (backupfile_for_dir) e mesmo arcname (nome cru do diretório, sem o
# caminho), pra um backup gerado aqui restaurar direitinho do outro lado.
def export_manual_component(backup_path, key, root="/"):
    backed_up = []
    with tarfile.open(backup_path, "a") as tar:
        for dir_path in MANUAL_COMPONENTS[key]:
            src = os.path.join(root, dir_path.lstrip("/"))
            if not os.path.isdir(src):
                continue

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as inner:
                inner.add(src, arcname=os.path.basename(dir_path))
            buf.seek(0)

            info = tarfile.TarInfo(f"backup/{backupfile_for_dir(dir_path)}")
            info.size = buf.getbuffer().nbytes
            tar.addfile(info, buf)
            backed_up.append(dir_path)
    return backed_up


def import_backup(filename_or_path, components):
    if not shutil.which(HELPER):
        raise IssabelBackupError("não parece ser uma central Issabel (issabel-helper ausente)")
    if not components:
        raise IssabelBackupError("nenhum componente selecionado.")

    directory, filename = _split_path(filename_or_path)
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        raise IssabelBackupError(f"arquivo de backup não encontrado: {path}")

    result = _run([
        HELPER, "backupengine", "--restore", "--backupfile", filename,
        "--tmpdir", directory, "--components", ",".join(components),
    ])
    return _warning_text(result)


def run_native_migration(filename_or_path):
    # migração 4->5: em vez de replicar campo a campo o que o
    # backupengine/menus_permissions quebra (menu.db, senha de admin,
    # tabela de versão de módulos), usa o migrador nativo do Issabel
    # (issabel-helper migration -> issabel_migration.sh), a mesma coisa que
    # o botão "Migrate from Issabel 4" da própria interface web roda.
    if not shutil.which(HELPER):
        raise IssabelBackupError("não parece ser uma central Issabel (issabel-helper ausente)")
    directory, filename = _split_path(filename_or_path)
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        raise IssabelBackupError(f"arquivo de backup não encontrado: {path}")

    result = _run([HELPER, "migration", path])
    return _warning_text(result)


def restore_manual_component(backup_path, key, root="/"):
    restored = []
    with tarfile.open(backup_path) as tar:
        names = set(tar.getnames())
        for dir_path in MANUAL_COMPONENTS[key]:
            member = f"backup/{backupfile_for_dir(dir_path)}"
            if member not in names:
                continue

            parent = os.path.join(root, os.path.dirname(dir_path).lstrip("/"))
            os.makedirs(parent, exist_ok=True)
            with tarfile.open(fileobj=tar.extractfile(member)) as inner:
                kwargs = {"filter": "data"} if _TAR_SUPPORTS_FILTER else {}
                inner.extractall(parent, **kwargs)

            dest = os.path.join(root, dir_path.lstrip("/"))
            subprocess.run(["chown", "-R", "asterisk:asterisk", dest])
            restored.append(dir_path)
    return restored


def inspect_backup(path):
    try:
        with tarfile.open(path) as tar:
            options_raw = tar.extractfile("backup/a_options.xml").read()
            versions_raw = tar.extractfile("backup/versions.xml").read()
            manifest_raw = None
            if MANIFEST_MEMBER in tar.getnames():
                manifest_raw = tar.extractfile(MANIFEST_MEMBER).read()
    except (OSError, KeyError, tarfile.TarError, AttributeError) as e:
        raise IssabelBackupError(f"não foi possível ler o backup: {e}")

    components = [
        option.text for group in ET.fromstring(options_raw) for option in group
    ]
    versions = {
        program.get("id"): program.get("ver") for program in ET.fromstring(versions_raw)
    }
    manifest = {}
    if manifest_raw:
        for line in manifest_raw.decode().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                manifest[key] = value
    return {"components": components, "versions": versions, "manifest": manifest}


def installed_issabel_version():
    # achado ao vivo (2026-10): "issabelpbx" (sem hífen) pode nem estar
    # instalado numa central real (Issabel 5 testada só tinha "issabel-pbx",
    # com hífen) -- e em centrais com histórico de upgrade, "issabelpbx" sem
    # hífen pode existir mas ser a versão de um framework interno bem
    # diferente da versão de produto (ex.: 2.11.0 vs 4.0.0 de "issabel-pbx"
    # na mesma central). "issabel-pbx" com hífen é o pacote de produto de
    # verdade -- prioriza ele. "issabel" é meta-pacote, às vezes ausente.
    for pkg in ("issabel-pbx", "issabelpbx", "issabel"):
        result = subprocess.run(
            ["rpm", "-q", "--queryformat", "%{version}", pkg],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return None


# achado ao vivo (2026-10): um restore (normal ou migração) pode trocar
# arquivos que o Asterisk já tem abertos (ex.: astdb.sqlite3) -- sem
# reiniciar, a conexão antiga fica presa apontando pro estado de antes do
# restore, e toda escrita nova falha (db.c ast_db_put: SQL logic error)
# mesmo com o arquivo no disco já correto. run_native_migration() já
# reinicia sozinho no fim (mesma convenção do próprio issabel_migration.sh
# nativo) -- import_backup() (restore normal) não reiniciava nada.
def restart_asterisk():
    result = subprocess.run(["asterisk", "-rx", "core restart now"], capture_output=True, text=True)
    if result.returncode != 0:
        return (result.stderr or result.stdout or "").strip() or None
    return None
