import urllib.error

from pvx.registry.client import fetch_index


def _parse_version(text):
    try:
        return tuple(int(p) for p in str(text).split(".")[:3])
    except (ValueError, AttributeError):
        return None


def _status(installed_version, latest_version):
    installed_v = _parse_version(installed_version)
    latest_v = _parse_version(latest_version)
    if installed_v is None or latest_v is None or installed_v == latest_v:
        return "atualizado"
    if installed_v < latest_v:
        return "atualização disponível"
    # achado ao vivo: deploy direto na VPS (fora do registry) deixa a
    # versão instalada mais nova que a publicada -- "atualização
    # disponível" nesse caso não faz sentido.
    return "à frente do registry"


def list_modules(installed, index_url):
    try:
        index = fetch_index(index_url)
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"não foi possível acessar o registry ({index_url}): {e}") from e

    registry_by_name = {m["name"]: m for m in index["modules"]}

    rows = []
    for name in sorted(set(installed) | set(registry_by_name)):
        installed_module = installed.get(name)
        registry_entry = registry_by_name.get(name)
        installed_version = installed_module.version if installed_module else "-"
        latest_version = registry_entry["latest"] if registry_entry else "-"

        if installed_module and registry_entry:
            status = _status(installed_version, latest_version)
        elif installed_module:
            status = "local"
        else:
            status = "disponível"

        rows.append({
            "name": name,
            "installed_version": installed_version,
            "latest_version": latest_version,
            "status": status,
        })

    return rows
