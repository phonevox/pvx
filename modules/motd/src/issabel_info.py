import os
import subprocess

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
    # du nativo em vez de os.walk + getsize por arquivo -- achado ao vivo: numa
    # central de produção com anos de gravação de chamada (dezenas de milhares
    # de arquivos), o loop em Python era o gargalo real que deixava o motd
    # lento. du (C, otimizado) resolve o mesmo cálculo muito mais rápido.
    if not os.path.isdir(path):
        return None
    try:
        # -sk (kilobytes) em vez de -sb: -b é extensão GNU, -k é POSIX (BSD/macOS
        # também tem) -- precisão de bloco não importa aqui, isso só alimenta um
        # indicador de "% do disco", já arredondado.
        result = subprocess.run(["du", "-sk", path], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.split()[0]) * 1024
    except (IndexError, ValueError):
        return None


def _percent_of(size, disk_total_bytes):
    if size is None or not disk_total_bytes:
        return None
    return round(size / disk_total_bytes * 100, 1)


def storage_percent(path, disk_total_bytes):
    return _percent_of(storage_bytes(path), disk_total_bytes)


def storage_info(path, disk_total_bytes):
    # bytes + percent numa chamada só -- evita repetir o du (ver storage_bytes)
    # pro mesmo diretório duas vezes seguidas.
    size = storage_bytes(path)
    return size, _percent_of(size, disk_total_bytes)


def recordings_info(disk_total_bytes):
    spooldir = find_spooldir()
    if spooldir is None:
        return None, None
    return storage_info(os.path.join(spooldir, "monitor"), disk_total_bytes)


def dialer_info(disk_total_bytes):
    return storage_info(DIALER_DIR, disk_total_bytes)
