import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request


def read_os_release(path="/etc/os-release"):
    try:
        content = open(path).read()
    except OSError:
        return {}
    data = {}
    for line in content.splitlines():
        key, _, value = line.partition("=")
        if not key:
            continue
        data[key] = value.strip('"')
    return data


def os_id(os_release=None):
    os_release = read_os_release() if os_release is None else os_release
    return os_release.get("ID", "").lower()


def os_label(os_release=None):
    os_release = read_os_release() if os_release is None else os_release
    return f"{os_id(os_release)}-{os_release.get('VERSION_ID', '0')}"


def machine_id(path="/etc/machine-id"):
    try:
        return open(path).read().strip()
    except OSError:
        return ""


# achado no script bash antigo (pzabbix) -- provider é decidido pelo campo "org" do
# ipinfo.io, não pelo nome do host (hostname pode mentir/mudar de padrão). "eveo" não
# tem assinatura reconhecível aqui, fica sempre manual (--provider).
_PROVIDER_ORG_KEYWORDS = {
    "ovh": "ovh",
    "qnax": "qnax",
    "amazon": "aws",
}


def detect_provider(timeout=5):
    try:
        with urllib.request.urlopen("https://ipinfo.io/json", timeout=timeout) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return "local"

    org = data.get("org", "").lower()
    for keyword, provider in _PROVIDER_ORG_KEYWORDS.items():
        if keyword in org:
            return provider
    return "local"


# heurística por provedor (nome de host segue um padrão fixo lá) -- mantida por pedido
# explícito, mesmo sendo frágil se o provedor mudar o padrão de nomenclatura um dia.
_HOSTNAME_PATTERNS = {
    "ovh": re.compile(r"^vps-[a-z0-9]+"),
    "qnax": re.compile(r"^SRV-[0-9]+$"),
}


def detect_hostname(provider, current_hostname=None):
    current_hostname = current_hostname if current_hostname is not None else os.uname().nodename
    pattern = _HOSTNAME_PATTERNS.get(provider)
    if pattern:
        match = pattern.match(current_hostname)
        if match:
            return match.group(0)
    return machine_id()


def asterisk_version():
    if not shutil.which("asterisk"):
        return None
    try:
        result = subprocess.run(["asterisk", "-V"], capture_output=True, text=True)
    except OSError:
        return None
    match = re.search(r"Asterisk (\d+)", result.stdout)
    return match.group(1) if match else None
