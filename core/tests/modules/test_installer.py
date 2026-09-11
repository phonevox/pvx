import hashlib
import json
import os
import subprocess
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pvx.modules import installer


class InstallTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._old_home = os.environ.get("PVX_HOME")
        os.environ["PVX_HOME"] = self._tmp.name

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("PVX_HOME", None)
        else:
            os.environ["PVX_HOME"] = self._old_home
        self._tmp.cleanup()

    def _build_fake_registry(self, registry_dir):
        dummy_dir = Path(__file__).resolve().parents[3] / "modules" / "dummy"
        build = subprocess.run(
            ["sh", "build.sh"], cwd=dummy_dir, capture_output=True, text=True, timeout=60,
        )
        assert build.returncode == 0, build.stderr

        pyz_bytes = (dummy_dir / "dist" / "module.pyz").read_bytes()
        manifest = json.loads((dummy_dir / "dist" / "manifest.json").read_text())

        (registry_dir / "dummy-0.1.0.pyz").write_bytes(pyz_bytes)
        (registry_dir / "index.json").write_text(json.dumps({
            "registry_version": 1,
            "modules": [{
                "name": "dummy",
                "latest": "0.1.0",
                "versions": ["0.1.0"],
                "url_template": f"file://{registry_dir}/{{name}}-{{version}}.pyz",
                "manifest_url": f"file://{registry_dir}/manifest.json",
            }],
        }))
        return manifest, pyz_bytes

    def test_installs_module_when_checksum_matches(self):
        with TemporaryDirectory() as registry_tmp:
            registry_dir = Path(registry_tmp)
            manifest, pyz_bytes = self._build_fake_registry(registry_dir)
            manifest["checksum_sha256"] = hashlib.sha256(pyz_bytes).hexdigest()
            (registry_dir / "manifest.json").write_text(json.dumps(manifest))

            installer.install("dummy", f"file://{registry_dir}/index.json")

        installed = Path(self._tmp.name) / "modules" / "dummy"
        self.assertTrue((installed / "module.pyz").exists())
        self.assertTrue((installed / "manifest.json").exists())

    def test_checksum_mismatch_raises_and_installs_nothing(self):
        with TemporaryDirectory() as registry_tmp:
            registry_dir = Path(registry_tmp)
            manifest, _ = self._build_fake_registry(registry_dir)
            manifest["checksum_sha256"] = "sha256-errado"
            (registry_dir / "manifest.json").write_text(json.dumps(manifest))

            with self.assertRaises(ValueError):
                installer.install("dummy", f"file://{registry_dir}/index.json")

        installed = Path(self._tmp.name) / "modules" / "dummy"
        self.assertFalse(installed.exists())

    @patch("pvx.modules.installer.update_check.clear_cache")
    def test_install_clears_the_update_check_cache(self, mock_clear):
        # achado ao vivo: instalar/atualizar um módulo manualmente na CLI
        # direta (`pvx module install`) não invalidava esse cache -- só o
        # loop de `module update --all` fazia isso, num ponto separado.
        with TemporaryDirectory() as registry_tmp:
            registry_dir = Path(registry_tmp)
            manifest, pyz_bytes = self._build_fake_registry(registry_dir)
            manifest["checksum_sha256"] = hashlib.sha256(pyz_bytes).hexdigest()
            (registry_dir / "manifest.json").write_text(json.dumps(manifest))

            installer.install("dummy", f"file://{registry_dir}/index.json")

        mock_clear.assert_called_once()

    @patch("pvx.modules.installer.update_check.clear_cache")
    def test_failed_install_does_not_clear_the_cache(self, mock_clear):
        with TemporaryDirectory() as registry_tmp:
            registry_dir = Path(registry_tmp)
            manifest, _ = self._build_fake_registry(registry_dir)
            manifest["checksum_sha256"] = "sha256-errado"
            (registry_dir / "manifest.json").write_text(json.dumps(manifest))

            with self.assertRaises(ValueError):
                installer.install("dummy", f"file://{registry_dir}/index.json")

        mock_clear.assert_not_called()

    def test_registry_unreachable_raises_clean_error(self):
        with patch(
            "pvx.modules.installer.fetch_index",
            side_effect=urllib.error.URLError("nome não resolvido"),
        ):
            with self.assertRaises(RuntimeError):
                installer.install("dummy", "https://example.com/index.json")

    @patch("pvx.modules.installer.pvx_version.__version__", "0.1.0")
    def test_raises_when_module_requires_a_newer_core_than_installed(self):
        # achado ao vivo: um módulo atualizado sozinho (registry independente
        # do core) crashou em produção com AttributeError -- usava uma
        # função de widgets que só existe numa versão de core mais nova.
        # min_pvx_version existe no manifest desde sempre, mas nada aqui
        # nunca checava -- só documentação morta.
        with TemporaryDirectory() as registry_tmp:
            registry_dir = Path(registry_tmp)
            manifest, pyz_bytes = self._build_fake_registry(registry_dir)
            manifest["checksum_sha256"] = hashlib.sha256(pyz_bytes).hexdigest()
            manifest["min_pvx_version"] = "9.9.9"
            (registry_dir / "manifest.json").write_text(json.dumps(manifest))

            with self.assertRaisesRegex(RuntimeError, "9.9.9"):
                installer.install("dummy", f"file://{registry_dir}/index.json")

        installed = Path(self._tmp.name) / "modules" / "dummy"
        self.assertFalse(installed.exists())

    @patch("pvx.modules.installer.pvx_version.__version__", "9.9.9")
    def test_installs_normally_when_core_satisfies_min_pvx_version(self):
        with TemporaryDirectory() as registry_tmp:
            registry_dir = Path(registry_tmp)
            manifest, pyz_bytes = self._build_fake_registry(registry_dir)
            manifest["checksum_sha256"] = hashlib.sha256(pyz_bytes).hexdigest()
            manifest["min_pvx_version"] = "0.1.0"
            (registry_dir / "manifest.json").write_text(json.dumps(manifest))

            installer.install("dummy", f"file://{registry_dir}/index.json")

        installed = Path(self._tmp.name) / "modules" / "dummy"
        self.assertTrue((installed / "module.pyz").exists())

    def test_installs_when_min_pvx_version_is_missing_or_unparseable(self):
        with TemporaryDirectory() as registry_tmp:
            registry_dir = Path(registry_tmp)
            manifest, pyz_bytes = self._build_fake_registry(registry_dir)
            manifest["checksum_sha256"] = hashlib.sha256(pyz_bytes).hexdigest()
            manifest["min_pvx_version"] = "não-é-uma-versão"
            (registry_dir / "manifest.json").write_text(json.dumps(manifest))

            installer.install("dummy", f"file://{registry_dir}/index.json")

        installed = Path(self._tmp.name) / "modules" / "dummy"
        self.assertTrue((installed / "module.pyz").exists())

    def test_unknown_module_raises_clean_error(self):
        with TemporaryDirectory() as registry_tmp:
            registry_dir = Path(registry_tmp)
            self._build_fake_registry(registry_dir)

            with self.assertRaises(ValueError):
                installer.install("inexistente", f"file://{registry_dir}/index.json")

    def test_uninstall_removes_module_directory(self):
        installed = Path(self._tmp.name) / "modules" / "dummy"
        installed.mkdir(parents=True)
        (installed / "module.pyz").write_bytes(b"fake")

        installer.uninstall("dummy")

        self.assertFalse(installed.exists())

    def test_uninstall_of_a_module_never_installed_does_not_raise(self):
        installer.uninstall("nao-existe")

    def test_uninstall_raises_when_the_directory_survives_removal(self):
        # achado ao vivo: rmtree(ignore_errors=True) escondia falha real (ex.:
        # arquivo com permissão travada) -- `pvx module uninstall` reportava
        # "removido" mesmo sem remover nada, e o módulo reaparecia no próximo
        # `pvx module list`/menu sem explicação nenhuma.
        installed = Path(self._tmp.name) / "modules" / "dummy"
        installed.mkdir(parents=True)
        with patch("pvx.modules.installer.shutil.rmtree"):
            with self.assertRaises(RuntimeError):
                installer.uninstall("dummy")

    @patch("pvx.modules.installer.update_check.clear_cache")
    def test_uninstall_clears_the_update_check_cache(self, mock_clear):
        # achado ao vivo: remover um módulo manualmente (CLI ou menu) não
        # invalidava o cache do aviso de update -- o banner continuava
        # dizendo "atualização disponível" pra um módulo que nem existia
        # mais, até o TTL de 6h expirar sozinho.
        installed = Path(self._tmp.name) / "modules" / "dummy"
        installed.mkdir(parents=True)

        installer.uninstall("dummy")

        mock_clear.assert_called_once()

    @patch("pvx.modules.installer.update_check.clear_cache")
    def test_uninstall_of_a_never_installed_module_still_clears_the_cache(self, mock_clear):
        installer.uninstall("nao-existe")
        mock_clear.assert_called_once()


if __name__ == "__main__":
    unittest.main()
