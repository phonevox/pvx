import re
import subprocess

# achado ao vivo: cada versão/variante do Asterisk (chan_sip clássico vs
# chan_pjsip) formata a saída de um jeito -- em vez de parsear coluna por
# coluna (frágil, muda a cada versão), extrai todo IPv4 que aparecer na
# saída bruta. "0.0.0.0"/"255.255.255.255" são placeholder de endpoint sem
# registro, nunca um peer de verdade.
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
_PLACEHOLDER_IPS = {"0.0.0.0", "255.255.255.255"}

_SOURCES = ("sip show peers", "pjsip show endpoints", "sip show registry")


def _cli(command, timeout=5):
    try:
        result = subprocess.run(["asterisk", "-rx", command], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _extract_ips(text):
    if not text:
        return []
    return [ip for ip in dict.fromkeys(_IPV4_RE.findall(text)) if ip not in _PLACEHOLDER_IPS]


def discover_asterisk_ips():
    # {ip: comando de origem} -- a primeira fonte que achar um IP "ganha" o
    # comentário (só pra dar contexto de onde veio, não muda o resultado).
    found = {}
    for command in _SOURCES:
        for ip in _extract_ips(_cli(command)):
            found.setdefault(ip, command)
    return found
