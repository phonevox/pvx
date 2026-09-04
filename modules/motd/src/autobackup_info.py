import json

from pvx import config as pvx_config

# lê o state.json de outro módulo pelo caminho conhecido -- acoplamento de
# arquivo, não de código (cada módulo é um .pyz isolado, importar o Python
# de outro nem seria possível em runtime). Se autobackup mudar o formato do
# state, isso é o único lugar aqui que precisa acompanhar.
_STATE_PATH = ("autobackup", "state", "state.json")


def status():
    state_path = pvx_config.modules_dir().joinpath(*_STATE_PATH)
    try:
        data = json.loads(state_path.read_text())
    except (OSError, ValueError):
        return None
    return {
        "username": data.get("username"),
        "script": data.get("script"),
        "cron_minute": data.get("cron_minute"),
        "cron_hour": data.get("cron_hour"),
    }
