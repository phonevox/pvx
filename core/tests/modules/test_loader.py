import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pvx.modules.loader import discover

# entrypoint "module:cli" -> loader pega o atributo `cli` (instância de PvxModule).
DUMMY_MODULE_SOURCE = """
from pvx.modules.base import PvxModule


class DummyModule(PvxModule):
    name = "dummy"
    version = "0.1.0"

    def cli_group(self):
        import click

        @click.group()
        def group():
            pass

        @group.command()
        def hello():
            click.echo("hello from dummy")

        return group


cli = DummyModule()
"""

# mesmo nome de arquivo (module.py) que o de cima -- pega colisão de import.
OTHER_MODULE_SOURCE = """
from pvx.modules.base import PvxModule


class OtherModule(PvxModule):
    name = "other"
    version = "0.1.0"

    def cli_group(self):
        import click

        @click.group()
        def group():
            pass

        return group


cli = OtherModule()
"""


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.modules_dir = Path(self._tmp.name)
        dummy_dir = self.modules_dir / "dummy"
        dummy_dir.mkdir()
        (dummy_dir / "manifest.json").write_text(json.dumps({
            "name": "dummy",
            "version": "0.1.0",
            "entrypoint": "module:cli",
        }))
        (dummy_dir / "module.py").write_text(DUMMY_MODULE_SOURCE)

    def tearDown(self):
        self._tmp.cleanup()

    def test_discovers_and_imports_installed_module(self):
        modules = discover(self.modules_dir)
        self.assertIn("dummy", modules)
        self.assertEqual(modules["dummy"].name, "dummy")

    def test_missing_modules_dir_returns_empty(self):
        missing = self.modules_dir / "does-not-exist"
        self.assertEqual(discover(missing), {})

    def test_two_modules_both_named_module_py_dont_clobber_each_other(self):
        other_dir = self.modules_dir / "other"
        other_dir.mkdir()
        (other_dir / "manifest.json").write_text(json.dumps({
            "name": "other",
            "version": "0.1.0",
            "entrypoint": "module:cli",
        }))
        (other_dir / "module.py").write_text(OTHER_MODULE_SOURCE)

        modules = discover(self.modules_dir)

        self.assertEqual(modules["dummy"].name, "dummy")
        self.assertEqual(modules["other"].name, "other")

    def test_discovers_real_built_module_pyz(self):
        dummy_dir = Path(__file__).resolve().parents[3] / "modules" / "dummy"
        build = subprocess.run(
            ["sh", "build.sh"], cwd=dummy_dir, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(build.returncode, 0, msg=build.stderr)

        with TemporaryDirectory() as tmp:
            modules_dir = Path(tmp)
            installed_dir = modules_dir / "dummy"
            installed_dir.mkdir()
            shutil.copy(dummy_dir / "dist" / "manifest.json", installed_dir / "manifest.json")
            shutil.copy(dummy_dir / "dist" / "module.pyz", installed_dir / "module.pyz")

            modules = discover(modules_dir)

        self.assertEqual(modules["dummy"].name, "dummy")


if __name__ == "__main__":
    unittest.main()
