import re

_URL_RE = re.compile(r"^https?://[a-zA-Z0-9.\-]+(:\d+)?$")


def parse_sftp(value):
    user, _, rest = value.partition("@")
    if not user or not rest:
        raise ValueError(f"SFTP inválido: {value}")

    host, _, port = rest.partition(":")
    if not host:
        raise ValueError(f"SFTP inválido: {value}")

    return {"user": user, "host": host, "port": int(port) if port else 22}


def validate_url(value):
    return bool(_URL_RE.match(value))


def parse_csv4(value, existing):
    if not value:
        return tuple(existing)
    parts = value.split(",")
    parts += [""] * (4 - len(parts))
    return tuple(part if part else existing[i] for i, part in enumerate(parts[:4]))
