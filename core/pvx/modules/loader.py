import importlib
import importlib.util
import json
import sys
import zipimport


def _load_from_pyz(pyz_path, module_file):
    # limpa TODO nome novo em sys.modules, não só module_file -- módulos
    # internos (ex. validators.py) de módulos diferentes colidem senão.
    before = set(sys.modules)
    path_str = str(pyz_path)

    # achado ao vivo: zipimport cacheia o zipimporter (índice interno do .zip)
    # por path, pra sempre -- `pvx modules update` sobrescreve o mesmo
    # module.pyz enquanto o menu interativo (processo longo, nunca reinicia)
    # continua rodando. Sem isso, o discover() de depois do update reusa o
    # índice do .zip ANTIGO sobre o arquivo NOVO (offsets não batem mais) e
    # crasha (ou pior, carrega conteúdo errado) só de reabrir o mesmo módulo.
    sys.path_importer_cache.pop(path_str, None)
    # sys.path_importer_cache só descarta o OBJETO zipimporter -- construir um
    # novo pro mesmo path ainda consulta esse cache mais baixo (índice bruto do
    # .zip) antes de reler o arquivo do disco. Sem limpar os dois, o problema
    # persiste idêntico. _zip_directory_cache é detalhe interno do CPython
    # (não é API pública) -- getattr com fallback pra nunca quebrar o loader
    # inteiro se uma versão futura do Python remover/renomear isso.
    getattr(zipimport, "_zip_directory_cache", {}).pop(path_str, None)

    sys.path.insert(0, path_str)
    try:
        return importlib.import_module(module_file)
    finally:
        sys.path.remove(path_str)
        for name in set(sys.modules) - before:
            # achado ao vivo: evictar um nome "pvx.*" (ex.: pvx.modules.base,
            # importado de dentro do module.py de CADA módulo) junto com o
            # "module"/helpers temporários era inofensivo enquanto core.pyz
            # nunca mudava em disco no meio do processo -- mas depois de um
            # self-update, reimportar um nome "pvx.*" evictado reusa o
            # zipimporter cacheado pro path do core.pyz com offsets da
            # versão ANTIGA e crasha ("bad local file header"). "pvx.*"
            # pertence ao core, nunca a um módulo -- nunca evict daqui.
            if name == "pvx" or name.startswith("pvx."):
                continue
            sys.modules.pop(name, None)


def _load_from_py(py_path, name):
    # nome de módulo sintético e único por instalação -- evita colisão
    # entre módulos que usam o mesmo nome de arquivo (module.py).
    spec = importlib.util.spec_from_file_location(f"pvx_installed_module_{name}", py_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover(modules_dir):
    if not modules_dir.exists():
        return {}

    modules = {}
    for module_dir in modules_dir.iterdir():
        if not module_dir.is_dir():
            continue
        manifest_path = module_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        manifest = json.loads(manifest_path.read_text())
        name = manifest["name"]
        module_file, attr_name = manifest["entrypoint"].split(":")

        pyz_path = module_dir / f"{module_file}.pyz"
        if pyz_path.exists():
            module = _load_from_pyz(pyz_path, module_file)
        else:
            module = _load_from_py(module_dir / f"{module_file}.py", name)

        modules[name] = getattr(module, attr_name)

    return modules
