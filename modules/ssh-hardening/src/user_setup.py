import grp
import subprocess
from pathlib import Path

# RHEL/CentOS/Rocky usam wheel; Debian/Ubuntu não têm esse grupo, usam sudo --
# checa qual existe de verdade em vez de assumir uma distro (achado ao vivo:
# usermod -aG wheel crashava num Debian 11).
_ADMIN_GROUP_CANDIDATES = ("wheel", "sudo")


def user_exists(username):
    return subprocess.run(["id", "-u", username], capture_output=True).returncode == 0


def create_user(username):
    if user_exists(username):
        return False
    subprocess.run(["useradd", "-m", "-s", "/bin/bash", username], check=True)
    return True


def delete_user(username):
    if not user_exists(username):
        return
    subprocess.run(["userdel", "-r", username], check=True)


def detect_admin_group():
    for name in _ADMIN_GROUP_CANDIDATES:
        try:
            grp.getgrnam(name)
            return name
        except KeyError:
            continue
    return None


def add_to_admin_group(username, group=None):
    group = group or detect_admin_group()
    if group is None:
        return False
    subprocess.run(["usermod", "-aG", group, username], check=True)
    return True


def set_password(username, password):
    subprocess.run(["chpasswd"], input=f"{username}:{password}\n", text=True, check=True)


def setup_authorized_key(home_dir, username, public_key):
    ssh_dir = Path(home_dir) / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    ssh_dir.chmod(0o700)

    authorized_keys = ssh_dir / "authorized_keys"
    key_line = public_key.strip()
    existing_lines = authorized_keys.read_text().splitlines() if authorized_keys.exists() else []
    if key_line not in existing_lines:
        with authorized_keys.open("a") as f:
            f.write(key_line + "\n")
    authorized_keys.chmod(0o600)

    subprocess.run(["chown", "-R", f"{username}:{username}", str(ssh_dir)], check=True)
