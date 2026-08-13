import json

from pvx import config


def save(index):
    path = config.registry_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index))


def load():
    path = config.registry_cache_path()
    if not path.exists():
        return None
    return json.loads(path.read_text())
