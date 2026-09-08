import shutil
import subprocess
from contextlib import contextmanager

# achado na revisão do script-base: ele desativava o firewall inteiro (iptables -F, ufw
# disable, stop firewalld) durante a emissão -- destrutivo (iptables -F apaga TODAS as
# regras pra sempre, não só durante o script) e perigoso (uma falha no meio deixa o
# servidor sem proteção nenhuma). Aqui só abre uma porta pontual, e só onde de fato há
# um firewall ativo -- nunca mexe no estado geral, nunca em fail2ban.
#
# achado ao vivo (2a rodada): firewalld/ufw inativos os dois não significa nada
# bloqueando -- regras iptables cruas (sem serviço nenhum gerenciando, então
# invisíveis pros dois checks acima) travavam o desafio HTTP-01 mesmo assim. Cobrir
# isso sem flush: uma regra ACCEPT pontual no topo da INPUT, removida depois.


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except OSError:
        return None


def _firewalld_active():
    result = _run(["systemctl", "is-active", "firewalld"])
    return result is not None and result.returncode == 0


def _ufw_active():
    if shutil.which("ufw") is None:
        return False
    result = _run(["ufw", "status"])
    return result is not None and "Status: active" in result.stdout


def _iptables_rule_args(port):
    return ["-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]


def _iptables_rule_present(port):
    result = _run(["iptables", "-C", "INPUT"] + _iptables_rule_args(port))
    return result is not None and result.returncode == 0


def open_port(port):
    opened = []
    if _firewalld_active():
        _run(["firewall-cmd", "--add-port", f"{port}/tcp"])
        opened.append("firewalld")
    if _ufw_active():
        _run(["ufw", "allow", f"{port}/tcp"])
        opened.append("ufw")
    if shutil.which("iptables") and not _iptables_rule_present(port):
        _run(["iptables", "-I", "INPUT", "1"] + _iptables_rule_args(port))
        opened.append("iptables")
    return opened


def close_port(port, opened):
    if "firewalld" in opened:
        _run(["firewall-cmd", "--remove-port", f"{port}/tcp"])
    if "ufw" in opened:
        _run(["ufw", "delete", "allow", f"{port}/tcp"])
    if "iptables" in opened:
        _run(["iptables", "-D", "INPUT"] + _iptables_rule_args(port))


@contextmanager
def temporarily_open(port):
    opened = open_port(port)
    try:
        yield
    finally:
        close_port(port, opened)
