import uoe_client

UPLOAD_PATH = "/upload"

_ISSABEL_TEMPLATE = "bash {pbackup_root}/scripts/issabel.sh --recordings --configuration -t {upload_url}:/ --token {token}"
_MAGNUS_TEMPLATE = "bash {pbackup_root}/scripts/magnus.sh -t {upload_url}:/ --token {token}"

SCRIPTS = ("issabel", "magnus", "custom")


def build_command(script, token, pbackup_root=None, custom_template=None, upload_base_url=None):
    upload_url = (upload_base_url or uoe_client.BASE_URL) + UPLOAD_PATH

    if script == "issabel":
        return _ISSABEL_TEMPLATE.format(pbackup_root=pbackup_root, upload_url=upload_url, token=token)
    if script == "magnus":
        return _MAGNUS_TEMPLATE.format(pbackup_root=pbackup_root, upload_url=upload_url, token=token)
    if script == "custom":
        if "{TOKEN}" not in custom_template:
            raise ValueError("o comando customizado precisa conter o placeholder literal {TOKEN}.")
        return custom_template.replace("{TOKEN}", token)

    raise ValueError(f"script desconhecido: {script} (opções: {', '.join(SCRIPTS)}).")
