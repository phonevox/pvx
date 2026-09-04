import json
import unittest

from pvx import config as pvx_config

import autobackup_info


class StatusTest(unittest.TestCase):
    def _write_state(self, data):
        path = pvx_config.modules_dir() / "autobackup" / "state"
        path.mkdir(parents=True, exist_ok=True)
        (path / "state.json").write_text(json.dumps(data))

    def test_returns_the_saved_fields_when_configured(self):
        self._write_state({
            "username": "empresa", "script": "issabel", "cron_minute": "25", "cron_hour": "2",
            "token": "não deveria vazar/importar aqui",
        })
        result = autobackup_info.status()
        self.assertEqual(result, {
            "username": "empresa", "script": "issabel", "cron_minute": "25", "cron_hour": "2",
        })

    def test_none_when_nothing_is_configured(self):
        self.assertIsNone(autobackup_info.status())

    def test_none_when_the_state_file_is_corrupted(self):
        path = pvx_config.modules_dir() / "autobackup" / "state"
        path.mkdir(parents=True, exist_ok=True)
        (path / "state.json").write_text("not json")
        self.assertIsNone(autobackup_info.status())


if __name__ == "__main__":
    unittest.main()
