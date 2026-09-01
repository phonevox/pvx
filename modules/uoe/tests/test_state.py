import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import state


class StateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "uoe.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_none_when_file_absent(self):
        self.assertIsNone(state.load(str(self.path)))

    def test_save_then_load_roundtrips(self):
        data = {"username": "empresa", "token": "abc123", "script": "issabel"}
        state.save(str(self.path), data)
        self.assertEqual(state.load(str(self.path)), data)

    def test_saved_file_has_owner_only_permissions(self):
        # guarda um token (credencial de bearer) -- nunca mundo-legível.
        state.save(str(self.path), {"token": "abc123"})
        self.assertEqual(oct(self.path.stat().st_mode)[-3:], "600")

    def test_save_leaves_no_temp_file_behind(self):
        state.save(str(self.path), {"token": "abc123"})
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_returns_none_when_content_is_not_valid_json(self):
        self.path.write_text("isso nao eh json")
        self.assertIsNone(state.load(str(self.path)))

    def test_returns_none_when_token_is_missing(self):
        self.path.write_text('{"username": "empresa"}')
        self.assertIsNone(state.load(str(self.path)))

    def test_remove_deletes_the_file(self):
        state.save(str(self.path), {"token": "abc123"})
        state.remove(str(self.path))
        self.assertFalse(self.path.exists())

    def test_remove_is_a_no_op_when_file_never_existed(self):
        state.remove(str(self.path))


if __name__ == "__main__":
    unittest.main()
