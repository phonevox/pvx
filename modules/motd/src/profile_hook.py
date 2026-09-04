import os
import shutil
import time

HOOK_PATH = "/etc/profile.d/pvx-motd.sh"
HOOK_CONTENT = "#!/bin/sh\npvx motd show\n"

# scripts de instalações anteriores (Issabel nativo e versões antigas do
# pmotd.sh) que precisam sair do caminho pra não duplicar o banner no login.
_LEGACY_PATHS = (
    "/usr/local/sbin/motd.sh",
    "/etc/profile.d/login-info.sh",
    "/etc/profile.d/motd.sh",
    "/etc/profile.d/pmotd.sh",
)


def _ensure_backup_dir(backup_dir, base_dir):
    if backup_dir is not None:
        return backup_dir
    backup_dir = os.path.join(base_dir, f"motd-bkp-{int(time.time())}")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def install(base_dir="/root"):
    backup_dir = None
    backed_up = []

    for path in _LEGACY_PATHS:
        if os.path.isfile(path):
            backup_dir = _ensure_backup_dir(backup_dir, base_dir)
            shutil.copy2(path, backup_dir)
            os.remove(path)
            backed_up.append(path)

    if os.path.isfile(HOOK_PATH):
        backup_dir = _ensure_backup_dir(backup_dir, base_dir)
        shutil.copy2(HOOK_PATH, backup_dir)
        backed_up.append(HOOK_PATH)

    with open(HOOK_PATH, "w") as f:
        f.write(HOOK_CONTENT)
    os.chmod(HOOK_PATH, 0o755)

    return {"backup_dir": backup_dir, "backed_up": backed_up}


def uninstall():
    if not os.path.isfile(HOOK_PATH):
        return False
    os.remove(HOOK_PATH)
    return True


def is_installed():
    return os.path.isfile(HOOK_PATH)
