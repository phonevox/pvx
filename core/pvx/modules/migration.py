import glob
import json
import os
from pathlib import Path
import shutil

from pvx import config


def _legacy_candidate_homes():
    homes = []
    root_home = Path("/root/.pvx")
    if root_home.is_dir():
        homes.append(root_home)
    for path in sorted(glob.glob("/home/*/.pvx")):
        p = Path(path)
        if p.is_dir():
            homes.append(p)
    return homes


def _parse_version(text):
    try:
        return tuple(int(p) for p in str(text).split(".")[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _module_version(module_dir):
    try:
        data = json.loads((module_dir / "manifest.json").read_text())
        return _parse_version(data.get("version", "0"))
    except (OSError, ValueError):
        return (0, 0, 0)


def migrate_legacy_modules(legacy_homes=None):
    # pvx passou a usar um diretório fixo (config.pvx_home()) em vez de
    # ~/.pvx -- qualquer usuário que já rodou `sudo pvx module install`
    # antes disso (inclusive root) tem módulos espalhados na própria home.
    # Só preenche o que falta no destino novo, nunca sobrescreve --
    # idempotente, seguro chamar em toda inicialização.
    if legacy_homes is None:
        legacy_homes = _legacy_candidate_homes()

    home = config.pvx_home()
    dest_modules = config.modules_dir()
    dest_modules.mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o755)
    os.chmod(dest_modules, 0o755)

    best_by_name = {}
    for legacy_home in legacy_homes:
        legacy_modules = legacy_home / "modules"
        if not legacy_modules.is_dir():
            continue
        for module_dir in legacy_modules.iterdir():
            if not module_dir.is_dir():
                continue
            name = module_dir.name
            if (dest_modules / name).exists():
                continue  # já migrado (ou já reinstalado) -- nunca sobrescreve
            version = _module_version(module_dir)
            if name not in best_by_name or version > best_by_name[name][0]:
                best_by_name[name] = (version, module_dir)

    migrated = []
    for name, (_, src) in best_by_name.items():
        shutil.copytree(src, dest_modules / name)
        migrated.append(name)
    return migrated
