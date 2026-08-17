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


def sync(ip_accept, ip_deny, port_accept, port_deny, failsafe_ip):
    if failsafe_ip and not insert_failsafe(failsafe_ip):
        raise RuntimeError("não consegui confirmar a regra de failsafe -- abortando sem limpar nada.")

    clear_input_except_failsafe(failsafe_ip)

    ensure_chain(defaults.IPTABLES_TRUSTED_CHAIN)
    ensure_chain(defaults.IPTABLES_DENY_CHAIN)
    ensure_chain(defaults.IPTABLES_PORT_CHAIN)

    for ip, _ in ip_accept:
        _run(["-A", defaults.IPTABLES_TRUSTED_CHAIN, "-s", ip, "-j", "ACCEPT"])
    for ip, _ in ip_deny:
        _run(["-A", defaults.IPTABLES_DENY_CHAIN, "-s", ip, "-j", "DROP"])

    for spec_str, _ in port_deny:
        for args in _rule_arg_groups(parse_port_spec(spec_str)):
            _run(["-A", defaults.IPTABLES_PORT_CHAIN, *args, "-j", "DROP"])
    for spec_str, _ in port_accept:
        for args in _rule_arg_groups(parse_port_spec(spec_str)):
            _run(["-A", defaults.IPTABLES_PORT_CHAIN, *args, "-j", "ACCEPT"])
    _run(["-A", defaults.IPTABLES_PORT_CHAIN, "-j", "DROP"])  # catch-all

    # INPUT já foi limpo (só sobra o failsafe) -- seguro só dar append, sem checar duplicata.
    _run(["-A", "INPUT", "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"])
    _run(["-A", "INPUT", "-p", "icmp", "-j", "ACCEPT"])
    _run(["-A", "INPUT", "-j", defaults.IPTABLES_DENY_CHAIN])
    _run(["-A", "INPUT", "-j", defaults.IPTABLES_TRUSTED_CHAIN])
    _run(["-A", "INPUT", "-j", defaults.IPTABLES_PORT_CHAIN])
