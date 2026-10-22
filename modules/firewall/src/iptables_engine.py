import subprocess

import defaults
from validators import parse_port_spec


def _run(args, check=True):
    return subprocess.run(["iptables"] + args, capture_output=True, text=True, check=check)


def chain_exists(chain):
    return _run(["-nL", chain], check=False).returncode == 0


def ensure_chain(chain):
    if chain_exists(chain):
        _run(["-F", chain])
    else:
        _run(["-N", chain])


def failsafe_present(ip):
    return _run(["-C", "INPUT", "-s", ip, "-j", "ACCEPT"], check=False).returncode == 0


def insert_failsafe(ip):
    if failsafe_present(ip):
        return True
    _run(["-I", "INPUT", "1", "-s", ip, "-j", "ACCEPT"])
    return failsafe_present(ip)


def count_input_rules():
    listing = _run(["-L", "INPUT", "--line-numbers", "-n"])
    return len([line for line in listing.stdout.splitlines()[2:] if line.strip()])


def _chain_rule_count(chain):
    if not chain_exists(chain):
        return 0
    listing = _run(["-nL", chain], check=False)
    if listing.returncode != 0:
        return 0
    return len([line for line in listing.stdout.splitlines()[2:] if line.strip()])


def count_configured_rules():
    # count_input_rules() só olha a INPUT (failsafe/established/icmp/3 jumps
    # -- sempre ~5 linhas fixas), não diz nada sobre quantas entradas de
    # ip_accept/ip_deny/port_* de fato viraram regra -- essas ficam nas
    # chains próprias (ptrusted/pdenyip/pdrop), nunca na INPUT diretamente.
    return (
        _chain_rule_count(defaults.IPTABLES_TRUSTED_CHAIN)
        + _chain_rule_count(defaults.IPTABLES_DENY_CHAIN)
        + _chain_rule_count(defaults.IPTABLES_PORT_CHAIN)
    )


def expected_rule_count(ip_accept, ip_deny, port_accept, port_deny, log_enabled=False, geo_enabled=False):
    # deriva do próprio expected_rules() -- contar na mão em paralelo é como
    # duas fontes de verdade divergirem sem ninguém notar (exatamente a
    # classe de bug que fez `check` mentir antes do M1).
    return len(expected_rules(
        ip_accept, ip_deny, port_accept, port_deny, log_enabled=log_enabled, geo_enabled=geo_enabled,
    ))


def clear_input_except_failsafe(failsafe_ip):
    listing = _run(["-L", "INPUT", "--line-numbers", "-n"])
    rule_lines = [line for line in listing.stdout.splitlines()[2:] if line.strip()]

    for line in reversed(rule_lines):
        if failsafe_ip and failsafe_ip in line:
            continue
        line_number = line.split()[0]
        _run(["-D", "INPUT", line_number])


def port_rule_args(spec):
    port_range = f"{spec['start']}" if spec["start"] == spec["end"] else f"{spec['start']}:{spec['end']}"
    if spec["protocol"]:
        return ["-p", spec["protocol"], "--dport", port_range]
    return [["-p", proto, "--dport", port_range] for proto in ("tcp", "udp")]


def _rule_arg_groups(spec):
    args = port_rule_args(spec)
    return args if isinstance(args[0], list) else [args]


def _log_args(prefix):
    return ["-m", "limit", "--limit", defaults.IPTABLES_LOG_RATE_LIMIT, "-j", "LOG", "--log-prefix", prefix]


def expected_rules(ip_accept, ip_deny, port_accept, port_deny, log_enabled=False, geo_enabled=False):
    # única fonte de verdade pra "quais regras deveriam existir" -- sync()
    # aplica exatamente esta lista, rules_match_expected() compara o kernel
    # contra ela. Nunca duplicar essa construção em outro lugar.
    rules = []
    for ip, _ in ip_accept:
        rules.append((defaults.IPTABLES_TRUSTED_CHAIN, ["-s", ip, "-j", "ACCEPT"]))
    for ip, _ in ip_deny:
        if log_enabled:
            rules.append((defaults.IPTABLES_DENY_CHAIN, ["-s", ip, *_log_args(defaults.LOG_PREFIX_DENY)]))
        rules.append((defaults.IPTABLES_DENY_CHAIN, ["-s", ip, "-j", "DROP"]))
    for spec_str, _ in port_deny:
        for args in _rule_arg_groups(parse_port_spec(spec_str)):
            if log_enabled:
                rules.append((defaults.IPTABLES_PORT_CHAIN, [*args, *_log_args(defaults.LOG_PREFIX_PORT)]))
            rules.append((defaults.IPTABLES_PORT_CHAIN, [*args, "-j", "DROP"]))
    for spec_str, _ in port_accept:
        for args in _rule_arg_groups(parse_port_spec(spec_str)):
            rules.append((defaults.IPTABLES_PORT_CHAIN, [*args, "-j", "ACCEPT"]))
    if log_enabled:
        rules.append((defaults.IPTABLES_PORT_CHAIN, _log_args(defaults.LOG_PREFIX_PORT)))
    rules.append((defaults.IPTABLES_PORT_CHAIN, ["-j", "DROP"]))  # catch-all, sempre por último

    if geo_enabled:
        # país permitido (presente no ipset) -> RETURN, segue pro resto
        # (pdrop decide a porta); fora da allowlist -> DROP, ponto final.
        rules.append((
            defaults.IPTABLES_GEO_CHAIN,
            ["-m", "set", "--match-set", defaults.GEO_IPSET_NAME, "src", "-j", "RETURN"],
        ))
        rules.append((defaults.IPTABLES_GEO_CHAIN, ["-j", "DROP"]))

    return rules


