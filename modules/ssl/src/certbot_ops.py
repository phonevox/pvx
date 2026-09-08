import os
import subprocess
from datetime import datetime, timezone

_LIVE_DIR = "/etc/letsencrypt/live"


class CertbotError(Exception):
    pass


def _run(args, error):
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except OSError as e:
        raise CertbotError(f"{error}: {e}")
    if result.returncode != 0:
        raise CertbotError(f"{error}: {(result.stderr or result.stdout).strip()}")
    return result.stdout


def cert_path(domain):
    return f"{_LIVE_DIR}/{domain}/fullchain.pem"


def has_certificate(domain):
    return os.path.exists(cert_path(domain))


def list_domains():
    if not os.path.isdir(_LIVE_DIR):
        return []
    return sorted(
        name for name in os.listdir(_LIVE_DIR)
        if os.path.isdir(os.path.join(_LIVE_DIR, name))
    )


def days_until_expiry(domain, now=None):
    if not has_certificate(domain):
        return None
    output = _run(
        ["openssl", "x509", "-enddate", "-noout", "-in", cert_path(domain)],
        f"não consegui ler a validade do certificado de {domain}",
    )
    _, _, raw_date = output.strip().partition("=")
    raw_date = raw_date.strip()
    if raw_date.endswith(" GMT"):
        raw_date = raw_date[: -len(" GMT")]
    expires_at = datetime.strptime(raw_date, "%b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return (expires_at - now).days


def issue(domain, email):
    _run(
        ["certbot", "--non-interactive", "--apache", "--agree-tos", "--email", email, "-d", domain],
        f"falha ao emitir certificado pra {domain}",
    )


def renew(domain, force=False):
    args = ["certbot", "renew", "--cert-name", domain]
    args.append("--force-renewal" if force else "--quiet")
    _run(args, f"falha ao renovar certificado de {domain}")


def remove(domain):
    _run(
        ["certbot", "delete", "--cert-name", domain, "--non-interactive"],
        f"falha ao remover certificado de {domain}",
    )
