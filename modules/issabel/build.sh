#!/bin/sh
set -e

cd "$(dirname "$0")"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

# backup_ops.py é importado por nome de topo (não relativo) -- precisa ir
# pra raiz do .pyz junto com o entrypoint, igual o netinstall.
cp src/*.py "$BUILD_DIR/"
mv "$BUILD_DIR/main.py" "$BUILD_DIR/module.py"

# scripts/*.sh (audit_ops.py) viajam dentro do .pyz, na mesma estrutura
# relativa que audit_ops.py espera achar em dev (scripts/ ao lado de src/) --
# get_data() lê tanto do zip quanto do disco solto (mesmo padrão do utilidades).
mkdir -p "$BUILD_DIR/scripts"
cp scripts/*.sh "$BUILD_DIR/scripts/"

echo "from module import cli" > "$BUILD_DIR/__main__.py"

mkdir -p dist
python3 -m zipapp "$BUILD_DIR" -o dist/module.pyz

python3 -c "
import hashlib, json
manifest = json.load(open('manifest.json'))
manifest['entrypoint'] = 'module:cli'
manifest['checksum_sha256'] = hashlib.sha256(open('dist/module.pyz', 'rb').read()).hexdigest()
json.dump(manifest, open('dist/manifest.json', 'w'), indent=2)
"

echo "module.pyz + manifest.json gerados em dist/"
