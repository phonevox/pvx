import os
import shutil
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _isolated_pvx_home():
    # nunca deixa um teste tocar o /etc/pvx real -- ver mesma fixture nos
    # outros módulos.
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
