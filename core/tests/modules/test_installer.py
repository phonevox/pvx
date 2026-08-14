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

    def test_registry_unreachable_raises_clean_error(self):
        with patch(
            "pvx.modules.installer.fetch_index",
            side_effect=urllib.error.URLError("nome não resolvido"),
        ):
            with self.assertRaises(RuntimeError):
                installer.install("dummy", "https://example.com/index.json")

    def test_uninstall_removes_module_directory(self):
        installed = Path(self._tmp.name) / "modules" / "dummy"
        installed.mkdir(parents=True)
        (installed / "module.pyz").write_bytes(b"fake")

        installer.uninstall("dummy")

        self.assertFalse(installed.exists())


if __name__ == "__main__":
    unittest.main()
