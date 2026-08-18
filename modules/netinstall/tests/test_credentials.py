import stat
import tempfile
import unittest
from pathlib import Path

import credentials


class SaveCredentialsTest(unittest.TestCase):
    def test_writes_file_with_expected_fields_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = credentials.save_credentials(
                tmp, "issabel5", "sqlpw123", "webpw456", extra={"ssh_port": "21122"}
            )
            content = Path(path).read_text()

            self.assertIn("produto=issabel5", content)
            self.assertIn("mysql_root_password=sqlpw123", content)
            self.assertIn("web_admin_password=webpw456", content)
            self.assertIn("ssh_port=21122", content)
            self.assertRegex(content, r"data=\d{8}T\d{6}")

            mode = stat.S_IMODE(Path(path).stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_creates_state_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "not-yet-created"
            path = credentials.save_credentials(nested, "issabel5", "a", "b")
            self.assertTrue(Path(path).exists())

    def test_extra_is_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = credentials.save_credentials(tmp, "issabel5", "a", "b")
            self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
