import unittest
from unittest.mock import patch

from pvx import build_info


class DescribeTest(unittest.TestCase):
    def test_returns_none_when_no_branch_info(self):
        with patch.object(build_info, "BRANCH", None):
            self.assertIsNone(build_info.describe())

    def test_dev_branch_is_labeled_nightly(self):
        with patch.object(build_info, "BRANCH", "dev"), patch.object(
            build_info, "COMMIT", "a1b2c3d"
        ):
            self.assertEqual(build_info.describe(), "nightly, a1b2c3d")

    def test_other_branch_is_labeled_local(self):
        with patch.object(build_info, "BRANCH", "main"), patch.object(
            build_info, "COMMIT", "a1b2c3d"
        ):
            self.assertEqual(build_info.describe(), "local, a1b2c3d")


if __name__ == "__main__":
    unittest.main()
