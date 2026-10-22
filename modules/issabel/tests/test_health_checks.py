import unittest
from unittest.mock import Mock, patch

import health_checks as hc


def _run_result(returncode=0, stdout="", stderr=""):
    result = Mock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


class CheckAstdbWriteTest(unittest.TestCase):
    def test_passes_when_put_and_get_confirm_the_value(self):
        with patch("health_checks.subprocess.run", side_effect=[
            _run_result(stdout="Updated database successfully"),
            _run_result(stdout="valor"),
            _run_result(),
        ]) as mock_run:
            result = hc.check_astdb_write()
        self.assertTrue(result.passed)
        self.assertEqual(result.name, "astdb_write")
        # put, get, del -- nessa ordem, e del sempre roda mesmo que não
        # precisasse (limpa a chave de teste independente do resultado).
        self.assertEqual(mock_run.call_count, 3)

    def test_fails_when_put_itself_fails(self):
        with patch("health_checks.subprocess.run", side_effect=[
            _run_result(returncode=1, stderr="Failed to update entry"),
            _run_result(),
            _run_result(),
        ]):
            result = hc.check_astdb_write()
        self.assertFalse(result.passed)
        self.assertIn("Failed to update entry", result.detail)

    def test_fails_when_the_value_does_not_round_trip(self):
        with patch("health_checks.subprocess.run", side_effect=[
            _run_result(stdout="Updated database successfully"),
            _run_result(stdout="outra-coisa"),
            _run_result(),
        ]):
            result = hc.check_astdb_write()
        self.assertFalse(result.passed)

    def test_always_cleans_up_the_test_key(self):
        with patch("health_checks.subprocess.run", side_effect=[
            _run_result(returncode=1, stderr="boom"),
            _run_result(),
            _run_result(),
        ]) as mock_run:
            hc.check_astdb_write()
        del_call = mock_run.call_args_list[2]
        self.assertIn("database del", " ".join(del_call.args[0]))


class CheckAstdbIntegrityTest(unittest.TestCase):
    def test_passes_when_every_present_file_is_ok(self):
        with patch("health_checks.os.path.isfile", return_value=True), \
             patch("health_checks.glob.glob", return_value=["/var/www/db/acl.db"]), \
             patch("health_checks.subprocess.run", return_value=_run_result(stdout="ok\n")):
            result = hc.check_astdb_integrity()
        self.assertTrue(result.passed)

    def test_fails_and_names_the_file_when_integrity_check_is_not_ok(self):
        with patch("health_checks.os.path.isfile", return_value=True), \
             patch("health_checks.glob.glob", return_value=[]), \
             patch("health_checks.subprocess.run", return_value=_run_result(stdout="*** in database main ***\n")):
            result = hc.check_astdb_integrity()
        self.assertFalse(result.passed)
        self.assertIn(hc.ASTDB_PATH, result.detail)

    def test_skips_files_that_do_not_exist(self):
        with patch("health_checks.os.path.isfile", return_value=False), \
             patch("health_checks.glob.glob", return_value=[]), \
             patch("health_checks.subprocess.run") as mock_run:
            result = hc.check_astdb_integrity()
        self.assertTrue(result.passed)
        mock_run.assert_not_called()


class CheckOdbcTest(unittest.TestCase):
    def test_passes_when_every_dsn_is_connected(self):
        output = (
            "  Name:   asterisk\n"
            "  DSN:    MySQL-asterisk\n"
            "    Connected: Yes\n"
            "  Name:   asteriskcdrdb\n"
            "  DSN:    MySQL-asteriskcdrdb\n"
            "    Connected: Yes\n"
        )
        with patch("health_checks.subprocess.run", return_value=_run_result(stdout=output)):
            result = hc.check_odbc()
        self.assertTrue(result.passed)

    def test_fails_and_names_the_disconnected_dsn(self):
        output = (
            "  Name:   asterisk\n"
            "    Connected: Yes\n"
            "  Name:   asteriskcdrdb\n"
            "    Connected: No\n"
        )
        with patch("health_checks.subprocess.run", return_value=_run_result(stdout=output)):
            result = hc.check_odbc()
        self.assertFalse(result.passed)
        self.assertIn("asteriskcdrdb", result.detail)

    def test_fails_when_the_command_itself_fails(self):
        with patch("health_checks.subprocess.run", return_value=_run_result(returncode=1, stderr="boom")):
            result = hc.check_odbc()
        self.assertFalse(result.passed)
        self.assertIn("boom", result.detail)


class CheckAsteriskPathsTest(unittest.TestCase):
    def _stat(self, uid, writable=True):
        st = Mock()
        st.st_uid = uid
        st.st_mode = 0o40775 if writable else 0o40575
        return st

    def test_passes_when_every_path_is_owned_and_writable(self):
        with patch("health_checks.pwd.getpwnam", return_value=Mock(pw_uid=100)), \
             patch("health_checks.os.path.isdir", return_value=True), \
             patch("health_checks.os.stat", return_value=self._stat(100)):
            result = hc.check_asterisk_paths()
        self.assertTrue(result.passed)

    def test_fails_and_names_the_path_with_wrong_owner(self):
        with patch("health_checks.pwd.getpwnam", return_value=Mock(pw_uid=100)), \
             patch("health_checks.pwd.getpwuid", return_value=Mock(pw_name="root")), \
             patch("health_checks.os.path.isdir", return_value=True), \
             patch("health_checks.os.stat", return_value=self._stat(0)):
            result = hc.check_asterisk_paths()
        self.assertFalse(result.passed)
        self.assertIn("root", result.detail)

    def test_fails_when_a_path_is_missing(self):
        with patch("health_checks.pwd.getpwnam", return_value=Mock(pw_uid=100)), \
             patch("health_checks.os.path.isdir", return_value=False):
            result = hc.check_asterisk_paths()
        self.assertFalse(result.passed)
        self.assertIn("não existe", result.detail)

    def test_fails_when_owned_correctly_but_not_writable(self):
        with patch("health_checks.pwd.getpwnam", return_value=Mock(pw_uid=100)), \
             patch("health_checks.os.path.isdir", return_value=True), \
             patch("health_checks.os.stat", return_value=self._stat(100, writable=False)):
            result = hc.check_asterisk_paths()
        self.assertFalse(result.passed)


class RunChecksTest(unittest.TestCase):
    def test_runs_everything_registered_by_default(self):
        fake = Mock(side_effect=lambda: hc.CheckResult("fake", True))
        with patch.dict(hc.CHECKS, {"fake": fake}, clear=True):
            results = hc.run_checks()
        self.assertEqual([r.name for r in results], ["fake"])

    def test_runs_only_the_requested_names(self):
        fake_a = Mock(side_effect=lambda: hc.CheckResult("a", True))
        fake_b = Mock(side_effect=lambda: hc.CheckResult("b", True))
        with patch.dict(hc.CHECKS, {"a": fake_a, "b": fake_b}, clear=True):
            results = hc.run_checks(["b"])
        self.assertEqual([r.name for r in results], ["b"])
        fake_a.assert_not_called()


if __name__ == "__main__":
    unittest.main()
