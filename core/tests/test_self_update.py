import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pvx import config, self_update


class SelfUpdateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._lib_path = Path(self._tmp.name) / "core.pyz"
        self._old_lib = os.environ.get("PVX_CORE_LIB_PATH")
        self._old_core_url = os.environ.get("PVX_CORE_URL")
        self._old_manifest_url = os.environ.get("PVX_CORE_MANIFEST_URL")
        os.environ["PVX_CORE_LIB_PATH"] = str(self._lib_path)

    def tearDown(self):
        for key, old in [
            ("PVX_CORE_LIB_PATH", self._old_lib),
            ("PVX_CORE_URL", self._old_core_url),
            ("PVX_CORE_MANIFEST_URL", self._old_manifest_url),
        ]:
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        self._tmp.cleanup()

    def _publish_fake_release(self, source_dir, core_bytes, checksum):
        (source_dir / "core.pyz").write_bytes(core_bytes)
        (source_dir / "core-manifest.json").write_text(json.dumps({
            "version": "0.2.0",
            "checksum_sha256": checksum,
        }))
        os.environ["PVX_CORE_URL"] = f"file://{source_dir}/core.pyz"
        os.environ["PVX_CORE_MANIFEST_URL"] = f"file://{source_dir}/core-manifest.json"

    def test_updates_core_pyz_when_checksum_matches(self):
        new_core_bytes = b"fake core.pyz content v2"
        with TemporaryDirectory() as source_tmp:
            self._publish_fake_release(
                Path(source_tmp), new_core_bytes, hashlib.sha256(new_core_bytes).hexdigest()
            )
            version = self_update.self_update()

        self.assertEqual(version, "0.2.0")
        self.assertEqual(self._lib_path.read_bytes(), new_core_bytes)

    def test_checksum_mismatch_raises_and_does_not_replace(self):
        self._lib_path.write_bytes(b"old core.pyz content")

        with TemporaryDirectory() as source_tmp:
            self._publish_fake_release(Path(source_tmp), b"tampered content", "sha256-errado")

            with self.assertRaises(ValueError):
                self_update.self_update()

        self.assertEqual(self._lib_path.read_bytes(), b"old core.pyz content")


class UninstallTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        base = Path(self._tmp.name)
        self._lib_path = base / "lib" / "core.pyz"
        self._bin_path = base / "bin" / "pvx"
        self._symlink_path = base / "usrbin" / "pvx"
        for path in (self._lib_path, self._bin_path, self._symlink_path):
            path.parent.mkdir(parents=True)
            path.write_text("conteúdo fake")

        self._old_env = {}
        overrides = {
            "PVX_CORE_LIB_PATH": str(self._lib_path),
            "PVX_BIN_PATH": str(self._bin_path),
            "PVX_BIN_SYMLINK_PATH": str(self._symlink_path),
        }
        for key, value in overrides.items():
            self._old_env[key] = os.environ.get(key)
            os.environ[key] = value

    def tearDown(self):
        for key, old in self._old_env.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        os.environ.pop("PVX_HOME", None)
        self._tmp.cleanup()

    def test_removes_core_lib_and_wrapper_and_symlink(self):
        self_update.uninstall()
        self.assertFalse(self._lib_path.exists())
        self.assertFalse(self._lib_path.parent.exists())
        self.assertFalse(self._bin_path.exists())
        self.assertFalse(self._symlink_path.exists())

    def test_missing_files_do_not_raise(self):
        self._lib_path.unlink()
        self._bin_path.unlink()
        self._symlink_path.unlink()
        self_update.uninstall()

    def test_purge_also_removes_pvx_home(self):
        os.environ["PVX_HOME"] = str(Path(self._tmp.name) / "home")
        home = config.pvx_home()
        (home / "modules").mkdir(parents=True)

        self_update.uninstall(purge=True)

        self.assertFalse(home.exists())

    def test_without_purge_keeps_pvx_home(self):
        os.environ["PVX_HOME"] = str(Path(self._tmp.name) / "home")
        home = config.pvx_home()
        home.mkdir(parents=True)

        self_update.uninstall(purge=False)

        self.assertTrue(home.exists())


if __name__ == "__main__":
    unittest.main()
