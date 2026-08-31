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
