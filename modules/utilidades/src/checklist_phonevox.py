import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pvx import config as pvx_config

# cada módulo é um subprojeto isolado (zipimport próprio, sem import cruzado
# de código -- ver /modules/CONTEXT.md) -- o que segue é a menor duplicação
# possível de caminho/formato de estado de cada módulo, só o suficiente pra
# LER (nunca escrever). Mesmo padrão de firewall/src/magnus_detect.py.
_LE_LIVE_DIR = "/etc/letsencrypt/live"
_ZABBIX_AGENT_CONFIG_PATHS = {
    "agent2": "/etc/zabbix/zabbix_agent2.conf",
    "agent": "/etc/zabbix/zabbix_agentd.conf",
}
_AUTOBLOQUEADOR_STATE = Path("/etc/phonevox/automacoes/state.json")
_FIREWALL_SYSTEMD_UNIT = "pvx-firewall.service"


# funções, não constantes: pvx_config.modules_dir() lê PVX_HOME em runtime --
# resolver isso uma vez só no import prenderia o valor ao PVX_HOME de quando
# o módulo foi carregado (achado ao vivo em teste: fixture troca PVX_HOME por
# teste, mas o import só acontece uma vez pra sessão inteira de testes).
def _autobackup_state_path():
    return pvx_config.modules_dir() / "autobackup" / "state" / "state.json"


def _ssh_hardening_state_dir():
    return pvx_config.modules_dir() / "ssh-hardening" / "state"


def _zabbix_state_dir():
    return pvx_config.modules_dir() / "zabbix" / "state"


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _read_params(path):
    # mesmo parser de zabbix/src/config.py:read_params() -- arquivo de config
    # do agent é "chave=valor", uma por linha.
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return {}
    params = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if sep:
            params[key] = value
    return params


def _result(label, level, detail):
    return {"label": label, "level": level, "detail": detail}


def _days_until_expiry(domain):
    cert_path = f"{_LE_LIVE_DIR}/{domain}/fullchain.pem"
    if not os.path.exists(cert_path):
        return None
    try:
        result = subprocess.run(
            ["openssl", "x509", "-enddate", "-noout", "-in", cert_path],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    _, _, raw_date = result.stdout.strip().partition("=")
    raw_date = raw_date.strip()
    if raw_date.endswith(" GMT"):
        raw_date = raw_date[: -len(" GMT")]
    try:
        expires_at = datetime.strptime(raw_date, "%b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (expires_at - datetime.now(timezone.utc)).days


def check_ssl():
    domains = []
    if os.path.isdir(_LE_LIVE_DIR):
        domains = sorted(
            name for name in os.listdir(_LE_LIVE_DIR) if os.path.isdir(os.path.join(_LE_LIVE_DIR, name))
        )
    if not domains:
        return _result("SSL", "warn", "nenhum certificado gerenciado")

    # reporta o domínio mais urgente (menos dias restantes) -- é o que mais
    # importa quando tem mais de um certificado na máquina.
    worst = None
    for domain in domains:
        days_left = _days_until_expiry(domain)
        if days_left is not None and (worst is None or days_left < worst[1]):
            worst = (domain, days_left)

    if worst is None:
        return _result("SSL", "warn", "não consegui ler a validade do certificado")

    domain, days_left = worst
    if days_left < 0:
        return _result("SSL", "error", f"{domain} expirado há {-days_left} dia(s)")
    return _result("SSL", "ok", f"{domain} expira em {days_left} dia(s)")


def check_autobackup():
    data = _read_json(_autobackup_state_path())
    if data is None:
        return _result("Autobackup", "warn", "não configurado")
    cron = f"{data.get('cron_minute', '?')} {data.get('cron_hour', '?')} * * *"
    return _result("Autobackup", "ok", f"cron: {cron}")


def check_ssh_hardening():
    state_dir = _ssh_hardening_state_dir()
    records = sorted(state_dir.glob("apply-*.json")) if state_dir.exists() else []
    if not records:
        return _result("SSH hardening", "warn", "não aplicado")

    record = _read_json(records[-1])
    if record is None:
        return _result("SSH hardening", "warn", "não aplicado")
    if not record.get("config_valid", True):
        return _result("SSH hardening", "warn", "aplicado, mas config resultante era inválida")
    return _result("SSH hardening", "ok", "aplicado")


def check_zabbix():
    variant_path = _zabbix_state_dir() / "agent_variant.txt"
    if not variant_path.exists():
        return _result("Zabbix", "warn", "não configurado")

    variant = variant_path.read_text().strip()
    config_path = _ZABBIX_AGENT_CONFIG_PATHS.get(variant)
    hostname = _read_params(config_path).get("Hostname") if config_path else None
    return _result("Zabbix", "ok", f"hostname={hostname}" if hostname else "configurado")


def check_zabbix_audit_script():
    entries = _read_json(_zabbix_state_dir() / "scripts.json") or {}
    if "audit" in entries:
        return _result("Zabbix -- script de auditoria", "ok", "adicionado")
    return _result("Zabbix -- script de auditoria", "warn", "não adicionado")


def check_autobloqueador():
    data = _read_json(_AUTOBLOQUEADOR_STATE)
    if data is None:
        return _result("Autobloqueador", "warn", "não configurado")
    return _result("Autobloqueador", "ok", f"type={data.get('type', '?')}")


def check_firewall_boot():
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", _FIREWALL_SYSTEMD_UNIT], capture_output=True, text=True,
        )
        enabled = result.stdout.strip() == "enabled"
    except OSError:
        enabled = False
    if enabled:
        return _result("Firewall (start-on-boot)", "ok", "habilitado")
    return _result("Firewall (start-on-boot)", "warn", "desabilitado")


CHECKS = (
    check_ssl,
    check_autobackup,
    check_ssh_hardening,
    check_zabbix,
    check_zabbix_audit_script,
    check_autobloqueador,
    check_firewall_boot,
)


def run_all():
    return [check() for check in CHECKS]
