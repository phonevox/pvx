import os
import time
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import autobloqueador_ops as ops


class ConfigsExistTest(unittest.TestCase):
    def test_false_when_nothing_saved(self):
        with patch("autobloqueador_ops.state.load", return_value=None):
            self.assertFalse(ops.configs_exist())

    def test_true_when_state_present(self):
        with patch("autobloqueador_ops.state.load", return_value={"url_base": "x"}):
            self.assertTrue(ops.configs_exist())


class SaveAndLoadConfigTest(unittest.TestCase):
    @patch("autobloqueador_ops.state.save")
    def test_save_config_writes_all_fields(self, mock_save):
        ops.save_config("https://x.com", "pabx", "c1", "chave-secreta")
        mock_save.assert_called_once_with(ops.STATE_FILE, {
            "url_base": "https://x.com", "type": "pabx", "code": "c1", "crypted_key": "chave-secreta",
        })

    @patch("autobloqueador_ops.state.load", return_value={"url_base": "https://x.com"})
    def test_load_config_delegates_to_state(self, mock_load):
        self.assertEqual(ops.load_config(), {"url_base": "https://x.com"})
        mock_load.assert_called_once_with(ops.STATE_FILE)


class NormalizeUrlBaseTest(unittest.TestCase):
    def test_adds_https_prefix_when_missing(self):
        self.assertEqual(ops.normalize_url_base("auto-blocker.falevox.com.br"), "https://auto-blocker.falevox.com.br")

    def test_keeps_explicit_scheme(self):
        self.assertEqual(ops.normalize_url_base("http://x.com"), "http://x.com")
        self.assertEqual(ops.normalize_url_base("https://x.com"), "https://x.com")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(ops.normalize_url_base("  x.com  "), "https://x.com")

    def test_raises_on_empty_value(self):
        with self.assertRaises(ops.AutobloqueadorError):
            ops.normalize_url_base("   ")


class ValidateCodeTest(unittest.TestCase):
    def test_true_for_normal_code(self):
        self.assertTrue(ops.validate_code("cliente-123"))

    def test_false_for_empty(self):
        self.assertFalse(ops.validate_code(""))

    def test_false_when_too_long(self):
        self.assertFalse(ops.validate_code("a" * 256))

    def test_true_at_the_boundary(self):
        self.assertTrue(ops.validate_code("a" * 255))


class RegisterCurlCommandsTest(unittest.TestCase):
    def test_linux_command_uses_single_quoted_json(self):
        linux, _ = ops.register_curl_commands("https://x.com", "pabx", "c1")
        self.assertIn('curl -L -X POST "https://x.com/register"', linux)
        self.assertIn("""-d '{"type": "pabx", "code": "c1"}'""", linux)

    def test_windows_command_escapes_quotes(self):
        _, windows = ops.register_curl_commands("https://x.com", "pabx", "c1")
        self.assertIn('-d "{\\"type\\": \\"pabx\\", \\"code\\": \\"c1\\"}"', windows)


class FindPm2Test(unittest.TestCase):
    @patch("autobloqueador_ops.shutil.which", return_value="/opt/bin/pm2")
    def test_prefers_which(self, mock_which):
        self.assertEqual(ops.find_pm2(), "/opt/bin/pm2")

    @patch("autobloqueador_ops.glob.glob")
    @patch("autobloqueador_ops.shutil.which", return_value=None)
    def test_falls_back_to_known_paths(self, mock_which, mock_glob):
        mock_glob.side_effect = lambda pattern: ["/usr/bin/pm2"] if pattern == "/usr/bin/pm2" else []
        self.assertEqual(ops.find_pm2(), "/usr/bin/pm2")

    @patch("autobloqueador_ops.glob.glob", return_value=[])
    @patch("autobloqueador_ops.shutil.which", return_value=None)
    def test_none_when_not_found_anywhere(self, mock_which, mock_glob):
        self.assertIsNone(ops.find_pm2())


