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
    "145.223.92.246",
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


def _result(rule, description, value, level):
    # pedido ao vivo: "section"+"text" misturava descrição e valor dinâmico
    # no mesmo texto, difícil saber o que cada item significa -- agora regra
    # (nome do item), descrição (fixa, o que ele checa) e valor (dinâmico)
    # são campos separados; "resumo" (passa/não) vem do level, via
    # widgets.status_cell em main.py:_print_checklist.
    return {"rule": rule, "description": description, "value": value, "level": level}


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
    description = "dias até o certificado gerenciado mais próximo expirar"
    domains = []
    if os.path.isdir(_LE_LIVE_DIR):
        domains = sorted(
            name for name in os.listdir(_LE_LIVE_DIR) if os.path.isdir(os.path.join(_LE_LIVE_DIR, name))
        )
    if not domains:
        return _result("SSL", description, "nenhum certificado gerenciado", "warn")

    # reporta o domínio mais urgente (menos dias restantes) -- é o que mais
    # importa quando tem mais de um certificado na máquina.
    worst = None
    for domain in domains:
        days_left = _days_until_expiry(domain)
        if days_left is not None and (worst is None or days_left < worst[1]):
            worst = (domain, days_left)

    if worst is None:
        return _result("SSL", description, "não consegui ler a validade do certificado", "warn")

    domain, days_left = worst
    if days_left < 0:
        return _result("SSL", description, f"{domain} expirado há {-days_left} dia(s)", "error")
    return _result("SSL", description, f"{domain} expira em {days_left} dia(s)", "ok")


def check_autobackup():
    description = "backup automático agendado (cron)"
    data = _read_json(_autobackup_state_path())
    if data is None:
        return _result("Autobackup", description, "não configurado", "warn")
    cron = f"{data.get('cron_minute', '?')} {data.get('cron_hour', '?')} * * *"
    return _result("Autobackup", description, f"cron: {cron}", "ok")


def check_ssh_hardening():
    description = "hardening de SSH aplicado e com config resultante válida"
    state_dir = _ssh_hardening_state_dir()
    records = sorted(state_dir.glob("apply-*.json")) if state_dir.exists() else []
    if not records:
        return _result("SSH Hardening", description, "não aplicado", "warn")

    record = _read_json(records[-1])
    if record is None:
        return _result("SSH Hardening", description, "não aplicado", "warn")
    if not record.get("config_valid", True):
        return _result("SSH Hardening", description, "aplicado, mas config resultante era inválida", "warn")
    return _result("SSH Hardening", description, "aplicado", "ok")


def check_zabbix():
    description = "agent Zabbix configurado"
    variant_path = _zabbix_state_dir() / "agent_variant.txt"
    if not variant_path.exists():
        return _result("Zabbix", description, "não configurado", "warn")

    variant = variant_path.read_text().strip()
    config_path = _ZABBIX_AGENT_CONFIG_PATHS.get(variant)
    hostname = _read_params(config_path).get("Hostname") if config_path else None
    return _result("Zabbix", description, f"hostname={hostname}" if hostname else "configurado", "ok")


def check_zabbix_audit_script():
    description = "script de auditoria adicionado ao Zabbix"
    entries = _read_json(_zabbix_state_dir() / "scripts.json") or {}
    if "audit" in entries:
        return _result("Zabbix (script de auditoria)", description, "adicionado", "ok")
    return _result("Zabbix (script de auditoria)", description, "não adicionado", "warn")


def check_autobloqueador():
    description = "bloqueio automático de tentativas configurado"
    data = _read_json(_AUTOBLOQUEADOR_STATE)
    if data is None:
        return _result("Autobloqueador", description, "não configurado", "warn")
    return _result("Autobloqueador", description, f"type={data.get('type', '?')}", "ok")


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
    description = "IPs base da Phonevox presentes na whitelist do firewall"
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
        return _result("Firewall (IPs base)", description, "presentes", "ok")
    return _result(
        "Firewall (IPs base)", description,
        f"{len(missing)} fora ({', '.join(missing)}) -- rode `pvx firewall ip trust-phonevox`",
        "warn",
    )


def check_firewall_asterisk_ips():
    description = "IPs conectados no Asterisk estão todos na whitelist do firewall"
    connected = _asterisk_connected_ips()
    if not connected:
        return _result("Firewall (IPs Asterisk)", description, "nenhum IP conectado pra conferir", "ok")

    trusted = _trusted_networks()
    untrusted = sorted(
        ip for ip in connected
        if not any(ipaddress.ip_address(ip) in network for network in trusted)
    )
    if not untrusted:
        return _result("Firewall (IPs Asterisk)", description, "todos na whitelist", "ok")
    return _result(
        "Firewall (IPs Asterisk)", description,
        f"{len(untrusted)} fora ({', '.join(untrusted)}) -- rode `pvx firewall ip trust-asterisk`",
        "warn",
    )


