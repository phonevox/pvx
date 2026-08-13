import importlib.util
import json


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
        module_path = module_dir / f"{module_file}.py"

        # nome de módulo sintético e único por instalação -- evita colisão
        # entre módulos que usam o mesmo nome de arquivo (module.py).
        spec = importlib.util.spec_from_file_location(f"pvx_installed_module_{name}", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        modules[name] = getattr(module, attr_name)

    return modules
