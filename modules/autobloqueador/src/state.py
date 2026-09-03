import json
import os
from pathlib import Path


def load(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def remove(path):
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    tmp_path.chmod(0o600)  # guarda a crypted_key -- nunca mundo-legível
    os.replace(tmp_path, path)
