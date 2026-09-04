import subprocess

ASTERISK_CONF = "/etc/asterisk/asterisk.conf"


def find_logdir(asterisk_conf=ASTERISK_CONF):
    try:
        with open(asterisk_conf) as f:
            content = f.read()
    except OSError:
        return None

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("astlogdir"):
            _key, _sep, value = line.partition("=>")
            value = value.strip()
            return value or None
    return None


def _cli(command, timeout=5):
    try:
        result = subprocess.run(["asterisk", "-rx", command], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def version():
    output = _cli("core show version")
    if not output:
        return None
    parts = output.split()
    return " ".join(parts[:2]) if len(parts) >= 2 else None


def active_calls():
    output = _cli("core show channels")
    if not output:
        return None
    for line in output.splitlines():
        if "active call" in line:
            first = line.split()[0]
            return int(first) if first.isdigit() else None
    return None
