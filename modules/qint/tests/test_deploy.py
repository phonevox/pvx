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
        self.assertEqual(deploy.compute_conflicts(base_dirs, "sgp"), [])

    def test_flags_category_whose_destination_subfolder_already_exists(self):
        (Path(self._tmp.name) / "sgp").mkdir()
        base_dirs = {"agi": self._tmp.name}
        self.assertEqual(deploy.compute_conflicts(base_dirs, "sgp"), ["agi"])


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

    def test_copies_source_into_a_subfolder_named_after_the_tipo(self):
        # achado ao vivo, conferido contra o instalador bash original: o destino usa o
        # nome do tipo (ixcsoft/sgp), nunca um "qint" fixo -- as duas integrações
        # convivem sem se pisar.
        deploy.deploy({"moh": str(self.source_dir)}, {"moh": str(self.base_dir)}, "sgp")

        dest = self.base_dir / "sgp"
        self.assertTrue(dest.is_dir())
        self.assertEqual((dest / "script.sh").read_text(), "echo oi")

    def test_overwrites_an_existing_destination(self):
        dest = self.base_dir / "sgp"
        dest.mkdir()
        (dest / "leftover").write_text("lixo")

        deploy.deploy({"moh": str(self.source_dir)}, {"moh": str(self.base_dir)}, "sgp")

        self.assertFalse((dest / "leftover").exists())
        self.assertTrue((dest / "script.sh").exists())

    @patch("deploy.subprocess.run")
    def test_chowns_and_chmods_only_agi_and_php(self, mock_run):
        deploy.deploy(
            {"agi": str(self.source_dir), "moh": str(self.source_dir)},
            {"agi": str(self.base_dir), "moh": str(self.base_dir)},
            "sgp",
        )

        commands = [call.args[0][0] for call in mock_run.call_args_list]
        self.assertEqual(mock_run.call_count, 2)  # chown + chmod, só pra "agi"
        self.assertTrue(all(cmd in ("chown", "chmod") for cmd in commands))


if __name__ == "__main__":
    unittest.main()
