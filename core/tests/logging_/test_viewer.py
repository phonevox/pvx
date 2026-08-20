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


class ListLogNamesTest(unittest.TestCase):
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

    def test_returns_sorted_stems_of_every_log_file(self):
        log_dir = Path(self._tmp.name) / "logs"
        log_dir.mkdir()
        (log_dir / "netinstall.log").write_text("")
        (log_dir / "core.log").write_text("")

        self.assertEqual(viewer.list_log_names(), ["core", "netinstall"])

    def test_empty_list_when_logs_dir_missing(self):
        self.assertEqual(viewer.list_log_names(), [])


class ReadCombinedLogsTest(unittest.TestCase):
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

    def test_merges_multiple_logs_in_chronological_order(self):
        # cada linha já vem com o timestamp do Formatter (get_module_logger) no início --
        # dá pra intercalar logs de fontes diferentes só ordenando as linhas como string.
        log_dir = Path(self._tmp.name) / "logs"
        log_dir.mkdir()
        (log_dir / "core.log").write_text("2026-08-20 10:00:00 INFO pvx.core: a\n")
        (log_dir / "netinstall.log").write_text("2026-08-20 10:00:01 INFO pvx.netinstall: b\n")

        combined = viewer.read_combined_logs(["core", "netinstall"])
        self.assertEqual(combined, "2026-08-20 10:00:00 INFO pvx.core: a\n2026-08-20 10:00:01 INFO pvx.netinstall: b")

    def test_respects_tail_across_the_merged_result(self):
        log_dir = Path(self._tmp.name) / "logs"
        log_dir.mkdir()
        (log_dir / "core.log").write_text("2026-08-20 10:00:00 INFO pvx.core: a\n2026-08-20 10:00:02 INFO pvx.core: c\n")
        (log_dir / "netinstall.log").write_text("2026-08-20 10:00:01 INFO pvx.netinstall: b\n")

        combined = viewer.read_combined_logs(["core", "netinstall"], lines=2)
        self.assertEqual(
            combined,
            "2026-08-20 10:00:01 INFO pvx.netinstall: b\n2026-08-20 10:00:02 INFO pvx.core: c",
        )


class LogFollowerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._old_home = os.environ.get("PVX_HOME")
        os.environ["PVX_HOME"] = self._tmp.name
        self._log_dir = Path(self._tmp.name) / "logs"
        self._log_dir.mkdir()

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("PVX_HOME", None)
        else:
            os.environ["PVX_HOME"] = self._old_home
        self._tmp.cleanup()

    def test_poll_ignores_content_written_before_construction(self):
        (self._log_dir / "dummy.log").write_text("linha antiga\n")
        follower = viewer.LogFollower(["dummy"])
        self.assertEqual(follower.poll(), [])

    def test_poll_returns_only_newly_appended_lines(self):
        (self._log_dir / "dummy.log").write_text("linha antiga\n")
        follower = viewer.LogFollower(["dummy"])
        with open(self._log_dir / "dummy.log", "a") as f:
            f.write("linha nova\n")
        self.assertEqual(follower.poll(), ["linha nova"])
        self.assertEqual(follower.poll(), [])

    def test_poll_merges_and_sorts_new_lines_across_files(self):
        (self._log_dir / "core.log").write_text("")
        (self._log_dir / "netinstall.log").write_text("")
        follower = viewer.LogFollower(["core", "netinstall"])
        with open(self._log_dir / "netinstall.log", "a") as f:
            f.write("2026-08-20 10:00:01 b\n")
        with open(self._log_dir / "core.log", "a") as f:
            f.write("2026-08-20 10:00:00 a\n")
        self.assertEqual(follower.poll(), ["2026-08-20 10:00:00 a", "2026-08-20 10:00:01 b"])

    def test_survives_a_file_that_does_not_exist_yet(self):
        follower = viewer.LogFollower(["nao-existe"])
        self.assertEqual(follower.poll(), [])


if __name__ == "__main__":
    unittest.main()
