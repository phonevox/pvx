import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import config


class ReadParamsTest(unittest.TestCase):
    def test_ignores_comments_and_blank_lines(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "zabbix_agentd.conf"
            path.write_text("# comment\nServer=127.0.0.1\n\n# Hostname=example\n")
            self.assertEqual(config.read_params(str(path)), {"Server": "127.0.0.1"})

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(config.read_params("/does/not/exist"), {})


class SetParamsTest(unittest.TestCase):
    def test_raises_when_file_missing(self):
        with self.assertRaises(FileNotFoundError):
            config.set_params("/does/not/exist", {"Server": "x"})

    def test_replaces_existing_active_param_in_place(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "conf"
            path.write_text("# Server=\nServer=old\nHostname=host1\n")
            config.set_params(str(path), {"Server": "new"})
            self.assertEqual(config.read_params(str(path)), {"Server": "new", "Hostname": "host1"})

    def test_appends_new_param_when_absent(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "conf"
            path.write_text("Hostname=host1\n")
            config.set_params(str(path), {"Server": "1.2.3.4"})
            self.assertEqual(config.read_params(str(path)), {"Hostname": "host1", "Server": "1.2.3.4"})

    def test_is_idempotent(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "conf"
            path.write_text("Server=1.2.3.4\n")
            config.set_params(str(path), {"Server": "1.2.3.4"})
            config.set_params(str(path), {"Server": "1.2.3.4"})
            self.assertEqual(path.read_text().count("Server="), 1)

    def test_raises_when_param_is_duplicated_in_file(self):
        # mesmo espírito do _param_has_duplicate() do script bash antigo, mas sem o bug
        # (lá a checagem existia mas nunca conseguia realmente barrar nada).
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "conf"
            path.write_text("Server=1.1.1.1\nServer=2.2.2.2\n")
            with self.assertRaises(ValueError):
                config.set_params(str(path), {"Server": "3.3.3.3"})

    def test_preserves_comments_and_unrelated_lines(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "conf"
            path.write_text("# top comment\nLogFile=/var/log/zabbix/zabbix_agentd.log\n")
            config.set_params(str(path), {"Server": "1.2.3.4"})
            content = path.read_text()
            self.assertIn("# top comment", content)
            self.assertIn("LogFile=/var/log/zabbix/zabbix_agentd.log", content)


class EnsureIncludeTest(unittest.TestCase):
    def test_appends_include_line_when_absent(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "conf"
            path.write_text("Server=1.2.3.4\n")
            confd_dir = str(Path(tmp) / "zabbix_agent2.d")
            config.ensure_include(str(path), confd_dir)
            self.assertIn(f"Include={confd_dir}/*.conf", path.read_text())

    def test_does_not_duplicate_when_already_present(self):
        with TemporaryDirectory() as tmp:
            confd_dir = str(Path(tmp) / "zabbix_agent2.d")
            path = Path(tmp) / "conf"
            path.write_text(f"Include={confd_dir}/*.conf\n")
            config.ensure_include(str(path), confd_dir)
            self.assertEqual(path.read_text().count("Include="), 1)

    def test_raises_when_file_missing(self):
        with self.assertRaises(FileNotFoundError):
            config.ensure_include("/does/not/exist", "/etc/zabbix/zabbix_agent2.conf.d")

    def test_creates_the_confd_dir_when_it_does_not_exist(self):
        # achado ao vivo: zabbix_agent2 recusa subir se o dir do Include= não existir
        # ("cannot include ...: no such file or directory") -- não basta escrever a
        # diretiva, o diretório precisa existir de verdade.
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "conf"
            path.write_text("Server=1.2.3.4\n")
            confd_dir = Path(tmp) / "confd.d"
            config.ensure_include(str(path), str(confd_dir))
            self.assertTrue(confd_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
