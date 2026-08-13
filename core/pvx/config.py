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
