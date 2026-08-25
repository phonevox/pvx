#!/bin/sh
set -e

cd "$(dirname "$0")/.."

MODULES_DIR="modules"
STAGE_DIR="dist/registry"
INDEX_URL="https://registry.phonevox.com.br/pvx/index.json"

ALL_MODULES="dummy firewall qint ssh-hardening netinstall"

usage() {
    cat <<'EOF'
uso: scripts/publish.sh <modo> [modulo|--all] [opções]

modos:
  diff      compara a versão local (dev) com a publicada no registry
  stage     builda e monta dist/registry/, pronta pra subir
  upload    stage + sobe via SFTP pro path intermediário do servidor
  publish   upload + roda o cp -R remoto pro path público final

opções (upload/publish):
  --host, -h HOST            host do servidor do registry
  --user, -u USER            usuário SFTP (upload)
  --publish-user USER        usuário SSH pra rodar o cp -R (publish, default: --user)
  --key, -i PATH              chave privada SSH
  --password-file PATH        arquivo com a senha (alternativa a --key, exige sshpass)
  --remote-path PATH           path intermediário no servidor (upload)
  --public-path PATH           path público final (publish)
  --yes, -y                    pula a confirmação
EOF
}

# --- utilitários ---

module_version() {
    python3 -c "import json; print(json.load(open('$MODULES_DIR/$1/manifest.json'))['version'])"
}

registry_version() {
    python3 -c "
import json, urllib.request
try:
    data = json.load(urllib.request.urlopen('$INDEX_URL'))
except Exception:
    print('-')
    raise SystemExit
for m in data['modules']:
    if m['name'] == '$1':
        print(m['latest'])
        break
else:
    print('-')
"
}

resolve_modules() {
    if [ "$1" = "--all" ] || [ -z "$1" ]; then
        echo "$ALL_MODULES"
    else
        echo "$1"
    fi
}

# --- modo: diff ---

cmd_diff() {
    for m in $(resolve_modules "$1"); do
        local_v="$(module_version "$m")"
        registry_v="$(registry_version "$m")"
        if [ "$local_v" = "$registry_v" ]; then
            printf '%-16s %s (igual ao registry)\n' "$m" "$local_v"
        else
            printf '%-16s registry: %-10s dev: %s\n' "$m" "$registry_v" "$local_v"
        fi
    done
}

# --- modo: stage ---

cmd_stage() {
    modules="$(resolve_modules "$1")"
    rm -rf "$STAGE_DIR"
    mkdir -p "$STAGE_DIR/modules"

    for m in $modules; do
        (cd "$MODULES_DIR/$m" && sh build.sh >/dev/null)
        version="$(module_version "$m")"
        mkdir -p "$STAGE_DIR/modules/$m"
        cp "$MODULES_DIR/$m/dist/module.pyz" "$STAGE_DIR/modules/$m/$version.pyz"
        cp "$MODULES_DIR/$m/dist/manifest.json" "$STAGE_DIR/modules/$m/manifest.json"
        echo "staged: $m -> $version"
    done

    python3 -c "
import json, urllib.request

data = json.load(urllib.request.urlopen('$INDEX_URL'))
versions = {}
for m in '$modules'.split():
    versions[m] = json.load(open('$MODULES_DIR/' + m + '/manifest.json'))['version']

for m in data['modules']:
    if m['name'] in versions:
        v = versions[m['name']]
        m['latest'] = v
        m['versions'] = [v]

json.dump(data, open('$STAGE_DIR/index.json', 'w'), indent=2, ensure_ascii=False)
"
    echo "index.json atualizado em $STAGE_DIR/index.json"
}

# --- opções compartilhadas de upload/publish ---

parse_remote_opts() {
    HOST="" USER="" PUBLISH_USER="" KEY="" PASSWORD_FILE="" REMOTE_PATH="" PUBLIC_PATH="" YES=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --host|-h) HOST="$2"; shift 2 ;;
            --user|-u) USER="$2"; shift 2 ;;
            --publish-user) PUBLISH_USER="$2"; shift 2 ;;
            --key|-i) KEY="$2"; shift 2 ;;
            --password-file) PASSWORD_FILE="$2"; shift 2 ;;
            --remote-path) REMOTE_PATH="$2"; shift 2 ;;
            --public-path) PUBLIC_PATH="$2"; shift 2 ;;
            --yes|-y) YES=1; shift ;;
            *) echo "opção desconhecida: $1" >&2; exit 1 ;;
        esac
    done
    [ -n "$HOST" ] || { echo "--host obrigatório" >&2; exit 1; }
    [ -n "$USER" ] || { echo "--user obrigatório" >&2; exit 1; }
    [ -n "$REMOTE_PATH" ] || { echo "--remote-path obrigatório" >&2; exit 1; }
    if [ -z "$KEY" ] && [ -z "$PASSWORD_FILE" ]; then
        echo "informe --key ou --password-file" >&2; exit 1
    fi
    PUBLISH_USER="${PUBLISH_USER:-$USER}"
}

# ssh/sftp/scp com --key ou --password-file (sshpass), nunca senha em argumento/env visível.
ssh_cmd() {
    user="$1" host="$2"; shift 2
    if [ -n "$KEY" ]; then
        ssh -i "$KEY" -o BatchMode=yes "$user@$host" "$@"
    else
        sshpass -f "$PASSWORD_FILE" ssh -o PreferredAuthentications=password "$user@$host" "$@"
    fi
}

sftp_put() {
    if [ -n "$KEY" ]; then
        sftp -i "$KEY" -b - "$USER@$HOST" <<EOF
put -R $STAGE_DIR/* $REMOTE_PATH
bye
EOF
    else
        sshpass -f "$PASSWORD_FILE" sftp -o PreferredAuthentications=password -b - "$USER@$HOST" <<EOF
put -R $STAGE_DIR/* $REMOTE_PATH
bye
EOF
    fi
}

confirm() {
    [ -n "$YES" ] && return 0
    printf '%s [y/N] ' "$1"
    read -r reply
    case "$reply" in
        y|Y|yes|s|S|sim) return 0 ;;
        *) echo "cancelado."; exit 1 ;;
    esac
}

# --- modo: upload ---

cmd_upload() {
    module_arg="$1"; shift
    parse_remote_opts "$@"
    cmd_stage "$module_arg"
    echo
    echo "vai subir $STAGE_DIR/ pra $USER@$HOST:$REMOTE_PATH"
    confirm "confirma o upload?"
    sftp_put
    echo "upload concluído."
}

# --- modo: publish ---

cmd_publish() {
    module_arg="$1"; shift
    parse_remote_opts "$@"
    [ -n "$PUBLIC_PATH" ] || { echo "--public-path obrigatório pra publish" >&2; exit 1; }
    cmd_stage "$module_arg"
    echo
    echo "vai subir $STAGE_DIR/ pra $USER@$HOST:$REMOTE_PATH"
    echo "e copiar pra $PUBLIC_PATH (usuário: $PUBLISH_USER)"
    confirm "confirma upload + publish?"
    sftp_put
    ssh_cmd "$PUBLISH_USER" "$HOST" "cp -R $REMOTE_PATH/* $PUBLIC_PATH"
    echo "publicado."
}

# --- dispatch ---

MODE="$1"
[ -n "$MODE" ] && shift || true

case "$MODE" in
    diff) cmd_diff "$1" ;;
    stage) cmd_stage "$1" ;;
    upload) cmd_upload "$@" ;;
    publish) cmd_publish "$@" ;;
    *) usage; exit 1 ;;
esac
