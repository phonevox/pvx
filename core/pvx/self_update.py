import hashlib
import json
import shutil
import sys
import urllib.request
import zipimport

from pvx import config, update_check


def self_update():
    with urllib.request.urlopen(config.core_manifest_url()) as response:
        manifest = json.loads(response.read())

    with urllib.request.urlopen(config.core_update_url()) as response:
        data = response.read()

    actual_checksum = hashlib.sha256(data).hexdigest()
    expected_checksum = manifest.get("checksum_sha256")
    if actual_checksum != expected_checksum:
        raise ValueError(
            f"checksum não bate no self-update: "
            f"esperado {expected_checksum}, obtido {actual_checksum}"
        )

    lib_path = config.core_lib_path()
    tmp_path = lib_path.with_suffix(".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(lib_path)

    # achado ao vivo: zipimport cacheia o zipimporter (índice interno do
    # .zip) por path pra sempre -- igual o problema já resolvido pra
    # module.pyz de módulos (ver loader.py), só que aqui é o PRÓPRIO
    # core.pyz. Um processo longo (menu interativo, nunca reinicia) que
    # importa algum "pvx.*" pela primeira vez só DEPOIS do self-update
    # reusaria o índice da versão ANTIGA sobre o arquivo NOVO e crasharia
    # com "bad local file header".
    path_str = str(lib_path)
    sys.path_importer_cache.pop(path_str, None)
    getattr(zipimport, "_zip_directory_cache", {}).pop(path_str, None)

    # achado ao vivo: o cache de update_check.py sobrevive à troca do
    # core.pyz (TTL não sabe que a lógica mudou) -- um aviso calculado pela
    # versão ANTIGA (ex.: formato de linha diferente) continuava sendo
    # servido até o cache expirar sozinho, mesmo já rodando o core novo.
    update_check.clear_cache()

    return manifest.get("version")


def uninstall(purge=False):
    lib_path = config.core_lib_path()
    lib_path.unlink(missing_ok=True)
    try:
        lib_path.parent.rmdir()
    except OSError:
        pass

    config.pvx_bin_path().unlink(missing_ok=True)
    config.pvx_bin_symlink_path().unlink(missing_ok=True)

    if purge:
        shutil.rmtree(config.pvx_home(), ignore_errors=True)
