import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import staged_config


class StagedConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "qint.conf"

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_none_when_file_absent(self):
        self.assertIsNone(staged_config.load(str(self.path)))

    def test_save_then_load_roundtrips(self):
        config = {"type": "ixcsoft", "url": "https://erp.example.com"}
        staged_config.save(str(self.path), config)
        self.assertEqual(staged_config.load(str(self.path)), config)

    def test_saved_file_has_owner_only_permissions(self):
        staged_config.save(str(self.path), {"type": "sgp"})
        self.assertEqual(oct(self.path.stat().st_mode)[-3:], "600")

    def test_save_leaves_no_temp_file_behind(self):
        staged_config.save(str(self.path), {"type": "sgp"})
        leftovers = list(self.path.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_returns_none_when_content_is_not_valid_json(self):
        self.path.write_text("isso nao eh json")
        self.assertIsNone(staged_config.load(str(self.path)))

    def test_returns_none_when_type_is_missing_or_invalid(self):
        self.path.write_text('{"url": "https://erp.example.com"}')
        self.assertIsNone(staged_config.load(str(self.path)))

        self.path.write_text('{"type": "algumacoisa"}')
        self.assertIsNone(staged_config.load(str(self.path)))


if __name__ == "__main__":
    unittest.main()
