import unittest
import urllib.error
from unittest.mock import patch

from pvx.modules import listing


class FakeInstalled:
    def __init__(self, version):
        self.version = version


class ListModulesTest(unittest.TestCase):
    @patch(
        "pvx.modules.listing.fetch_index",
        return_value={
            "modules": [
                {"name": "dummy", "latest": "1.1.0"},
                {"name": "ssh-hardening", "latest": "1.0.0"},
            ]
        },
    )
    def test_merges_installed_and_registry(self, mock_fetch):
        installed = {"dummy": FakeInstalled("1.0.0"), "local-only": FakeInstalled("0.1.0")}

        rows = listing.list_modules(installed, "https://example.com/index.json")
        by_name = {r["name"]: r for r in rows}

        self.assertEqual(by_name["dummy"]["installed_version"], "1.0.0")
        self.assertEqual(by_name["dummy"]["latest_version"], "1.1.0")
        self.assertEqual(by_name["dummy"]["status"], "atualização disponível")

        self.assertEqual(by_name["ssh-hardening"]["installed_version"], "-")
        self.assertEqual(by_name["ssh-hardening"]["latest_version"], "1.0.0")
        self.assertEqual(by_name["ssh-hardening"]["status"], "disponível")

        self.assertEqual(by_name["local-only"]["latest_version"], "-")
        self.assertEqual(by_name["local-only"]["status"], "local")

    @patch(
        "pvx.modules.listing.fetch_index",
        return_value={"modules": [{"name": "dummy", "latest": "1.0.0"}]},
    )
    def test_up_to_date_status(self, mock_fetch):
        rows = listing.list_modules({"dummy": FakeInstalled("1.0.0")}, "https://example.com/index.json")
        self.assertEqual(rows[0]["status"], "atualizado")

    @patch(
        "pvx.modules.listing.fetch_index",
        side_effect=urllib.error.URLError("nome não resolvido"),
    )
    def test_registry_unreachable_raises_clean_error(self, mock_fetch):
        with self.assertRaises(RuntimeError):
            listing.list_modules({}, "https://example.com/index.json")


if __name__ == "__main__":
    unittest.main()
