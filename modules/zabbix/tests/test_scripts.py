import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import scripts


class AddTest(unittest.TestCase):
    def test_adds_new_entry(self):
        with TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "state.json")
            entries = scripts.add(state_path, "cpu.custom", "/opt/scripts/cpu.sh")
            self.assertEqual(entries["cpu.custom"], {"command": "/opt/scripts/cpu.sh", "needs_root": False})

    def test_needs_root_flag_is_stored(self):
        with TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "state.json")
            entries = scripts.add(state_path, "disk.check", "/opt/scripts/disk.sh", needs_root=True)
            self.assertTrue(entries["disk.check"]["needs_root"])

    def test_raises_when_key_already_exists(self):
        with TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "state.json")
            scripts.add(state_path, "cpu.custom", "/opt/scripts/cpu.sh")
            with self.assertRaises(KeyError):
                scripts.add(state_path, "cpu.custom", "/opt/scripts/other.sh")

    def test_persists_across_calls(self):
        with TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "state.json")
            scripts.add(state_path, "cpu.custom", "/opt/scripts/cpu.sh")
            self.assertIn("cpu.custom", scripts.list_all(state_path))


class RemoveTest(unittest.TestCase):
    def test_removes_existing_entry(self):
        with TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "state.json")
            scripts.add(state_path, "cpu.custom", "/opt/scripts/cpu.sh")
            scripts.remove(state_path, "cpu.custom")
            self.assertEqual(scripts.list_all(state_path), {})

    def test_raises_when_key_missing(self):
        with TemporaryDirectory() as tmp:
            state_path = str(Path(tmp) / "state.json")
            with self.assertRaises(KeyError):
                scripts.remove(state_path, "does-not-exist")


class ListAllTest(unittest.TestCase):
    def test_empty_when_state_file_missing(self):
        self.assertEqual(scripts.list_all("/does/not/exist"), {})


class RenderUserparameterConfTest(unittest.TestCase):
    def test_renders_one_line_per_entry_sorted_by_key(self):
        entries = {
            "b.check": {"command": "/opt/b.sh", "needs_root": False},
            "a.check": {"command": "/opt/a.sh", "needs_root": False},
        }
        rendered = scripts.render_userparameter_conf(entries)
        self.assertEqual(
            rendered, "UserParameter=a.check,/opt/a.sh\nUserParameter=b.check,/opt/b.sh\n"
        )

    def test_needs_root_prefixes_with_sudo_n(self):
        # o comando roda via `sudo -n` -- sem senha, sem prompt travando o agent. A regra
        # que autoriza isso sem senha é escopada por comando exato (ver sudoers.py), nunca
        # acesso amplo.
        entries = {"disk.check": {"command": "/opt/disk.sh", "needs_root": True}}
        rendered = scripts.render_userparameter_conf(entries)
        self.assertEqual(rendered, "UserParameter=disk.check,sudo -n /opt/disk.sh\n")

    def test_empty_when_no_entries(self):
        self.assertEqual(scripts.render_userparameter_conf({}), "")


class RootRequiringCommandsTest(unittest.TestCase):
    def test_returns_only_needs_root_commands(self):
        entries = {
            "a": {"command": "/opt/a.sh", "needs_root": True},
            "b": {"command": "/opt/b.sh", "needs_root": False},
        }
        self.assertEqual(scripts.root_requiring_commands(entries), ["/opt/a.sh"])


if __name__ == "__main__":
    unittest.main()
