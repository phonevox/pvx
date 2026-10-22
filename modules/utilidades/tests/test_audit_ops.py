import os
import stat
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import audit_ops


class DefaultDestDirTest(unittest.TestCase):
    def test_lives_under_the_utilidades_module_dir(self):
        # PVX_HOME é isolado por teste via conftest.py (_isolated_pvx_home).
        from pvx import config as pvx_config

        expected = str(pvx_config.modules_dir() / "utilidades" / "scripts")
        self.assertEqual(audit_ops.default_dest_dir(), expected)


class DeployTest(unittest.TestCase):
    def test_writes_the_real_script_content_and_makes_it_executable(self):
        with TemporaryDirectory() as tmp:
            dest_dir = Path(tmp) / "scripts"
            path = audit_ops.deploy(str(dest_dir))

            content = Path(path).read_text()
            self.assertIn("#!/bin/bash", content)
            self.assertIn("audit.sh", content)
            self.assertTrue(path.endswith("audit.sh"))
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertTrue(mode & stat.S_IXUSR)

    def test_overwrites_an_existing_deploy_idempotently(self):
        with TemporaryDirectory() as tmp:
            first = audit_ops.deploy(tmp)
            second = audit_ops.deploy(tmp)
            self.assertEqual(first, second)
            self.assertTrue(Path(second).exists())


class SurvivesSysModulesEvictionTest(unittest.TestCase):
    # mesmo achado ao vivo do known_scripts.py do zabbix: loader.py do core
    # remove o módulo de sys.modules logo após importar o entrypoint -- deploy()
    # não pode depender de sys.modules[__name__] continuar existindo depois.
    def test_deploy_works_after_module_is_evicted_from_sys_modules(self):
        sys.modules.pop("audit_ops", None)
        with TemporaryDirectory() as tmp:
            path = audit_ops.deploy(tmp)
            self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
