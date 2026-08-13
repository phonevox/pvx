import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pvx.logging_ import viewer


class ReadLogTest(unittest.TestCase):
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

    def test_returns_full_log_content(self):
        log_dir = Path(self._tmp.name) / "logs"
        log_dir.mkdir()
        (log_dir / "dummy.log").write_text("linha1\nlinha2\nlinha3\n")

        self.assertEqual(viewer.read_log("dummy"), "linha1\nlinha2\nlinha3\n")

    def test_returns_last_n_lines(self):
        log_dir = Path(self._tmp.name) / "logs"
        log_dir.mkdir()
        (log_dir / "dummy.log").write_text("linha1\nlinha2\nlinha3\n")

        self.assertEqual(viewer.read_log("dummy", lines=2), "linha2\nlinha3")

    def test_missing_log_returns_empty_string(self):
        self.assertEqual(viewer.read_log("does-not-exist"), "")


if __name__ == "__main__":
    unittest.main()
