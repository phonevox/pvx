#!/bin/sh
set -e

CORE_URL="${PVX_CORE_URL:-https://registry.pvx.dev/core/latest/core.pyz}"
# caminho fixo de sistema, igual qualquer pacote instalado via apt/yum --
# nunca $HOME: install.sh roda como root (via sudo, que reseta $HOME pra
# /root), então o binário compartilhado não pode morar na home de quem
# instalou, senão outros usuários tomam Permission denied.
PVX_LIB_DIR="/usr/local/lib/pvx"

is_python_new_enough() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null
}

find_py_bin() {
    for candidate in python3.12 python3.11 python3.10 python3.9 python3.8 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && is_python_new_enough "$candidate"; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

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

PY_BIN="$(find_py_bin || true)"

if [ -z "$PY_BIN" ]; then
    # python3 do sistema é antigo demais (comum em RHEL/Rocky 8, preso no
    # 3.6 porque o yum/dnf depende dessa versão exata) -- instala um
    # binário dedicado SEM trocar o python3 do sistema.
    if command -v yum >/dev/null 2>&1; then
        yum install -y python3.11 || yum install -y python39 || yum install -y python38 || true
    elif command -v apt-get >/dev/null 2>&1; then
        apt-get install -y python3.11 || apt-get install -y python3.9 || true
    fi
    PY_BIN="$(find_py_bin || true)"
fi

if [ -z "$PY_BIN" ]; then
    echo "pvx: nenhum python3 >= 3.8 disponível ou instalável" >&2
    exit 1
fi

mkdir -p "$PVX_LIB_DIR"

TMP_CORE="$(mktemp)"
# baixa via python3 (já garantido acima) em vez de curl/wget -- evita mais
# uma dependência externa que pode não existir na imagem base.
if ! "$PY_BIN" -c "
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
exec "$PY_BIN" "$PVX_LIB_DIR/core.pyz" "\$@"
EOF
chmod +x /usr/local/bin/pvx

# /usr/local/bin costuma ficar fora do secure_path do sudo (RHEL/Rocky
# excluem de propósito) -- symlink em /usr/bin garante pvx acessível
# mesmo com PATH restrito, sem mexer no sudoers.
ln -sf /usr/local/bin/pvx /usr/bin/pvx

echo "pvx instalado com sucesso."
