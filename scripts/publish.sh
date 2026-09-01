#!/bin/sh
set -e

cd "$(dirname "$0")/.."

MODULES_DIR="modules"
STAGE_DIR="dist/registry"
INDEX_URL="https://registry.phonevox.com.br/pvx/index.json"

# descoberto de modules/*/manifest.json -- nunca lista fixa (achado ao vivo:
# zabbix ficou de fora de --all porque a lista hardcoded nunca foi atualizada
# quando o módulo foi criado).
all_modules() {
    for d in "$MODULES_DIR"/*/; do
        m="$(basename "$d")"
        case "$m" in _*) continue ;; esac
        [ -f "$MODULES_DIR/$m/manifest.json" ] && printf '%s ' "$m"
    done
}
ALL_MODULES="$(all_modules)"

usage() {
    cat <<'EOF'
uso: scripts/publish.sh <modo> [modulo|--all] [opções]

modos:
  diff      compara a versão local (dev) com a publicada no registry
  stage     builda e monta dist/registry/, pronta pra subir
  upload    stage + sobe via SFTP pro path intermediário do servidor
  publish   upload + roda o cp -R remoto pro path público final

opções (upload/publish):
  --host, -h HOST[:PORTA]    host do servidor do registry (porta default: 22)
  --user, -u USER            usuário SFTP/SSH
  --publish-user USER        usuário SSH pra rodar o cp -R (publish, default: --user)
  --key, -i PATH              chave privada SSH
  --password-file PATH        arquivo com a senha (alternativa a --key, exige sshpass)
  --remote-path PATH           path intermediário no servidor (opcional -- sem isso, sobe
                                direto pro --public-path, sem cp -R depois)
  --public-path PATH           path público final (obrigatório pra publish)
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
base = '$INDEX_URL'.rsplit('/', 1)[0] + '/'
by_name = {m['name']: m for m in data['modules']}

# módulo que já existe no índice remoto só tem a versão atualizada; módulo
# novo (nunca publicado) precisa da entrada inteira criada -- achado ao vivo:
# a versão anterior só atualizava, nunca adicionava (zabbix sumia do index.json
# mesmo staged com sucesso, porque não existia ainda no remoto pra 'achar').
for m in '$modules'.split():
    manifest = json.load(open('$MODULES_DIR/' + m + '/manifest.json'))
    v = manifest['version']
    if m in by_name:
        by_name[m]['latest'] = v
        by_name[m]['versions'] = [v]
    else:
        entry = {
            'name': m,
            'description': manifest.get('description', ''),
            'latest': v,
            'versions': [v],
            'url_template': base + 'modules/{name}/{version}.pyz',
            'manifest_url': base + 'modules/' + m + '/manifest.json',
        }
        data['modules'].append(entry)
        by_name[m] = entry

json.dump(data, open('$STAGE_DIR/index.json', 'w'), indent=2, ensure_ascii=False)
"
    echo "index.json atualizado em $STAGE_DIR/index.json"
}

# --- opções compartilhadas de upload/publish ---

parse_remote_opts() {
    HOST="" PORT="22" USER="" PUBLISH_USER="" KEY="" PASSWORD_FILE="" REMOTE_PATH="" PUBLIC_PATH="" YES=""
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
    case "$HOST" in
        *:*) PORT="${HOST##*:}"; HOST="${HOST%%:*}" ;;
    esac
    [ -n "$HOST" ] || { echo "--host obrigatório" >&2; exit 1; }
    [ -n "$USER" ] || { echo "--user obrigatório" >&2; exit 1; }
    if [ -z "$KEY" ] && [ -z "$PASSWORD_FILE" ]; then
        echo "informe --key ou --password-file" >&2; exit 1
    fi
    PUBLISH_USER="${PUBLISH_USER:-$USER}"
}

# ssh/sftp/scp com --key ou --password-file (sshpass), nunca senha em argumento/env visível.
ssh_cmd() {
    user="$1" host="$2"; shift 2
    if [ -n "$KEY" ]; then
        ssh -p "$PORT" -i "$KEY" -o BatchMode=yes "$user@$host" "$@"
    else
        sshpass -f "$PASSWORD_FILE" ssh -p "$PORT" -o PreferredAuthentications=password "$user@$host" "$@"
    fi
}

# sobe pra $1 (destino remoto) via SFTP.
sftp_put() {
    dest="$1"
    if [ -n "$KEY" ]; then
        sftp -P "$PORT" -i "$KEY" -b - "$USER@$HOST" <<EOF
put -R $STAGE_DIR/* $dest
bye
EOF
    else
        sshpass -f "$PASSWORD_FILE" sftp -P "$PORT" -o PreferredAuthentications=password -b - "$USER@$HOST" <<EOF
put -R $STAGE_DIR/* $dest
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
    dest="${REMOTE_PATH:-$PUBLIC_PATH}"
    [ -n "$dest" ] || { echo "informe --remote-path ou --public-path" >&2; exit 1; }
    cmd_stage "$module_arg"
    echo
    echo "vai subir $STAGE_DIR/ pra $USER@$HOST:$PORT:$dest"
    confirm "confirma o upload?"
    sftp_put "$dest"
    echo "upload concluído."
}

# --- modo: publish ---

cmd_publish() {
    module_arg="$1"; shift
    parse_remote_opts "$@"
    [ -n "$PUBLIC_PATH" ] || { echo "--public-path obrigatório pra publish" >&2; exit 1; }
    cmd_stage "$module_arg"
    echo
    if [ -n "$REMOTE_PATH" ]; then
        echo "vai subir $STAGE_DIR/ pra $USER@$HOST:$PORT:$REMOTE_PATH"
        echo "e copiar pra $PUBLIC_PATH (usuário: $PUBLISH_USER)"
        confirm "confirma upload + publish?"
        sftp_put "$REMOTE_PATH"
        ssh_cmd "$PUBLISH_USER" "$HOST" "cp -R $REMOTE_PATH/* $PUBLIC_PATH"
    else
        echo "vai subir $STAGE_DIR/ direto pra $USER@$HOST:$PORT:$PUBLIC_PATH (sem --remote-path, sem cp -R)"
        confirm "confirma o publish?"
        sftp_put "$PUBLIC_PATH"
    fi
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
