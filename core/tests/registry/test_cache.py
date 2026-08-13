import os
import unittest
from tempfile import TemporaryDirectory

from pvx.registry import cache


class CacheTest(unittest.TestCase):
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

    def test_save_then_load_roundtrips(self):
        cache.save({"registry_version": 1, "modules": []})
        self.assertEqual(cache.load(), {"registry_version": 1, "modules": []})

    def test_load_without_cache_returns_none(self):
        self.assertIsNone(cache.load())


if __name__ == "__main__":
    unittest.main()
