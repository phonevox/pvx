import subprocess

import os_ops


def repo_rpm_url(zabbix_version, os_major):
    return (
        f"https://repo.zabbix.com/zabbix/{zabbix_version}/rhel/{os_major}/x86_64/"
        f"zabbix-release-latest.el{os_major}.noarch.rpm"
    )


def install_repo(zabbix_version, os_major, logger=None):
    # "yum", nunca "dnf": CentOS/RHEL 7 não tem dnf de jeito nenhum (achado ao
    # vivo -- falhava direto, silencioso, com FileNotFoundError). RHEL/Rocky
    # 8+ mantém "yum" como wrapper de compatibilidade pro dnf, então funciona
    # nos dois sem precisar detectar o SO.
    url = repo_rpm_url(zabbix_version, os_major)
    return os_ops.run_cmd(
        ["yum", "install", "-y", url], logger=logger, action=f"instalar repositório ({url})",
        verify_cmd=["rpm", "-q", "zabbix-release"],
    )


def install_agent(package, logger=None):
    return os_ops.run_cmd(
        ["yum", "install", "-y", package], logger=logger, action=f"instalar {package}",
        verify_cmd=["rpm", "-q", package],
    )


def enable_and_start(service, logger=None):
    os_ops.run_cmd(["systemctl", "enable", service], logger=logger, action=f"habilitar {service}")
    return os_ops.run_cmd(["systemctl", "restart", service], logger=logger, action=f"reiniciar {service}")


def disable_and_stop(service, logger=None):
    os_ops.run_cmd(["systemctl", "stop", service], logger=logger, action=f"parar {service}")
    os_ops.run_cmd(["systemctl", "disable", service], logger=logger, action=f"desabilitar {service}")


def detect_existing_agent(packages):
    # rastro de instalação prévia (pzabbix ou manual) -- checado antes de instalar
    # pra não colidir dois agentes na mesma porta nem sobrescrever sem avisar.
    for package in packages:
        if os_ops.run_cmd(["rpm", "-q", package]):
            return package
    return None


def remove_agent(package, logger=None):
    return os_ops.run_cmd(["yum", "remove", "-y", package], logger=logger, action=f"remover {package}")


def service_status(service):
    # is-active/is-enabled devolvem o texto real no stdout mesmo com exit code != 0
    # (ex.: "inactive" sai com código 3) -- por isso subprocess.run direto, não
    # os_ops.run_cmd (que só devolve bool do returncode).
    active = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True).stdout.strip()
    enabled = subprocess.run(["systemctl", "is-enabled", service], capture_output=True, text=True).stdout.strip()
    return {"active": active, "enabled": enabled}
