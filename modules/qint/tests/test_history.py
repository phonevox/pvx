import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import history


class AppendTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "nested" / "history.log"

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_parent_dirs_and_writes_a_timestamped_line(self):
        history.append(str(self.path), "apply ixcsoft 1.2.3")

        line = self.path.read_text().strip()
        self.assertRegex(line, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} apply ixcsoft 1\.2\.3$")

    def test_appends_without_overwriting_previous_lines(self):
        history.append(str(self.path), "first")
        history.append(str(self.path), "second")

        lines = self.path.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].endswith("second"))


if __name__ == "__main__":
    unittest.main()
