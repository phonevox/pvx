#!/bin/sh
set -e

cd "$(dirname "$0")"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

# módulo tem várias unidades (system_info.py, metadata.py, config.py, ...) que se
# importam por nome de topo entre si -- todas precisam ir pra raiz do .pyz,
# não só o entrypoint.
cp src/*.py "$BUILD_DIR/"
mv "$BUILD_DIR/main.py" "$BUILD_DIR/module.py"

# scripts/*.sh (known_scripts.CATALOG) viajam dentro do .pyz, na mesma
# estrutura relativa que known_scripts.py espera achar em dev (scripts/ ao
# lado de src/) -- get_data() lê tanto do zip quanto do disco solto.
mkdir -p "$BUILD_DIR/scripts"
cp scripts/*.sh "$BUILD_DIR/scripts/"

# zipapp exige um entry point -- module.pyz nunca é rodado direto (o
# loader importa "module" via zipimport), então é só um placeholder.
echo "from module import cli" > "$BUILD_DIR/__main__.py"

mkdir -p dist
python3 -m zipapp "$BUILD_DIR" -o dist/module.pyz

# manifest de instalação usa entrypoint "module:cli" (o .pyz contém
# module.py) -- diferente do manifest.json fonte, que usa "main:cli"
# (aponta pra src/main.py, layout de código-fonte).
python3 -c "
import hashlib, json
manifest = json.load(open('manifest.json'))
manifest['entrypoint'] = 'module:cli'
manifest['checksum_sha256'] = hashlib.sha256(open('dist/module.pyz', 'rb').read()).hexdigest()
json.dump(manifest, open('dist/manifest.json', 'w'), indent=2)
"

echo "module.pyz + manifest.json gerados em dist/"
