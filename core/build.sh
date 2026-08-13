#!/bin/sh
set -e

cd "$(dirname "$0")"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cp -r pvx "$BUILD_DIR/"
python3 -m pip install --quiet --target "$BUILD_DIR" click questionary rich

cat > "$BUILD_DIR/__main__.py" <<'EOF'
from pvx.__main__ import main

if __name__ == "__main__":
    main()
EOF

mkdir -p dist
python3 -m zipapp "$BUILD_DIR" -o dist/core.pyz -p "/usr/bin/env python3"

echo "core.pyz gerado em dist/core.pyz"
