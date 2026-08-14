import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pvx import config


class ConfigPathsTest(unittest.TestCase):
    def setUp(self):
        self._old_home = os.environ.get("PVX_HOME")

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("PVX_HOME", None)
        else:
            os.environ["PVX_HOME"] = self._old_home
        os.environ.pop("PVX_REGISTRY_URL", None)

    def test_pvx_home_respects_env_override(self):
        os.environ["PVX_HOME"] = "/tmp/fake-pvx-home"
        self.assertEqual(config.pvx_home(), Path("/tmp/fake-pvx-home"))

    def test_pvx_home_defaults_under_user_home(self):
        os.environ.pop("PVX_HOME", None)
        self.assertEqual(config.pvx_home(), Path.home() / ".pvx")

    def test_subpaths_are_relative_to_pvx_home(self):
        os.environ["PVX_HOME"] = "/tmp/fake-pvx-home"
        base = Path("/tmp/fake-pvx-home")
        self.assertEqual(config.bin_dir(), base / "bin")
        self.assertEqual(config.modules_dir(), base / "modules")
        self.assertEqual(config.logs_dir(), base / "logs")
        self.assertEqual(config.registry_cache_path(), base / "registry.json")
        self.assertEqual(config.config_file_path(), base / "config.json")

    def test_registry_index_url_respects_env_override(self):
        os.environ["PVX_REGISTRY_URL"] = "https://example.com/index.json"
        self.assertEqual(config.registry_index_url(), "https://example.com/index.json")


class ThemeConfigTest(unittest.TestCase):
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

    def test_theme_name_defaults_to_azul(self):
        self.assertEqual(config.get_theme_name(), "azul")

    def test_set_theme_name_persists_and_is_read_back(self):
        config.set_theme_name("verde")
        self.assertEqual(config.get_theme_name(), "verde")

    def test_set_theme_name_preserves_other_config_keys(self):
        config.write_config({"outra_chave": 123})
        config.set_theme_name("roxo")
        data = config.read_config()
        self.assertEqual(data["outra_chave"], 123)
        self.assertEqual(data["theme"], "roxo")


if __name__ == "__main__":
    unittest.main()
