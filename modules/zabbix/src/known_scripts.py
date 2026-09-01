import os
from pathlib import Path

# catálogo de scripts que o pvx distribui junto com o módulo (pasta scripts/,
# na raiz do módulo -- build.sh empacota ela dentro do module.pyz). nunca
# comando arbitrário do usuário: só o que está aqui.
CATALOG = {
    "audit": {
        "filename": "audit.sh",
        "description": "auditoria de comprometimento (mineração, persistência, webshell, abuso de PBX...)",
        "args": "--zabbix",
        "needs_root": True,
    },
}


def _script_source(filename):
    # funciona tanto rodando de module.pyz (zipimport, __loader__.archive
    # aponta pro .pyz real em disco) quanto em dev/teste (SourceFileLoader,
    # arquivo solto em scripts/ ao lado de src/) -- get_data() abstrai os dois.
    # __loader__ direto (global de módulo, não via sys.modules): o loader.py do
    # core remove o módulo de sys.modules logo após o import (evita colisão de
    # nome entre módulos diferentes) -- sys.modules[__name__] já não existe mais
    # quando deploy() roda de verdade.
    loader = __loader__
    archive = getattr(loader, "archive", None)
    if archive:
        path = os.path.join(archive, "scripts", filename)
    else:
        path = str(Path(__file__).resolve().parent.parent / "scripts" / filename)
    return loader.get_data(path).decode()


def deploy(dest_dir, key):
    entry = CATALOG[key]
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, entry["filename"])
    with open(dest_path, "w") as f:
        f.write(_script_source(entry["filename"]))
    os.chmod(dest_path, 0o755)
    return dest_path


def remove_deployed(dest_dir, key):
    entry = CATALOG.get(key)
    if entry is None:
        return
    try:
        os.remove(os.path.join(dest_dir, entry["filename"]))
    except FileNotFoundError:
        pass
