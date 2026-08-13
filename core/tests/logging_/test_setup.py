import os
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

from pvx.logging_ import setup


class GetModuleLoggerTest(unittest.TestCase):
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

    def test_repeated_calls_do_not_duplicate_handlers(self):
        # nome exclusivo desta chamada: logging.getLogger cacheia por nome
        # no processo, então reusar nome de outro teste vazaria handlers.
        setup.get_module_logger("repeat-test")
        logger = setup.get_module_logger("repeat-test")
        file_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
        self.assertEqual(len(file_handlers), 1)

    def test_writes_to_module_specific_log_file_under_logs_dir(self):
        logger = setup.get_module_logger("write-test")
        logger.info("hello from write-test")
        for handler in logger.handlers:
            handler.flush()
        log_path = Path(self._tmp.name) / "logs" / "write-test.log"
        self.assertTrue(log_path.exists())
        self.assertIn("hello from write-test", log_path.read_text())


if __name__ == "__main__":
    unittest.main()
