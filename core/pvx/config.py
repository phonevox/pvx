import json
import os
from pathlib import Path


def pvx_home() -> Path:
    override = os.environ.get("PVX_HOME")
    if override:
        return Path(override)

    # pvx é uma ferramenta administrativa, roda como root -- um único
    # diretório fixo, compartilhado por qualquer usuário que chamar `pvx`
    # (nunca baseado em $HOME/SUDO_USER: achado ao vivo, SUDO_USER fica
    # pendurado no ambiente depois de um `sudo`, e um `su` sem `-` logo em
    # seguida reseta $HOME mas não limpa SUDO_USER -- pvx acabava resolvendo
    # a home de um TERCEIRO usuário, às vezes ilegível pra quem chamou).
    return Path("/etc/pvx")


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
    return os.environ.get(
        "PVX_REGISTRY_URL", "https://registry.phonevox.com.br/pvx/index.json"
    )


def core_update_url() -> str:
    return os.environ.get(
        "PVX_CORE_URL", "https://github.com/phonevox/pvx/releases/latest/download/core.pyz"
    )


def core_manifest_url() -> str:
    return os.environ.get(
        "PVX_CORE_MANIFEST_URL",
        "https://github.com/phonevox/pvx/releases/latest/download/core-manifest.json",
    )


def core_lib_path() -> Path:
    override = os.environ.get("PVX_CORE_LIB_PATH")
    if override:
        return Path(override)
    return Path("/usr/local/lib/pvx/core.pyz")


def pvx_bin_path() -> Path:
    override = os.environ.get("PVX_BIN_PATH")
    if override:
        return Path(override)
    return Path("/usr/local/bin/pvx")


def pvx_bin_symlink_path() -> Path:
    override = os.environ.get("PVX_BIN_SYMLINK_PATH")
    if override:
        return Path(override)
    return Path("/usr/bin/pvx")


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
