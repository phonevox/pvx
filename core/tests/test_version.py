import unittest

from pvx import version


class VersionTest(unittest.TestCase):
    def test_version_is_semver_string(self):
        self.assertRegex(version.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