class ApplyActionTest(unittest.TestCase):
    @patch("autobloqueador_ops._run")
    def test_pabx_uses_the_service_command(self, mock_run):
        result = ops._apply_action("pabx", "restart")
        mock_run.assert_called_once_with(
            ["service", "asterisk", "restart"], "falha ao executar 'service asterisk restart'",
        )
        self.assertIsNone(result)

    @patch("autobloqueador_ops._run")
    @patch("autobloqueador_ops.find_pm2", return_value="/usr/bin/pm2")
    def test_opa_uses_pm2(self, mock_find, mock_run):
        result = ops._apply_action("opa", "stop")
        mock_run.assert_called_once_with(["/usr/bin/pm2", "stop", "all"], "falha ao executar 'pm2 stop all'")
        self.assertIsNone(result)

    @patch("autobloqueador_ops._run")
    @patch("autobloqueador_ops.find_pm2", return_value=None)
    def test_opa_without_pm2_warns_instead_of_raising(self, mock_find, mock_run):
        # achado no original: pm2 ausente só loga aviso e segue -- nunca é
        # motivo pra abortar a checagem de status inteira.
        result = ops._apply_action("opa", "restart")
        mock_run.assert_not_called()
        self.assertIn("pm2", result.lower())


class QueryStatusTest(unittest.TestCase):
    @patch("autobloqueador_ops.urllib.request.urlopen")
    def test_returns_the_http_status_on_success(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.status = 200
        code = ops._query_status("https://x.com", "pabx", "ch@ve secreta", last_status=0)
        self.assertEqual(code, 200)

    @patch("autobloqueador_ops.urllib.request.urlopen")
    def test_url_encodes_the_key_and_pads_last_status(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.status = 200
        ops._query_status("https://x.com", "pabx", "ch@ve secreta", last_status=200)
        requested_url = mock_urlopen.call_args.args[0]
        self.assertIn("crypted_key=ch%40ve%20secreta", requested_url)
        self.assertIn("last_status=200", requested_url)
        self.assertIn("type=pabx", requested_url)

    @patch("autobloqueador_ops.urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 402, "Payment Required", {}, None))
    def test_returns_the_code_from_an_http_error(self, mock_urlopen):
        # 402 (bloqueio) SEMPRE levanta HTTPError no urllib -- não é uma
        # falha de rede, é a resposta de verdade que a checagem precisa ler.
        self.assertEqual(ops._query_status("https://x.com", "pabx", "k", last_status=0), 402)

    @patch("autobloqueador_ops.urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused"))
    def test_returns_zero_when_connection_fails(self, mock_urlopen):
        # equivalente ao "000" do curl original quando não há resposta.
        self.assertEqual(ops._query_status("https://x.com", "pabx", "k", last_status=0), 0)


class CheckAndApplyTest(unittest.TestCase):
    @patch("autobloqueador_ops._write_last_response")
    @patch("autobloqueador_ops._apply_action", return_value=None)
    @patch("autobloqueador_ops._query_status", return_value=200)
    @patch("autobloqueador_ops._read_last_status", return_value=200)
    def test_no_action_when_status_unchanged_at_200(self, mock_read, mock_query, mock_apply, mock_write):
        result = ops.check_and_apply("https://x.com", "pabx", "k")
        self.assertIsNone(result["action"])
        mock_apply.assert_not_called()
        mock_write.assert_called_once_with(200)

    @patch("autobloqueador_ops._write_last_response")
    @patch("autobloqueador_ops._apply_action", return_value=None)
    @patch("autobloqueador_ops._query_status", return_value=200)
    @patch("autobloqueador_ops._read_last_status", return_value=402)
    def test_restarts_when_recovering_from_a_non_200(self, mock_read, mock_query, mock_apply, mock_write):
        result = ops.check_and_apply("https://x.com", "pabx", "k")
        self.assertEqual(result["action"], "restart")
        mock_apply.assert_called_once_with("pabx", "restart")

    @patch("autobloqueador_ops._write_last_response")
    @patch("autobloqueador_ops._apply_action", return_value=None)
    @patch("autobloqueador_ops._query_status", return_value=402)
    @patch("autobloqueador_ops._read_last_status", return_value=200)
    def test_stops_on_402(self, mock_read, mock_query, mock_apply, mock_write):
        result = ops.check_and_apply("https://x.com", "pabx", "k")
        self.assertEqual(result["action"], "stop")
        mock_apply.assert_called_once_with("pabx", "stop")

    @patch("autobloqueador_ops._write_last_response")
    @patch("autobloqueador_ops._apply_action")
    @patch("autobloqueador_ops._query_status", return_value=500)
    @patch("autobloqueador_ops._read_last_status", return_value=200)
    def test_ignores_any_other_status_and_keeps_last_status(self, mock_read, mock_query, mock_apply, mock_write):
        result = ops.check_and_apply("https://x.com", "pabx", "k")
        self.assertIsNone(result["action"])
        mock_apply.assert_not_called()
        mock_write.assert_not_called()

    @patch("autobloqueador_ops._write_last_response")
    @patch("autobloqueador_ops._apply_action")
    @patch("autobloqueador_ops._query_status", return_value=402)
    @patch("autobloqueador_ops._read_last_status", return_value=200)
    def test_dry_run_reports_the_action_without_applying_it(self, mock_read, mock_query, mock_apply, mock_write):
        result = ops.check_and_apply("https://x.com", "pabx", "k", dry_run=True)
        self.assertEqual(result["action"], "stop")
        mock_apply.assert_not_called()
        mock_write.assert_called_once_with(402)

    @patch("autobloqueador_ops._write_last_response")
    @patch("autobloqueador_ops._apply_action", return_value="pm2 não encontrado em nenhum caminho conhecido -- ação não executada.")
    @patch("autobloqueador_ops._query_status", return_value=402)
    @patch("autobloqueador_ops._read_last_status", return_value=200)
    def test_surfaces_the_warning_from_apply_action(self, mock_read, mock_query, mock_apply, mock_write):
        result = ops.check_and_apply("https://x.com", "opa", "k")
        self.assertIn("pm2", result["warning"])


class ReadWriteLastResponseTest(unittest.TestCase):
    @patch("autobloqueador_ops.state.load", return_value=None)
    def test_read_defaults_to_zero_when_nothing_saved(self, mock_load):
        self.assertEqual(ops._read_last_status(), 0)

    @patch("autobloqueador_ops.state.load", return_value={"http_code": 402, "timestamp": "x"})
    def test_read_returns_the_saved_code(self, mock_load):
        self.assertEqual(ops._read_last_status(), 402)

    @patch("autobloqueador_ops.state.save")
    def test_write_saves_the_code_and_a_timestamp(self, mock_save):
        ops._write_last_response(402)
        args = mock_save.call_args.args
        self.assertEqual(args[0], ops.LAST_RESPONSE_FILE)
        self.assertEqual(args[1]["http_code"], 402)
        self.assertIn("timestamp", args[1])


class LockTest(unittest.TestCase):
    def test_blocks_a_concurrent_lock_until_released(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lock")
            events = []

            with ops.lock(path):
                events.append("first-acquired")
                # timeout curto de propósito -- não pode esperar 30s de
                # verdade num teste.
                with self.assertRaises(ops.AutobloqueadorError):
                    with ops.lock(path, timeout=0.2, poll_interval=0.05):
                        events.append("should-not-happen")

            with ops.lock(path, timeout=1):
                events.append("second-acquired-after-release")

            self.assertEqual(events, ["first-acquired", "second-acquired-after-release"])


class LastResponseTest(unittest.TestCase):
    @patch("autobloqueador_ops.state.load", return_value={"http_code": 402, "timestamp": "x"})
    def test_delegates_to_state(self, mock_load):
        self.assertEqual(ops.last_response(), {"http_code": 402, "timestamp": "x"})
        mock_load.assert_called_once_with(ops.LAST_RESPONSE_FILE)


class LogTest(unittest.TestCase):
    def test_appends_a_timestamped_line(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "log")
            with patch("autobloqueador_ops.LOG_FILE", path):
                ops.log("consultando status")
                ops.log("http 200")
            content = Path(path).read_text()
        self.assertIn("consultando status", content)
        self.assertIn("http 200", content)
        self.assertEqual(len(content.splitlines()), 2)

    def test_log_file_has_owner_only_permissions(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log")
            with patch("autobloqueador_ops.LOG_FILE", path):
                ops.log("x")
            self.assertEqual(oct(Path(path).stat().st_mode)[-3:], "600")

    def test_rotates_and_compresses_when_over_the_size_limit(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log")
            Path(path).write_text("x" * 100)
            with patch("autobloqueador_ops.LOG_FILE", path), patch("autobloqueador_ops.LOG_MAX_BYTES", 50):
                ops.log("nova entrada")
            rotated = list(Path(tmp).glob("log.*.gz"))
            self.assertEqual(len(rotated), 1)
            self.assertIn("nova entrada", Path(path).read_text())

    def test_does_not_rotate_under_the_size_limit(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log")
            Path(path).write_text("x" * 10)
            with patch("autobloqueador_ops.LOG_FILE", path), patch("autobloqueador_ops.LOG_MAX_BYTES", 1000):
                ops.log("nova entrada")
            self.assertEqual(list(Path(tmp).glob("log.*.gz")), [])


class TailLogTest(unittest.TestCase):
    def test_empty_string_when_log_file_is_absent(self):
        with patch("autobloqueador_ops.LOG_FILE", "/does/not/exist"):
            self.assertEqual(ops.tail_log(), "")

    def test_returns_only_the_last_n_lines(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "log")
            Path(path).write_text("\n".join(f"linha{i}" for i in range(10)) + "\n")
            with patch("autobloqueador_ops.LOG_FILE", path):
                result = ops.tail_log(lines=3)
        self.assertEqual(result.splitlines(), ["linha7", "linha8", "linha9"])


class TimerStatusTest(unittest.TestCase):
    @patch("autobloqueador_ops.subprocess.run")
    def test_returns_stdout_on_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="NEXT  LEFT\n10s  left\n")
        self.assertEqual(ops.timer_status(), "NEXT  LEFT\n10s  left")

    @patch("autobloqueador_ops.subprocess.run")
    def test_none_when_timer_is_not_installed(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stdout="")
        self.assertIsNone(ops.timer_status())


class StartStopTimerTest(unittest.TestCase):
    @patch("autobloqueador_ops._run")
    def test_start_enables_and_starts_the_timer(self, mock_run):
        ops.start_timer()
        mock_run.assert_called_once_with(["systemctl", "enable", "--now", "pvx-autobloqueador.timer"], unittest.mock.ANY)

    @patch("autobloqueador_ops._run")
    def test_stop_stops_and_disables_the_timer(self, mock_run):
        ops.stop_timer()
        calls = [c.args[0] for c in mock_run.call_args_list]
        self.assertIn(["systemctl", "stop", "pvx-autobloqueador.timer"], calls)
        self.assertIn(["systemctl", "disable", "pvx-autobloqueador.timer"], calls)


class RemoveTimerTest(unittest.TestCase):
    @patch("autobloqueador_ops.subprocess.run")
    def test_removes_unit_files_even_when_systemctl_calls_fail(self, mock_run):
        # best-effort, igual o `|| true` do original -- remove() nunca pode
        # travar por causa de uma unit que já não existe mais.
        mock_run.return_value = Mock(returncode=1)
        with TemporaryDirectory() as tmp:
            service_path = os.path.join(tmp, "s.service")
            timer_path = os.path.join(tmp, "t.timer")
            Path(service_path).write_text("x")
            Path(timer_path).write_text("x")
            with patch("autobloqueador_ops.SERVICE_UNIT_PATH", service_path), \
                 patch("autobloqueador_ops.TIMER_UNIT_PATH", timer_path):
                ops.remove_timer()  # não deve levantar
            self.assertFalse(os.path.exists(service_path))
            self.assertFalse(os.path.exists(timer_path))

    def test_is_a_no_op_when_units_never_existed(self):
        with patch("autobloqueador_ops.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1)
            with patch("autobloqueador_ops.SERVICE_UNIT_PATH", "/does/not/exist.service"), \
                 patch("autobloqueador_ops.TIMER_UNIT_PATH", "/does/not/exist.timer"):
                ops.remove_timer()  # não deve levantar


class RemoveConfigTest(unittest.TestCase):
    @patch("autobloqueador_ops.state.remove")
    def test_removes_state_and_last_response(self, mock_remove):
        ops.remove_config()
        calls = [c.args[0] for c in mock_remove.call_args_list]
        self.assertIn(ops.STATE_FILE, calls)
        self.assertIn(ops.LAST_RESPONSE_FILE, calls)


class InstallTimerTest(unittest.TestCase):
    @patch("autobloqueador_ops._run")
    def test_writes_service_and_timer_units_pointing_at_the_pvx_binary(self, mock_run):
        with TemporaryDirectory() as tmp:
            service_path = os.path.join(tmp, "s.service")
            timer_path = os.path.join(tmp, "t.timer")
            with patch("autobloqueador_ops.SERVICE_UNIT_PATH", service_path), patch("autobloqueador_ops.TIMER_UNIT_PATH", timer_path):
                ops.install_timer(pvx_bin="/usr/local/bin/pvx")
            service_content = Path(service_path).read_text()
            timer_content = Path(timer_path).read_text()
        self.assertIn("ExecStart=/usr/local/bin/pvx autobloqueador run", service_content)
        self.assertIn("OnCalendar=", timer_content)
        mock_run.assert_any_call(["systemctl", "daemon-reload"], unittest.mock.ANY)
        mock_run.assert_any_call(["systemctl", "enable", "--now", "pvx-autobloqueador.timer"], unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
