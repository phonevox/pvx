import subprocess

import defaults
from validators import parse_port_spec


def _run(args, check=True):
    return subprocess.run(["firewall-cmd"] + args, capture_output=True, text=True, check=check)


def zone_exists(zone):
    return _run(["--info-zone", zone], check=False).returncode == 0


def ensure_zone(zone):
    if not zone_exists(zone):
        _run(["--permanent", "--new-zone", zone])
        _run(["--reload"])
    # target DROP explícito -- bug legado era zona sem target definido (fail-open).
    _run(["--permanent", "--zone", zone, "--set-target", "DROP"])
    _run(["--set-default-zone", zone])


def _rich_rule(priority, source=None, port=None, protocol=None, action="accept"):
    parts = [f'rule priority="{priority}"', 'family="ipv4"']
    if source:
        parts.append(f'source address="{source}"')
    if port:
        parts.append(f'port port="{port}" protocol="{protocol}"')
    parts.append(action)
    return " ".join(parts)


def _icmp_rule():
    return f'rule priority="{defaults.FIREWALLD_PRIORITY_ICMP}" family="ipv4" protocol value="icmp" accept'


def _rich_rule_present(zone, rule, permanent=False):
    args = (["--permanent"] if permanent else []) + ["--zone", zone, "--query-rich-rule", rule]
    return _run(args, check=False).returncode == 0


def failsafe_present(zone, ip):
    # estado em vigor AGORA -- sempre runtime, nunca permanent (é o que
    # `check`/status.py usa pra saber se a proteção está de fato ativa).
    return _rich_rule_present(zone, _rich_rule(defaults.FIREWALLD_PRIORITY_FAILSAFE, source=ip))


def insert_failsafe(zone, ip):
    # opera inteiramente em --permanent -- sync() dá um --reload no final
    # que promove tudo pro runtime de uma vez só. achado ao vivo (testando
    # com firewalld real): sem --permanent aqui, aquele --reload descartava
    # a regra recém-adicionada silenciosamente (reload recarrega DO
    # permanent, joga fora qualquer coisa só em runtime).
    rule = _rich_rule(defaults.FIREWALLD_PRIORITY_FAILSAFE, source=ip)
    if _rich_rule_present(zone, rule, permanent=True):
        return True
    _run(["--permanent", "--zone", zone, "--add-rich-rule", rule])
    return _rich_rule_present(zone, rule, permanent=True)


def count_rich_rules(zone):
    # zona pode nem existir ainda (antes do primeiro sync) -- não é erro,
    # só significa zero regras. runtime (não permanent) -- é o que está de
    # fato em vigor agora.
    listing = _run(["--zone", zone, "--list-rich-rules"], check=False)
    if listing.returncode != 0:
        return 0
    return len([line for line in listing.stdout.splitlines() if line.strip()])


def clear_zone_except_failsafe(zone, failsafe_rule):
    listing = _run(["--permanent", "--zone", zone, "--list-rich-rules"])
    for line in listing.stdout.splitlines():
        line = line.strip()
        if not line or line == failsafe_rule:
            continue
        _run(["--permanent", "--zone", zone, "--remove-rich-rule", line])


def port_rule_args(spec):
    port_range = f"{spec['start']}" if spec["start"] == spec["end"] else f"{spec['start']}-{spec['end']}"
    protocols = [spec["protocol"]] if spec["protocol"] else ["tcp", "udp"]
    return [(port_range, proto) for proto in protocols]


def sync(ip_accept, ip_deny, port_accept, port_deny, failsafe_ip):
    zone = defaults.FIREWALLD_ZONE
    ensure_zone(zone)

    failsafe_rule = None
    if failsafe_ip:
        failsafe_rule = _rich_rule(defaults.FIREWALLD_PRIORITY_FAILSAFE, source=failsafe_ip)
        if not insert_failsafe(zone, failsafe_ip):
            raise RuntimeError("não consegui confirmar a regra de failsafe -- abortando sem limpar nada.")

    clear_zone_except_failsafe(zone, failsafe_rule)

    # tudo abaixo é --permanent, de propósito -- só o --reload final (que
    # promove permanent -> runtime de uma vez) aplica de verdade.
    _run(["--permanent", "--zone", zone, "--add-rich-rule", _icmp_rule()])

    for ip, _ in ip_deny:
        _run(["--permanent", "--zone", zone, "--add-rich-rule",
              _rich_rule(defaults.FIREWALLD_PRIORITY_DENY_IP, source=ip, action="drop")])
    for ip, _ in ip_accept:
        _run(["--permanent", "--zone", zone, "--add-rich-rule",
              _rich_rule(defaults.FIREWALLD_PRIORITY_TRUSTED_IP, source=ip, action="accept")])

    for spec_str, _ in port_deny:
        for port_range, proto in port_rule_args(parse_port_spec(spec_str)):
            _run(["--permanent", "--zone", zone, "--add-rich-rule",
                  _rich_rule(defaults.FIREWALLD_PRIORITY_PORT_DENY, port=port_range, protocol=proto, action="drop")])
    for spec_str, _ in port_accept:
        for port_range, proto in port_rule_args(parse_port_spec(spec_str)):
            _run(["--permanent", "--zone", zone, "--add-rich-rule",
                  _rich_rule(defaults.FIREWALLD_PRIORITY_PORT_ACCEPT, port=port_range, protocol=proto,
                             action="accept")])

    _run(["--reload"])
