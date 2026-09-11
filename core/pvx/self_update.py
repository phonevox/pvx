import hashlib
import json
import os
import shutil
import sys
import urllib.request
import zipfile
import zipimport

import pvx as pvx_pkg
from pvx import config, update_check
from pvx import version as pvx_version


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
    # com "bad local file header". Achado ao vivo (2a vez, mais fundo): não
    # basta limpar a chave exata do zip -- cada SUBPACOTE (ex.: "core.pyz/pvx")
    # ganha sua PRÓPRIA entrada em sys.path_importer_cache, então limpa
    # tudo que começa com o path do zip, não só ele.
    path_str = str(lib_path)
    for cache in (sys.path_importer_cache, getattr(zipimport, "_zip_directory_cache", {})):
        for key in [k for k in cache if k == path_str or k.startswith(path_str + os.sep)]:
            cache.pop(key, None)

    # achado ao vivo: "pvx.version" já importado (processo longo, menu
    # interativo nunca reinicia) continua com o __version__ ANTIGO -- trocar
    # o arquivo em disco não re-executa um módulo já carregado. update_check.py
    # (banner "atualização disponível") e root.py (ação "versão") liam esse
    # valor preso, então o próprio menu dizia "ainda desatualizado" segundos
    # depois de um self-update bem-sucedido.
    #
    # achado ao vivo (mais fundo ainda): importlib.reload() sozinho NÃO
    # basta, mesmo com os caches acima limpos -- reload() reusa o
    # module.__loader__ JÁ CONSTRUÍDO (a instância de zipimporter antiga, com
    # o índice do arquivo VELHO gravado nela mesma na hora em que foi
    # criada); limpar os caches globais só evita que uma instância NOVA
    # reuse índice velho, nunca conserta uma que já existe. Construir um
    # zipimporter NOVO na mão (lendo o arquivo já trocado, caches já limpos
    # acima) e chamar load_module() faz o que reload() promete de verdade --
    # atualiza pvx.version IN PLACE (mesmo objeto que todo mundo já importou).
    # is_zipfile(): em dev/teste "pvx" é um pacote de verdade em disco (não
    # dentro de um .pyz) -- só faz sentido em produção, rodando via core.pyz.
    if zipfile.is_zipfile(lib_path):
        zipimport.zipimporter(pvx_pkg.__path__[0]).load_module("pvx.version")

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
