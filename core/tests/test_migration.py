import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pvx.modules import migration


def _make_module(base, name, version="0.1.0"):
    module_dir = Path(base) / "modules" / name
    module_dir.mkdir(parents=True)
    (module_dir / "manifest.json").write_text(json.dumps({"name": name, "version": version}))
    (module_dir / "module.pyz").write_text("fake")
    return module_dir


class MigrateLegacyModulesTest(unittest.TestCase):
    def setUp(self):
        self._dest_tmp = TemporaryDirectory()
        self._legacy_tmp = TemporaryDirectory()
        self.dest_home = Path(self._dest_tmp.name) / "etc-pvx"
        self._patches = [
            patch("pvx.modules.migration.config.pvx_home", return_value=self.dest_home),
            patch("pvx.modules.migration.config.modules_dir", return_value=self.dest_home / "modules"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._dest_tmp.cleanup()
        self._legacy_tmp.cleanup()

    def _legacy_home(self, name):
        return Path(self._legacy_tmp.name) / name

    def test_copies_a_module_missing_from_the_destination(self):
        legacy = self._legacy_home("home1")
        _make_module(legacy, "zabbix")

        migrated = migration.migrate_legacy_modules(legacy_homes=[legacy])

        self.assertEqual(migrated, ["zabbix"])
        self.assertTrue((self.dest_home / "modules" / "zabbix" / "module.pyz").exists())

    def test_never_overwrites_a_module_already_at_the_destination(self):
        legacy = self._legacy_home("home1")
        _make_module(legacy, "zabbix", version="0.1.0")
        dest_module = self.dest_home / "modules" / "zabbix"
        dest_module.mkdir(parents=True)
        (dest_module / "manifest.json").write_text(json.dumps({"version": "9.9.9"}))

        migrated = migration.migrate_legacy_modules(legacy_homes=[legacy])

        self.assertEqual(migrated, [])
        manifest = json.loads((dest_module / "manifest.json").read_text())
        self.assertEqual(manifest["version"], "9.9.9")

    def test_picks_the_highest_version_across_multiple_legacy_homes(self):
        home_root = self._legacy_home("root")
        home_rocky = self._legacy_home("rocky")
        _make_module(home_root, "uoe", version="0.1.0")
        _make_module(home_rocky, "uoe", version="0.2.5")

        migration.migrate_legacy_modules(legacy_homes=[home_root, home_rocky])

        manifest = json.loads((self.dest_home / "modules" / "uoe" / "manifest.json").read_text())
        self.assertEqual(manifest["version"], "0.2.5")

    def test_merges_different_modules_from_different_homes(self):
        home_root = self._legacy_home("root")
        home_rocky = self._legacy_home("rocky")
        _make_module(home_root, "firewall")
        _make_module(home_rocky, "qint")

        migrated = migration.migrate_legacy_modules(legacy_homes=[home_root, home_rocky])

        self.assertEqual(sorted(migrated), ["firewall", "qint"])

    def test_skips_legacy_homes_without_a_modules_subdir(self):
        empty_home = self._legacy_home("empty")
        empty_home.mkdir(parents=True)

        migrated = migration.migrate_legacy_modules(legacy_homes=[empty_home])

        self.assertEqual(migrated, [])

    def test_no_op_when_no_legacy_homes_given(self):
        migrated = migration.migrate_legacy_modules(legacy_homes=[])
        self.assertEqual(migrated, [])

    def test_creates_the_destination_world_readable(self):
        migration.migrate_legacy_modules(legacy_homes=[])
        self.assertEqual(oct(self.dest_home.stat().st_mode)[-3:], "755")
        self.assertEqual(oct((self.dest_home / "modules").stat().st_mode)[-3:], "755")

    def test_ignores_a_module_with_a_corrupt_manifest_but_still_copies_it(self):
        # versão ilegível vira (0,0,0) -- nunca trava a migração por causa
        # de um manifest quebrado, só perde a prioridade no desempate.
        legacy = self._legacy_home("home1")
        module_dir = Path(legacy) / "modules" / "broken"
        module_dir.mkdir(parents=True)
        (module_dir / "manifest.json").write_text("isso nao eh json")

        migrated = migration.migrate_legacy_modules(legacy_homes=[legacy])

        self.assertEqual(migrated, ["broken"])


class LegacyCandidateHomesTest(unittest.TestCase):
    @patch("pvx.modules.migration.glob.glob", return_value=["/home/rocky/.pvx", "/home/phonevox/.pvx"])
    @patch("pvx.modules.migration.Path.is_dir", return_value=True)
    def test_includes_root_and_every_home_pvx_dir(self, mock_is_dir, mock_glob):
        homes = migration._legacy_candidate_homes()
        self.assertIn(Path("/root/.pvx"), homes)
        self.assertIn(Path("/home/rocky/.pvx"), homes)
        self.assertIn(Path("/home/phonevox/.pvx"), homes)
        mock_glob.assert_called_once_with("/home/*/.pvx")

    @patch("pvx.modules.migration.glob.glob", return_value=[])
    @patch("pvx.modules.migration.Path.is_dir", return_value=False)
    def test_empty_when_nothing_exists(self, mock_is_dir, mock_glob):
        self.assertEqual(migration._legacy_candidate_homes(), [])


if __name__ == "__main__":
    unittest.main()
