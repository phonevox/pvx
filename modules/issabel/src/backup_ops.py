import datetime
import os
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET

HELPER = "issabel-helper"

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


def available_components():
    components = dict(COMPONENTS)
    if os.path.isfile(_EXTRAS_MARKER):
        components.update(EXTRA_COMPONENTS)
    return components


def default_filename(now=None):
    now = now or datetime.datetime.now()
    return f"issabel-backup-{now:%Y%m%d%H%M%S}.tar"


def _split_path(filename_or_path):
    # issabel-helper só aceita --backupfile como nome sem diretório --
    # --tmpdir carrega o diretório de verdade. Um nome sem "/" (ex.: só
    # "x.tar") é relativo a onde o pvx foi chamado, não a um lugar fixo.
    directory, filename = os.path.split(filename_or_path)
    directory = os.path.abspath(directory) if directory else os.getcwd()
    return directory, filename


def export_backup(filename_or_path, components):
    if not shutil.which(HELPER):
        raise IssabelBackupError("não parece ser uma central Issabel (issabel-helper ausente)")
    if not components:
        raise IssabelBackupError("nenhum componente selecionado.")

    directory, filename = _split_path(filename_or_path)
    if not os.path.isdir(directory):
        raise IssabelBackupError(f"diretório não existe: {directory}")

    result = _run([
        HELPER, "backupengine", "--backup", "--backupfile", filename,
        "--tmpdir", directory, "--components", ",".join(components),
    ])
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        detail = _warning_text(result)
        msg = "issabel-helper rodou mas o arquivo de backup não foi gerado."
        raise IssabelBackupError(f"{msg} {detail}" if detail else msg)
    return path, _warning_text(result)


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


def inspect_backup(path):
    try:
        with tarfile.open(path) as tar:
            options_raw = tar.extractfile("backup/a_options.xml").read()
            versions_raw = tar.extractfile("backup/versions.xml").read()
    except (OSError, KeyError, tarfile.TarError, AttributeError) as e:
        raise IssabelBackupError(f"não foi possível ler o backup: {e}")

    components = [
        option.text for group in ET.fromstring(options_raw) for option in group
    ]
    versions = {
        program.get("id"): program.get("ver") for program in ET.fromstring(versions_raw)
    }
    return {"components": components, "versions": versions}


def installed_issabel_version():
    result = subprocess.run(
        ["rpm", "-q", "--queryformat", "%{version}", "issabel"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None
