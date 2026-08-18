import unittest
from unittest.mock import MagicMock, patch

import preflight


class ReadOsReleaseTest(unittest.TestCase):
    def test_parses_quoted_key_value_pairs(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".os-release") as f:
            f.write('ID="rocky"\nID_LIKE="rhel centos fedora"\nVERSION_ID="9.3"\n')
            path = f.name
        data = preflight.read_os_release(path)
        self.assertEqual(data["ID"], "rocky")
        self.assertEqual(data["VERSION_ID"], "9.3")

    def test_empty_dict_when_file_missing(self):
        self.assertEqual(preflight.read_os_release("/nonexistent/os-release"), {})


class IsRhelLikeTest(unittest.TestCase):
    def test_true_for_rocky(self):
        self.assertTrue(preflight.is_rhel_like({"ID": "rocky", "ID_LIKE": "rhel centos fedora"}))

    def test_false_for_debian(self):
        self.assertFalse(preflight.is_rhel_like({"ID": "debian", "ID_LIKE": ""}))


class VersionMajorTest(unittest.TestCase):
    def test_extracts_major_from_dotted_version(self):
        self.assertEqual(preflight.version_major({"VERSION_ID": "9.3"}), 9)

    def test_zero_when_missing(self):
        self.assertEqual(preflight.version_major({}), 0)


class AlreadyInstalledTest(unittest.TestCase):
    @patch("preflight.os.path.exists", return_value=False)
    @patch("preflight.shutil.which", return_value="/usr/sbin/asterisk")
    def test_true_when_asterisk_binary_present(self, mock_which, mock_exists):
        self.assertTrue(preflight.already_installed())

    @patch("preflight.os.path.exists", return_value=True)
    @patch("preflight.shutil.which", return_value=None)
    def test_true_when_issabel_conf_present(self, mock_which, mock_exists):
        self.assertTrue(preflight.already_installed())

    @patch("preflight.os.path.exists", return_value=False)
    @patch("preflight.shutil.which", return_value=None)
    def test_false_when_neither_present(self, mock_which, mock_exists):
        self.assertFalse(preflight.already_installed())


class NetworkReachableTest(unittest.TestCase):
    @patch("preflight.subprocess.run")
    def test_true_when_curl_succeeds(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(preflight.network_reachable())

    @patch("preflight.subprocess.run")
    def test_false_when_curl_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=28)
        self.assertFalse(preflight.network_reachable())


class CheckTest(unittest.TestCase):
    @patch("preflight.is_root", return_value=False)
    def test_root_check_short_circuits_everything_else(self, mock_root):
        errors, warnings = preflight.check(min_version=8)
        self.assertEqual(len(errors), 1)
        self.assertIn("root", errors[0].lower())

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=False)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_no_errors_or_warnings_on_a_healthy_host(
        self, mock_root, mock_rhel, mock_version, mock_mem, mock_installed, mock_net
    ):
        errors, warnings = preflight.check(min_version=8)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    @patch("preflight.is_root", return_value=True)
    @patch("preflight.is_rhel_like", return_value=False)
    def test_error_when_not_rhel_like(self, mock_rhel, mock_root):
        errors, warnings = preflight.check(min_version=8)
        self.assertTrue(any("RHEL" in e for e in errors))

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=False)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=7)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_error_when_version_below_minimum(self, *_mocks):
        errors, warnings = preflight.check(min_version=8)
        self.assertTrue(any("versão" in e.lower() for e in errors))

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=False)
    @patch("preflight.os_ops.mem_total_kb", return_value=512 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_low_memory_is_a_warning_not_an_error(self, *_mocks):
        errors, warnings = preflight.check(min_version=8)
        self.assertEqual(errors, [])
        self.assertTrue(any("RAM" in w for w in warnings))

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=True)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_refuses_reinstall_over_existing_without_force(self, *_mocks):
        errors, warnings = preflight.check(min_version=8, force=False)
        self.assertTrue(any("force" in e.lower() for e in errors))

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=True)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_force_allows_reinstall_over_existing(self, *_mocks):
        errors, warnings = preflight.check(min_version=8, force=True)
        self.assertEqual(errors, [])

    @patch("preflight.network_reachable", return_value=False)
    @patch("preflight.already_installed", return_value=False)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_error_when_network_unreachable(self, *_mocks):
        errors, warnings = preflight.check(min_version=8)
        self.assertTrue(any("rede" in e.lower() for e in errors))


class CheckReportTest(unittest.TestCase):
    # report(label, status, detail) é opcional e não imprime nada aqui -- preflight.py só
    # relata o fato de cada checagem, na ordem real de execução (pra quem chamou mostrar
    # ao vivo, uma linha por vez -- não faz sentido bufferizar e só imprimir tudo no final).
    # status: "ok" | "warn" (reprova mas não bloqueia, ex.: RAM baixa) | "error" (bloqueia).
    # "rede" é a única checagem de fato lenta (curl real) -- por isso reporta em duas fases:
    # ("rede", "pending", None) antes de rodar, e o resultado de verdade depois.
    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=False)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_reports_each_check_in_execution_order_on_a_healthy_host(self, *_mocks):
        rows = []
        preflight.check(min_version=8, report=lambda *a: rows.append(a))
        self.assertEqual(
            [(label, status) for label, status, _detail in rows],
            [
                ("root", "ok"), ("SO", "ok"), ("rede", "pending"), ("rede", "ok"),
                ("RAM", "ok"), ("instalação prévia", "ok"),
            ],
        )

    @patch("preflight.is_root", return_value=False)
    def test_root_failure_reports_only_root(self, mock_root):
        rows = []
        preflight.check(min_version=8, report=lambda *a: rows.append(a))
        self.assertEqual(rows, [("root", "error", None)])

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=False)
    @patch("preflight.os_ops.mem_total_kb", return_value=512 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_low_ram_is_a_warning_not_an_error_status(self, *_mocks):
        rows = []
        preflight.check(min_version=8, report=lambda *a: rows.append(a))
        ram_row = next(r for r in rows if r[0] == "RAM")
        self.assertEqual(ram_row, ("RAM", "warn", "512 MB"))

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=False)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_ram_detail_shows_megabytes(self, *_mocks):
        rows = []
        preflight.check(min_version=8, report=lambda *a: rows.append(a))
        ram_row = next(r for r in rows if r[0] == "RAM")
        self.assertEqual(ram_row, ("RAM", "ok", "8192 MB"))

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=True)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_already_installed_detail_mentions_force_when_given(self, *_mocks):
        rows = []
        preflight.check(min_version=8, force=True, report=lambda *a: rows.append(a))
        row = next(r for r in rows if r[0] == "instalação prévia")
        self.assertEqual(row, ("instalação prévia", "ok", "detectada, ignorada por --force"))

    @patch("preflight.network_reachable", return_value=True)
    @patch("preflight.already_installed", return_value=True)
    @patch("preflight.os_ops.mem_total_kb", return_value=8 * 1024 * 1024)
    @patch("preflight.version_major", return_value=9)
    @patch("preflight.is_rhel_like", return_value=True)
    @patch("preflight.is_root", return_value=True)
    def test_already_installed_without_force_is_an_error_status(self, *_mocks):
        rows = []
        preflight.check(min_version=8, force=False, report=lambda *a: rows.append(a))
        row = next(r for r in rows if r[0] == "instalação prévia")
        self.assertEqual(row, ("instalação prévia", "error", "detectada"))


if __name__ == "__main__":
    unittest.main()
