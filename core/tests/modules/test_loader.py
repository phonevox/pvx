import json
import shutil
import subprocess
import sys
import zipapp
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

    def test_sibling_helper_files_dont_leak_between_two_pyz_modules(self):
        # bug real: dois módulos instalados que cada um tem seu próprio
        # helper.py (mesmo nome de arquivo, conteúdo diferente) -- sem
        # limpar TODO nome novo que entrou em sys.modules (não só o
        # entrypoint "module"), o segundo módulo carregado herdava o
        # helper.py cacheado do primeiro.
        def build_pyz(build_dir, helper_value, name):
            build_dir.mkdir(parents=True)
            (build_dir / "helper.py").write_text(f'VALUE = "{helper_value}"\n')
            (build_dir / "module.py").write_text(f"""
from pvx.modules.base import PvxModule
import helper


class Mod(PvxModule):
    name = helper.VALUE
    version = "0.1.0"

    def cli_group(self):
        import click

        @click.group()
        def group():
            pass

        return group


cli = Mod()
""")
            (build_dir / "__main__.py").write_text("from module import cli\n")
            pyz_path = build_dir.parent / f"{name}.pyz"
            zipapp.create_archive(build_dir, pyz_path)
            return pyz_path

        with TemporaryDirectory() as tmp:
            build_root = Path(tmp) / "build"
            first_pyz = build_pyz(build_root / "first_src", "first-value", "first")
            second_pyz = build_pyz(build_root / "second_src", "second-value", "second")

            modules_dir = Path(tmp) / "modules"
            for mod_name, pyz_path in (("first", first_pyz), ("second", second_pyz)):
                mod_dir = modules_dir / mod_name
                mod_dir.mkdir(parents=True)
                (mod_dir / "manifest.json").write_text(json.dumps({
                    "name": mod_name, "version": "0.1.0", "entrypoint": "module:cli",
                }))
                shutil.copy(pyz_path, mod_dir / "module.pyz")

            modules = discover(modules_dir)

        self.assertEqual(modules["first"].name, "first-value")
        self.assertEqual(modules["second"].name, "second-value")

    def test_rediscovers_a_module_after_its_pyz_is_replaced_in_place(self):
        # bug real: `pvx modules update` sobrescreve o mesmo module.pyz (mesmo
        # path) enquanto o menu interativo (processo longo, nunca reinicia)
        # continua rodando. zipimport cacheia o zipimporter (índice interno do
        # .zip) por path pra sempre -- sem invalidar isso, o discover() de
        # depois do update usa o índice do .zip ANTIGO sobre o arquivo NOVO
        # (offsets não batem mais) e crasha, em vez de enxergar a versão nova.
        def build_pyz(build_dir, version, pyz_path):
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "module.py").write_text(f"""
from pvx.modules.base import PvxModule


class Mod(PvxModule):
    name = "dummy"
    version = "{version}"

    def cli_group(self):
        import click

        @click.group()
        def group():
            pass

        return group


cli = Mod()
""")
            (build_dir / "__main__.py").write_text("from module import cli\n")
            if pyz_path.exists():
                pyz_path.unlink()
            zipapp.create_archive(build_dir, pyz_path)
            shutil.rmtree(build_dir)

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mod_dir = tmp_path / "modules" / "dummy"
            mod_dir.mkdir(parents=True)
            (mod_dir / "manifest.json").write_text(json.dumps({
                "name": "dummy", "version": "0.1.0", "entrypoint": "module:cli",
            }))
            pyz_path = mod_dir / "module.pyz"

            build_pyz(tmp_path / "build_v1", "0.1.0", pyz_path)
            first = discover(tmp_path / "modules")
            self.assertEqual(first["dummy"].version, "0.1.0")

            # update de verdade: mesmo path, conteúdo (tamanho/índice) diferente.
            build_pyz(tmp_path / "build_v2", "0.2.0-com-bastante-conteudo-a-mais", pyz_path)
            second = discover(tmp_path / "modules")
            self.assertEqual(second["dummy"].version, "0.2.0-com-bastante-conteudo-a-mais")

    def test_shared_pvx_submodules_are_never_evicted_from_sys_modules(self):
        # achado ao vivo (produção): a limpeza de sys.modules no fim de cada
        # load (pra evitar colisão entre módulos com arquivo interno de
        # mesmo nome, ex. "module"/"helper") também removia qualquer nome
        # "pvx.*" que por acaso tivesse entrado durante aquele load
        # específico (ex.: pvx.modules.base, se ainda não tivesse sido
        # importado antes). Inofensivo enquanto core.pyz nunca mudava em
        # disco no meio do processo -- mas depois de um self-update
        # (substitui o arquivo), reimportar um nome "pvx.*" evictado reusa o
        # zipimporter cacheado pro path do core.pyz com offsets da versão
        # ANTIGA e crasha com "bad local file header" (ex.: "atualizar >
        # tudo", que roda self-update e depois atualiza módulos na mesma
        # sessão longa do menu interativo).
        with TemporaryDirectory() as tmp:
            build_dir = Path(tmp) / "build"
            build_dir.mkdir()
            (build_dir / "module.py").write_text("""
import sys
from pvx.modules.base import PvxModule

sys.modules["pvx.fake_shared_submodule"] = sys.modules[__name__]


class Mod(PvxModule):
    name = "leaks-pvx-name"
    version = "0.1.0"

    def cli_group(self):
        import click

        @click.group()
        def group():
            pass

        return group


cli = Mod()
""")
            (build_dir / "__main__.py").write_text("from module import cli\n")
            pyz_path = Path(tmp) / "leaks.pyz"
            zipapp.create_archive(build_dir, pyz_path)

            module_dir = self.modules_dir / "leaks-pvx-name"
            module_dir.mkdir()
            (module_dir / "manifest.json").write_text(json.dumps({
                "name": "leaks-pvx-name", "version": "0.1.0", "entrypoint": "module:cli",
            }))
            shutil.copy(pyz_path, module_dir / "module.pyz")

            try:
                discover(self.modules_dir)
                self.assertIn("pvx.fake_shared_submodule", sys.modules)
            finally:
                sys.modules.pop("pvx.fake_shared_submodule", None)

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
