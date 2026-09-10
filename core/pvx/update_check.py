import json
import time
import urllib.error
import urllib.request

from pvx import config
from pvx.modules import listing
from pvx.version import __version__

# best-effort, silencioso: nunca deve travar/quebrar o menu por causa de rede
# ruim ou registry fora do ar -- só um aviso a menos.
_TIMEOUT_SECONDS = 2
_CACHE_TTL_SECONDS = 6 * 3600


def _parse_version(text):
    try:
        return tuple(int(p) for p in str(text).split(".")[:3])
    except (ValueError, AttributeError):
        return None


def _fetch_core_latest():
    with urllib.request.urlopen(config.core_manifest_url(), timeout=_TIMEOUT_SECONDS) as response:
        manifest = json.loads(response.read())
    return manifest.get("version")


def _core_notice():
    try:
        latest = _fetch_core_latest()
    except (urllib.error.URLError, OSError, ValueError):
        return None

    current_v = _parse_version(__version__)
    latest_v = _parse_version(latest)
    # mesma regra de listing._status(): instalado à frente do registry (ex.:
    # deploy direto na VPS) não é "atualização disponível".
    if current_v is None or latest_v is None or latest_v <= current_v:
        return None
    return f"core: atualização disponível ({__version__} -> {latest})"


def _module_notices(installed):
    # achado ao vivo: um aviso por módulo lotava o banner (uma linha por
    # módulo pendente) -- colapsa numa linha só, mesmo padrão de "core: ..."
    # (widgets.warning() sempre imprime no máximo 1 linha por chamador).
    try:
        rows = listing.list_modules(installed, config.registry_index_url())
    except RuntimeError:
        return []
    outdated = [row["name"] for row in rows if row["status"] == "atualização disponível"]
    if not outdated:
        return []
    word = "atualização disponível" if len(outdated) == 1 else "atualizações disponíveis"
    return [f"módulos: {len(outdated)} {word} ({', '.join(outdated)})"]


def _run_check(installed):
    notices = []
    core_notice = _core_notice()
    if core_notice:
        notices.append(core_notice)
    notices += _module_notices(installed)
    return notices


def _read_cache():
    path = config.update_check_cache_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_cache(notices):
    path = config.update_check_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"checked_at": time.time(), "notices": notices}))


def clear_cache():
    # achado ao vivo: trocar o core.pyz (self-update) não afeta o TTL do
    # cache -- um aviso calculado pela lógica ANTIGA continuava sendo
    # servido até o cache expirar sozinho, mesmo já rodando o core novo.
    # self_update.self_update() chama isso depois de trocar o binário.
    config.update_check_cache_path().unlink(missing_ok=True)


def pending_notices(installed, force=False):
    cache = _read_cache()
    if not force and cache and time.time() - cache.get("checked_at", 0) < _CACHE_TTL_SECONDS:
        return cache.get("notices", [])

    notices = _run_check(installed)
    _write_cache(notices)
    return notices
