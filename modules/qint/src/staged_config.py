import json
import os
from pathlib import Path

VALID_TYPES = {"ixcsoft", "sgp"}


def load(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get("type") not in VALID_TYPES:
        return None
    return data


def save(path, config):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(config, indent=2))
    tmp_path.chmod(0o600)
    os.replace(tmp_path, path)
