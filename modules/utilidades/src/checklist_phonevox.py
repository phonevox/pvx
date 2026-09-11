import ipaddress
import json
import os
import re
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
_FIREWALL_IP_ACCEPT_FILENAME = "ip_accept.conf"
# mesma regex/fontes de firewall/src/asterisk_ips.py -- módulo isolado, sem
# import cruzado (ver nota no topo do arquivo), duplicação mínima de novo.
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
_PLACEHOLDER_IPS = {"0.0.0.0", "255.255.255.255"}
_ASTERISK_IP_SOURCES = ("sip show peers", "pjsip show endpoints", "sip show registry")
# mesma lista de firewall/src/defaults.py:DEFAULT_LISTS["ip_accept"] -- módulo
# isolado, sem import cruzado (ver nota no topo do arquivo). Manter em sincronia
# manualmente se a lista base mudar lá.
_FIREWALL_BASE_IPS = (
    "127.0.0.1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "189.124.85.75", "186.233.124.252", "189.124.85.152/29", "186.233.120.72/29",
    "179.199.136.199", "149.78.185.36", "31.97.160.127", "45.140.193.125", "186.233.122.92",
)


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


def _firewall_ip_accept_path():
    return pvx_config.modules_dir() / "firewall" / "state" / _FIREWALL_IP_ACCEPT_FILENAME


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


def _result(section, level, text):
    # "section" agrupa os itens na tela (ver main.py:_print_checklist) -- um
    # módulo pode contribuir mais de um item pra mesma seção (zabbix: config +
    # script de auditoria).
    return {"section": section, "level": level, "text": text}


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
        return _result("SSH Hardening", "warn", "não aplicado")

    record = _read_json(records[-1])
    if record is None:
        return _result("SSH Hardening", "warn", "não aplicado")
    if not record.get("config_valid", True):
        return _result("SSH Hardening", "warn", "aplicado, mas config resultante era inválida")
    return _result("SSH Hardening", "ok", "aplicado")


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
        return _result("Zabbix", "ok", "script de auditoria adicionado")
    return _result("Zabbix", "warn", "script de auditoria não adicionado")


def check_autobloqueador():
    data = _read_json(_AUTOBLOQUEADOR_STATE)
    if data is None:
        return _result("Autobloqueador", "warn", "não configurado")
    return _result("Autobloqueador", "ok", f"type={data.get('type', '?')}")


def _trusted_networks():
    try:
        lines = _firewall_ip_accept_path().read_text().splitlines()
    except OSError:
        return []
    networks = []
    for line in lines:
        entry = line.partition("#")[0].strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return networks


def _asterisk_cli(command, timeout=5):
    try:
        result = subprocess.run(["asterisk", "-rx", command], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _asterisk_connected_ips():
    ips = set()
    for command in _ASTERISK_IP_SOURCES:
        output = _asterisk_cli(command)
        if not output:
            continue
        ips.update(ip for ip in _IPV4_RE.findall(output) if ip not in _PLACEHOLDER_IPS)
    return ips


def check_firewall_base_ips():
    # achado ao vivo: `pvx firewall ip accept` numa central sem ip_accept.conf
    # ainda sobrescrevia a lista inteira com só a entrada nova, apagando os
    # IPs base da Phonevox -- técnico perdeu acesso à própria sessão SSH.
    trusted = _trusted_networks()
    missing = []
    for entry in _FIREWALL_BASE_IPS:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        if not any(network.version == t.version and network.subnet_of(t) for t in trusted):
            missing.append(entry)

    if not missing:
        return _result("Firewall", "ok", "IPs base da Phonevox presentes na whitelist")
    return _result(
        "Firewall", "warn",
        f"{len(missing)} IP(s) base da Phonevox fora da whitelist ({', '.join(missing)}) -- "
        "rode `pvx firewall ip trust-phonevox`",
    )


def check_firewall_asterisk_ips():
    connected = _asterisk_connected_ips()
    if not connected:
        return _result("Firewall", "ok", "nenhum IP conectado no Asterisk pra conferir")

    trusted = _trusted_networks()
    untrusted = sorted(
        ip for ip in connected
        if not any(ipaddress.ip_address(ip) in network for network in trusted)
    )
    if not untrusted:
        return _result("Firewall", "ok", "IPs conectados no Asterisk estão todos na whitelist")
    return _result(
        "Firewall", "warn",
        f"{len(untrusted)} IP(s) conectado(s) no Asterisk fora da whitelist "
        f"({', '.join(untrusted)}) -- rode `pvx firewall ip trust-asterisk`",
    )


def check_firewall_synced():
    # cross-módulo via CLI (mesmo padrão de autobackup/src/magnus_upload_ops.py,
    # que já roda "pvx magnus backup export ...") -- nunca importa o código do
    # firewall direto (módulo isolado), e reusa a lógica de verdade em vez de
    # duplicar a contagem de regras de dois engines (iptables/firewalld) aqui.
    try:
        result = subprocess.run(["pvx", "firewall", "check"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return _result("Firewall", "warn", "não consegui checar se está ativo/sincronizado")
    output = result.stdout.lower()
    if "status: ativo" in output:
        return _result("Firewall", "ok", "ativo e sincronizado")
    if "status: inativo" in output:
        return _result("Firewall", "warn", "inativo/não sincronizado -- rode `pvx firewall apply`")
    return _result("Firewall", "warn", "não consegui determinar o status")


def check_firewall_boot():
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", _FIREWALL_SYSTEMD_UNIT], capture_output=True, text=True,
        )
        enabled = result.stdout.strip() == "enabled"
    except OSError:
        enabled = False
    if enabled:
        return _result("Firewall", "ok", "start-on-boot habilitado")
    return _result("Firewall", "warn", "start-on-boot desabilitado")


# ordem = ordem de exibição -- seções adjacentes com o mesmo nome (zabbix)
# são agrupadas sob um único header (ver main.py:_print_checklist).
CHECKS = (
    check_ssl,
    check_autobackup,
    check_ssh_hardening,
    check_zabbix,
    check_zabbix_audit_script,
    check_autobloqueador,
    check_firewall_boot,
    check_firewall_synced,
    check_firewall_base_ips,
    check_firewall_asterisk_ips,
)


def run_all():
    return [check() for check in CHECKS]
