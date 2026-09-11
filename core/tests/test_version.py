import os
import unittest
import zipapp
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pvx import version


class VersionTest(unittest.TestCase):
    def test_version_is_semver_string(self):
        self.assertRegex(version.__version__, r"^\d+\.\d+\.\d+$")


class InstalledVersionTest(unittest.TestCase):
    def _build_fake_core_pyz(self, build_dir, pyz_path, version_string):
        pvx_dir = build_dir / "pvx"
        pvx_dir.mkdir(parents=True)
        (pvx_dir / "__init__.py").write_text("")
        (pvx_dir / "version.py").write_text(f'__version__ = "{version_string}"\n')
        (build_dir / "__main__.py").write_text("")
        zipapp.create_archive(build_dir, pyz_path)

    def test_reads_the_version_straight_from_the_pyz_on_disk(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pyz_path = tmp_path / "core.pyz"
            self._build_fake_core_pyz(tmp_path / "build", pyz_path, "9.9.9")

            old = os.environ.get("PVX_CORE_LIB_PATH")
            os.environ["PVX_CORE_LIB_PATH"] = str(pyz_path)
            try:
                self.assertEqual(version.installed_version(), "9.9.9")
            finally:
                if old is None:
                    os.environ.pop("PVX_CORE_LIB_PATH", None)
                else:
                    os.environ["PVX_CORE_LIB_PATH"] = old

    def test_falls_back_to_the_in_memory_constant_when_not_running_from_a_zip(self):
        # dev/teste: "pvx" roda de fonte (diretório de verdade), não de
        # dentro de um .pyz -- nunca deve levantar, só recorrer ao valor
        # já importado normalmente.
        with patch("pvx.config.core_lib_path", return_value=Path("/does/not/exist.pyz")):
            self.assertEqual(version.installed_version(), version.__version__)


if __name__ == "__main__":
    unittest.main()
