import subprocess

from pvx import config as pvx_config


def is_module_installed(name):
    return (pvx_config.modules_dir() / name / "manifest.json").exists()


def ensure_module_installed(name, pvx_bin="pvx"):
    if is_module_installed(name):
        return True
    result = subprocess.run([pvx_bin, "module", "install", name], capture_output=True, text=True)
    return result.returncode == 0


def _run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    return {"ok": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}


def run_ssh_hardening(config, pvx_bin="pvx"):
    if not ensure_module_installed("ssh-hardening", pvx_bin):
        return {"ok": False, "stdout": "", "stderr": "falha ao instalar o módulo ssh-hardening"}

    args = [pvx_bin, "ssh-hardening", "apply", "--yes"]
    if config.get("lock_root"):
        args += ["--lock-root", "--root-password", config["root_password"]]
    else:
        args += ["--no-lock-root"]

    if config.get("create_user"):
        args += ["--create-user", "--username", config["username"], "--public-key", config["pubkey"]]
        if config.get("allow_password"):
            args += ["--allow-password", "--user-password", config["user_password"]]
        else:
            args += ["--no-allow-password"]
    else:
        args += ["--no-create-user"]

    if config.get("change_port"):
        args += ["--change-port", "--port", config["port"]]
    else:
        args += ["--no-change-port"]

    return _run(args)


def run_firewall_sync(pvx_bin="pvx"):
    if not ensure_module_installed("firewall", pvx_bin):
        return {"ok": False, "stdout": "", "stderr": "falha ao instalar o módulo firewall"}
    return _run([pvx_bin, "firewall", "sync", "--yes", "--force"])


_QINT_FLAGS = {
    "sftp": "--sftp", "url": "--url", "token": "--token",
    "timecondition_out": "--timecondition-out", "filas": "--filas", "asterisk_ip": "--asterisk-ip",
    "versao": "--versao", "filial": "--filial", "departamentos": "--departamentos",
    "assuntos": "--assuntos", "app": "--app", "setores": "--setores",
    "ocorrencias": "--ocorrencias", "motivo_os": "--motivo-os",
}


def run_qint(config, pvx_bin="pvx"):
    if not ensure_module_installed("qint", pvx_bin):
        return {"ok": False, "stdout": "", "stderr": "falha ao instalar o módulo qint"}

    prepare_args = [pvx_bin, "qint", "prepare", config["tipo"]]
    for key, flag in _QINT_FLAGS.items():
        if config.get(key) is not None:
            prepare_args += [flag, config[key]]

    prepared = _run(prepare_args)
    if not prepared["ok"]:
        return prepared

    return _run([pvx_bin, "qint", "apply", "--yes"])
