import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import deploy


class ComputeConflictsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_empty_when_nothing_exists(self):
        base_dirs = {"agi": self._tmp.name}
        self.assertEqual(deploy.compute_conflicts(base_dirs), [])

    def test_flags_category_whose_destination_subfolder_already_exists(self):
        (Path(self._tmp.name) / "qint").mkdir()
        base_dirs = {"agi": self._tmp.name}
        self.assertEqual(deploy.compute_conflicts(base_dirs), ["agi"])


class DeployTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.source_dir = Path(self._tmp.name) / "source"
        self.base_dir = Path(self._tmp.name) / "base"
        self.source_dir.mkdir()
        self.base_dir.mkdir()
        (self.source_dir / "script.sh").write_text("echo oi")

    def tearDown(self):
        self._tmp.cleanup()

    def test_copies_source_into_a_qint_subfolder_of_the_base_dir(self):
        deploy.deploy({"moh": str(self.source_dir)}, {"moh": str(self.base_dir)})

        dest = self.base_dir / "qint"
        self.assertTrue(dest.is_dir())
        self.assertEqual((dest / "script.sh").read_text(), "echo oi")

    def test_overwrites_an_existing_destination(self):
        dest = self.base_dir / "qint"
        dest.mkdir()
        (dest / "leftover").write_text("lixo")

        deploy.deploy({"moh": str(self.source_dir)}, {"moh": str(self.base_dir)})

        self.assertFalse((dest / "leftover").exists())
        self.assertTrue((dest / "script.sh").exists())

    @patch("deploy.subprocess.run")
    def test_chowns_and_chmods_only_agi_and_php(self, mock_run):
        deploy.deploy(
            {"agi": str(self.source_dir), "moh": str(self.source_dir)},
            {"agi": str(self.base_dir), "moh": str(self.base_dir)},
        )

        commands = [call.args[0][0] for call in mock_run.call_args_list]
        self.assertEqual(mock_run.call_count, 2)  # chown + chmod, só pra "agi"
        self.assertTrue(all(cmd in ("chown", "chmod") for cmd in commands))


if __name__ == "__main__":
    unittest.main()
