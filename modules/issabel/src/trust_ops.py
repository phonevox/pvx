import hashlib
import json
import socket
import urllib.error
import urllib.request
from base64 import b64encode

from pvx import config as pvx_config

PENDING_FILENAME = "trust_pending.json"
CACHE_FILENAME = "trust_cache.json"

# mesmo servidor do registry de módulos (registry.phonevox.com.br), mesmo
# namespace /pvx/ -- override via env PVX_AUDIT_TRUST_URL (config.py já usa
# essa mesma convenção pro registry).
DEFAULT_URL = "https://registry.phonevox.com.br"

# POST /pvx/trust só confere a SENHA do Basic Auth (ver simplewebserver) --
# não existe usuário de verdade, então aqui é só um valor fixo qualquer pra
# compor um header Basic bem formado.
_BASIC_AUTH_USER = "pvx"


class TrustError(Exception):
    pass


def _state_dir():
    path = pvx_config.modules_dir() / "issabel" / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pending_path():
    return _state_dir() / PENDING_FILENAME


def _cache_path():
    return _state_dir() / CACHE_FILENAME


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# melhor esforço -- IP usado de fato pra sair à rede (UDP "connect" só
# resolve a rota local, não troca pacote nenhum com 8.8.8.8).
def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "desconhecido"


def load_pending():
    try:
        return json.loads(_pending_path().read_text())
    except (OSError, ValueError):
        return []


def _save_pending(items):
    _pending_path().write_text(json.dumps(items, indent=2))


def clear_pending():
    _save_pending([])


# remove pendência local SEM publicar nada -- desfaz um trust/untrust
# staged por engano. paths=None (ou vazio) limpa tudo; senão remove só os
# caminhos informados. Retorna quantos itens foram de fato removidos.
def remove_pending(paths=None):
    items = load_pending()
    if not paths:
        clear_pending()
        return len(items)
    paths = set(paths)
    remaining = [i for i in items if i["caminho"] not in paths]
    _save_pending(remaining)
    return len(items) - len(remaining)


# staga uma trust/untrust localmente -- nunca toca rede. Rodar trust/untrust
# de novo pro mesmo caminho antes de publicar substitui a pendência anterior
# (não acumula duplicata pro mesmo arquivo).
def stage(path, action, ip_origem=None):
    sha256 = sha256_of(path)
    ip_origem = ip_origem or local_ip()
    items = [i for i in load_pending() if i["caminho"] != path]
    items.append({"sha256": sha256, "caminho": path, "ip_origem": ip_origem, "acao": action})
    _save_pending(items)
    return sha256


def load_cached_trust():
    try:
        return json.loads(_cache_path().read_text())
    except (OSError, ValueError):
        return []


# best-effort -- rede fora nunca pode bloquear um audit run. Sem rede, usa o
# último cache que deu certo (ou vazio, se nunca buscou com sucesso).
def fetch_remote_trust(url=None):
    url = url or DEFAULT_URL
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/pvx/trust.json", timeout=10) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, ValueError, OSError):
        return load_cached_trust()

    items = data.get("items", [])
    _cache_path().write_text(json.dumps(items))
    return items


# mescla a trust DB remota (url=None usa DEFAULT_URL) com o que o técnico já
# marcou localmente, mas ainda não publicou -- a própria central já filtra o
# achado dela mesma antes de esperar o round-trip de publish-trust. untrust
# pendente some do resultado mesmo que a remota ainda ache que é confiável.
# A ORIGEM ("remoto" x "local") é de propósito preservada em cada entrada --
# rede (já publicado, vale pra toda central) e local (só pendente aqui,
# ainda não publicado) são coisas diferentes, quem exibe precisa saber qual
# das duas suprimiu um achado.
def merged_trusted_items(url=None):
    by_path = {
        item["caminho"]: {"sha256": item["sha256"], "origem": "remoto"}
        for item in fetch_remote_trust(url)
    }
    for item in load_pending():
        if item["acao"] == "trust":
            by_path[item["caminho"]] = {"sha256": item["sha256"], "origem": "local"}
        else:
            by_path.pop(item["caminho"], None)
    return by_path


# audit.sh não expõe caminho de arquivo como campo estruturado -- só dá pra
# casar pelo texto da mensagem. Reconfere o sha256 NA HORA (não confia só no
# registro de trust) -- se o arquivo mudou desde que foi confiado, o achado
# volta a contar como não-confiado (proteção contra trocarem o conteúdo por
# baixo do pé). Nunca esconde achado -- devolve TODOS, na ordem original,
# anotados com (caminho, origem) do trust que casou (ou None) pra quem exibe
# decidir como marcar/explicar, em vez de just sumir silenciosamente.
def annotate_findings(findings, trusted_by_path):
    return [(finding, _matching_trusted_path(finding, trusted_by_path)) for finding in findings]


def _matching_trusted_path(finding, trusted_by_path):
    msg = finding.get("msg", "")
    for caminho, info in trusted_by_path.items():
        if caminho in msg and _still_matches(caminho, info["sha256"]):
            return caminho, info["origem"]
    return None


def _still_matches(path, sha256):
    try:
        return sha256_of(path) == sha256
    except OSError:
        return False


def publish(auth_pass, url=None, gerado_por=None):
    url = url or DEFAULT_URL
    pending = load_pending()
    if not pending:
        raise TrustError("nada pendente pra publicar.")

    gerado_por = gerado_por or socket.gethostname()
    body = json.dumps({"gerado_por": gerado_por, "itens": pending}).encode()
    token = b64encode(f"{_BASIC_AUTH_USER}:{auth_pass}".encode()).decode()
    request = urllib.request.Request(
        f"{url.rstrip('/')}/pvx/trust",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise TrustError(f"servidor respondeu {e.code}: {e.read().decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise TrustError(str(e.reason))

    clear_pending()
    return result
