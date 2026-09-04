import os
import shutil


def is_installed(binary):
    return shutil.which(binary) is not None


def is_process_running(name):
    try:
        pids = [entry for entry in os.listdir("/proc") if entry.isdigit()]
    except OSError:
        return False

    for pid in pids:
        try:
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
        except OSError:
            # processo de outro usuário (comum quando logado como não-root) ou
            # já morreu entre o listdir e a leitura -- ignora e segue.
            continue
        if comm == name:
            return True
    return False


def daemon_status(binaries, process_name):
    if not any(is_installed(b) for b in binaries):
        return {"installed": False, "running": False}
    return {"installed": True, "running": is_process_running(process_name)}
