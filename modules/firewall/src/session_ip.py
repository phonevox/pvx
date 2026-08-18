import os
import re
import subprocess

from validators import validate_cidr


def _who_m_ip():
    try:
        output = subprocess.run(["who", "-m"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"\(([^)]+)\)", output)
    return match.group(1) if match else None


def detect_session_ip():
    candidate = None

    ssh_client = os.environ.get("SSH_CLIENT", "")
    if ssh_client:
        candidate = ssh_client.split()[0]

    who_ip = _who_m_ip()
    if who_ip:
        candidate = who_ip

    if candidate and validate_cidr(candidate):
        return candidate
    return None
