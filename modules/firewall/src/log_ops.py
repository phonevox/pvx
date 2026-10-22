import subprocess
from pathlib import Path

import defaults

MARKER_FILENAME = "logging_enabled"

_PREFIXES = (defaults.LOG_PREFIX_DENY, defaults.LOG_PREFIX_PORT)


def _marker_path(base_dir):
    return Path(base_dir) / MARKER_FILENAME


def is_enabled(base_dir):
    return _marker_path(base_dir).exists()


def enable(base_dir):
    path = _marker_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def disable(base_dir):
    path = _marker_path(base_dir)
    if path.exists():
        path.unlink()


def read_lines(tail=50):
    # todo host aqui já roda systemd (ver systemd_unit.py) -- journald já
    # captura o log do kernel (LOG target do iptables), sem precisar de
    # rsyslog/syslog próprio.
    try:
        result = subprocess.run(
            ["journalctl", "-k", "-n", str(tail), "--no-pager"], capture_output=True, text=True,
        )
    except OSError:
        return []
    return [line for line in result.stdout.splitlines() if any(prefix in line for prefix in _PREFIXES)]


def follow():
    # streaming direto pro terminal -- interativo, Ctrl+C encerra.
    try:
        subprocess.run(["journalctl", "-k", "-f"])
    except OSError as e:
        raise RuntimeError(f"não consegui acompanhar o journal: {e}")
