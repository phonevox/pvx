import uoe_client

UPLOAD_PATH = "/upload"

# pedido ao vivo: centraliza a orquestração no pvx em vez de depender do
# scripts/issabel.sh do pbackup (nada contra o script -- é só pra não ter
# que ir atualizar noutro repo se algo mudar). A geração em si continua
# sendo trabalho do issabel-helper (issabel_upload_ops.py só orquestra).
_ISSABEL_PVX_TEMPLATE = "pvx autobackup issabel-upload --upload-url {upload_url} --token {token}"
_ISSABEL_PVX_RECORDINGS_TEMPLATE = "pvx autobackup issabel-upload --upload-url {upload_url} --token {token} --recordings"
_MAGNUS_TEMPLATE = "bash {pbackup_root}/scripts/magnus.sh -t {upload_url}:/ --token {token}"
# alternativa que não passa pelo magnus.sh do pbackup (nem pelo cron.php do
# próprio MagnusBilling, que é a causa raiz de falha silenciosa que motivou
# isso) -- pvx magnus só gera o backup (mysqldump direto), upload continua
# sendo sempre trabalho do pbackup. Orquestração (nome com data, cleanup)
# vive em magnus_upload_ops.py, não numa linha de shell -- nada de `&&`
# encadeado nem `$(date ...)` escapado direto no crontab.
_MAGNUS_PVX_TEMPLATE = "pvx autobackup magnus-upload --upload-url {upload_url} --token {token}"

SCRIPTS = ("issabel", "magnus", "magnus-pvx", "custom")


def build_command(script, token, pbackup_root=None, custom_template=None, upload_base_url=None, issabel_recordings=False):
    upload_url = (upload_base_url or uoe_client.BASE_URL) + UPLOAD_PATH

    if script == "issabel":
        template = _ISSABEL_PVX_RECORDINGS_TEMPLATE if issabel_recordings else _ISSABEL_PVX_TEMPLATE
        return template.format(upload_url=upload_url, token=token)
    if script == "magnus":
        return _MAGNUS_TEMPLATE.format(pbackup_root=pbackup_root, upload_url=upload_url, token=token)
    if script == "magnus-pvx":
        return _MAGNUS_PVX_TEMPLATE.format(upload_url=upload_url, token=token)
    if script == "custom":
        if "{TOKEN}" not in custom_template:
            raise ValueError("o comando customizado precisa conter o placeholder literal {TOKEN}.")
        return custom_template.replace("{TOKEN}", token)

    raise ValueError(f"script desconhecido: {script} (opções: {', '.join(SCRIPTS)}).")
