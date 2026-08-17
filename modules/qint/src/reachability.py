import socket


def is_reachable(host, port, timeout=6):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
