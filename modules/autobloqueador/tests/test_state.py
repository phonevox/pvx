import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import state


class StateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "sub" / "autobloqueador.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_none_when_file_absent(self):
        self.assertIsNone(state.load(str(self.path)))

    def test_save_then_load_roundtrips(self):
        data = {"url_base": "https://x.com", "type": "pabx", "code": "c1", "crypted_key": "abc"}
        state.save(str(self.path), data)
        self.assertEqual(state.load(str(self.path)), data)

    def test_save_creates_parent_dir_with_owner_only_permissions(self):
        state.save(str(self.path), {"crypted_key": "abc"})
        self.assertEqual(oct(self.path.parent.stat().st_mode)[-3:], "700")

    def test_saved_file_has_owner_only_permissions(self):
        # guarda a crypted_key -- nunca mundo-legível.
        state.save(str(self.path), {"crypted_key": "abc"})
        self.assertEqual(oct(self.path.stat().st_mode)[-3:], "600")

    def test_save_leaves_no_temp_file_behind(self):
        state.save(str(self.path), {"crypted_key": "abc"})
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_returns_none_when_content_is_not_valid_json(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("isso nao eh json")
        self.assertIsNone(state.load(str(self.path)))

    def test_remove_deletes_the_file(self):
        state.save(str(self.path), {"crypted_key": "abc"})
        state.remove(str(self.path))
        self.assertFalse(self.path.exists())

    def test_remove_is_a_no_op_when_file_never_existed(self):
        state.remove(str(self.path))


if __name__ == "__main__":
    unittest.main()
