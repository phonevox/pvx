import hashlib
import json
import subprocess
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]


class BuildShTest(unittest.TestCase):
    def test_manifest_checksum_matches_built_pyz(self):
        result = subprocess.run(
            ["sh", "build.sh"], cwd=MODULE_DIR, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        pyz_bytes = (MODULE_DIR / "dist" / "module.pyz").read_bytes()
        manifest = json.loads((MODULE_DIR / "dist" / "manifest.json").read_text())

        self.assertEqual(manifest["checksum_sha256"], hashlib.sha256(pyz_bytes).hexdigest())
        self.assertEqual(manifest["entrypoint"], "module:cli")


if __name__ == "__main__":
    unittest.main()
