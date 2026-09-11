import hashlib
import json
import shutil
import urllib.error
import urllib.request

from pvx import config, update_check
from pvx import version as pvx_version
from pvx.registry import schema
from pvx.registry.client import fetch_index


def _parse_version(text):
    try:
        return tuple(int(p) for p in str(text).split(".")[:3])
    except (ValueError, AttributeError):
        return None


def install(name, index_url, version=None):
    try:
        index = fetch_index(index_url)
        entry = next((m for m in index["modules"] if m["name"] == name), None)
        if entry is None:
            raise ValueError(f"módulo '{name}' não encontrado no registry ({index_url})")
        version = version or entry["latest"]

        with urllib.request.urlopen(entry["manifest_url"]) as response:
            manifest = json.loads(response.read())
        schema.validate_manifest(manifest)

        pyz_url = entry["url_template"].format(name=name, version=version)
        with urllib.request.urlopen(pyz_url) as response:
            pyz_bytes = response.read()
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"não foi possível acessar o registry ({index_url}): {e}") from e

    actual_checksum = hashlib.sha256(pyz_bytes).hexdigest()
    expected_checksum = manifest.get("checksum_sha256")
    if actual_checksum != expected_checksum:
        raise ValueError(
            f"checksum não bate pra módulo '{name}': "
            f"esperado {expected_checksum}, obtido {actual_checksum}"
        )

    # achado ao vivo: um módulo atualizado sozinho (registry independente do
    # core) crashou em produção com AttributeError -- usava widgets.state_line,
    # que só existe numa versão de core mais nova. min_pvx_version existe no
    # manifest desde sempre, mas nunca era checado -- só documentação morta.
    # Unparseável (min_pvx_version ausente/inválido) nunca bloqueia -- mesma
    # postura permissiva de listing.py/_status() pra versão que não dá pra ler.
    min_version = _parse_version(manifest.get("min_pvx_version"))
    current_version = _parse_version(pvx_version.__version__)
    if min_version and current_version and current_version < min_version:
        raise RuntimeError(
            f"módulo '{name}' precisa do pvx >= {manifest['min_pvx_version']} "
            f"(instalado: {pvx_version.__version__}) -- rode `pvx self-update` primeiro."
        )

    install_dir = config.modules_dir() / name
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "module.pyz").write_bytes(pyz_bytes)
    (install_dir / "manifest.json").write_text(json.dumps(manifest))

    # achado ao vivo: instalar/atualizar um módulo manualmente não invalidava
    # o cache do aviso de update -- o banner continuava servindo o status
    # antigo até o TTL de 6h expirar sozinho, mesmo já com o módulo novo no
    # disco. install()/uninstall() são o funil que TODO caller (CLI direta,
    # menu interativo) já passa, então o fix mora aqui uma vez só.
    update_check.clear_cache()


def uninstall(name):
    # achado ao vivo: ignore_errors=True escondia falha real (ex.: arquivo
    # travado por permissão) -- `pvx module uninstall` reportava "removido"
    # sem remover nada, e o módulo reaparecia sozinho no próximo
    # `module list`/menu, sem nenhum aviso do que deu errado.
    path = config.modules_dir() / name
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        raise RuntimeError(
            f"não consegui remover o módulo '{name}' por completo -- "
            f"verifique permissões em {path}."
        )
    update_check.clear_cache()
