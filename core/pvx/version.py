import re
import zipfile

__version__ = "0.2.43"


def installed_version():
    # __version__ (valor em memória) fica preso na versão antiga num
    # processo longo (menu interativo) depois de um self-update -- zipimport
    # não recarrega isso de forma confiável. Lê o .pyz em disco direto via
    # zipfile (nunca zipimport/sys.modules), sempre a versão real atual.
    from pvx import config

    try:
        with zipfile.ZipFile(config.core_lib_path()) as archive:
            content = archive.read("pvx/version.py").decode()
    except (OSError, KeyError, zipfile.BadZipFile):
        return __version__  # dev/teste: "pvx" roda de fonte, não de .pyz

    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    return match.group(1) if match else __version__
