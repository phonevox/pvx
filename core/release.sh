#!/bin/sh
# Build de release oficial do core -- wrapper em cima de build.sh que sempre
# seta PVX_RELEASE_BUILD=1 (sem stamp de branch/commit) e já gera o
# core-manifest.json. Achado ao vivo: releases cortadas com "sh build.sh" cru
# saiam com stamp de "nightly" mesmo sendo a release oficial, porque
# PVX_RELEASE_BUILD é fácil de esquecer numa chamada manual -- aqui não tem
# como esquecer.
#
# NÃO publica nada sozinho (gh release create fica de fora de propósito --
# publicar é ação pública/irreversível, sempre um passo explícito à parte).
# Uso: sh release.sh
set -e

cd "$(dirname "$0")"

VERSION=$(python3 -c "
import re
print(re.search(r'\"([0-9.]+)\"', open('pvx/version.py').read()).group(1))
")

PVX_RELEASE_BUILD=1 sh build.sh

python3 -c "
import hashlib, json, sys, zipimport

data = open('dist/core.pyz', 'rb').read()
manifest = {'version': '$VERSION', 'checksum_sha256': hashlib.sha256(data).hexdigest()}
json.dump(manifest, open('dist/core-manifest.json', 'w'), indent=2)

# nunca mais mandar um build com stamp pra release -- se isso disparar, o
# build.sh (ou essa env var) quebrou, não é seguro publicar.
try:
    zipimport.zipimporter('dist/core.pyz').load_module('pvx._build_stamp')
    sys.exit('ERRO: dist/core.pyz tem _build_stamp -- NÃO publicar, PVX_RELEASE_BUILD falhou.')
except ImportError:
    pass

print(f'release v{manifest[\"version\"]} pronta -- dist/core.pyz + dist/core-manifest.json (limpo, sem stamp)')
"

echo ""
echo "pra publicar:"
echo "  gh release create v$VERSION dist/core.pyz dist/core-manifest.json --repo phonevox/pvx --target main --title v$VERSION --notes \"...\""
