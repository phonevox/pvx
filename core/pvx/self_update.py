import hashlib
import json
import os
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

    # zipimport cacheia o índice do .zip por path pra sempre, inclusive por
    # subpacote ("core.pyz/pvx", não só a raiz) -- limpa tudo que começa com
    # o path do core.pyz, senão um "pvx.*" importado pela primeira vez só
    # depois do self-update crasha com "bad local file header".
    path_str = str(lib_path)
    for cache in (sys.path_importer_cache, getattr(zipimport, "_zip_directory_cache", {})):
        for key in [k for k in cache if k == path_str or k.startswith(path_str + os.sep)]:
            cache.pop(key, None)

    # __version__ de um módulo já importado fica preso na versão antiga
    # depois disto (zipimport não tem um jeito 100% confiável de recarregar
    # em memória) -- quem precisa da versão real usa
    # pvx.version.installed_version(), que lê o .pyz em disco direto.

    # TTL do cache de update_check.py não sabe que o core mudou -- limpa
    # pra não continuar servindo um aviso calculado pela versão antiga.
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
