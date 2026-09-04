import shutil
import subprocess


def service_is_active(name):
    try:
        result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True)
    except OSError:
        return False
    return result.stdout.strip() == "active"


def detect_engine():
    if shutil.which("firewall-cmd") and service_is_active("firewalld"):
        return "firewalld"
    if shutil.which("iptables"):
        return "iptables"
    raise RuntimeError("nenhum engine de firewall suportado encontrado (iptables ou firewalld).")
