import re

_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_PUBLIC_KEY_RE = re.compile(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-\S+) \S+(?: .*)?$")


def validate_username(name):
    return bool(_USERNAME_RE.match(name))


def validate_public_key(key):
    return bool(_PUBLIC_KEY_RE.match(key))


def validate_port(value):
    return value.isdigit() and 1 <= int(value) <= 65535
