import shutil
import subprocess
from pathlib import Path

_CHOWN_CHMOD_CATEGORIES = ("agi", "php")


def _destination_path(base_dir):
    return str(Path(base_dir) / "qint")


def compute_conflicts(base_dirs):
    return [category for category, base in base_dirs.items() if Path(_destination_path(base)).exists()]


def deploy(source_dirs, base_dirs):
    for category, source in source_dirs.items():
        dest = Path(_destination_path(base_dirs[category]))
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)

        if category in _CHOWN_CHMOD_CATEGORIES:
            subprocess.run(["chown", "-R", "asterisk:asterisk", str(dest)], check=True)
            subprocess.run(["chmod", "-R", "755", str(dest)], check=True)
