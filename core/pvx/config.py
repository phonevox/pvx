import json
import os
from pathlib import Path


def pvx_home() -> Path:
    override = os.environ.get("PVX_HOME")
    if override:
        return Path(override)
    return Path.home() / ".pvx"


def bin_dir() -> Path:
    return pvx_home() / "bin"


def modules_dir() -> Path:
    return pvx_home() / "modules"


def logs_dir() -> Path:
    return pvx_home() / "logs"


def registry_cache_path() -> Path:
    return pvx_home() / "registry.json"


def config_file_path() -> Path:
    return pvx_home() / "config.json"


def registry_index_url() -> str:
    return os.environ.get("PVX_REGISTRY_URL", "https://registry.pvx.dev/index.json")


def read_config() -> dict:
    path = config_file_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_config(data: dict) -> None:
    path = config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def get_theme_name() -> str:
    return read_config().get("theme", "azul")


def set_theme_name(name: str) -> None:
    data = read_config()
    data["theme"] = name
    write_config(data)
