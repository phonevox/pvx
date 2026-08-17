import os
import shutil
import subprocess

import defaults
import os_ops


def is_root():
    return os.geteuid() == 0


def read_os_release(path="/etc/os-release"):
    try:
        content = open(path).read()
    except OSError:
        return {}
    data = {}
    for line in content.splitlines():
        key, _, value = line.partition("=")
        if not key:
            continue
        data[key] = value.strip('"')
    return data


def is_rhel_like(os_release=None):
    os_release = read_os_release() if os_release is None else os_release
    id_like = f"{os_release.get('ID_LIKE', '')} {os_release.get('ID', '')}".lower()
    return "rhel" in id_like or "fedora" in id_like


def version_major(os_release=None):
    os_release = read_os_release() if os_release is None else os_release
    major = os_release.get("VERSION_ID", "0").split(".")[0]
    return int(major) if major.isdigit() else 0


def already_installed():
    return shutil.which("asterisk") is not None or os.path.exists("/etc/issabel.conf")


def network_reachable(url=defaults.MIRROR_PROBE_URL, timeout=15):
    try:
        result = subprocess.run(
            ["curl", "-fsS", "--connect-timeout", "10", "--max-time", str(timeout),
             "--retry", "2", "--retry-delay", "2", "--retry-connrefused", "-o", "/dev/null", url],
            capture_output=True, text=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def check(min_version, force=False):
    # bloqueia cedo em vez de deixar um dnf install de centenas de pacotes falhar 20min depois.
    errors = []
    warnings = []

    if not is_root():
        errors.append("netinstall precisa rodar como root (sudo).")
        return errors, warnings  # nada mais faz sentido checar sem root

    if not is_rhel_like():
        errors.append("SO não é RHEL-like (Rocky/CentOS/RHEL) -- não suportado.")
    elif version_major() < min_version:
        errors.append(f"versão do SO abaixo do mínimo suportado ({min_version}+).")

    mem_kb = os_ops.mem_total_kb()
    if 0 < mem_kb < defaults.MIN_MEM_KB:
        warnings.append(
            f"RAM+swap baixa ({mem_kb // 1024} MB, recomendado >= {defaults.MIN_MEM_KB // 1024} MB)."
        )

    if already_installed() and not force:
        errors.append(
            "esta máquina já parece ter Issabel/Asterisk instalado -- use --force pra continuar mesmo assim."
        )

    if not network_reachable():
        errors.append(f"sem acesso de rede ({defaults.MIRROR_PROBE_URL} não respondeu).")

    return errors, warnings
