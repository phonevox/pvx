import shutil
import subprocess
from pathlib import Path

_CHOWN_CHMOD_CATEGORIES = ("agi", "php")


def _destination_path(base_dir, tipo):
    # achado ao vivo, conferido contra o instalador bash original: o destino usa o
    # nome do tipo (ixcsoft/sgp) como subpasta, nunca um "qint" fixo -- assim as duas
    # integrações convivem sem se pisar.
    return str(Path(base_dir) / tipo)


def compute_conflicts(base_dirs, tipo):
    return [
        category for category, base in base_dirs.items()
        if Path(_destination_path(base, tipo)).exists()
    ]


def deploy(source_dirs, base_dirs, tipo):
    for category, source in source_dirs.items():
        dest = Path(_destination_path(base_dirs[category], tipo))
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)

        if category in _CHOWN_CHMOD_CATEGORIES:
            subprocess.run(["chown", "-R", "asterisk:asterisk", str(dest)], check=True)
            subprocess.run(["chmod", "-R", "755", str(dest)], check=True)
