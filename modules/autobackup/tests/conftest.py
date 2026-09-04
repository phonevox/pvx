import os
import shutil
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _isolated_pvx_home():
    # nunca deixa um teste tocar o /etc/pvx real -- PVX_HOME sempre aponta
    # pra um tmpdir descartável, isolado por teste. Achado ao vivo: sem
    # isso, testes que não mockam config a fundo (ex.: comandos que logam
    # via get_module_logger) tentavam criar diretório de verdade em
    # /etc/pvx e quebravam com PermissionError fora de uma máquina de dev
    # rodando como root.
    tmp_dir = tempfile.mkdtemp(prefix="pvx-test-home-")
    old = os.environ.get("PVX_HOME")
    os.environ["PVX_HOME"] = tmp_dir
    try:
        yield tmp_dir
    finally:
        if old is None:
            os.environ.pop("PVX_HOME", None)
        else:
            os.environ["PVX_HOME"] = old
        shutil.rmtree(tmp_dir, ignore_errors=True)
