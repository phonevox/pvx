COMMON_DEFAULTS = {
    "sftp_port": 22,
    "sftp_remote_path": "/sfiles/qint/integracoes",
    "sftp_versao": "recent",
}

TYPE_DEFAULTS = {
    "ixcsoft": {"id_filial": "1"},
    "sgp": {"app": "app"},
}

REQUIRED_FIELDS = {
    "common": [
        "sftp_user", "sftp_host", "erp_url", "token", "id_timecondition_exitpoint",
        "fila_geral", "fila_comercial", "fila_suporte", "fila_financeiro", "asterisk_ip",
    ],
    "ixcsoft": [
        "id_departamento_geral", "id_departamento_comercial",
        "id_departamento_suporte", "id_departamento_financeiro",
        "id_assunto_geral", "id_assunto_comercial", "id_assunto_suporte", "id_assunto_financeiro",
    ],
    "sgp": [
        "id_setor_geral", "id_setor_comercial", "id_setor_suporte", "id_setor_financeiro",
        "id_ocorrencia_geral", "id_ocorrencia_comercial",
        "id_ocorrencia_suporte", "id_ocorrencia_financeiro",
        "id_motivo_os_geral", "id_motivo_os_comercial",
        "id_motivo_os_suporte", "id_motivo_os_financeiro",
    ],
}

# caminhos padrão de instalação Asterisk/Issabel -- confirmar contra um
# Issabel real antes de qualquer deploy de produção, nunca validados aqui.
DESTINATION_BASE_DIRS = {
    "agi": "/var/lib/asterisk/agi-bin",
    "php": "/var/www/html",
    "dialplan": "/etc/asterisk",
    "moh": "/var/lib/asterisk/moh",
    "audio": "/var/lib/asterisk/sounds/custom",
}


def apply_defaults(config):
    type_ = config.get("type")
    return {**COMMON_DEFAULTS, **TYPE_DEFAULTS.get(type_, {}), **config}


def missing_fields(config):
    type_ = config.get("type")
    required = REQUIRED_FIELDS["common"] + REQUIRED_FIELDS.get(type_, [])
    return [field for field in required if not config.get(field)]
