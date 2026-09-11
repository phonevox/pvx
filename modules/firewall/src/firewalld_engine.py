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


def expected_rule_count(ip_accept, ip_deny, port_accept, port_deny):
    # espelha a expansão real de sync() (port_rule_args) -- 1 regra por IP +
    # 1 pro icmp, mas uma porta sem protocolo explícito vira 2 (tcp + udp).
    total = len(ip_accept) + len(ip_deny) + 1  # +1: rich-rule de icmp
    for spec_str, _ in list(port_deny) + list(port_accept):
        total += len(port_rule_args(parse_port_spec(spec_str)))
    return total


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


def _conflicts_with_denied(port_str, proto, specs):
    if "-" in port_str or not port_str.isdigit():
        return False  # faixa -- fora de escopo do reconciliador hoje.
    port_num = int(port_str)
    return any(
        (spec["protocol"] is None or spec["protocol"] == proto) and spec["start"] <= port_num <= spec["end"]
        for spec in specs
    )


def remove_conflicting_ports(zone, port_deny):
    # achado ao vivo (MagnusBilling): o instalador do Magnus abre porta 22/tcp pra
    # QUALQUER origem via --add-port simples -- isso é avaliado ANTES da nossa
    # rich-rule de port_deny (prioridade positiva), então o allow do Magnus sempre
    # ganha e port_deny vira decoração pras portas que ele já tinha aberto. Só dá
    # pra fazer port_deny valer de verdade removendo a porta simples conflitante.
    listing = _run(["--permanent", "--zone", zone, "--list-ports"], check=False)
    if listing.returncode != 0:
        return
    specs = [parse_port_spec(spec_str) for spec_str, _ in port_deny]
    for entry in listing.stdout.split():
        port_str, _, proto = entry.partition("/")
        if _conflicts_with_denied(port_str, proto, specs):
            _run(["--permanent", "--zone", zone, "--remove-port", entry])


def _service_ports(service):
    result = _run(["--info-service", service], check=False)
    if result.returncode != 0:
        return []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("ports:"):
            return line[len("ports:"):].split()
    return []


def remove_conflicting_services(zone, port_deny):
    # achado ao vivo (MagnusBilling): além de porta simples, a zona também tinha o
    # serviço nomeado "ssh" (mecanismo separado de --list-ports, mesma prioridade
    # de avaliação) reabrindo a 22 mesmo depois da porta simples já removida.
    listing = _run(["--permanent", "--zone", zone, "--list-services"], check=False)
    if listing.returncode != 0:
        return
    specs = [parse_port_spec(spec_str) for spec_str, _ in port_deny]
    for service in listing.stdout.split():
        for entry in _service_ports(service):
            port_str, _, proto = entry.partition("/")
            if _conflicts_with_denied(port_str, proto, specs):
                _run(["--permanent", "--zone", zone, "--remove-service", service])
                break


def sync(ip_accept, ip_deny, port_accept, port_deny, failsafe_ip, zone=None, manage_zone=True):
    zone = zone or defaults.FIREWALLD_ZONE
    if manage_zone:
        ensure_zone(zone)

    failsafe_rule = None
    if failsafe_ip:
        failsafe_rule = _rich_rule(defaults.FIREWALLD_PRIORITY_FAILSAFE, source=failsafe_ip)
        if not insert_failsafe(zone, failsafe_ip):
            raise RuntimeError("não consegui confirmar a regra de failsafe -- abortando sem limpar nada.")

    clear_zone_except_failsafe(zone, failsafe_rule)

    if not manage_zone:
        # só faz sentido numa zona alheia -- a nossa própria nunca tem porta/serviço
        # de outra ferramenta pra reconciliar.
        remove_conflicting_ports(zone, port_deny)
        remove_conflicting_services(zone, port_deny)

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
