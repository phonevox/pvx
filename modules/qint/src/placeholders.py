from urllib.parse import urlsplit

PHP_COMMON = {
    "$server_local = ''": "asterisk_ip",
    "$protocol_web = ''": "_erp_url_scheme",
    "$servidor_web = ''": "_erp_url_host",
    "$porta_web = ''": "_erp_url_port",
    "$token = ''": "token",
}
PHP_SGP_EXTRA = {"$app = ''": "app"}

MACRO_COMMON = {
    "Set(dep_outros_assuntos=XXX)": "fila_geral",
    "Set(dep_comercial=XXX)": "fila_comercial",
    "Set(dep_suporte=XXX)": "fila_suporte",
    "Set(dep_financeiro=XXX)": "fila_financeiro",
    "Goto(timeconditions,TIMECONDITION_DESTINO,1)": "id_timecondition_exitpoint",
}

MACRO_IXCSOFT = {
    "Set(FILIAL_ID=XXX)": "id_filial",
    "Set(ocorrencia_outros_assuntos=XXX)": "id_assunto_geral",
    "Set(ocorrencia_comercial=XXX)": "id_assunto_comercial",
    "Set(ocorrencia_suporte=XXX)": "id_assunto_suporte",
    "Set(ocorrencia_financeiro=XXX)": "id_assunto_financeiro",
    "Set(setor_outros_assuntos=XXX)": "id_departamento_geral",
    "Set(setor_comercial=XXX)": "id_departamento_comercial",
    "Set(setor_suporte=XXX)": "id_departamento_suporte",
    "Set(setor_financeiro=XXX)": "id_departamento_financeiro",
}

MACRO_SGP = {
    "Set(ocorrencia_outros_assuntos=XXX)": "id_ocorrencia_geral",
    "Set(ocorrencia_comercial=XXX)": "id_ocorrencia_comercial",
    "Set(ocorrencia_comercial_adesao=XXX)": "id_ocorrencia_comercial",
    "Set(ocorrencia_comercial_cancelamento=XXX)": "id_ocorrencia_comercial",
    "Set(ocorrencia_suporte=XXX)": "id_ocorrencia_suporte",
    "Set(ocorrencia_financeiro=XXX)": "id_ocorrencia_financeiro",
    "Set(ocorrencia_financeiro_simples=XXX)": "id_ocorrencia_financeiro",
    "Set(ocorrencia_financeiro_bloqueio=XXX)": "id_ocorrencia_financeiro",
    "Set(motivoos_outros_assuntos=XXX)": "id_motivo_os_geral",
    "Set(motivoos_comercial_adesao=XXX)": "id_motivo_os_comercial",
    "Set(motivoos_comercial_cancelamento=XXX)": "id_motivo_os_comercial",
    "Set(motivoos_suporte=XXX)": "id_motivo_os_suporte",
    "Set(motivoos_financeiro_simples=XXX)": "id_motivo_os_financeiro",
    "Set(motivoos_financeiro_bloqueio=XXX)": "id_motivo_os_financeiro",
    "Set(setor_outros_assuntos=XXX)": "id_setor_geral",
    "Set(setor_comercial=XXX)": "id_setor_comercial",
    "Set(setor_suporte=XXX)": "id_setor_suporte",
    "Set(setor_financeiro=XXX)": "id_setor_financeiro",
}


def _split_erp_url(erp_url):
    parts = urlsplit(erp_url)
    return {
        "_erp_url_scheme": parts.scheme,
        "_erp_url_host": parts.hostname or "",
        "_erp_url_port": str(parts.port) if parts.port else "",
    }


def build_php_replacements(config):
    placeholders_ = dict(PHP_COMMON)
    if config["type"] == "sgp":
        placeholders_.update(PHP_SGP_EXTRA)

    values = {**config, **_split_erp_url(config["erp_url"])}
    return {placeholder: str(values[key]) for placeholder, key in placeholders_.items()}


def build_macro_replacements(config):
    placeholders_ = dict(MACRO_COMMON)
    if config["type"] == "ixcsoft":
        placeholders_.update(MACRO_IXCSOFT)
    elif config["type"] == "sgp":
        placeholders_.update(MACRO_SGP)

    return {placeholder: str(config[key]) for placeholder, key in placeholders_.items()}
