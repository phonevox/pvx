import os
import shutil
import socket
import subprocess
import time


def _read_cpu_times():
    # primeira linha de /proc/stat: "cpu  user nice system idle iowait irq
    # softirq ...", em jiffies desde o boot -- iowait conta como ocioso pro
    # que interessa aqui (CPU não tava processando nada).
    with open("/proc/stat") as f:
        fields = [int(v) for v in f.readline().split()[1:]]
    idle = fields[3] + fields[4]
    return idle, sum(fields)


def cpu_usage_percent(interval=0.1):
    # amostra única não diz nada (seria a média desde o boot) -- precisa de
    # duas leituras com um intervalo curto entre elas pra achar o uso atual.
    idle1, total1 = _read_cpu_times()
    time.sleep(interval)
    idle2, total2 = _read_cpu_times()

    delta_total = total2 - total1
    if delta_total <= 0:
        return 0.0
    delta_idle = idle2 - idle1
    return round((1 - delta_idle / delta_total) * 100, 1)


def load_average():
    with open("/proc/loadavg") as f:
        one, five, fifteen = f.read().split()[:3]
    return float(one), float(five), float(fifteen)


def memory_usage():
    values = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                values[key] = int(rest.strip().split()[0])  # kB

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    ram_percent = round((1 - available / total) * 100, 1) if total else 0.0

    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    swap_percent = round((1 - swap_free / swap_total) * 100, 1) if swap_total else 0.0

    return {
        "ram_percent": ram_percent,
        "ram_total_mb": total // 1024,
        "swap_percent": swap_percent,
    }


def disk_usage(path="/"):
    total, used, _free = shutil.disk_usage(path)
    percent = round(used / total * 100, 1) if total else 0.0
    return {
        "percent": percent,
        "used_gb": round(used / 2**30, 1),
        "total_gb": round(total / 2**30, 1),
    }


def _format_uptime(seconds):
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days} dia{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
    if minutes or not parts:
        parts.append(f"{minutes} minuto{'s' if minutes != 1 else ''}")
    return "up " + ", ".join(parts)


def uptime_human():
    with open("/proc/uptime") as f:
        seconds = float(f.read().split()[0])
    return _format_uptime(seconds)


def hostname():
    return socket.gethostname()


def machine_id():
    try:
        return open("/etc/machine-id").read().strip()
    except OSError:
        return None


def os_pretty_name():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.partition("=")[2].strip().strip('"')
    except OSError:
        pass
    return None


def _run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result if result.returncode == 0 else None


def ip_addresses():
    result = _run(["hostname", "-I"])
    return result.stdout.split() if result else []


def open_sessions():
    result = _run(["who"])
    return len(result.stdout.splitlines()) if result else 0


def timezone_name():
    try:
        target = os.readlink("/etc/localtime")
        return target.split("zoneinfo/")[-1]
    except OSError:
        pass
    result = _run(["timedatectl", "show", "-p", "Timezone", "--value"])
    return result.stdout.strip() if result else None
