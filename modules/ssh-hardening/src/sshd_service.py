import subprocess

# Debian/Ubuntu chamam a unit de "ssh", RHEL/Rocky/CentOS de "sshd" -- tenta
# os dois, sem assumir a distro.
_CANDIDATE_UNITS = ("sshd", "ssh")


def restart():
    for unit in _CANDIDATE_UNITS:
        try:
            result = subprocess.run(["systemctl", "restart", unit], capture_output=True)
        except OSError:
            return None
        if result.returncode == 0:
            return unit
    return None
