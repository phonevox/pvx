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


def check(min_version, force=False, report=None):
    # bloqueia cedo em vez de deixar um dnf install de centenas de pacotes falhar 20min depois.
    # report(label, status, detail) é opcional -- preflight não imprime nada, só relata o fato
    # de cada checagem, na ordem real de execução, pra quem chamou mostrar ao vivo (uma linha
    # por vez -- ver main.py). status: "ok" | "warn" (reprova mas não bloqueia) | "error"
    # (bloqueia). "rede" é a única checagem de fato lenta (curl real) -- reporta em duas fases:
    # ("rede", "pending", None) antes de rodar, resultado de verdade depois.
    def _report(label, status, detail=None):
        if report:
            report(label, status, detail)

    errors = []
    warnings = []

    root_ok = is_root()
    _report("root", "ok" if root_ok else "error")
    if not root_ok:
        errors.append("netinstall precisa rodar como root (sudo).")
        return errors, warnings  # nada mais faz sentido checar sem root

    rhel_ok = is_rhel_like()
    major = version_major() if rhel_ok else 0
    so_ok = rhel_ok and major >= min_version
    _report("SO", "ok" if so_ok else "error", f"Rocky/RHEL {major}" if rhel_ok else None)
    if not rhel_ok:
        errors.append("SO não é RHEL-like (Rocky/CentOS/RHEL) -- não suportado.")
    elif major < min_version:
        errors.append(f"versão do SO abaixo do mínimo suportado ({min_version}+).")

    _report("rede", "pending")
    net_ok = network_reachable()
    _report("rede", "ok" if net_ok else "error")
    if not net_ok:
        errors.append(f"sem acesso de rede ({defaults.MIRROR_PROBE_URL} não respondeu).")

    mem_kb = os_ops.mem_total_kb()
    ram_ok = not (0 < mem_kb < defaults.MIN_MEM_KB)
    _report("RAM", "ok" if ram_ok else "warn", f"{mem_kb // 1024} MB" if mem_kb > 0 else None)
    if 0 < mem_kb < defaults.MIN_MEM_KB:
        warnings.append(
            f"RAM+swap baixa ({mem_kb // 1024} MB, recomendado >= {defaults.MIN_MEM_KB // 1024} MB)."
        )

    installed = already_installed()
    clean_ok = not installed or force
    _report(
        "instalação prévia", "ok" if clean_ok else "error",
        "detectada, ignorada por --force" if installed and force else ("detectada" if installed else None),
    )
    if installed and not force:
        errors.append(
            "esta máquina já parece ter Issabel/Asterisk instalado -- use --force pra continuar mesmo assim."
        )

    return errors, warnings
