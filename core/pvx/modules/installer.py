import hashlib
import json
import shutil
import urllib.error
import urllib.request

from pvx import config
from pvx.registry import schema
from pvx.registry.client import fetch_index


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

    install_dir = config.modules_dir() / name
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "module.pyz").write_bytes(pyz_bytes)
    (install_dir / "manifest.json").write_text(json.dumps(manifest))


def uninstall(name):
    shutil.rmtree(config.modules_dir() / name, ignore_errors=True)
