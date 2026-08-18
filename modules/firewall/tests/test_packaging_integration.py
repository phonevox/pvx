import subprocess
import sys
import tempfile
import unittest
import zipapp
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CORE_DIR = Path(__file__).resolve().parents[3] / "core"


def _build_pyz(dest_dir):
    build_dir = Path(dest_dir) / "build"
    build_dir.mkdir()
    for py_file in SRC_DIR.glob("*.py"):
        (build_dir / py_file.name).write_text(py_file.read_text())
    (build_dir / "main.py").rename(build_dir / "module.py")
    (build_dir / "__main__.py").write_text("from module import cli\n")

    pyz_path = Path(dest_dir) / "module.pyz"
    zipapp.create_archive(build_dir, pyz_path)
    return pyz_path


# roda num subprocesso Python limpo -- se rodasse no processo do próprio
# pytest, "validators"/"iptables_engine" já estariam em sys.modules (outros
# arquivos de teste importam por nome de topo), mascarando o bug: um import
# lazy (dentro da função) só resolve enquanto o .pyz do módulo ainda está no
# sys.path, janela que fecha assim que o loader termina de carregar.
_SCRIPT = """
import sys
sys.path.insert(0, {core_dir!r})
from pvx.modules.loader import _load_from_pyz

from unittest.mock import patch, MagicMock

module = _load_from_pyz({pyz_path!r}, "module")
with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="")):
    module.sync_module.iptables_engine.sync(
        ip_accept=[], ip_deny=[], port_accept=[("5060/udp", "SIP")], port_deny=[], failsafe_ip=None,
    )
print("OK")
"""


class PackagedSyncTest(unittest.TestCase):
    # achado ao vivo na VPS: `pvx firewall sync` falhava com
    # `No module named 'validators'`, mesmo com todos os testes unitários
    # verdes -- causa raiz era `iptables_engine.sync()`/`firewalld_engine.sync()`
    # importando `validators` dentro da própria função em vez de no topo do
    # arquivo (único cross-import lazy do módulo; todo o resto já era eager).
    def test_sync_resolves_cross_module_import_after_the_pyz_leaves_sys_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            pyz_path = _build_pyz(tmp)
            script = _SCRIPT.format(core_dir=str(CORE_DIR), pyz_path=str(pyz_path))
            result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
