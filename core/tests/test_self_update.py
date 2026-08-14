import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pvx import self_update


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


if __name__ == "__main__":
    unittest.main()
