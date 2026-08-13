#!/bin/sh
set -e

CORE_URL="${PVX_CORE_URL:-https://registry.pvx.dev/core/latest/core.pyz}"
# caminho fixo de sistema, igual qualquer pacote instalado via apt/yum --
# nunca $HOME: install.sh roda como root (via sudo, que reseta $HOME pra
# /root), então o binário compartilhado não pode morar na home de quem
# instalou, senão outros usuários tomam Permission denied.
PVX_LIB_DIR="/usr/local/lib/pvx"

if ! command -v python3 >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update && apt-get install -y python3
    elif command -v yum >/dev/null 2>&1; then
        yum install -y python3
    elif command -v apk >/dev/null 2>&1; then
        apk add --no-cache python3
    else
        echo "pvx: nenhum gerenciador de pacote suportado (apt/yum/apk) encontrado" >&2
        exit 1
    fi
fi

mkdir -p "$PVX_LIB_DIR"

# baixa via python3 (já garantido acima) em vez de curl/wget -- evita mais
# uma dependência externa que pode não existir na imagem base.
TMP_CORE="$(mktemp)"
if ! python3 -c "
import sys, urllib.request
urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
" "$CORE_URL" "$TMP_CORE"; then
    echo "pvx: falha ao baixar core.pyz de $CORE_URL" >&2
    rm -f "$TMP_CORE"
    exit 1
fi

mv "$TMP_CORE" "$PVX_LIB_DIR/core.pyz"
chmod 644 "$PVX_LIB_DIR/core.pyz"

cat > /usr/local/bin/pvx <<EOF
#!/bin/sh
exec python3 "$PVX_LIB_DIR/core.pyz" "\$@"
EOF
chmod +x /usr/local/bin/pvx

echo "pvx instalado com sucesso."
