#!/bin/sh
set -e

cd "$(dirname "$0")"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cp -r pvx "$BUILD_DIR/"
# rich>=15 exige Python 3.9+ (usa `os.PathLike[str]` como generic subscript,
# só suportado nativamente a partir do 3.9) -- quebra silenciosamente o
# suporte a 3.8 que o pvx promete, já que o build roda com o python3 do dev
# (normalmente mais novo), não o do host onde o core.pyz vai rodar.
python3 -m pip install --quiet --target "$BUILD_DIR" click questionary "rich<15"

if [ -z "$PVX_RELEASE_BUILD" ] && git rev-parse --git-dir >/dev/null 2>&1; then
    cat > "$BUILD_DIR/pvx/_build_stamp.py" <<EOF
BRANCH = "$(git rev-parse --abbrev-ref HEAD)"
COMMIT = "$(git rev-parse --short HEAD)"
EOF
fi

cat > "$BUILD_DIR/__main__.py" <<'EOF'
from pvx.__main__ import main

if __name__ == "__main__":
    main()
EOF

mkdir -p dist
python3 -m zipapp "$BUILD_DIR" -o dist/core.pyz -p "/usr/bin/env python3"

echo "core.pyz gerado em dist/core.pyz"
