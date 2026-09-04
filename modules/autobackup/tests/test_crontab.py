import unittest
from unittest.mock import MagicMock, patch

import crontab

MARKER = crontab.MARKER
LEGACY_MARKER = "# gerenciado pelo pvx uoe -- não editar à mão, use `pvx uoe relogin`"


class FindManagedEntryTest(unittest.TestCase):
    def test_finds_the_line_right_after_the_marker(self):
        lines = [
            "0 3 * * * some-other-job.sh",
            MARKER,
            "25 2 * * * bash /root/pbackup/scripts/issabel.sh --token abc",
        ]
        result = crontab.find_managed_entry(lines)
        self.assertEqual(result, (2, "25 2 * * * bash /root/pbackup/scripts/issabel.sh --token abc"))

    def test_none_when_marker_is_absent(self):
        lines = ["0 3 * * * some-other-job.sh"]
        self.assertIsNone(crontab.find_managed_entry(lines))

    def test_none_when_marker_is_the_last_line(self):
        lines = ["0 3 * * * some-other-job.sh", MARKER]
        self.assertIsNone(crontab.find_managed_entry(lines))

    def test_also_finds_the_legacy_marker_from_before_the_uoe_to_autobackup_rename(self):
        # achado ao vivo: módulo renomeado de uoe pra autobackup -- centrais
        # já em produção têm o marcador antigo na cron. Sem isso,
        # relogin/remove nunca acham a entrada existente e duplicam.
        lines = [
            "0 3 * * * some-other-job.sh",
            LEGACY_MARKER,
            "25 2 * * * bash /root/pbackup/scripts/issabel.sh --token abc",
        ]
        result = crontab.find_managed_entry(lines)
        self.assertEqual(result, (2, "25 2 * * * bash /root/pbackup/scripts/issabel.sh --token abc"))


class UpsertManagedEntryTest(unittest.TestCase):
    def test_appends_marker_and_entry_when_absent(self):
        lines = ["0 3 * * * some-other-job.sh"]
        result = crontab.upsert_managed_entry(lines, "25 2 * * * bash issabel.sh --token abc")
        self.assertEqual(result, [
            "0 3 * * * some-other-job.sh",
            MARKER,
            "25 2 * * * bash issabel.sh --token abc",
        ])

    def test_replaces_existing_managed_entry_in_place(self):
        lines = [
            "0 3 * * * some-other-job.sh",
            MARKER,
            "25 2 * * * bash issabel.sh --token old",
            "0 4 * * * another-job.sh",
        ]
        result = crontab.upsert_managed_entry(lines, "25 2 * * * bash issabel.sh --token new")
        self.assertEqual(result, [
            "0 3 * * * some-other-job.sh",
            MARKER,
            "25 2 * * * bash issabel.sh --token new",
            "0 4 * * * another-job.sh",
        ])

    def test_modernizes_a_legacy_marker_when_updating_the_entry(self):
        lines = [
            "0 3 * * * some-other-job.sh",
            LEGACY_MARKER,
            "25 2 * * * bash issabel.sh --token old",
        ]
        result = crontab.upsert_managed_entry(lines, "25 2 * * * bash issabel.sh --token new")
        self.assertEqual(result, [
            "0 3 * * * some-other-job.sh",
            MARKER,
            "25 2 * * * bash issabel.sh --token new",
        ])


class RemoveManagedEntryTest(unittest.TestCase):
    def test_removes_marker_and_its_entry(self):
        lines = [
            "0 3 * * * some-other-job.sh",
            MARKER,
            "25 2 * * * bash issabel.sh --token abc",
            "0 4 * * * another-job.sh",
        ]
        result, removed = crontab.remove_managed_entry(lines)
        self.assertTrue(removed)
        self.assertEqual(result, ["0 3 * * * some-other-job.sh", "0 4 * * * another-job.sh"])

    def test_no_op_when_absent(self):
        lines = ["0 3 * * * some-other-job.sh"]
        result, removed = crontab.remove_managed_entry(lines)
        self.assertFalse(removed)
        self.assertEqual(result, lines)


class FindLegacyCandidatesTest(unittest.TestCase):
    def test_flags_lines_that_look_like_backup_and_are_not_managed(self):
        lines = [
            "0 3 * * * /usr/bin/issabel-helper backupengine --backup",
            MARKER,
            "25 2 * * * bash issabel.sh --token abc",
            "0 5 * * * rclone sync /data remote:backup",
            "*/5 * * * * /opt/monitor.sh",
        ]
        result = crontab.find_legacy_candidates(lines)
        self.assertEqual(result, [
            "0 3 * * * /usr/bin/issabel-helper backupengine --backup",
            "0 5 * * * rclone sync /data remote:backup",
        ])

    def test_ignores_blank_lines_and_comments(self):
        lines = ["", "# just a comment", "   "]
        self.assertEqual(crontab.find_legacy_candidates(lines), [])

    def test_excludes_the_managed_entry_itself_even_if_it_matches_keywords(self):
        lines = [MARKER, "25 2 * * * bash /root/pbackup/scripts/issabel.sh --token abc"]
        self.assertEqual(crontab.find_legacy_candidates(lines), [])


class ReadCrontabTest(unittest.TestCase):
    # `crontab -l` sai com status != 0 quando o usuário nunca teve uma cron --
    # não é erro, é "vazio".
    @patch("crontab.subprocess.run")
    def test_returns_lines_when_crontab_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="a\nb\n")
        self.assertEqual(crontab.read_crontab(), ["a", "b"])

    @patch("crontab.subprocess.run")
    def test_empty_list_when_no_crontab_exists_yet(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        self.assertEqual(crontab.read_crontab(), [])


class WriteCrontabTest(unittest.TestCase):
    @patch("crontab.subprocess.run")
    def test_writes_lines_joined_with_newlines(self, mock_run):
        crontab.write_crontab(["a", "b"])
        mock_run.assert_called_once_with(["crontab", "-"], input="a\nb\n", text=True, check=True)


if __name__ == "__main__":
    unittest.main()
