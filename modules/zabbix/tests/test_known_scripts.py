import os
import stat
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import known_scripts


class CatalogTest(unittest.TestCase):
    def test_audit_is_registered_and_needs_root(self):
        entry = known_scripts.CATALOG["audit"]
        self.assertEqual(entry["filename"], "audit.sh")
        self.assertTrue(entry["needs_root"])


class DeployTest(unittest.TestCase):
    def test_writes_the_real_script_content_and_makes_it_executable(self):
        with TemporaryDirectory() as tmp:
            dest_dir = Path(tmp) / "pvx-scripts.d"
            path = known_scripts.deploy(str(dest_dir), "audit")

            content = Path(path).read_text()
            self.assertIn("#!/bin/bash", content)
            self.assertIn("audit.sh", content)  # docstring do proprio script se auto-referencia
            self.assertTrue(path.endswith("audit.sh"))
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertTrue(mode & stat.S_IXUSR)

    def test_raises_for_unknown_key(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(KeyError):
                known_scripts.deploy(tmp, "does-not-exist")


class RemoveDeployedTest(unittest.TestCase):
    def test_removes_the_deployed_file(self):
        with TemporaryDirectory() as tmp:
            path = known_scripts.deploy(tmp, "audit")
            known_scripts.remove_deployed(tmp, "audit")
            self.assertFalse(Path(path).exists())

    def test_is_a_no_op_when_file_never_existed(self):
        with TemporaryDirectory() as tmp:
            known_scripts.remove_deployed(tmp, "audit")


class SurvivesSysModulesEvictionTest(unittest.TestCase):
    # achado ao vivo: loader.py do core remove o módulo de sys.modules logo
    # após importar o entrypoint (evita colisão de nome entre módulos
    # diferentes) -- deploy() não pode depender de sys.modules[__name__]
    # continuar existindo depois (KeyError em produção, testes locais não
    # pegam porque pytest nunca faz essa limpeza).
    def test_deploy_works_after_module_is_evicted_from_sys_modules(self):
        sys.modules.pop("known_scripts", None)
        with TemporaryDirectory() as tmp:
            path = known_scripts.deploy(tmp, "audit")
            self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