def _firewall_check_json():
    # cross-módulo via CLI (mesmo padrão de autobackup/src/magnus_upload_ops.py,
    # que já roda "pvx magnus backup export ...") -- nunca importa o código do
    # firewall direto (módulo isolado). `--json` é o contrato estável: nunca
    # muda com o tema/formato de exibição escolhido pelo usuário (achado ao
    # vivo: scraping de texto formatado quebrou quando o display mudou).
    try:
        result = subprocess.run(
            ["pvx", "firewall", "check", "--json"], capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


def check_firewall_synced():
    description = "engine ativo e com as regras batendo com a config atual"
    status = _firewall_check_json()
    if status is None:
        return _result("Firewall (sincronizado)", description, "não consegui checar", "warn")
    if status.get("engine_active") and status.get("synced"):
        return _result("Firewall (sincronizado)", description, "ativo e sincronizado", "ok")
    return _result(
        "Firewall (sincronizado)", description, "inativo/não sincronizado -- rode `pvx firewall apply`", "warn",
    )


def check_firewall_geoban():
    description = "bloqueio geográfico ligado (toda porta, exceto IPs confiáveis)"
    status = _firewall_check_json()
    if status is None:
        return _result("Firewall (geoban)", description, "não consegui checar", "warn")
    countries = ((status.get("lists") or {}).get("geo_accept")) or []
    if countries:
        names = ", ".join(cc for cc, _ in countries)
        return _result("Firewall (geoban)", description, f"ligado ({names})", "ok")
    return _result(
        "Firewall (geoban)", description,
        "desligado -- avalie `pvx firewall geo enable` pra bloquear acesso de fora do Brasil",
        "warn",
    )


_ADMIN_PORTS = ((3306, "MySQL"), (5038, "AMI"))


def _port_spec_covers(spec, port):
    # mesmo formato do firewall: "3306/tcp", "10000-20000/udp", "20-23" (sem
    # protocolo = tcp e udp). AMI/MySQL são tcp -- spec udp nunca cobre.
    ports, _, protocol = str(spec).partition("/")
    if protocol and protocol != "tcp":
        return False
    start, _, end = ports.partition("-")
    try:
        return int(start) <= port <= int(end or start)
    except ValueError:
        return False


def check_firewall_admin_ports():
    description = "MySQL (3306) e AMI (5038) fechados pro mundo (só IPs confiáveis passam)"
    status = _firewall_check_json()
    if status is None:
        return _result("Firewall (AMI/MySQL)", description, "não consegui checar", "warn")
    lists_data = status.get("lists") or {}
    accepted = [spec for spec, _ in lists_data.get("port_accept") or []]
    denied = [spec for spec, _ in lists_data.get("port_deny") or []]
    # deny vence accept na mesma chain; fora das duas, o catch-all derruba.
    exposed = [
        f"{label} ({port}/tcp)" for port, label in _ADMIN_PORTS
        if any(_port_spec_covers(s, port) for s in accepted) and not any(_port_spec_covers(s, port) for s in denied)
    ]
    if not exposed:
        return _result("Firewall (AMI/MySQL)", description, "bloqueados", "ok")
    return _result(
        "Firewall (AMI/MySQL)", description,
        f"liberado pro mundo: {', '.join(exposed)} -- rode `pvx firewall port deny <porta>`",
        "error",
    )


def check_firewall_boot():
    description = "reaplica as regras sozinho depois de reiniciar (systemd)"
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", _FIREWALL_SYSTEMD_UNIT], capture_output=True, text=True,
        )
        enabled = result.stdout.strip() == "enabled"
    except OSError:
        enabled = False
    if enabled:
        return _result("Firewall (boot)", description, "habilitado", "ok")
    return _result("Firewall (boot)", description, "desabilitado", "warn")


# ordem = ordem de exibição na tabela (ver main.py:_print_checklist).
CHECKS = (
    check_ssl,
    check_autobackup,
    check_ssh_hardening,
    check_zabbix,
    check_zabbix_audit_script,
    check_autobloqueador,
    check_firewall_boot,
    check_firewall_synced,
    check_firewall_geoban,
    check_firewall_admin_ports,
    check_firewall_base_ips,
    check_firewall_asterisk_ips,
)


def run_all():
    return [check() for check in CHECKS]
