import os

ASTERISK_CONF = "/etc/asterisk/asterisk.conf"
DIALER_DIR = "/opt/issabel/dialer"


def find_spooldir(asterisk_conf=ASTERISK_CONF):
    try:
        with open(asterisk_conf) as f:
            content = f.read()
    except OSError:
        return None

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("astspooldir"):
            _key, _sep, value = line.partition("=>")
            value = value.strip()
            return value or None
    return None


def storage_bytes(path):
    if not os.path.isdir(path):
        return None

    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                # sem permissão de ler esse arquivo específico (comum como
                # usuário não-root) -- ignora e continua somando o resto.
                continue
    return total


def storage_percent(path, disk_total_bytes):
    size = storage_bytes(path)
    if size is None or not disk_total_bytes:
        return None
    return round(size / disk_total_bytes * 100, 1)


def recordings_bytes():
    spooldir = find_spooldir()
    if spooldir is None:
        return None
    return storage_bytes(os.path.join(spooldir, "monitor"))


def dialer_bytes():
    return storage_bytes(DIALER_DIR)


def recordings_percent(disk_total_bytes):
    spooldir = find_spooldir()
    if spooldir is None:
        return None
    return storage_percent(os.path.join(spooldir, "monitor"), disk_total_bytes)


def dialer_percent(disk_total_bytes):
    return storage_percent(DIALER_DIR, disk_total_bytes)
