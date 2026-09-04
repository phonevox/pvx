import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pbackup_ops


class ParseVersionTest(unittest.TestCase):
    def test_parses_plain_semver(self):
        self.assertEqual(pbackup_ops._parse_version("1.3.1"), (1, 3, 1))

    def test_strips_leading_v(self):
        self.assertEqual(pbackup_ops._parse_version("v1.3.1"), (1, 3, 1))


class IsSupportedTest(unittest.TestCase):
    def test_true_when_at_or_above_minimum(self):
        self.assertTrue(pbackup_ops.is_supported((1, 1, 0)))
        self.assertTrue(pbackup_ops.is_supported((1, 3, 1)))

    def test_false_when_below_minimum(self):
        self.assertFalse(pbackup_ops.is_supported((1, 0, 9)))

    def test_false_when_none(self):
        self.assertFalse(pbackup_ops.is_supported(None))


class FindInstallTest(unittest.TestCase):
    def test_none_when_no_binary_path_exists(self):
        with patch("pbackup_ops.os.path.islink", return_value=False), \
             patch("pbackup_ops.os.path.isfile", return_value=False):
            self.assertIsNone(pbackup_ops.find_install())

    def test_resolves_the_symlink_to_find_the_real_root(self):
        with patch("pbackup_ops.os.path.islink", side_effect=lambda p: p == "/usr/sbin/pbackup"), \
             patch("pbackup_ops.os.path.isfile", return_value=True), \
             patch("pbackup_ops.os.path.realpath", return_value="/root/pbackup/pbackup.sh"):
            self.assertEqual(pbackup_ops.find_install(), "/root/pbackup")


class InstalledVersionTest(unittest.TestCase):
    def test_reads_version_from_version_json(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "lib").mkdir()
            (Path(tmp) / "lib" / "version.json").write_text('{"version": "1.3.1"}')
            self.assertEqual(pbackup_ops.installed_version(tmp), (1, 3, 1))

    def test_none_when_version_json_is_missing(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(pbackup_ops.installed_version(tmp))

    def test_none_when_version_json_is_malformed(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "lib").mkdir()
            (Path(tmp) / "lib" / "version.json").write_text("not json")
            self.assertIsNone(pbackup_ops.installed_version(tmp))


class EnsureSymlinkTest(unittest.TestCase):
    @patch("pbackup_ops.os.symlink")
    @patch("pbackup_ops.os.remove")
    @patch("pbackup_ops.os.path.lexists", return_value=False)
    @patch("pbackup_ops.os.path.realpath", side_effect=lambda p: p)
    def test_creates_symlinks_when_absent(self, mock_realpath, mock_lexists, mock_remove, mock_symlink):
        pbackup_ops._ensure_symlink("/root/pbackup")
        mock_symlink.assert_any_call("/root/pbackup/pbackup.sh", "/usr/sbin/pbackup")
        mock_symlink.assert_any_call("/root/pbackup/pbackup.sh", "/usr/bin/pbackup")
        mock_remove.assert_not_called()

    @patch("pbackup_ops.os.symlink")
    @patch("pbackup_ops.os.remove")
    @patch("pbackup_ops.os.path.realpath", return_value="/root/pbackup/pbackup.sh")
    def test_skips_paths_already_pointing_correctly(self, mock_realpath, mock_remove, mock_symlink):
        pbackup_ops._ensure_symlink("/root/pbackup")
        mock_symlink.assert_not_called()
        mock_remove.assert_not_called()

    @patch("pbackup_ops.os.symlink")
    @patch("pbackup_ops.os.remove")
    @patch("pbackup_ops.os.path.lexists", return_value=True)
    def test_replaces_a_symlink_pointing_elsewhere(self, mock_lexists, mock_remove, mock_symlink):
        def fake_realpath(p):
            return p if p == "/root/pbackup/pbackup.sh" else "/some/other/place.sh"

        with patch("pbackup_ops.os.path.realpath", side_effect=fake_realpath):
            pbackup_ops._ensure_symlink("/root/pbackup")
        self.assertEqual(mock_remove.call_count, 2)
        self.assertEqual(mock_symlink.call_count, 2)


class FreshInstallTest(unittest.TestCase):
    @patch("pbackup_ops._ensure_symlink")
    @patch("pbackup_ops._chmod_scripts")
    @patch("pbackup_ops._extract_archive")
    @patch("pbackup_ops._download", return_value=b"tar-bytes")
    @patch("pbackup_ops._latest_release_tag", return_value="v1.3.1")
    def test_downloads_the_latest_release_tag_and_installs_it(
        self, mock_tag, mock_download, mock_extract, mock_chmod, mock_symlink
    ):
        result = pbackup_ops.fresh_install("/opt/pbackup")
        self.assertEqual(result, "/opt/pbackup")
        mock_download.assert_called_once_with(
            "https://github.com/phonevox/pbackup/archive/refs/tags/v1.3.1.tar.gz"
        )
        mock_extract.assert_called_once_with(b"tar-bytes", "/opt/pbackup", is_zip=False)
        mock_chmod.assert_called_once_with("/opt/pbackup")
        mock_symlink.assert_called_once_with("/opt/pbackup")


class UpdateInPlaceTest(unittest.TestCase):
    # mesma fonte que o pbackup.sh --update usa de verdade: zip da branch main,
    # não uma tag -- sobrescreve por cima de onde já está instalado.
    @patch("pbackup_ops._chmod_scripts")
    @patch("pbackup_ops._extract_archive")
    @patch("pbackup_ops._download", return_value=b"zip-bytes")
    def test_downloads_the_main_branch_zip_over_the_existing_install(
        self, mock_download, mock_extract, mock_chmod
    ):
        pbackup_ops.update_in_place("/root/pbackup")
        mock_download.assert_called_once_with(
            "https://github.com/phonevox/pbackup/archive/refs/heads/main.zip"
        )
        mock_extract.assert_called_once_with(b"zip-bytes", "/root/pbackup", is_zip=True)
        mock_chmod.assert_called_once_with("/root/pbackup")


if __name__ == "__main__":
    unittest.main()
