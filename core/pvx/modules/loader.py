import importlib
import importlib.util
import json
import sys


def _load_from_pyz(pyz_path, module_file):
    # zipimport resolve pelo nome puro (não dá pra usar um nome sintético
    # único aqui) -- processa um módulo de cada vez e limpa sys.path/
    # sys.modules logo em seguida, pra não colidir com o próximo .pyz que
    # também se chame "module".
    sys.path.insert(0, str(pyz_path))
    try:
        return importlib.import_module(module_file)
    finally:
        sys.path.remove(str(pyz_path))
        sys.modules.pop(module_file, None)


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
