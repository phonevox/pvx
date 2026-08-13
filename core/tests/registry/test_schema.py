import unittest

from pvx.registry.schema import validate_manifest


class ValidateManifestTest(unittest.TestCase):
    def test_valid_manifest_passes(self):
        manifest = {"name": "dummy", "version": "0.1.0", "entrypoint": "module:cli"}
        self.assertTrue(validate_manifest(manifest))

    def test_missing_required_field_raises(self):
        with self.assertRaises(ValueError):
            validate_manifest({"name": "dummy"})


if __name__ == "__main__":
    unittest.main()
