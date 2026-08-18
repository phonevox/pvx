import zipfile
from pathlib import Path


def extract_prefix(pyz_path, prefix, dest_dir):
    # o .pyz é um zip de verdade (PEP 441) -- não precisa de import, zipfile.ZipFile direto
    # já lê os assets estáticos (repos, control_panel) empacotados junto do código. Assets
    # nunca ficam soltos ao lado do .pyz no host instalado -- só module.pyz + manifest.json
    # chegam lá (ver installer.py), então é daqui de dentro que precisam vir.
    if not pyz_path or not Path(pyz_path).exists():
        return []

    extracted = []
    with zipfile.ZipFile(pyz_path) as zf:
        for name in zf.namelist():
            if not name.startswith(prefix + "/") or name.endswith("/"):
                continue
            rel = name[len(prefix) + 1:]
            dest = Path(dest_dir) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            extracted.append(str(dest))
    return extracted
