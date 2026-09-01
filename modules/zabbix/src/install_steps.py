import subprocess

import os_ops


def repo_rpm_url(zabbix_version, os_major):
    return (
        f"https://repo.zabbix.com/zabbix/{zabbix_version}/rhel/{os_major}/x86_64/"
        f"zabbix-release-latest.el{os_major}.noarch.rpm"
    )


def install_repo(zabbix_version, os_major):
    return os_ops.run_cmd(["dnf", "install", "-y", repo_rpm_url(zabbix_version, os_major)])


def install_agent(package):
    return os_ops.run_cmd(["dnf", "install", "-y", package])


def enable_and_start(service):
    os_ops.run_cmd(["systemctl", "enable", service])
    return os_ops.run_cmd(["systemctl", "restart", service])


def detect_existing_agent(packages):
    # rastro de instalação prévia (pzabbix ou manual) -- checado antes de instalar
    # pra não colidir dois agentes na mesma porta nem sobrescrever sem avisar.
    for package in packages:
        if os_ops.run_cmd(["rpm", "-q", package]):
            return package
    return None


def remove_agent(package):
    return os_ops.run_cmd(["dnf", "remove", "-y", package])


def service_status(service):
    # is-active/is-enabled devolvem o texto real no stdout mesmo com exit code != 0
    # (ex.: "inactive" sai com código 3) -- por isso subprocess.run direto, não
    # os_ops.run_cmd (que só devolve bool do returncode).
    active = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True).stdout.strip()
    enabled = subprocess.run(["systemctl", "is-enabled", service], capture_output=True, text=True).stdout.strip()
    return {"active": active, "enabled": enabled}
