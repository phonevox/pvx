import os
import tempfile
import unittest
from unittest.mock import patch

import profile_hook


class ProfileHookTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.hook_path = os.path.join(self.root, "profile.d", "pvx-motd.sh")
        os.makedirs(os.path.dirname(self.hook_path))
        self.legacy_paths = (
            os.path.join(self.root, "usr-local-sbin-motd.sh"),
            os.path.join(self.root, "profile.d", "login-info.sh"),
            os.path.join(self.root, "profile.d", "motd.sh"),
            os.path.join(self.root, "profile.d", "pmotd.sh"),
        )
        self._patches = [
            patch("profile_hook.HOOK_PATH", self.hook_path),
            patch("profile_hook._LEGACY_PATHS", self.legacy_paths),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _touch(self, path, content="legacy"):
        with open(path, "w") as f:
            f.write(content)


class InstallTest(ProfileHookTestCase):
    def test_writes_the_hook_script_and_makes_it_executable(self):
        result = profile_hook.install(base_dir=self.root)
        self.assertTrue(os.path.isfile(self.hook_path))
        self.assertEqual(open(self.hook_path).read(), profile_hook.HOOK_CONTENT)
        self.assertTrue(os.stat(self.hook_path).st_mode & 0o111)
        self.assertIsNone(result["backup_dir"])
        self.assertEqual(result["backed_up"], [])

    def test_backs_up_and_removes_legacy_scripts(self):
        self._touch(self.legacy_paths[0])
        self._touch(self.legacy_paths[2])

        result = profile_hook.install(base_dir=self.root)

        self.assertFalse(os.path.isfile(self.legacy_paths[0]))
        self.assertFalse(os.path.isfile(self.legacy_paths[2]))
        self.assertIsNotNone(result["backup_dir"])
        self.assertTrue(os.path.isdir(result["backup_dir"]))
        self.assertIn(self.legacy_paths[0], result["backed_up"])
        self.assertIn(self.legacy_paths[2], result["backed_up"])
        backed_up_names = os.listdir(result["backup_dir"])
        self.assertIn(os.path.basename(self.legacy_paths[0]), backed_up_names)

    def test_ignores_legacy_scripts_that_do_not_exist(self):
        result = profile_hook.install(base_dir=self.root)
        self.assertEqual(result["backed_up"], [])

    def test_backs_up_an_existing_hook_before_overwriting(self):
        self._touch(self.hook_path, content="versao antiga")

        result = profile_hook.install(base_dir=self.root)

        self.assertEqual(open(self.hook_path).read(), profile_hook.HOOK_CONTENT)
        self.assertIn(self.hook_path, result["backed_up"])
        self.assertIsNotNone(result["backup_dir"])


class UninstallTest(ProfileHookTestCase):
    def test_removes_an_installed_hook(self):
        self._touch(self.hook_path, content=profile_hook.HOOK_CONTENT)
        self.assertTrue(profile_hook.uninstall())
        self.assertFalse(os.path.isfile(self.hook_path))

    def test_false_when_nothing_was_installed(self):
        self.assertFalse(profile_hook.uninstall())


class IsInstalledTest(ProfileHookTestCase):
    def test_true_when_the_hook_file_exists(self):
        self._touch(self.hook_path)
        self.assertTrue(profile_hook.is_installed())

    def test_false_when_it_does_not(self):
        self.assertFalse(profile_hook.is_installed())


if __name__ == "__main__":
    unittest.main()