def _rule_text(chain, args):
    # iptables -S devolve entre aspas qualquer valor com espaço (ex.:
    # --log-prefix "pvx-fw-deny: ") -- reproduzir aqui, senão a comparação
    # dá falso negativo com logging habilitado.
    quoted = [f'"{a}"' if " " in a else a for a in args]
    return " ".join(["-A", chain, *quoted])


def _live_rule_lines(chain):
    result = _run(["-S", chain], check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("-A ")]


def rules_match_expected(ip_accept, ip_deny, port_accept, port_deny, log_enabled=False, geo_enabled=False):
    # comparação sensível a ORDEM dentro de cada chain -- um catch-all DROP
    # presente mas fora do lugar (ex.: virou a primeira regra em vez da
    # última) teria o mesmo conjunto de linhas e passaria batido numa
    # comparação por conjunto, mas já não bloqueia nada de verdade.
    expected_by_chain = {}
    for chain, args in expected_rules(
        ip_accept, ip_deny, port_accept, port_deny, log_enabled=log_enabled, geo_enabled=geo_enabled,
    ):
        expected_by_chain.setdefault(chain, []).append(_rule_text(chain, args))

    chains_to_check = [defaults.IPTABLES_TRUSTED_CHAIN, defaults.IPTABLES_DENY_CHAIN, defaults.IPTABLES_PORT_CHAIN]
    if geo_enabled:
        # chain pgeo só é checada quando geo está ligado -- desligar geo não
        # limpa uma pgeo órfã que tenha sobrado (inerte, nada mais pula pra
        # ela), não vale a pena cobrar conteúdo de uma chain que ninguém usa.
        chains_to_check.append(defaults.IPTABLES_GEO_CHAIN)

    for chain in chains_to_check:
        if _live_rule_lines(chain) != expected_by_chain.get(chain, []):
            return False
    return True


def chain_drop_counters(chain):
    # -x dá o número exato (sem sufixo K/M) -- com -v vem pkts/bytes de cada
    # regra, nas duas primeiras colunas.
    result = _run(["-L", chain, "-v", "-n", "-x"], check=False)
    if result.returncode != 0:
        return {"packets": 0, "bytes": 0}

    packets = 0
    total_bytes = 0
    for line in result.stdout.splitlines()[2:]:
        parts = line.split()
        if len(parts) < 3 or parts[2] != "DROP":
            continue
        packets += int(parts[0])
        total_bytes += int(parts[1])
    return {"packets": packets, "bytes": total_bytes}


def dropped_counters():
    # contadores zeram a cada `apply` (as chains são recriadas) -- refletem
    # só o que foi dropado desde a última sincronização.
    totals = {"packets": 0, "bytes": 0}
    for chain in (defaults.IPTABLES_DENY_CHAIN, defaults.IPTABLES_PORT_CHAIN):
        counters = chain_drop_counters(chain)
        totals["packets"] += counters["packets"]
        totals["bytes"] += counters["bytes"]
    return totals


def sync(ip_accept, ip_deny, port_accept, port_deny, failsafe_ip, log_enabled=False, geo_enabled=False):
    if failsafe_ip and not insert_failsafe(failsafe_ip):
        raise RuntimeError("não consegui confirmar a regra de failsafe -- abortando sem limpar nada.")

    clear_input_except_failsafe(failsafe_ip)

    ensure_chain(defaults.IPTABLES_TRUSTED_CHAIN)
    ensure_chain(defaults.IPTABLES_DENY_CHAIN)
    ensure_chain(defaults.IPTABLES_PORT_CHAIN)
    if geo_enabled:
        ensure_chain(defaults.IPTABLES_GEO_CHAIN)

    for chain, args in expected_rules(
        ip_accept, ip_deny, port_accept, port_deny, log_enabled=log_enabled, geo_enabled=geo_enabled,
    ):
        _run(["-A", chain, *args])

    # INPUT já foi limpo (só sobra o failsafe) -- seguro só dar append, sem checar duplicata.
    _run(["-A", "INPUT", "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"])
    _run(["-A", "INPUT", "-p", "icmp", "-j", "ACCEPT"])
    _run(["-A", "INPUT", "-j", defaults.IPTABLES_DENY_CHAIN])
    _run(["-A", "INPUT", "-j", defaults.IPTABLES_TRUSTED_CHAIN])
    if geo_enabled:
        _run(["-A", "INPUT", "-j", defaults.IPTABLES_GEO_CHAIN])
    _run(["-A", "INPUT", "-j", defaults.IPTABLES_PORT_CHAIN])
