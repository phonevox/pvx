import os
import shutil
import subprocess

_INSTALL_STEPS = {
    "rhel": [["yum", "install", "-y", "epel-release"], ["yum", "install", "-y", "sngrep"]],
    "debian": [["apt-get", "update"], ["apt-get", "install", "-y", "sngrep"]],
    "alpine": [["apk", "add", "sngrep"]],
}


class SngrepError(Exception):
    pass


def detect_distro():
    if os.path.exists("/etc/alpine-release"):
        return "alpine"
    if os.path.exists("/etc/redhat-release"):
        return "rhel"
    if os.path.exists("/etc/debian_version"):
        return "debian"
    return None


def is_installed():
    return shutil.which("sngrep") is not None


def install(distro):
    steps = _INSTALL_STEPS.get(distro)
    if steps is None:
        raise SngrepError(f"distribuição não suportada: {distro}")

    for step in steps:
        result = subprocess.run(step, capture_output=True, text=True)
        if result.returncode != 0:
            raise SngrepError(f"falha ao instalar sngrep: {(result.stderr or result.stdout).strip()}")
