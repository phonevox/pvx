import os
from pathlib import Path

from pvx import config as pvx_config

FILENAME = "audit.sh"


def default_dest_dir():
    return str(pvx_config.modules_dir() / "utilidades" / "scripts")


def _script_source():
    # funciona tanto rodando de module.pyz (zipimport, __loader__.archive
    # aponta pro .pyz real em disco) quanto em dev/teste (SourceFileLoader,
    # arquivo solto em scripts/ ao lado de src/) -- get_data() abstrai os dois.
    # __loader__ direto (global de módulo, não via sys.modules): o loader.py do
    # core remove o módulo de sys.modules logo após o import -- mesmo padrão
    # de modules/zabbix/src/known_scripts.py.
    loader = __loader__
    archive = getattr(loader, "archive", None)
    if archive:
        path = os.path.join(archive, "scripts", FILENAME)
    else:
        path = str(Path(__file__).resolve().parent.parent / "scripts" / FILENAME)
    return loader.get_data(path).decode()


def deploy(dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, FILENAME)
    with open(dest_path, "w") as f:
        f.write(_script_source())
    os.chmod(dest_path, 0o755)
    return dest_path
