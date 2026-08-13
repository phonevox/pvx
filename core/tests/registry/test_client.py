import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pvx.registry.client import fetch_index


class FetchIndexTest(unittest.TestCase):
    def test_fetches_and_parses_index_json(self):
        with TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "index.json"
            index_path.write_text(json.dumps({"registry_version": 1, "modules": []}))
            index = fetch_index(f"file://{index_path}")

        self.assertEqual(index["registry_version"], 1)
        self.assertEqual(index["modules"], [])


if __name__ == "__main__":
    unittest.main()
