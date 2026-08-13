import os
import unittest
from pathlib import Path

from pvx import config


class ConfigPathsTest(unittest.TestCase):
    def setUp(self):
        self._old_home = os.environ.get("PVX_HOME")

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("PVX_HOME", None)
        else:
            os.environ["PVX_HOME"] = self._old_home

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


if __name__ == "__main__":
    unittest.main()
