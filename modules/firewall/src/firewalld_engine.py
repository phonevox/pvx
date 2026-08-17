import subprocess

import defaults


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


def _rich_rule_present(zone, rule):
    return _run(["--zone", zone, "--query-rich-rule", rule], check=False).returncode == 0


def failsafe_present(zone, ip):
    return _rich_rule_present(zone, _rich_rule(defaults.FIREWALLD_PRIORITY_FAILSAFE, source=ip))


def insert_failsafe(zone, ip):
    rule = _rich_rule(defaults.FIREWALLD_PRIORITY_FAILSAFE, source=ip)
    if _rich_rule_present(zone, rule):
        return True
    _run(["--zone", zone, "--add-rich-rule", rule])
    return _rich_rule_present(zone, rule)


def count_rich_rules(zone):
    listing = _run(["--zone", zone, "--list-rich-rules"])
    return len([line for line in listing.stdout.splitlines() if line.strip()])


def clear_zone_except_failsafe(zone, failsafe_rule):
    listing = _run(["--zone", zone, "--list-rich-rules"])
    for line in listing.stdout.splitlines():
        line = line.strip()
        if not line or line == failsafe_rule:
            continue
        _run(["--zone", zone, "--remove-rich-rule", line])


def port_rule_args(spec):
    port_range = f"{spec['start']}" if spec["start"] == spec["end"] else f"{spec['start']}-{spec['end']}"
    protocols = [spec["protocol"]] if spec["protocol"] else ["tcp", "udp"]
    return [(port_range, proto) for proto in protocols]


def sync(ip_accept, ip_deny, port_accept, port_deny, failsafe_ip):
    from validators import parse_port_spec

    zone = defaults.FIREWALLD_ZONE
    ensure_zone(zone)

    failsafe_rule = None
    if failsafe_ip:
        failsafe_rule = _rich_rule(defaults.FIREWALLD_PRIORITY_FAILSAFE, source=failsafe_ip)
        if not insert_failsafe(zone, failsafe_ip):
            raise RuntimeError("não consegui confirmar a regra de failsafe -- abortando sem limpar nada.")

    clear_zone_except_failsafe(zone, failsafe_rule)

    _run(["--zone", zone, "--add-rich-rule", _icmp_rule()])

    for ip, _ in ip_deny:
        _run(["--zone", zone, "--add-rich-rule",
              _rich_rule(defaults.FIREWALLD_PRIORITY_DENY_IP, source=ip, action="drop")])
    for ip, _ in ip_accept:
        _run(["--zone", zone, "--add-rich-rule",
              _rich_rule(defaults.FIREWALLD_PRIORITY_TRUSTED_IP, source=ip, action="accept")])

    for spec_str, _ in port_deny:
        for port_range, proto in port_rule_args(parse_port_spec(spec_str)):
            _run(["--zone", zone, "--add-rich-rule",
                  _rich_rule(defaults.FIREWALLD_PRIORITY_PORT_DENY, port=port_range, protocol=proto, action="drop")])
    for spec_str, _ in port_accept:
        for port_range, proto in port_rule_args(parse_port_spec(spec_str)):
            _run(["--zone", zone, "--add-rich-rule",
                  _rich_rule(defaults.FIREWALLD_PRIORITY_PORT_ACCEPT, port=port_range, protocol=proto,
                             action="accept")])

    _run(["--reload"])
